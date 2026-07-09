"""
score_assist.py
対話セッションのClaudeが「無料で」inboxを採点するための補助（claude -p を使わない）。

使い方:
  # ① 候補を集めてJSONに書き出す（claude不要）。対話中のClaudeがこれを読む
  python score_assist.py --dump
  # ② 対話中のClaudeが /tmp/triage_scores.json に {id:{score,one_liner,tags}} を書いたら適用
  python score_assist.py --apply

SPEC.md のトリアージ採点を、6/15以降の課金を避けて対話セッション(サブスク内)で行うための経路。
"""

from __future__ import annotations

import argparse
import json

import yaml

from candidate import Candidate, dedupe
from ingest_recent import ingest as ingest_recent
from openalex_classic import fetch_classics
from inbox_writer import write_inbox
from triage_main import _imported_prefixes, drop_already_imported, drop_dismissed

CANDS_PATH = "/tmp/triage_cands.json"      # 採点対象（Claudeが読む）
SCORES_PATH = "/tmp/triage_scores.json"    # Claudeが書く採点結果


def collect(cfg: dict) -> list:
    mailto = cfg.get("unpaywall", {}).get("email", "")
    recent = ingest_recent(cfg)
    classics = dedupe(fetch_classics(cfg.get("classic", {}), mailto=mailto))
    imported = _imported_prefixes(cfg.get("pipeline", {}).get("vault_dir", ""))
    recent = drop_dismissed(drop_already_imported(recent, imported))
    classics = drop_dismissed(drop_already_imported(classics, imported))
    return recent + classics


def dump(cfg: dict):
    cands = collect(cfg)
    json.dump([c.to_dict() for c in cands], open(CANDS_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 採点用の軽量ビュー（Claudeが読みやすいよう抜粋）
    view = [{"id": c.id, "theme": c.classic_theme or "新着", "title": c.title,
             "year": c.year, "abstract": (c.abstract or "")[:450]} for c in cands]
    print(f"採点対象 {len(cands)} 件 → {CANDS_PATH}")
    print(json.dumps(view, ensure_ascii=False, indent=1))


def apply(cfg: dict):
    raw = json.load(open(CANDS_PATH, encoding="utf-8"))
    scores = json.load(open(SCORES_PATH, encoding="utf-8"))
    cands = [Candidate(**d) for d in raw]
    daily_limit = int(cfg.get("pipeline", {}).get("daily_candidate_limit", 10))
    for c in cands:
        s = scores.get(c.id)
        if not s:
            continue
        try:
            c.relevance_score = max(0, min(100, int(s.get("score", 0) or 0)))
        except (TypeError, ValueError):
            c.relevance_score = 0
        c.one_liner = str(s.get("one_liner", "")).strip()
        tags = s.get("tags", [])
        c.tags = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",")]

    recent = [c for c in cands if c.source_feed != "openalex_classic"]
    classics = [c for c in cands if c.source_feed == "openalex_classic"]
    recent_top = sorted(recent, key=lambda x: x.relevance_score, reverse=True)[:daily_limit]
    path = cfg.get("pipeline", {}).get("inbox_path", "")
    write_inbox(path, recent=recent_top, classics=classics,
                retention_days=int(cfg.get("pipeline", {}).get("inbox_retention_days", 14)))
    print(f"採点適用 → {path}（新着{len(recent_top)} / 古典{len(classics)}）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    if args.dump:
        dump(cfg)
    elif args.apply:
        apply(cfg)
