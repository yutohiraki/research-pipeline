#!/usr/bin/env python3
"""
notion_enricher.py
Notionに登録済みの「未読」論文にGroqでAI要約・構造化情報を追加/更新する

Unpaywall / Semantic Scholar でコンテンツ取得してからGroqに渡すため、
アブストしか入っていなかった論文もPDF全文や正確なアブストで再処理できる。

使い方:
  python notion_enricher.py               # 未読論文を全件エンリッチ
  python notion_enricher.py --dry-run     # 確認のみ（Notionへの書き込みなし）
  python notion_enricher.py --limit 20    # 最大20件処理
  python notion_enricher.py --config path/to/config.yaml
"""

import argparse
import time
import yaml
from notion_writer import _notion_request
from gemini_summarizer import enrich_paper
from paper_fetcher import fetch_paper_content


# ──────────────────────────────────────────────
# Notion ページ取得
# ──────────────────────────────────────────────

def fetch_unread_pages(api_key: str, db_id: str, status_prop: str, limit: int) -> list:
    """読了ステータスが「未読」のページを最大 limit 件取得"""
    pages = []
    cursor = None
    while len(pages) < limit:
        payload = {
            "page_size": min(100, limit - len(pages)),
            "filter": {
                "property": status_prop,
                "status": {"equals": "未読"},
            },
        }
        if cursor:
            payload["start_cursor"] = cursor
        result = _notion_request(api_key, "POST", f"databases/{db_id}/query", payload)
        pages.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return pages[:limit]


# ──────────────────────────────────────────────
# Notion ページ → paper dict
# ──────────────────────────────────────────────

def _get_title(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))

def _get_text(prop: dict) -> str:
    return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))

def _get_url(prop: dict) -> str:
    return prop.get("url", "") or ""


def page_to_paper(page: dict, props_map: dict) -> dict:
    """Notionページから enrich_paper() に渡せる paper dict を復元"""
    props = page.get("properties", {})
    title   = _get_title(props.get(props_map["title"], {}))
    summary = _get_text(props.get(props_map["summary"], {}))
    authors = _get_text(props.get(props_map["authors"], {}))
    url     = _get_url(props.get(props_map["url"], {}))
    doi     = _get_text(props.get(props_map["doi"], {}))
    source  = _get_text(props.get(props_map["source"], {}))

    return {
        "title":    title,
        "authors":  authors,
        "url":      url,
        "doi":      doi,
        "source":   source,
        "summary":  summary,
        "raw_body": summary,
    }


# ──────────────────────────────────────────────
# Notion ページ更新（PATCH）
# ──────────────────────────────────────────────

def update_page(api_key: str, page_id: str, paper: dict, props_map: dict):
    """エンリッチ済み paper dict で Notion ページを更新"""
    def _text(val):
        return {"rich_text": [{"text": {"content": str(val)[:2000]}}]} if val else {"rich_text": []}

    def _url_prop(val):
        return {"url": val} if val else {"url": None}

    def _multi_select(val):
        tags = val if isinstance(val, list) else ([val] if val else [])
        return {"multi_select": [{"name": t} for t in tags if t]}

    updates = {
        props_map.get("summary"):           _text(paper.get("summary", "")),
        props_map.get("methods"):           _text(paper.get("methods", "")),
        props_map.get("sampling"):          _text(paper.get("sampling", "")),
        props_map.get("results"):           _text(paper.get("main_results", "")),
        props_map.get("novelty"):           _text(paper.get("novelty", "")),
        props_map.get("limitations"):       _text(paper.get("limitations", "")),
        props_map.get("future_work"):       _text(paper.get("future_work", "")),
        props_map.get("data_availability"): _text(paper.get("data_availability", "")),
        props_map.get("relevance"):         _text(paper.get("relevance", "")),
        props_map.get("tags"):              _multi_select(paper.get("tags", [])),
        props_map.get("authors"):           _text(paper.get("authors_clean") or paper.get("authors", "")),
        props_map.get("doi"):               _text(paper.get("doi", "")),
        props_map.get("pdf_url"):           _url_prop(paper.get("pdf_url", "")),
    }

    properties = {k: v for k, v in updates.items() if k}
    _notion_request(api_key, "PATCH", f"pages/{page_id}", {"properties": properties})


# ──────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────

def run(config_path: str, dry_run: bool, limit: int):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    notion_cfg       = cfg["notion"]
    groq_cfg         = cfg["groq"]
    research_context = cfg.get("user", {}).get("research_context", "")
    themes           = cfg.get("sheets", {}).get("themes", ["その他"])
    unpaywall_email  = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key       = cfg.get("unpaywall", {}).get("semantic_scholar_api_key", "")

    api_key   = notion_cfg["api_key"]
    db_id     = notion_cfg["database_id"]
    props_map = notion_cfg["properties"]

    print(f"{'[DRY-RUN] ' if dry_run else ''}Notionから未読論文を取得中（最大{limit}件）...")
    pages = fetch_unread_pages(api_key, db_id, props_map["status"], limit)
    print(f"{len(pages)} 件を検出\n")

    ok = error = 0
    for i, page in enumerate(pages, 1):
        paper = page_to_paper(page, props_map)
        title_short = paper["title"][:60] or "(no title)"
        print(f"({i}/{len(pages)}) {title_short}")

        if not paper["title"]:
            print("  スキップ: タイトルなし")
            continue

        if dry_run:
            print(f"  [DRY-RUN] エンリッチ予定（現在のbody長: {len(paper['raw_body'])}文字）")
            ok += 1
            continue

        try:
            # Unpaywall / Semantic Scholar でコンテンツ補強
            if unpaywall_email:
                paper = fetch_paper_content(paper, unpaywall_email, ss_api_key=ss_api_key)

            enriched = enrich_paper(paper, groq_cfg, themes, research_context)
            update_page(api_key, page["id"], enriched, props_map)
            print(f"  → 更新完了")
            ok += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            error += 1

        time.sleep(8)  # Groq レート制限対策

    print(f"\n完了: 更新={ok}件 / エラー={error}件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notionの未読論文をAI再エンリッチ")
    parser.add_argument("--config",  default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Notionへの書き込みなしで確認")
    parser.add_argument("--limit",   type=int, default=50, help="最大処理件数（デフォルト50）")
    args = parser.parse_args()
    run(args.config, args.dry_run, args.limit)
