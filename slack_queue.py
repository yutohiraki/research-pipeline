"""
slack_queue.py
Cloudflare Worker に溜まった Slack ボタンのタップ結果（✅取り込む / 🗑️いらない）を
Mac 側で取得して inbox に反映する。

- 🗑️ dismiss → `dismissed.json` に永久登録＋ inbox から該当行を削除（＝×作業ゼロ）
- ✅ want    → inbox の該当 `- [ ]` を `- [x]`（取り込み待ち）にする → 既存の取り込みフローが処理

使い方:
  python slack_queue.py --sync        # キューを取得して inbox に反映（設定未了なら何もしない）
triage_main.py（朝）と promote_check.py（取り込み前）から自動で呼ばれる。

設定（config.yaml の slack）:
  worker_url: "https://xxx.workers.dev"   # Cloudflare Worker の URL
  pull_secret: "……"                      # Worker の PULL_SECRET と一致させる合言葉
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from inbox_writer import _line_keys, _load_dismissed_keys

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_DISMISSED = os.path.join(_PROJECT_DIR, "dismissed.json")


# Cloudflare のボット判定(error 1010)を避けるため、リクエストにブラウザ UA を付ける。
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _pull(worker_url: str, secret: str, kind: str, user: str) -> list:
    """Worker から自分（user=SlackメンバーID）の want|dismiss キューを取得（取得すると空になる）。
    user でキューを分けるので、1 つの Worker を研究室の全員で共有できる。"""
    import urllib.parse
    url = worker_url.rstrip("/") + f"/pull/{kind}?user=" + urllib.parse.quote(user)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {secret}",
        "User-Agent": _UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("items", []) or []
    except Exception as e:
        print(f"  [SlackQueue] {kind} 取得失敗: {str(e)[:120]}")
        return []


def _keys_of(items: list) -> set:
    return {it.get("k", "") for it in items if it.get("k")}


def sync_inbox(cfg: dict, verbose: bool = True) -> dict:
    """Worker のキューを inbox に反映。設定が無ければ何もしない（安全）。
    返り値: {'want': n, 'dismiss': n}（反映件数）。"""
    slack = cfg.get("slack", {})
    worker_url = slack.get("worker_url", "")
    secret = slack.get("pull_secret", "")
    user = slack.get("dm_user_id", "")   # 自分の Slack メンバーID＝自分のキューの鍵
    inbox_path = cfg.get("pipeline", {}).get("inbox_path", "")
    if not worker_url or not secret or not user:
        return {"want": 0, "dismiss": 0}

    want = _pull(worker_url, secret, "want", user)
    dismiss = _pull(worker_url, secret, "dismiss", user)
    want_keys = _keys_of(want)
    dismiss_keys = _keys_of(dismiss)
    if not want_keys and not dismiss_keys:
        return {"want": 0, "dismiss": 0}

    # 1) dismiss を dismissed.json に永久登録
    if dismiss_keys:
        existing = _load_dismissed_keys()
        merged = existing | dismiss_keys
        if len(merged) != len(existing):
            json.dump(sorted(merged), open(_DISMISSED, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)

    # 2) inbox に反映（want→[x]、dismiss→行削除）
    n_want = n_dismiss = 0
    if os.path.exists(inbox_path) and (want_keys or dismiss_keys):
        lines = open(inbox_path, encoding="utf-8").read().splitlines()
        out = []
        for l in lines:
            st = l.strip()
            is_task = st.startswith("- [") or st.startswith("* [")
            keys = _line_keys(l) if is_task else set()
            if is_task and (keys & dismiss_keys):
                n_dismiss += 1
                continue  # 🗑️: 行を削除
            if is_task and (keys & want_keys) and re.match(r"\s*- \[ \]", l):
                l = re.sub(r"^(\s*- )\[ \]", r"\1[x]", l, count=1)  # ✅: 取り込み待ちへ
                n_want += 1
            out.append(l)
        open(inbox_path, "w", encoding="utf-8").write("\n".join(out))

    if verbose and (n_want or n_dismiss or want_keys or dismiss_keys):
        print(f"  [SlackQueue] ✅取り込み待ち {n_want} 件 / 🗑️除外 {n_dismiss} 件を反映")
    return {"want": n_want, "dismiss": n_dismiss}


if __name__ == "__main__":
    import yaml
    cfg = yaml.safe_load(open(os.path.join(_PROJECT_DIR, "config.yaml"), encoding="utf-8"))
    res = sync_inbox(cfg)
    print(f"同期完了: 取り込み待ち+{res['want']} / 除外+{res['dismiss']}")
