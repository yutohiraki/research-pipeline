"""
openalex_classic.py
INGEST（古典）: OpenAlex から各テーマの高被引用論文（古典）を取得する。

SPEC.md §4 STAGE1-B に対応。
- 対象テーマ: 魚類の音 / PAM / eDNA / Sciaenidae（config.yaml の classic.queries で設定）
- 各テーマ cited_by_count 降順で上位 N 件を candidate 化
- 実行頻度は週1（呼び出し側スケジュールで制御）

OpenAlex は API キー不要（mailto を付けると polite pool で安定）。
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from candidate import Candidate

# OpenAlex への連続クエリで 429 を避けるためのクエリ間小休止（秒）
_QUERY_PAUSE = 0.5


OPENALEX_WORKS = "https://api.openalex.org/works"


def _reconstruct_abstract(inv_index: dict) -> str:
    """OpenAlex の abstract_inverted_index を平文に復元"""
    if not inv_index:
        return ""
    positions = []
    for word, idxs in inv_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _work_to_candidate(work: dict, theme: str) -> Candidate:
    doi = work.get("doi") or ""
    authors = [
        a.get("author", {}).get("display_name", "")
        for a in (work.get("authorships") or [])
        if a.get("author")
    ]
    host = (work.get("primary_location") or {}).get("source") or {}
    journal = host.get("display_name") or ""

    oa = work.get("open_access") or {}
    is_oa = bool(oa.get("is_oa"))
    oa_pdf_url = ""
    best = work.get("best_oa_location") or {}
    if best:
        oa_pdf_url = best.get("pdf_url") or best.get("landing_page_url") or ""

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index") or {})

    return Candidate(
        title=work.get("title") or "",
        authors=[a for a in authors if a],
        year=str(work.get("publication_year") or ""),
        journal=journal,
        doi=doi,
        url=doi or (work.get("id") or ""),
        source_feed="openalex_classic",
        cited_by_count=int(work.get("cited_by_count") or 0),
        is_oa=is_oa,
        oa_pdf_url=oa_pdf_url,
        abstract=abstract[:3000],
        classic_theme=theme,
    )


def fetch_classic_for_query(search: str, theme: str, per_page: int,
                            mailto: str = "", from_year: int = 0,
                            to_year: int = 0) -> list:
    """1テーマぶんの高被引用論文を取得"""
    filters = [f"title_and_abstract.search:{search}"]
    if from_year or to_year:
        lo = from_year or 1900
        hi = to_year or 2100
        filters.append(f"publication_year:{lo}-{hi}")

    params = {
        "filter": ",".join(filters),
        "sort": "cited_by_count:desc",
        "per_page": str(per_page),
    }
    if mailto:
        params["mailto"] = mailto

    url = f"{OPENALEX_WORKS}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    [OpenAlex] {theme} 取得失敗: {e}")
        return []

    return [_work_to_candidate(w, theme) for w in data.get("results", [])]


def fetch_recent_for_query(search: str, theme: str, per_page: int,
                           mailto: str = "", days: int = 30) -> list:
    """1テーマぶんの『最近の論文』をキーワードで取得（発行日降順・直近days日）。
    Gmail アラート不要で最新を集めるための入口。source_feed=openalex_recent。"""
    import datetime
    from_date = (datetime.date.today() - datetime.timedelta(days=max(1, days))).isoformat()
    params = {
        "filter": f"title_and_abstract.search:{search},from_publication_date:{from_date}",
        "sort": "publication_date:desc",
        "per_page": str(per_page),
    }
    if mailto:
        params["mailto"] = mailto
    url = f"{OPENALEX_WORKS}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    [OpenAlex] {theme}(最新) 取得失敗: {e}")
        return []
    out = []
    for w in data.get("results", []):
        c = _work_to_candidate(w, theme)
        c.source_feed = "openalex_recent"
        out.append(c)
    return out


def fetch_recents(cfg: dict, mailto: str = "") -> list:
    """config に従い『最近の論文』をキーワードで取得（Gmail不要）。
    recent.queries があればそれ、無ければ classic.queries のキーワードを流用する。

    recent:
      enabled: true
      days: 30
      per_query: 8
      # queries: 省略時は classic.queries を使う
    """
    rc = (cfg.get("recent") or {})
    if not rc.get("enabled", True):
        return []
    days = int(rc.get("days", 30))
    per_query = int(rc.get("per_query", 8))
    queries = rc.get("queries") or (cfg.get("classic") or {}).get("queries", [])
    out = []
    for q in queries:
        search = q.get("search", "")
        if not search:
            continue
        theme = q.get("theme", "")
        print(f"  [OpenAlex] 最新取得: {theme} ← '{search[:40]}' (直近{days}日・上位{per_query}件)")
        out.extend(fetch_recent_for_query(search, theme, per_query, mailto=mailto, days=days))
        time.sleep(_QUERY_PAUSE)   # 429回避
    return out


def fetch_by_doi(doi: str, mailto: str = "") -> Candidate | None:
    """DOI から1件の論文メタを OpenAlex で正規化（著者全員・年・誌・OA・被引用・アブスト）"""
    if not doi:
        return None
    from candidate import normalize_doi
    ndoi = normalize_doi(doi)
    params = {"mailto": mailto} if mailto else {}
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{OPENALEX_WORKS}/doi:{urllib.parse.quote(ndoi, safe='/')}{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            work = json.loads(resp.read())
    except Exception:
        return None
    c = _work_to_candidate(work, theme="")
    c.source_feed = "openalex_recent"
    return c


def fetch_by_title(title: str, mailto: str = "") -> Candidate | None:
    """タイトルで OpenAlex を検索して正規化メタを得る（DOIが無い新着論文用）。
    取得タイトルが入力と十分一致しなければ None（誤マッチ防止）。"""
    if not title or len(title) < 12:
        return None
    from candidate import normalize_title
    q = " ".join(title.split()[:14])
    params = {"filter": f"title.search:{q}", "per_page": "1"}
    if mailto:
        params["mailto"] = mailto
    url = f"{OPENALEX_WORKS}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    results = data.get("results", [])
    if not results:
        return None
    c = _work_to_candidate(results[0], theme="")
    c.source_feed = "openalex_recent"
    # 誤マッチ防止: 正規化タイトル先頭の一致を確認
    nt_in, nt_got = normalize_title(title), normalize_title(c.title)
    if not (nt_in[:25] in nt_got or nt_got[:25] in nt_in):
        return None
    return c


def fetch_classics(classic_cfg: dict, mailto: str = "") -> list:
    """
    config.yaml の classic セクションに従い全テーマの古典を取得。

    classic:
      per_query: 10
      queries:
        - theme: "魚類の音"
          search: "fish sound OR fish vocalization"
        - ...
    """
    per_query = int(classic_cfg.get("per_query", 10))
    queries = classic_cfg.get("queries", [])
    out = []
    for q in queries:
        theme = q.get("theme", "")
        search = q.get("search", "")
        if not search:
            continue
        n = int(q.get("per_query", per_query))
        print(f"  [OpenAlex] 古典取得: {theme} ← '{search}' (上位{n}件)")
        out.extend(
            fetch_classic_for_query(
                search, theme, n, mailto=mailto,
                from_year=int(q.get("from_year", 0) or 0),
                to_year=int(q.get("to_year", 0) or 0),
            )
        )
        time.sleep(_QUERY_PAUSE)   # 429回避
    return out


if __name__ == "__main__":
    # 単体テスト: config.yaml の設定で実際に取得して表示
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mailto = cfg.get("unpaywall", {}).get("email", "")
    cands = fetch_classics(cfg.get("classic", {}), mailto=mailto)
    print(f"\n合計 {len(cands)} 件\n")
    for c in cands:
        print(f"[{c.classic_theme}] {c.cited_by_count:>5} cites | {c.year} | {c.oa_mark} | "
              f"{c.first_author} | {c.title[:60]}")
