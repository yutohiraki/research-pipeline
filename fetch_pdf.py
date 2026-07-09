"""
fetch_pdf.py
DOI（またはタイトル）から OA PDF を vault の papers/ に取得する単体ツール。
グローバル skill（別プロジェクトからの深掘りメモ生成）や、取り込み前の PDF 確保に使う。
promote_check の改良版ダウンローダ（citation_pdf_url 追跡＋ブラウザUA）を再利用。

使い方:
  python3 fetch_pdf.py --doi 10.1016/j.xxx
  python3 fetch_pdf.py --title "論文タイトル"
  python3 fetch_pdf.py --doi 10.xxx --config /path/to/config.yaml
出力: 取得できたら PDF の絶対パス（1行）。取れなければ "MANUAL: <理由>"。
"""

from __future__ import annotations

import argparse
import os

import yaml

from candidate import Candidate
from openalex_classic import fetch_by_doi, fetch_by_title
from promote_check import _sanitize, find_existing_pdf, resolve_and_download


def fetch(config_path: str, doi: str = "", title: str = "") -> str:
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    mailto = cfg.get("unpaywall", {}).get("email", "")
    vault = cfg.get("pipeline", {}).get("vault_dir", "")
    papers = os.path.join(vault, "papers")
    os.makedirs(papers, exist_ok=True)

    c: Candidate | None = None
    if doi:
        c = fetch_by_doi(doi, mailto=mailto)
    if not c and title:
        c = fetch_by_title(title, mailto=mailto)
    if not c:
        return "MANUAL: OpenAlex に見つからず（DOI/タイトルを確認、または手動で papers/ に配置）"

    # 手持ち照合（既に papers/ にあれば再取得しない）
    existing = find_existing_pdf(papers, c)
    if existing:
        return existing

    dest = os.path.join(papers, _sanitize(f"{c.first_author} et al. {c.year} - {c.title}") + ".pdf")
    if os.path.exists(dest):
        return dest
    if c.is_oa and resolve_and_download(c, dest, mailto):
        return dest
    reason = "非OA（paywall）" if not c.is_oa else "OA だが自動DL不可（bot遮断/ランディング）"
    return f"MANUAL: {reason} → ブラウザでDLして papers/ に配置。DOI={c.doi or '-'}"


def _default_config() -> str:
    """config の既定を解決: 環境変数 PAPER_CONFIG → config.local.yaml → config.yaml。
    配布先（後輩）は config.local.yaml、別プロジェクトからは PAPER_CONFIG を使う。"""
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.get("PAPER_CONFIG", "")
    if env and os.path.exists(env):
        return env
    for name in ("config.local.yaml", "config.yaml"):
        p = os.path.join(here, name)
        if os.path.exists(p):
            return p
    return os.path.join(here, "config.yaml")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DOI/タイトルから OA PDF を vault papers/ に取得")
    ap.add_argument("--doi", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--config", default=_default_config())
    args = ap.parse_args()
    if not args.doi and not args.title:
        print("MANUAL: --doi か --title を指定してください")
    else:
        print(fetch(args.config, doi=args.doi, title=args.title))
