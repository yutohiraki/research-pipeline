"""
triage_main.py
毎朝8時の本体: INGEST（最新＋古典）→ TRIAGE（claude -p 採点）→ `_inbox.md` 生成 → Slack DM。

SPEC.md §4 STAGE1+STAGE2。有料API不要（採点は claude -p = サブスク内）。

使い方:
  python triage_main.py --preview     # /tmp/_inbox.md に生成（vault に触れない）
  python triage_main.py               # config の pipeline.inbox_path に生成（本番）
  python triage_main.py --no-classic  # 古典をスキップ（古典は本来 週1）
  python triage_main.py --no-slack    # Slack 通知をスキップ
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re

import yaml

DISMISSED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dismissed.json")


def load_dismissed() -> set:
    """ユーザーが「もう出さなくていい」とした候補IDの集合（恒久除外）"""
    try:
        return set(json.load(open(DISMISSED_PATH, encoding="utf-8")))
    except Exception:
        return set()


def add_dismissed(ids: list):
    cur = load_dismissed() | {i for i in ids if i}
    json.dump(sorted(cur), open(DISMISSED_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return cur


def drop_dismissed(cands: list) -> list:
    dis = load_dismissed()
    return [c for c in cands if c.id not in dis]

from candidate import dedupe
from ingest_recent import ingest as ingest_recent
from openalex_classic import fetch_classics
from triage import score_all
from inbox_writer import write_inbox
from notify_slack_dm import notify_triage, notify_triage_buttons
import slack_queue


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _imported_prefixes(vault_dir: str) -> set:
    """literature_notes の {筆頭著者姓}{年} 接頭辞集合（取り込み済み判定用）"""
    lit = os.path.join(vault_dir, "literature_notes")
    out = set()
    if not os.path.isdir(lit):
        return out
    for fn in os.listdir(lit):
        m = re.match(r"([A-Za-z]+)(\d{4})_", fn)
        if m:
            out.add((m.group(1).lower(), m.group(2)))
    return out


def drop_already_imported(cands: list, imported: set) -> list:
    """既に literature_notes にある論文を候補から除外（再掲防止・採点コスト節約）"""
    kept = []
    for c in cands:
        key = (c.first_author.lower(), c.year)
        if key in imported:
            continue
        kept.append(c)
    return kept


def run(config_path: str, preview: bool = False, with_classic: bool = True,
        with_slack: bool = True, force_classic: bool = False, no_score: bool = False):
    cfg = load_config(config_path)
    # Slackボタンのタップ結果を反映（✅→[x] / 🗑️→dismissed）。preview時はvault不可侵なのでスキップ
    if not preview:
        try:
            slack_queue.sync_inbox(cfg)
        except Exception as e:
            print(f"  [SlackQueue] 同期スキップ: {str(e)[:100]}")
    pipe = cfg.get("pipeline", {})
    classic_cfg = cfg.get("classic", {})
    mailto = cfg.get("unpaywall", {}).get("email", "")
    research = cfg.get("user", {}).get("research_context", "")
    themes = cfg.get("sheets", {}).get("themes", ["その他"])
    daily_limit = int(pipe.get("daily_candidate_limit", 10))

    # 古典は週1（指定曜日のみ）。毎朝の自動実行でも曜日が合う日だけ取得する。
    classic_weekday = int(classic_cfg.get("weekday", 0))  # 0=月曜
    if with_classic and not force_classic and not preview:
        if datetime.date.today().weekday() != classic_weekday:
            with_classic = False

    print("=" * 50)
    print(f"{'[PREVIEW] ' if preview else ''}トリアージ開始 {datetime.date.today().isoformat()}")
    print("=" * 50)

    # 1. INGEST 最新
    print("\n[1/4] 最新論文を取得・正規化...")
    recent = ingest_recent(cfg)

    # 2. INGEST 古典（本来は週1）
    classics = []
    if with_classic:
        print("\n[2/4] 古典（高被引用）を取得...")
        classics = fetch_classics(cfg.get("classic", {}), mailto=mailto)
        classics = dedupe(classics)
    else:
        print("\n[2/4] 古典スキップ")

    # 取り込み済み（literature_notes に既にある）＋ 恒久除外(dismissed) を候補から除外
    imported = _imported_prefixes(pipe.get("vault_dir", ""))
    before_r, before_c = len(recent), len(classics)
    recent = drop_dismissed(drop_already_imported(recent, imported))
    classics = drop_dismissed(drop_already_imported(classics, imported))
    dropped = (before_r - len(recent)) + (before_c - len(classics))
    if dropped:
        print(f"  取り込み済み・除外を反映: {dropped} 件")

    # 3. TRIAGE（最新＋古典を1回のバッチ採点）
    all_cands = recent + classics
    if no_score:
        print(f"\n[3/4] 採点スキップ（--no-score。スコア0で出力）")
    else:
        engine = (cfg.get("scoring_engine") or "ollama")
        print(f"\n[3/4] 採点（engine={engine}・最新{len(recent)}＋古典{len(classics)}件）...")
        score_all(all_cands, cfg, research, themes)

    # 最新は関連度トップ daily_limit 件に絞る
    recent_sorted = sorted(recent, key=lambda x: x.relevance_score, reverse=True)
    recent_top = recent_sorted[:daily_limit]
    if len(recent_sorted) > daily_limit:
        print(f"  [Triage] 最新は上位 {daily_limit} 件に制限（{len(recent_sorted)}件中）")

    # 4. _inbox.md 生成
    inbox_path = "/tmp/_inbox.md" if preview else pipe.get("inbox_path", "/tmp/_inbox.md")
    print(f"\n[4/4] inbox 生成 → {inbox_path}")
    write_inbox(inbox_path, recent=recent_top, classics=classics,
                retention_days=int(pipe.get("inbox_retention_days", 14)))

    # Slack 通知（interactive=true ならボタン付き、それ以外は片方向テキスト）
    if with_slack and not preview:
        slack_cfg = cfg.get("slack", {})
        if slack_cfg.get("interactive"):
            n = notify_triage_buttons(slack_cfg, recent_top, classics, inbox_path)
            print(f"  [Slack] ボタン付き通知 {n} 件投稿")
        else:
            notify_triage(slack_cfg, recent_top, classics, inbox_path)
    else:
        print("  [Slack] スキップ（preview or --no-slack）")

    print(f"\n✅ 完了: 最新{len(recent_top)} / 古典{len(classics)} 件を {inbox_path} に出力")
    return inbox_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="トリアージ本体（最新＋古典→採点→inbox）")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--preview", action="store_true", help="/tmp/_inbox.md に生成（vault不可侵）")
    ap.add_argument("--no-classic", action="store_true", help="古典をスキップ")
    ap.add_argument("--force-classic", action="store_true", help="曜日に関わらず古典を取得")
    ap.add_argument("--no-slack", action="store_true", help="Slack通知をスキップ")
    ap.add_argument("--no-score", action="store_true", help="claude採点をスキップ（認証不要・スコア0）")
    args = ap.parse_args()
    run(args.config, preview=args.preview,
        with_classic=not args.no_classic, with_slack=not args.no_slack,
        force_classic=args.force_classic, no_score=args.no_score)
