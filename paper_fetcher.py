"""
paper_fetcher.py
DOI / タイトルから論文コンテンツを取得する

優先順位:
  1. Unpaywall → OA PDF URL → PyMuPDF でフルテキスト抽出
  2. Semantic Scholar → アブスト全文 + tldr
  3. 元のメール本文そのまま（フォールバック）
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request


# ──────────────────────────────────────────────
# Unpaywall
# ──────────────────────────────────────────────

def fetch_unpaywall_pdf_url(doi: str, email: str) -> str:
    """Unpaywall API からオープンアクセス PDF URL を取得"""
    if not doi:
        return ""
    # DOIはスラッシュをそのまま保持する（Unpaywall APIの仕様）
    url = f"https://api.unpaywall.org/v2/{doi}?email={urllib.parse.quote(email)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "research-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        loc = data.get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception:
        return ""


def extract_text_from_pdf_url(pdf_url: str, max_chars: int = 8000) -> str:
    """PDF URL からテキストを抽出（PyMuPDF 使用）"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("    [Fetch] PyMuPDF 未インストール: pip install pymupdf")
        return ""

    try:
        req = urllib.request.Request(pdf_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/pdf,*/*",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not pdf_url.lower().endswith(".pdf"):
                return ""
            pdf_bytes = resp.read()

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text_parts = []
            chars = 0
            for page in doc:
                t = page.get_text()
                text_parts.append(t)
                chars += len(t)
                if chars >= max_chars:
                    break

        text = "\n".join(text_parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {3,}", " ", text)
        return text[:max_chars]
    except Exception as e:
        print(f"    [Fetch] PDF取得失敗: {e}")
        return ""


# ──────────────────────────────────────────────
# Semantic Scholar
# ──────────────────────────────────────────────

def fetch_semantic_scholar(doi: str = "", title: str = "", api_key: str = "") -> dict:
    """Semantic Scholar API からアブスト・著者・年を取得（リトライあり）"""
    import time as _time
    fields = "abstract,tldr,authors,year,title,externalIds"
    base = "https://api.semanticscholar.org/graph/v1/paper"

    if doi:
        url = f"{base}/DOI:{urllib.parse.quote(doi, safe='')}?fields={fields}"
    elif title:
        q = urllib.parse.quote(title[:100])
        url = f"{base}/search?query={q}&fields={fields}&limit=1"
    else:
        return {}

    headers = {"User-Agent": "research-pipeline/1.0"}
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            if "data" in data:
                if not data["data"]:
                    return {}
                data = data["data"][0]

            return {
                "abstract": data.get("abstract") or "",
                "tldr": (data.get("tldr") or {}).get("text") or "",
                "year": str(data.get("year") or ""),
                "authors": ", ".join(
                    a.get("name", "") for a in (data.get("authors") or [])[:15]
                ),
                "doi": (data.get("externalIds") or {}).get("DOI") or "",
            }
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f"    [Fetch] Semantic Scholar レート制限、{wait}秒待機...")
                _time.sleep(wait)
            else:
                print(f"    [Fetch] Semantic Scholar 失敗: HTTP {e.code}")
                return {}
        except Exception as e:
            print(f"    [Fetch] Semantic Scholar 失敗: {e}")
            return {}
    return {}


# ──────────────────────────────────────────────
# メイン取得関数
# ──────────────────────────────────────────────

def fetch_paper_content(paper: dict, unpaywall_email: str, ss_api_key: str = "") -> dict:
    """
    論文コンテンツを取得して paper dict の raw_body を更新する。

    取得優先順位:
      1. Unpaywall → PDF フルテキスト（OA論文のみ）
      2. Semantic Scholar → アブスト全文
      3. フォールバック（メール本文のまま）
    """
    doi = paper.get("doi", "")
    title = paper.get("title", "")

    # ── 1. Unpaywall → PDF ──
    if doi:
        pdf_url = fetch_unpaywall_pdf_url(doi, unpaywall_email)
        if pdf_url:
            full_text = extract_text_from_pdf_url(pdf_url)
            if len(full_text) > 300:
                paper["raw_body"] = full_text
                if not paper.get("pdf_url"):
                    paper["pdf_url"] = pdf_url
                print(f"    [Fetch] ✓ PDF全文 ({len(full_text)}文字): {pdf_url[:60]}")
                return paper
            else:
                print(f"    [Fetch] Unpaywall: PDFは取得できたがテキスト抽出失敗")
        else:
            print(f"    [Fetch] Unpaywall: OA版なし (DOI: {doi})")

    # ── 2. Semantic Scholar → アブスト ──
    ss = fetch_semantic_scholar(doi, title, api_key=ss_api_key)
    abstract = ss.get("abstract", "")
    if len(abstract) > 100:
        tldr = ss.get("tldr", "")
        paper["raw_body"] = f"{abstract}\n\nTLDR: {tldr}".strip() if tldr else abstract
        # 他フィールドも補完
        if ss.get("authors") and not paper.get("authors"):
            paper["authors"] = ss["authors"]
        if ss.get("year") and not paper.get("published_date"):
            paper["published_date"] = f"{ss['year']}-01-01"
        if ss.get("doi") and not paper.get("doi"):
            paper["doi"] = ss["doi"]
            if not paper.get("url"):
                paper["url"] = f"https://doi.org/{ss['doi']}"
        print(f"    [Fetch] ✓ Semantic Scholar アブスト ({len(abstract)}文字)")
        return paper
    else:
        print(f"    [Fetch] Semantic Scholar: アブストなし → メール本文を使用")

    return paper
