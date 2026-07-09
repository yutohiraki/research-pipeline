#!/usr/bin/env python3
"""
notion_to_paperpile.py
NotionデータベースのAI要約をPaperpile用BibTeXとしてエクスポートする

Paperpileは annote フィールドをノートとして取り込みます。
DOI/タイトルで既存文献と照合するため、インポート時に重複は作成されず
ノートが追加・更新されます。

使い方:
  python notion_to_paperpile.py                          # notion_export.bib に出力
  python notion_to_paperpile.py --output enriched.bib   # 出力先を指定
  python notion_to_paperpile.py --limit 50               # 最大50件
  python notion_to_paperpile.py --only-enriched          # AI要約済みのみ

Paperpile へのインポート手順:
  1. 生成された .bib ファイルを Paperpile の「Import」→「BibTeX」から読み込む
  2. DOI/タイトルで自動照合され、既存論文のノートが更新される
"""

import argparse
import re
import yaml
from notion_writer import _notion_request


# ──────────────────────────────────────────────
# Notion ページ取得
# ──────────────────────────────────────────────

def fetch_pages(api_key: str, db_id: str, limit: int, only_enriched: bool) -> list:
    pages = []
    cursor = None
    payload_base = {"page_size": 100}
    if only_enriched:
        payload_base["filter"] = {
            "property": "手法・解析ツール",  # methods が空でないもの
            "rich_text": {"is_not_empty": True},
        }

    while len(pages) < limit:
        payload = {**payload_base, "page_size": min(100, limit - len(pages))}
        if cursor:
            payload["start_cursor"] = cursor
        result = _notion_request(api_key, "POST", f"databases/{db_id}/query", payload)
        pages.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")

    return pages[:limit]


# ──────────────────────────────────────────────
# プロパティ抽出ヘルパー
# ──────────────────────────────────────────────

def _title(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in (prop or {}).get("title", []))

def _text(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in (prop or {}).get("rich_text", []))

def _url(prop: dict) -> str:
    return (prop or {}).get("url", "") or ""

def _date(prop: dict) -> str:
    d = ((prop or {}).get("date") or {})
    return d.get("start", "") or ""

def _tags(prop: dict) -> list:
    return [t.get("name", "") for t in (prop or {}).get("multi_select", [])]


# ──────────────────────────────────────────────
# BibTeX エントリ生成
# ──────────────────────────────────────────────

def _escape_bib(text: str) -> str:
    """BibTeX値内の特殊文字をエスケープ"""
    return text.replace("\\", "").replace("{", "").replace("}", "")


def page_to_bib(page: dict, props_map: dict) -> str | None:
    props = page.get("properties", {})

    title     = _title(props.get(props_map["title"], {}))
    authors   = _text(props.get(props_map["authors"], {}))
    doi       = _text(props.get(props_map["doi"], {}))
    url_val   = _url(props.get(props_map["url"], {}))
    date_val  = _date(props.get(props_map.get("published_date", ""), {}))
    source    = _text(props.get(props_map["source"], {}))
    summary   = _text(props.get(props_map["summary"], {}))
    methods   = _text(props.get(props_map["methods"], {}))
    results   = _text(props.get(props_map["results"], {}))
    relevance = _text(props.get(props_map["relevance"], {}))
    novelty   = _text(props.get(props_map["novelty"], {}))
    tags      = _tags(props.get(props_map["tags"], {}))

    if not title:
        return None

    # annote: Paperpile がノートとして取り込むフィールド
    annote_parts = []
    if summary:
        annote_parts.append(f"[要約] {summary}")
    if methods:
        annote_parts.append(f"[手法] {methods}")
    if results:
        annote_parts.append(f"[結果] {results}")
    if novelty:
        annote_parts.append(f"[新規性] {novelty}")
    if relevance:
        annote_parts.append(f"[示唆] {relevance}")
    annote = " || ".join(annote_parts)

    # BibTeX キー生成
    year = date_val[:4] if date_val else "0000"
    first_author_last = ""
    if authors:
        # "First Last" 形式の最初の著者の姓
        first = authors.split(",")[0].strip()
        first_author_last = re.sub(r"[^a-zA-Z]", "", first.split()[-1]) if first else ""
    title_word = re.sub(r"[^a-zA-Z]", "", title.split()[0])[:12] if title else "noTitle"
    key = f"{first_author_last or 'Unknown'}{year}{title_word}"

    lines = [f"@article{{{key},"]
    lines.append(f'  title = {{{_escape_bib(title)}}},')
    if authors:
        lines.append(f'  author = {{{_escape_bib(authors)}}},')
    if year and year != "0000":
        lines.append(f'  year = {{{year}}},')
    if doi:
        lines.append(f'  doi = {{{_escape_bib(doi)}}},')
    if url_val:
        lines.append(f'  url = {{{_escape_bib(url_val)}}},')
    if source:
        lines.append(f'  journal = {{{_escape_bib(source)}}},')
    if tags:
        lines.append(f'  keywords = {{{", ".join(tags)}}},')
    if annote:
        lines.append(f'  annote = {{{_escape_bib(annote)}}},')
    lines.append("}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────

def run(config_path: str, output: str, limit: int, only_enriched: bool):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    notion_cfg = cfg["notion"]
    api_key    = notion_cfg["api_key"]
    db_id      = notion_cfg["database_id"]
    props_map  = notion_cfg["properties"]

    label = "AI要約済み論文" if only_enriched else "全論文"
    print(f"Notionから{label}を取得中（最大{limit}件）...")
    pages = fetch_pages(api_key, db_id, limit, only_enriched)
    print(f"{len(pages)} 件を取得\n")

    bib_entries = []
    skipped = 0
    for page in pages:
        try:
            bib = page_to_bib(page, props_map)
            if bib:
                bib_entries.append(bib)
            else:
                skipped += 1
        except Exception as e:
            print(f"  [WARN] ページ変換エラー: {e}")
            skipped += 1

    with open(output, "w", encoding="utf-8") as f:
        f.write("\n\n".join(bib_entries))

    print(f"✅ {len(bib_entries)}件を '{output}' にエクスポートしました（スキップ: {skipped}件）")
    print()
    print("【Paperpileへのインポート手順】")
    print(f"  1. Paperpile を開く → Import → BibTeX → '{output}' を選択")
    print("  2. DOI/タイトルで自動照合され、既存論文のノートが更新されます")
    print("  3. annote フィールド（要約・手法・結果・示唆）がノートとして追加されます")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notion → Paperpile BibTeXエクスポート")
    parser.add_argument("--config",         default="config.yaml")
    parser.add_argument("--output",         default="notion_export.bib", help="出力BibTeXファイル名")
    parser.add_argument("--limit",          type=int, default=500, help="最大取得件数（デフォルト500）")
    parser.add_argument("--only-enriched",  action="store_true", help="AI要約済み（手法フィールドあり）のみ出力")
    args = parser.parse_args()
    run(args.config, args.output, args.limit, args.only_enriched)
