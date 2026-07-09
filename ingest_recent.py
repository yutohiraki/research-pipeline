"""
ingest_recent.py
INGEST（最新）: Gmail の Scholar/WoS アラートから候補を作り、OpenAlex で正規化する。

SPEC.md §4 STAGE1-A。著者・年・誌・OA可否・アブストは**メール推測ではなく API で補完**
（著者情報が機能していない問題の根治）。DOI が取れたものは OpenAlex で上書き正規化する。
"""

from __future__ import annotations

import imaplib
import time

from candidate import Candidate, dedupe
from openalex_classic import fetch_by_doi, fetch_by_title


def _paper_to_candidate(p: dict) -> Candidate:
    authors = p.get("authors", "")
    author_list = [a.strip() for a in authors.split(",") if a.strip()] if authors else []
    year = ""
    pd = p.get("published_date", "")
    if pd and len(pd) >= 4:
        year = pd[:4]
    # 注: メール由来の著者・誌は不正確なことが多い。journal はソース名(Google Scholar等)を
    # 入れず空にし、OpenAlex 正規化で埋める（埋まらなければ空のまま）。
    return Candidate(
        title=p.get("title", ""),
        authors=author_list,
        year=year,
        journal="",
        doi=p.get("doi", ""),
        url=p.get("url", ""),
        source_feed="gmail_scholar" if "scholar" in p.get("source", "").lower() else "gmail_wos",
        abstract=p.get("raw_body", "")[:2000],
    )


def ingest(cfg: dict, verbose: bool = True) -> list:
    """Gmail から候補を取得し OpenAlex で正規化して返す。失敗しても空リストで継続。"""
    gmail_cfg = cfg["gmail"]
    mailto = cfg.get("unpaywall", {}).get("email", "")
    # 瞬断対策: IMAP の本文フェッチ中に Broken pipe 等で切れると、以前は「最新0件で
    # 空の一日」になっていた。**一過性エラーのみ**数回リトライ（毎回 fresh な接続で試す）。
    # 認証失敗など**恒久エラーは即諦める**（毎朝ジョブを無駄に待たせない）。全滅時も
    # 従来どおり空リストで継続してクラッシュさせない。
    retries = max(0, int(gmail_cfg.get("fetch_retries", 2)))   # 既定=2（=最大3回試行）
    # 再試行する一過性エラー。BrokenPipeError/ConnectionError は OSError の subclass。
    TRANSIENT = (OSError, TimeoutError, imaplib.IMAP4.abort)

    papers = None
    for attempt in range(retries + 1):
        try:
            from gmail_fetcher import collect_alert_emails, extract_papers_from_emails
            emails = collect_alert_emails(gmail_cfg)   # use_imap で IMAP/旧APIを自動切替
            papers = extract_papers_from_emails(emails)
            break
        except TRANSIENT as e:
            if attempt < retries:
                if verbose:
                    print(f"  [Ingest] Gmail 瞬断（{attempt + 1}/{retries + 1}回目）: {e} → 再試行")
                time.sleep(min(5 * (attempt + 1), 30))   # 5s → 10s … の緩いバックオフ
                continue
            if verbose:
                print(f"  [Ingest] Gmail 取得失敗（{retries + 1}回試行して断念・最新はスキップ）: {e}")
            return []
        except Exception as e:
            # 認証失敗・設定ミス等の恒久エラーは待たずに即スキップ。
            if verbose:
                print(f"  [Ingest] Gmail 取得失敗（恒久エラー・最新はスキップ）: {e}")
            return []

    candidates = []
    for p in papers:
        c = _paper_to_candidate(p)
        # OpenAlex で正規化（著者全員・年・誌・OA・アブスト）。
        # DOI 優先、無ければタイトル検索（メール推測の不正確な著者/誌を上書き）。
        norm = None
        if c.doi:
            norm = fetch_by_doi(c.doi, mailto=mailto)
        if not norm and c.title:
            norm = fetch_by_title(c.title, mailto=mailto)
        if norm and norm.title:
            norm.source_feed = c.source_feed
            if not norm.url:
                norm.url = c.url
            if not norm.abstract:
                norm.abstract = c.abstract
            c = norm
        candidates.append(c)

    candidates = dedupe(candidates)
    if verbose:
        print(f"  [Ingest] 最新 {len(candidates)} 件（正規化済み）")
    return candidates


if __name__ == "__main__":
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for c in ingest(cfg):
        print(f"{c.oa_mark} {c.year} | {c.first_author} | {c.title[:60]}")
