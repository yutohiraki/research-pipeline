"""
notify_slack_dm.py
Slack: Bot Token で @自分 に DM 通知する（cron/python から送るため）。

SPEC.md §4 STAGE2 / STAGE3 の通知。旧 slack_notifier.py（webhook→チャンネル）を置き換える。

必要な設定（config.yaml の slack）:
  slack:
    bot_token: "xoxb-..."     # Slack App の Bot User OAuth Token（scope: chat:write）
    dm_user_id: "U0XXXXXXX"   # 自分の Slack メンバーID（プロフィール→「メンバーIDをコピー」）
環境変数 SLACK_BOT_TOKEN でも可。
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.request

try:
    from candidate import candidate_id, normalize_doi
except Exception:                      # 単体でも動くようフォールバック
    def normalize_doi(d):
        return (d or "").strip()

    def candidate_id(doi, title):
        return "doi:" + normalize_doi(doi) if doi else ""

SLACK_POST = "https://slack.com/api/chat.postMessage"


def send_dm(slack_cfg: dict, text: str) -> bool:
    token = slack_cfg.get("bot_token", "")
    user_id = slack_cfg.get("dm_user_id", "")
    if not token or not user_id:
        print("  [Slack] bot_token / dm_user_id 未設定。通知スキップ。")
        return False

    payload = json.dumps({
        "channel": user_id,   # ユーザーIDを渡すと DM(IM) に投稿される
        "text": text,
        "unfurl_links": False,
    }).encode("utf-8")
    req = urllib.request.Request(SLACK_POST, data=payload, headers={
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            print(f"  [Slack] 送信失敗: {data.get('error')}")
            return False
        return True
    except Exception as e:
        print(f"  [Slack] 送信失敗: {e}")
        return False


def _clip(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _link(c) -> str:
    """Slack mrkdwn のリンク（DOI優先→URL）。無ければ空。"""
    doi = normalize_doi(getattr(c, "doi", "") or "")
    if doi:
        return f"<https://doi.org/{doi}|🔗doi>"
    url = getattr(c, "url", "") or ""
    if url:
        return f"<{url}|🔗link>"
    return ""


def _fmt_item(c, classic: bool = False) -> str:
    """1候補を2行（見出し＋メタ）に整形。関連度順ダイジェスト用。"""
    oa = getattr(c, "oa_mark", "") or ""
    head = f"*[{c.relevance_score}]* {oa} {_clip(c.title, 90)}".strip()
    meta = []
    if getattr(c, "one_liner", ""):
        meta.append(_clip(c.one_liner, 100))
    who = " ".join(x for x in [getattr(c, "first_author", ""), str(getattr(c, "year", "") or "")] if x)
    if who:
        meta.append(who)
    if classic and getattr(c, "cited_by_count", 0):
        meta.append(f"{c.cited_by_count}cites")
    elif getattr(c, "journal", ""):
        meta.append(_clip(c.journal, 40))
    lk = _link(c)
    if lk:
        meta.append(lk)
    line = "• " + head
    if meta:
        line += "\n    " + " · ".join(meta)
    return line


def notify_triage(slack_cfg: dict, recent: list, classics: list,
                  inbox_path: str) -> bool:
    """TRIAGE 完了通知＝**関連度順の片方向ダイジェスト DM**。
    新着（上位 digest_recent 件）＋古典（収集日のみ・上位 digest_classic 件）を、
    スコア・OA可否・日本語要約・DOIリンク付きで表示。判断はここで完結できる。"""
    n_recent = int(slack_cfg.get("digest_recent", 12))
    n_classic = int(slack_cfg.get("digest_classic", 6))
    today = datetime.date.today().isoformat()

    rec = sorted(recent, key=lambda x: getattr(x, "relevance_score", 0), reverse=True)
    cls = sorted(classics, key=lambda x: getattr(x, "cited_by_count", 0), reverse=True)

    lines = [f":books: *論文 inbox 更新 — {today}*　新着 {len(recent)} 件"
             + (f" / 古典 {len(classics)} 件" if classics else "")]

    if rec:
        lines.append("")
        lines.append("*━ 新着（関連度トップ）━*")
        for c in rec[:n_recent]:
            lines.append(_fmt_item(c))
        if len(rec) > n_recent:
            lines.append(f"…ほか {len(rec) - n_recent} 件（`_inbox.md` に全件）")

    if cls:
        lines.append("")
        lines.append("*━ 古典・高被引用 ━*")
        for c in cls[:n_classic]:
            lines.append(_fmt_item(c, classic=True))
        if len(cls) > n_classic:
            lines.append(f"…ほか {len(cls) - n_classic} 件")

    lines.append("")
    lines.append("要る → Obsidian で `[x]`／いらない → `🗑️ 二度と出さない` へ移動")
    lines.append("取り込み → Claude Code（Remote Control）で「*inbox の◯◯を取り込んで*」")
    return send_dm(slack_cfg, "\n".join(lines))


def send_blocks(slack_cfg: dict, blocks: list, fallback: str) -> bool:
    """Block Kit（ボタン付き）メッセージを DM に投稿。"""
    token = slack_cfg.get("bot_token", "")
    user_id = slack_cfg.get("dm_user_id", "")
    if not token or not user_id:
        print("  [Slack] bot_token / dm_user_id 未設定。通知スキップ。")
        return False
    payload = json.dumps({
        "channel": user_id, "text": fallback, "blocks": blocks, "unfurl_links": False,
    }).encode("utf-8")
    req = urllib.request.Request(SLACK_POST, data=payload, headers={
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            print(f"  [Slack] blocks 送信失敗: {data.get('error')}")
            return False
        return True
    except Exception as e:
        print(f"  [Slack] blocks 送信失敗: {e}")
        return False


def _paper_blocks(c, classic: bool = False) -> list:
    """1論文＝section（情報）＋actions（✅/🗑️ボタン）。value にキー・タイトルを載せる。"""
    oa = getattr(c, "oa_mark", "") or ""
    title = _clip(c.title, 140)
    meta = []
    if getattr(c, "one_liner", ""):
        meta.append(_clip(c.one_liner, 140))
    who = " ".join(x for x in [getattr(c, "first_author", ""), str(getattr(c, "year", "") or "")] if x)
    if who:
        meta.append(who)
    if classic and getattr(c, "cited_by_count", 0):
        meta.append(f"{c.cited_by_count}cites")
    elif getattr(c, "journal", ""):
        meta.append(_clip(c.journal, 40))
    lk = _link(c)
    if lk:
        meta.append(lk)
    body = f"*[{c.relevance_score}]* {oa} {title}"
    if meta:
        body += "\n" + " · ".join(meta)

    key = candidate_id(getattr(c, "doi", "") or "", c.title)
    short = _clip(c.title, 80)
    val_want = json.dumps({"k": key, "t": short, "a": "want"}, ensure_ascii=False)
    val_dis = json.dumps({"k": key, "t": short, "a": "dismiss"}, ensure_ascii=False)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "✅ 取り込む"},
             "style": "primary", "action_id": "act_want", "value": val_want},
            {"type": "button", "text": {"type": "plain_text", "text": "🗑️ いらない"},
             "action_id": "act_dismiss", "value": val_dis},
        ]},
        {"type": "divider"},
    ]


def notify_triage_buttons(slack_cfg: dict, recent: list, classics: list,
                          inbox_path: str = "") -> int:
    """TRIAGE 完了通知＝**✅/🗑️ ボタン付き**（Slackでポチポチ選別）。1論文=1メッセージ。
    タップは Cloudflare Worker→KV→Mac が拾って inbox に反映する。投稿件数を返す。"""
    n_recent = int(slack_cfg.get("digest_recent", 12))
    n_classic = int(slack_cfg.get("digest_classic", 6))
    pause = float(slack_cfg.get("post_pause", 0.5))  # Slackレート制限回避
    today = datetime.date.today().isoformat()

    rec = sorted(recent, key=lambda x: getattr(x, "relevance_score", 0), reverse=True)[:n_recent]
    cls = sorted(classics, key=lambda x: getattr(x, "cited_by_count", 0), reverse=True)[:n_classic]
    if not rec and not cls:
        return 0

    header = (f":books: *論文 inbox 更新 — {today}*　"
              f"新着 {len(recent)} 件" + (f" / 古典 {len(classics)} 件" if classics else "")
              + "\n✅取り込む / 🗑️いらない をタップ → Claude Code で「取り込んで」")
    send_dm(slack_cfg, header)
    time.sleep(pause)

    posted = 0
    for c in rec:
        if send_blocks(slack_cfg, _paper_blocks(c), fallback=f"[{c.relevance_score}] {c.title[:80]}"):
            posted += 1
        time.sleep(pause)
    for c in cls:
        if send_blocks(slack_cfg, _paper_blocks(c, classic=True),
                       fallback=f"[{c.relevance_score}] {c.title[:80]}"):
            posted += 1
        time.sleep(pause)
    return posted


def notify_promote(slack_cfg: dict, imported: list, manual_dl: list,
                   deferred: int = 0) -> bool:
    """PROMOTE 完了通知"""
    lines = [f":white_check_mark: *深掘り取り込み完了*: {len(imported)} 件"]
    for t in imported[:5]:
        lines.append(f"• {t[:70]}")
    if manual_dl:
        lines.append(f":warning: 要手動DL（PDF未取得）: {len(manual_dl)} 件")
        for t in manual_dl[:5]:
            lines.append(f"• {t[:70]}")
    if deferred:
        lines.append(f":hourglass: 1日上限超過で翌日へ繰り越し: {deferred} 件")
    return send_dm(slack_cfg, "\n".join(lines))


if __name__ == "__main__":
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ok = send_dm(cfg.get("slack", {}), ":wave: research-pipeline テスト通知")
    print("送信:", "成功" if ok else "失敗（設定を確認）")
