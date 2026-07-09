"""
candidate.py
新パイプライン（SPEC.md）の共通データモデル。

candidate（候補レコード）は INGEST 段階で各ソース（Gmail / OpenAlex 等）から
正規化して作り、TRIAGE 段階でスコア・OA可否・一言を付け、_inbox.md に描画する。

SPEC.md §3.1 に対応。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field, asdict


# ──────────────────────────────────────────────
# 正規化ユーティリティ
# ──────────────────────────────────────────────

def normalize_doi(doi: str) -> str:
    """DOI を小文字・接頭辞なしに正規化（重複排除キー用）"""
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.strip()


def normalize_title(title: str) -> str:
    """タイトルを比較用に正規化（記号・空白除去、小文字化）"""
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"[^a-z0-9]+", "", t)
    return t


def candidate_id(doi: str, title: str) -> str:
    """DOI 優先、無ければ正規化タイトルのハッシュを ID にする"""
    ndoi = normalize_doi(doi)
    if ndoi:
        return f"doi:{ndoi}"
    ntitle = normalize_title(title)
    if ntitle:
        return "title:" + hashlib.sha1(ntitle.encode("utf-8")).hexdigest()[:16]
    return ""


# ──────────────────────────────────────────────
# Candidate
# ──────────────────────────────────────────────

@dataclass
class Candidate:
    title: str = ""
    authors: list = field(default_factory=list)   # 著者名のリスト（可能な限り全員）
    year: str = ""
    journal: str = ""
    doi: str = ""
    url: str = ""
    source_feed: str = ""        # gmail_scholar | gmail_wos | openalex_recent | openalex_classic | s2
    cited_by_count: int = 0
    is_oa: bool = False
    oa_pdf_url: str = ""
    abstract: str = ""           # トリアージ用本文（アブスト or TLDR）。全文は取らない
    relevance_score: int = 0     # 0–100（TRIAGE で付与）
    relevance_reason: str = ""   # 1行
    one_liner: str = ""          # 1–2文の客観サマリ（日本語、TRIAGE で付与）
    tags: list = field(default_factory=list)
    classic_theme: str = ""      # 古典の場合の所属テーマ（魚類の音 / PAM / eDNA / Sciaenidae）
    status: str = "candidate"    # candidate | promoted | dismissed
    first_seen: str = ""         # YYYY-MM-DD

    @property
    def id(self) -> str:
        return candidate_id(self.doi, self.title)

    @property
    def first_author(self) -> str:
        if not self.authors:
            return ""
        first = self.authors[0]
        # "Last, First" / "First Last" どちらでも姓を返す
        if "," in first:
            return first.split(",")[0].strip()
        parts = first.split()
        return parts[-1] if parts else first

    @property
    def oa_mark(self) -> str:
        return "✅" if self.is_oa else "⛔"

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
# 重複排除
# ──────────────────────────────────────────────

def dedupe(candidates: list) -> list:
    """ID（DOI or 正規化タイトル）で重複排除。被引用数の多い方を残す"""
    by_id = {}
    for c in candidates:
        cid = c.id
        if not cid:
            # ID が作れないものはタイトルそのままで一応残す
            by_id[id(c)] = c
            continue
        if cid not in by_id or c.cited_by_count > by_id[cid].cited_by_count:
            by_id[cid] = c
    return list(by_id.values())
