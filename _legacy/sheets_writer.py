"""
sheets_writer.py
Google Sheets API でテーマ別タブに論文情報を書き込む
"""

from datetime import datetime, timezone, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES_SHEETS = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_sheets_service(credentials_file: str, token_file: str):
    """Gmail と同じ credentials.json / token.json を使い回す"""
    creds = None
    if __import__("os").path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES_SHEETS)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES_SHEETS)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def _ensure_sheet_exists(service, spreadsheet_id: str, sheet_name: str):
    """シートが存在しなければ作成する"""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = [s["properties"]["title"] for s in meta["sheets"]]
    if sheet_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()
        print(f"  [Sheets] タブ作成: {sheet_name}")


def _get_last_row(service, spreadsheet_id: str, sheet_name: str) -> int:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:A",
    ).execute()
    values = result.get("values", [])
    return len(values)


def append_paper_to_sheet(paper: dict, sheets_cfg: dict, service) -> bool:
    """論文をテーマ別タブに追記する"""
    spreadsheet_id = sheets_cfg["spreadsheet_id"]
    columns = sheets_cfg.get("columns", [])

    # tags がリストの場合は最初のものをタブ振り分けに使う
    themes = sheets_cfg.get("themes", ["その他"])
    raw_tags = paper.get("tags") or paper.get("tag", "その他")
    if isinstance(raw_tags, list):
        tag = next((t for t in raw_tags if t in themes), "その他")
    else:
        tag = raw_tags if raw_tags in themes else "その他"
    sheet_name = tag

    _ensure_sheet_exists(service, spreadsheet_id, sheet_name)

    # ヘッダー行がなければ追加
    last_row = _get_last_row(service, spreadsheet_id, sheet_name)
    if last_row == 0:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="RAW",
            body={"values": [columns]},
        ).execute()

    jst = timezone(timedelta(hours=9))
    now_str = datetime.now(jst).strftime("%Y-%m-%d %H:%M")

    # 列の順序に従って値をセット
    tags_val = paper.get("tags") or paper.get("tag", "その他")
    tags_str = ", ".join(tags_val) if isinstance(tags_val, list) else str(tags_val)

    col_map = {
        "タイトル": paper.get("title", ""),
        "著者": paper.get("authors_clean") or paper.get("authors", ""),
        "Published日": paper.get("published_date", ""),
        "URL": paper.get("url", ""),
        "一言まとめ": paper.get("summary", ""),
        "手法・解析ツール": paper.get("methods", ""),
        "主な結果": paper.get("main_results", ""),
        "新規性": paper.get("novelty", ""),
        "研究の限界": paper.get("limitations", ""),
        "今後の課題": paper.get("future_work", ""),
        "データ公開": paper.get("data_availability", ""),
        "自分の研究への示唆": paper.get("relevance", ""),
        "タグ": tags_str,
        "登録日時": now_str,
    }
    row = [str(col_map.get(col, "")) for col in columns]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()
    print(f"  [Sheets] 追記完了 → タブ「{sheet_name}」: {paper.get('title', '')[:50]}")
    return True
