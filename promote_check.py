"""
promote_check.py
PROMOTE 準備: `_inbox.md` で **チェック(`- [x]`)された論文**を拾い、PDFを確保して
「作業リスト」を出力する。深掘りメモ生成そのものは **対話セッションの Claude が無料で行う**
（6/15以降 claude -p は従量課金対象になるため、自動の claude -p 呼び出しはしない）。

使い方:
  # ① 採用分の準備（PDF確保＋作業リスト出力）。対話中のClaudeがこれを見てメモを書く
  python promote_check.py --prepare
  # ② メモを書き終えた論文を「取り込み済み」へ移す（DOI指定）
  python promote_check.py --mark-done "10.1098/rsos.150088,10.1577/t05-207.1"
  # 確認だけ
  python promote_check.py --dry-run

分担:
- Python(このファイル): チェック行の検出 / 5件/日 / PDF確保(手持ち照合+OA DL) / inbox更新
- 対話セッションの Claude: PDF全文読解 → literature_notes 生成 → [[Wikilink]]（vault CLAUDE.md準拠）
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import urllib.request
from urllib.parse import urljoin

import yaml

from candidate import candidate_id, normalize_doi
from inbox_writer import _line_key
from openalex_classic import fetch_by_doi

SEC_DONE = "## 取り込み済み"
WORKLIST_PATH = "/tmp/promote_worklist.json"


# ── 1日上限の状態 ──
def _state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "promote_state.json")


def get_today_count() -> int:
    p, today = _state_path(), datetime.date.today().isoformat()
    if os.path.exists(p):
        try:
            st = json.load(open(p, encoding="utf-8"))
            if st.get("date") == today:
                return int(st.get("count", 0))
        except Exception:
            pass
    return 0


def add_today_count(n: int):
    today = datetime.date.today().isoformat()
    json.dump({"date": today, "count": get_today_count() + n},
              open(_state_path(), "w", encoding="utf-8"))


# ── inbox 解析・更新 ──
def parse_checked_tasks(text: str) -> list:
    """チェック済み(`- [x]`)タスク行のうち DOI を持つものを返す: [(raw_line, doi)]"""
    rows, in_done = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            in_done = line.startswith(SEC_DONE)
            continue
        if in_done:
            continue
        if re.match(r"\s*- \[[xX]\] ", line):
            m = re.search(r"doi\.org/([^\s\)\]]+)", line)
            if m:
                rows.append((line, normalize_doi(m.group(1))))
    return rows


def _title_from_line(raw: str) -> str:
    t = re.sub(r"^\s*- \[[xX]\] ", "", raw)
    t = re.sub(r"\*\*\[\d+\]\*\*", "", t)        # **[score]**
    t = t.replace("✅", "").replace("⛔", "")
    t = re.split(r" — | · ", t)[0]
    return t.strip()


def _ident_to_key(idstr: str) -> str:
    """--mark-done に渡された識別子を candidate_id キーに変換（DOIでもタイトルでも可）。"""
    idstr = (idstr or "").strip()
    if not idstr:
        return ""
    low = idstr.lower()
    if "/" in idstr or low.startswith("10.") or "doi.org" in low:
        return candidate_id(idstr, "")      # → doi:...
    return candidate_id("", idstr)          # → title:...


def mark_done(inbox_path: str, dois: list):
    """指定の識別子（DOI **またはタイトル**）のチェック行を inbox から除去し、
    取り込み済みに日付つきで追記。DOIが無いチェック行もタイトルで移動できる。"""
    text = open(inbox_path, encoding="utf-8").read()
    want = {k for k in (_ident_to_key(d) for d in dois) if k}
    today = datetime.date.today().isoformat()
    keep, moved = [], []
    for line in text.splitlines():
        if re.match(r"\s*- \[[xX]\] ", line) and _line_key(line) in want:
            moved.append(line)
            continue
        keep.append(line)
    text = "\n".join(keep)
    # 取り込み済み記録に doi.org リンクを残す → 次回トリアージの重複排除が効き、再出現を防ぐ
    def _line(m):
        d = re.search(r"doi\.org/([^\s\)\]]+)", m)
        suffix = f" · doi.org/{normalize_doi(d.group(1))}" if d else ""
        return f"- {today} {_title_from_line(m)}{suffix}\n"
    add = "".join(_line(m) for m in moved)
    if SEC_DONE in text:
        text = text.replace(SEC_DONE + "\n", SEC_DONE + "\n" + add, 1)
    else:
        text += f"\n{SEC_DONE}\n{add}"
    open(inbox_path, "w", encoding="utf-8").write(text)
    if moved:
        add_today_count(len(moved))
    return len(moved)


# ── PDF 確保 ──
def _sanitize(name: str) -> str:
    name = re.sub(r"[/\\:*?\"<>|]", " ", name)
    return re.sub(r"\s+", " ", name).strip()[:150]


def find_existing_pdf(papers_dir: str, c) -> str:
    if not os.path.isdir(papers_dir):
        return ""
    author = (c.first_author or "").lower()
    if not author:
        return ""
    # 著者は「単語境界」で照合（短い姓 "He" が "niche" 等に部分一致する誤マッチを防ぐ）
    author_re = re.compile(r"(?<![a-z])" + re.escape(author) + r"(?![a-z])")
    tokens = sorted({w.lower() for w in re.findall(r"[A-Za-z]{6,}", c.title or "")},
                    key=len, reverse=True)[:4]
    for fn in os.listdir(papers_dir):
        if not fn.lower().endswith(".pdf"):
            continue
        low = fn.lower()
        if not author_re.search(low):
            continue
        years = re.findall(r"\b(?:19|20)\d{2}\b", fn)
        # 年が分かるなら一致を必須化（誤マッチ防止）
        if c.year:
            if not years or str(c.year) not in years:
                continue
        # タイトル特徴語の一致も必須（最低1語）
        if tokens and not any(t in low for t in tokens):
            continue
        # 短い姓(<=3文字)は年＋タイトル語の両方一致を要求済み。さらに念のため2語一致を要求
        if len(author) <= 3 and tokens:
            if sum(1 for t in tokens if t in low) < 2:
                continue
        return os.path.join(papers_dir, fn)
    return ""


# フルブラウザUA。MDPI等は簡易UAだと 403 で弾くため（Groq の error 1010 と同種の対策）。
_DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/pdf,text/html,application/xhtml+xml,*/*",
}


def _pdf_url_from_landing(html: str, base_url: str) -> str:
    """OAランディングページのHTMLから実PDF直リンクを取り出す。
    第一候補は citation_pdf_url メタタグ（Scholar等が使う広く普及した標準。
    HAL/bioRxiv/MDPI/PLOS 等が対応）。無ければ .pdf を指す<a>を拾う。"""
    for pat in (
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return urljoin(base_url, m.group(1).strip())
    # 保険: 明らかに PDF を指すリンク
    m = re.search(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html, re.I)
    if m:
        return urljoin(base_url, m.group(1).strip())
    return ""


def _try_download(url: str, dest_path: str, _follow_landing: bool = True) -> bool:
    try:
        req = urllib.request.Request(url, headers=_DL_HEADERS)
        with urllib.request.urlopen(req, timeout=45) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            final_url = resp.geturl()
            data = resp.read()
        if "pdf" in ctype or data[:5] == b"%PDF-":
            with open(dest_path, "wb") as f:
                f.write(data)
            return True
        # PDFでなくHTMLランディングなら、citation_pdf_url を辿って1回だけ再試行
        if _follow_landing and ("html" in ctype or b"<html" in data[:2000].lower()):
            pdf_url = _pdf_url_from_landing(data.decode("utf-8", "ignore"), final_url)
            if pdf_url and pdf_url != url:
                return _try_download(pdf_url, dest_path, _follow_landing=False)
        return False
    except Exception:
        return False


def resolve_and_download(c, dest_path: str, unpaywall_email: str) -> bool:
    urls = []
    if c.oa_pdf_url:
        urls.append(c.oa_pdf_url)
    if unpaywall_email and c.doi:
        try:
            from paper_fetcher import fetch_unpaywall_pdf_url
            up = fetch_unpaywall_pdf_url(c.doi, unpaywall_email)
            if up and up not in urls:
                urls.append(up)
        except Exception:
            pass
    return any(_try_download(u, dest_path) for u in urls)


# ── メイン: 準備 ──
def prepare(config_path: str, inbox_path: str = "", dry_run: bool = False):
    cfg = yaml.safe_load(open(config_path, encoding="utf-8"))
    # Slackボタンのタップ結果を先に反映（✅→[x] / 🗑️→除外）。取り込み直前に同期
    if not dry_run:
        try:
            import slack_queue
            slack_queue.sync_inbox(cfg)
        except Exception as e:
            print(f"  [SlackQueue] 同期スキップ: {str(e)[:100]}")
    pipe = cfg.get("pipeline", {})
    mailto = cfg.get("unpaywall", {}).get("email", "")
    vault_dir = pipe.get("vault_dir", "")
    papers_dir = os.path.join(vault_dir, "papers")
    inbox_path = inbox_path or pipe.get("inbox_path", "")
    daily_limit = int(pipe.get("promote_daily_limit", 5))

    if not os.path.exists(inbox_path):
        print(f"inbox が見つかりません: {inbox_path}")
        return []
    text = open(inbox_path, encoding="utf-8").read()
    rows = parse_checked_tasks(text)
    if not rows:
        print("チェック(`- [x]`)された論文はありません。")
        return []

    remaining = daily_limit - get_today_count()
    print(f"チェック済み {len(rows)} 件 / 本日残り枠 {max(0, remaining)}（上限{daily_limit}/日）")

    worklist = []
    for raw, doi in rows:
        c = fetch_by_doi(doi, mailto=mailto)
        title = c.title if c else _title_from_line(raw)
        entry = {"doi": doi, "title": title,
                 "authors": c.authors if c else [], "year": c.year if c else "",
                 "journal": c.journal if c else "", "pdf_path": "", "status": "manual"}
        if c:
            existing = find_existing_pdf(papers_dir, c)
            if existing:
                entry["pdf_path"], entry["status"] = existing, "ready"
            elif not dry_run and c.is_oa and c.oa_pdf_url:
                dest = os.path.join(papers_dir, _sanitize(
                    f"{c.first_author} et al. {c.year} - {c.title}") + ".pdf")
                if os.path.exists(dest) or resolve_and_download(c, dest, mailto):
                    entry["pdf_path"], entry["status"] = dest, "ready"
            elif c.is_oa and c.oa_pdf_url:
                entry["status"] = "oa-downloadable"
        worklist.append(entry)

    ready = [w for w in worklist if w["status"] == "ready"][:max(0, remaining)]
    manual = [w for w in worklist if w["status"] != "ready"]

    print(f"\n取り込み可能(PDF確保済): {len(ready)} 件")
    for w in ready:
        print(f"  ✓ {w['title'][:60]}\n      PDF: {os.path.basename(w['pdf_path'])}")
    if manual:
        print(f"\n要手動DL（papers/ にPDFを置けば次回取り込み可）: {len(manual)} 件")
        for w in manual:
            print(f"  ⛔ {w['title'][:60]}  ({w['doi']})")

    if not dry_run:
        json.dump(ready, open(WORKLIST_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n作業リスト → {WORKLIST_PATH}（対話セッションのClaudeがこれを読んでメモ生成）")
    return ready


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="PROMOTE準備（チェック済み論文のPDF確保＋作業リスト）")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--inbox", default="")
    ap.add_argument("--prepare", action="store_true", help="採用分のPDF確保＋作業リスト出力（既定）")
    ap.add_argument("--mark-done", default="", help="取り込み済みに移すDOI（カンマ区切り）")
    ap.add_argument("--dry-run", action="store_true", help="DLせず計画だけ表示")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    inbox = args.inbox or cfg.get("pipeline", {}).get("inbox_path", "")
    if args.mark_done:
        n = mark_done(inbox, [d for d in args.mark_done.split(",") if d.strip()])
        print(f"取り込み済みへ移動: {n} 件")
    else:
        prepare(args.config, inbox_path=args.inbox, dry_run=args.dry_run)
