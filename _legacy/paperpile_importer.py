#!/usr/bin/env python3
"""
paperpile_importer.py
Paperpile からエクスポートした .bib ファイルを Notion データベースに一括インポートする

使い方:
  python paperpile_importer.py --bib path/to/references.bib
  python paperpile_importer.py --bib path/to/references.bib --dry-run
  python paperpile_importer.py --bib path/to/references.bib --enrich
  python paperpile_importer.py --bib path/to/references.bib --config path/to/config.yaml

オプション:
  --enrich    Notionへの登録後にGroqでAI要約・構造化情報を生成して補完する
"""

import argparse
import re
import time

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

import yaml
from notion_writer import add_paper_to_notion
from gemini_summarizer import enrich_paper, assign_tags


MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def load_bib(path: str) -> list:
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    with open(path, encoding="utf-8") as f:
        db = bibtexparser.load(f, parser=parser)
    return db.entries


def _clean_braces(text: str) -> str:
    """BibTeX の余分な {} を除去"""
    return re.sub(r"[{}]", "", text).strip()


def _format_authors(raw: str) -> str:
    """'Last, First and Last2, First2' → 'First Last, First2 Last2'"""
    if not raw:
        return ""
    parts = [a.strip() for a in raw.split(" and ")]
    names = []
    for p in parts:
        if "," in p:
            last, first = p.split(",", 1)
            names.append(f"{first.strip()} {last.strip()}")
        else:
            names.append(p)
    return ", ".join(names)


def _format_date(year: str, month: str) -> str:
    """year + month → 'YYYY-MM-DD' (Notion date形式)"""
    if not year:
        return ""
    y = year.strip()
    m = MONTH_MAP.get(month.strip().lower()[:3], "") if month else ""
    if m:
        return f"{y}-{m}-01"
    return f"{y}-01-01"


def _extract_tags(entry: dict, themes: list, synonyms: dict = None) -> list:
    """keywordsフィールドからthemesに合致するタグを抽出、なければ['その他']
    synonyms: {テーマ名: [部分一致キーワードリスト]} で同義語展開
    """
    raw = _clean_braces(entry.get("keywords", ""))
    if not raw:
        return ["その他"]

    kws_lower = raw.lower()

    matched = []
    for theme in themes:
        if theme == "その他":
            continue
        # 直接一致
        if theme.lower() in kws_lower:
            matched.append(theme)
            continue
        # 同義語マップで一致
        if synonyms:
            aliases = synonyms.get(theme, [])
            if any(alias.lower() in kws_lower for alias in aliases):
                matched.append(theme)

    return matched if matched else ["その他"]


def entry_to_paper(entry: dict, themes: list = None, synonyms: dict = None) -> dict:
    title = _clean_braces(entry.get("title", ""))
    authors = _format_authors(entry.get("author", ""))
    doi = _clean_braces(entry.get("doi", ""))
    url = entry.get("url", "")
    if doi and not url:
        url = f"https://doi.org/{doi}"
    abstract = _clean_braces(entry.get("abstract", ""))
    year = entry.get("year", "")
    month = entry.get("month", "")
    journal = _clean_braces(entry.get("journal", entry.get("booktitle", "")))
    tags = _extract_tags(entry, themes or [], synonyms=synonyms) if themes else ["その他"]

    return {
        "title": title,
        "authors": authors,
        "url": url,
        "doi": doi,
        "published_date": _format_date(year, month),
        "pdf_url": "",
        "source": journal,
        "summary": abstract[:2000] if abstract else "",
        "raw_body": abstract[:1500] if abstract else "",  # Groq用
        "tags": tags,
        "methods": "",
        "sampling": "",
        "main_results": "",
        "novelty": "",
        "limitations": "",
        "future_work": "",
        "data_availability": "",
        "relevance": "",
    }


def run(bib_path: str, config_path: str, dry_run: bool = False, do_enrich: bool = False, do_auto_tag: bool = False):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    notion_cfg       = cfg["notion"]
    groq_cfg         = cfg.get("groq", {})
    research_context = cfg.get("user", {}).get("research_context", "")
    themes           = cfg.get("sheets", {}).get("themes", ["その他"])
    synonyms         = cfg.get("tag_synonyms", {})

    print(f"{'[DRY-RUN] ' if dry_run else ''}BibTeX 読み込み中: {bib_path}")
    entries = load_bib(bib_path)
    print(f"{len(entries)} 件を検出")
    if do_enrich:
        print("--enrich 有効: 新規登録論文にGroqでAI要約を付与します（タグも含む）")
    elif do_auto_tag:
        print("--auto-tag 有効: Groqでタグのみ自動設定します")

    ok = skip = error = 0
    for i, entry in enumerate(entries, 1):
        paper = entry_to_paper(entry, themes, synonyms=synonyms)
        title_short = paper["title"][:60] or f"(no title) [{entry.get('ID', '')}]"

        if dry_run:
            print(f"  ({i}/{len(entries)}) [DRY-RUN] {title_short}")
            ok += 1
            continue

        try:
            if do_enrich and paper["title"]:
                # フル要約＋タグ生成
                try:
                    paper = enrich_paper(paper, groq_cfg, themes, research_context)
                    time.sleep(8)  # Groq レート制限対策
                except Exception as e:
                    print(f"  ({i}/{len(entries)}) [Groq ERROR] {title_short}: {e}")
            elif do_auto_tag and paper["title"]:
                # タグのみGroqで判定（軽量）
                try:
                    paper["tags"] = assign_tags(paper, groq_cfg, themes)
                    time.sleep(4)  # タグのみなので短めに待機
                except Exception as e:
                    print(f"  ({i}/{len(entries)}) [Groq TAG ERROR] {title_short}: {e}")

            added = add_paper_to_notion(paper, notion_cfg)
            if added:
                ok += 1
            else:
                skip += 1
        except Exception as e:
            print(f"  ({i}/{len(entries)}) [ERROR] {title_short}: {e}")
            error += 1

        # Notion API レート制限対策（3リクエスト/秒が上限）
        time.sleep(0.4)

    print(f"\n完了: 登録={ok}件 / スキップ(重複)={skip}件 / エラー={error}件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Paperpile BibTeX → Notion 一括インポート")
    parser.add_argument("--bib",     required=True, help=".bib ファイルのパス")
    parser.add_argument("--config",  default="config.yaml", help="設定ファイルのパス")
    parser.add_argument("--dry-run",  action="store_true", help="Notionへの書き込みを行わず確認のみ")
    parser.add_argument("--enrich",   action="store_true", help="新規登録論文にGroqでAI要約+タグを付与する")
    parser.add_argument("--auto-tag", action="store_true", help="Groqでタグのみ自動設定する（--enrichより高速）")
    args = parser.parse_args()
    run(args.bib, args.config, dry_run=args.dry_run, do_enrich=args.enrich, do_auto_tag=args.auto_tag)
