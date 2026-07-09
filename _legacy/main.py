#!/usr/bin/env python3
"""
main.py
Gmail → Gemini → Notion / Sheets / Slack パイプライン
使い方:
  python main.py                  # 本番実行
  python main.py --dry-run        # 処理内容を確認するだけ（外部書き込みなし）
  python main.py --config path    # 設定ファイルを指定
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from gmail_fetcher import get_gmail_service, fetch_alert_emails, extract_papers_from_emails
from gemini_summarizer import enrich_paper
from notion_writer import add_paper_to_notion
from paper_fetcher import fetch_paper_content
from sheets_writer import get_sheets_service, append_paper_to_sheet
from slack_notifier import post_summary
from notion_enricher import run as run_enricher
from notion_to_paperpile import run as run_exporter


# ──────────────────────────────────────────────
# 設定読み込み
# ──────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 環境変数で上書き
    overrides = {
        ("groq", "api_key"): "GROQ_API_KEY",
        ("notion", "api_key"): "NOTION_API_KEY",
        ("slack", "webhook_url"): "SLACK_WEBHOOK_URL",
        ("slack", "bot_token"): "SLACK_BOT_TOKEN",
        ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    }
    for (section, key), env_var in overrides.items():
        val = os.environ.get(env_var)
        if val and section in cfg:
            cfg[section][key] = val

    return cfg


# ──────────────────────────────────────────────
# メインパイプライン
# ──────────────────────────────────────────────

def run(config_path: str, dry_run: bool = False):
    cfg = load_config(config_path)
    gmail_cfg = cfg["gmail"]
    groq_cfg = cfg["groq"]
    notion_cfg = cfg["notion"]
    sheets_cfg = cfg["sheets"]
    slack_cfg = cfg["slack"]
    user_cfg = cfg.get("user", {})
    research_context = user_cfg.get("research_context", "")
    themes = sheets_cfg.get("themes", ["その他"])

    print("=" * 50)
    print(f"{'[DRY-RUN] ' if dry_run else ''}論文パイプライン開始")
    print("=" * 50)

    # 1. Gmail から論文メールを取得
    print("\n[1/4] Gmail から論文アラートを取得中...")
    gmail_service = get_gmail_service(gmail_cfg["credentials_file"], gmail_cfg["token_file"])
    emails = fetch_alert_emails(gmail_service, gmail_cfg["search_query"], gmail_cfg.get("max_emails", 20))
    papers = extract_papers_from_emails(emails)

    if not papers:
        print("新着論文はありませんでした。")
        if slack_cfg.get("enabled", True):
            post_summary([], slack_cfg)
        return

    # 2. コンテンツ取得（Unpaywall PDF / Semantic Scholar）→ Groq 要約
    unpaywall_email = cfg.get("unpaywall", {}).get("email", "")
    ss_api_key = cfg.get("unpaywall", {}).get("semantic_scholar_api_key", "")
    print(f"\n[2/4] コンテンツ取得 → Groq 要約（{len(papers)} 件）...")
    enriched_papers = []
    for i, paper in enumerate(papers, 1):
        print(f"  ({i}/{len(papers)}) {paper.get('title', '')[:60]}...")
        # フルテキスト or アブスト取得
        if unpaywall_email:
            paper = fetch_paper_content(paper, unpaywall_email, ss_api_key=ss_api_key)
        if i > 1:
            time.sleep(8)  # Groq レート制限対策
        try:
            enriched = enrich_paper(paper, groq_cfg, themes, research_context)
            enriched_papers.append(enriched)
        except Exception as e:
            print(f"  [Groq] エラー: {e}")

    # 3. Notion & Sheets に登録
    if not dry_run:
        print(f"\n[3/4] Notion / Sheets に登録中...")
        sheets_service = get_sheets_service(gmail_cfg["credentials_file"], gmail_cfg["token_file"])
        for paper in enriched_papers:
            try:
                add_paper_to_notion(paper, notion_cfg)
            except Exception as e:
                print(f"  [Notion] エラー: {e}")
            try:
                append_paper_to_sheet(paper, sheets_cfg, sheets_service)
            except Exception as e:
                print(f"  [Sheets] エラー: {e}")
    else:
        print(f"\n[3/4] [DRY-RUN] Notion / Sheets への書き込みをスキップ")
        for p in enriched_papers:
            print(json.dumps({
                "title": p.get("title_ja", p.get("title", "")),
                "tag": p.get("tag", ""),
                "summary": p.get("summary", ""),
            }, ensure_ascii=False, indent=2))

    # 4. Slack に通知
    print(f"\n[4/4] Slack に通知中...")
    if not dry_run:
        if slack_cfg.get("enabled", True):
            post_summary(enriched_papers, slack_cfg)
        else:
            print("[Slack] 無効化中（config.yaml の enabled: false）")
    else:
        print("[DRY-RUN] Slack 投稿をスキップ")

    print(f"\n✅ Gmail パイプライン完了！ {len(enriched_papers)} 件処理しました。")

    # ── 追加ステップ1: Notion未エンリッチ論文にAI要約を補完（50件/日）──
    print("\n" + "=" * 50)
    print(f"{'[DRY-RUN] ' if dry_run else ''}[追加] Notion未エンリッチ論文の要約補完（最大2件）")
    print("=" * 50)
    if not dry_run:
        try:
            run_enricher(config_path, dry_run=False, limit=2)
        except Exception as e:
            print(f"[notion_enricher ERROR] {e}")
    else:
        print("[DRY-RUN] スキップ")

    # ── 追加ステップ2: Paperpile用 enriched.bib を生成 ──
    print("\n" + "=" * 50)
    print(f"{'[DRY-RUN] ' if dry_run else ''}[追加] Paperpile用 BibTeX エクスポート")
    print("=" * 50)
    if not dry_run:
        try:
            export_dir = Path.home() / "Desktop" / "Paperpile_Sync"
            export_dir.mkdir(exist_ok=True)
            export_path = str(export_dir / "enriched.bib")
            run_exporter(config_path, output=export_path, limit=500, only_enriched=True)
        except Exception as e:
            print(f"[notion_to_paperpile ERROR] {e}")
    else:
        print("[DRY-RUN] スキップ")


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="論文自動収集パイプライン")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="外部への書き込みを行わず動作確認のみ")
    args = parser.parse_args()
    run(args.config, dry_run=args.dry_run)
