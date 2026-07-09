"""
slack_notifier.py
Slack Incoming Webhook で通知を送る
"""

import json
import urllib.request
from datetime import datetime, timezone, timedelta


def post_summary(papers: list, slack_cfg: dict):
    """処理した論文一覧をSlackに投稿する"""
    webhook_url = slack_cfg["webhook_url"]
    if not webhook_url or webhook_url.startswith("YOUR_"):
        print("[Slack] Webhook URL未設定のためスキップ")
        return

    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y-%m-%d")

    if not papers:
        text = f"📚 *{today} の論文まとめ*\n今日は新着論文はありませんでした。"
    else:
        lines = [f"📚 *今日の論文まとめ ({today})* | {len(papers)}件\n{'━'*30}"]
        for i, p in enumerate(papers, 1):
            title = p.get("title_ja") or p.get("title", "（タイトル不明）")
            url = p.get("url", "")
            tag = p.get("tag", "その他")
            summary = p.get("slack_summary") or p.get("summary", "")
            lines.append(
                f"\n*[{i}] {title}*"
                + (f"\n🔗 {url}" if url else "")
                + f"\n🏷 {tag}"
                + (f"\n{summary}" if summary else "")
            )
        text = "\n".join(lines)

    _post(webhook_url, text, slack_cfg)


def _post(webhook_url: str, text: str, slack_cfg: dict):
    payload = json.dumps({
        "username": slack_cfg.get("username", "論文Bot"),
        "icon_emoji": slack_cfg.get("icon_emoji", ":books:"),
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status == 200:
            print("[Slack] 投稿完了")
        else:
            print(f"[Slack] エラー: HTTP {resp.status}")
