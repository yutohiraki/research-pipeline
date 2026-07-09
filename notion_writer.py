"""
notion_writer.py
Notion API で論文情報をデータベースに登録する
"""

import json
import urllib.error
import urllib.request
from datetime import date


def _notion_request(api_key: str, method: str, endpoint: str, payload: dict = None) -> dict:
    url = f"https://api.notion.com/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"HTTP {e.code} {e.reason}: {body}")


def is_duplicate(api_key: str, database_id: str, url: str) -> bool:
    """同じURLの論文がすでにDBに存在するか確認"""
    if not url:
        return False
    result = _notion_request(api_key, "POST", f"databases/{database_id}/query", {
        "filter": {"property": "URL", "url": {"equals": url}}
    })
    return len(result.get("results", [])) > 0


def add_paper_to_notion(paper: dict, notion_cfg: dict) -> bool:
    """論文1件をNotionデータベースに追加"""
    api_key = notion_cfg["api_key"]
    db_id = notion_cfg["database_id"]
    props_map = notion_cfg["properties"]
    default_status = notion_cfg.get("default_status", "未読")

    # 重複チェック
    if is_duplicate(api_key, db_id, paper.get("url", "")):
        print(f"  [Notion] スキップ（重複）: {paper.get('title', '')[:50]}")
        return False

    # プロパティ構築
    # ※ Notionのプロパティタイプはデータベースの設定に依存するため、
    #   以下は一般的なタイプを想定しています。実際のDBに合わせて調整してください。
    properties = {
        props_map["title"]: {
            "title": [{"text": {"content": paper.get("title", "")[:2000]}}]
        },
    }

    def _text(val):
        return {"rich_text": [{"text": {"content": str(val)[:2000]}}]} if val else {"rich_text": []}

    def _url_prop(val):
        return {"url": val} if val else {"url": None}

    def _date(val):
        return {"date": {"start": val}} if val else {"date": None}

    def _select(val):
        return {"select": {"name": val}} if val else {"select": None}

    def _status(val):
        return {"status": {"name": val}} if val else {"status": None}

    def _multi_select(val):
        if isinstance(val, list):
            tags = val
        elif val:
            tags = [val]
        else:
            tags = []
        return {"multi_select": [{"name": t} for t in tags if t]}

    # 各プロパティをマッピング
    field_map = {
        props_map.get("authors"): _text(paper.get("authors_clean") or paper.get("authors", "")),
        props_map.get("url"): _url_prop(paper.get("url", "")),
        props_map.get("doi"): _text(paper.get("doi", "")),
        props_map.get("published_date"): _date(paper.get("published_date", "")),
        props_map.get("status"): _status(default_status),
        props_map.get("tags"): _multi_select(paper.get("tags") or paper.get("tag", "その他")),
        props_map.get("summary"): _text(paper.get("summary", "")),
        props_map.get("methods"): _text(paper.get("methods", "")),
        props_map.get("sampling"): _text(paper.get("sampling", "")),
        props_map.get("results"): _text(paper.get("main_results", "")),
        props_map.get("novelty"): _text(paper.get("novelty", "")),
        props_map.get("limitations"): _text(paper.get("limitations", "")),
        props_map.get("future_work"): _text(paper.get("future_work", "")),
        props_map.get("data_availability"): _text(paper.get("data_availability", "")),
        props_map.get("relevance"): _text(paper.get("relevance", "")),
        props_map.get("pdf_url"): _url_prop(paper.get("pdf_url", "")),
        props_map.get("source"): _text(paper.get("source", "")),
        props_map.get("added_date"): _date(date.today().isoformat()),
    }

    for key, val in field_map.items():
        if key:
            properties[key] = val

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }

    _notion_request(api_key, "POST", "pages", payload)
    print(f"  [Notion] 登録完了: {paper.get('title', '')[:60]}")
    return True
