"""
validate_note.py
深掘りメモ（literature_note）の**保存前バリデーション**。vault を規約違反メモで汚さないための
機械チェック。paper-note-writer skill / /paper-import が生成後に呼ぶ（任意・保険）。

使い方:
  python3 validate_note.py path/to/Author2025_Keyword.md
  # 終了コード 0=合格(警告はあってもOK) / 1=規約違反あり

ハード違反（exit 1・vault を汚すので弾く。vault CLAUDE.md §2/§3 準拠）:
  - ファイル名が {筆頭著者姓}{年}_{キーワード}.md パターンに不一致
  - frontmatter が無い / 必須キー欠落
  - tags に literature を含まない
  - status が read でない、read_date が絶対日付(YYYY-MM-DD)でない
  - [[Wikilink]] が1つも無い
ソフト警告（exit 0・品質の目安。実メモもページ番号引用は1〜数箇所のことがあり、
  セクション/図表引用(Abstract/Fig.7 等)も正当なので**弾かない**）:
  - 引用箇所が少ない（ページ番号 or セクション引用の合計が目安5未満）
依存なし（標準ライブラリのみ）。YAML は簡易パースで必須キーの有無だけ見る。
"""

from __future__ import annotations

import os
import re
import sys

REQUIRED_KEYS = [
    "title", "authors", "year", "journal", "doi", "tags",
    "status", "read_date", "research_field", "related_concepts", "my_rating",
]
FILENAME_RE = re.compile(r"^[A-Za-z][A-Za-z'-]*\d{4}_.+\.md$")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
PAGE_CITE_RE = re.compile(r"\(?\bp{1,2}\.?\s?\d", re.IGNORECASE)  # p.12 / pp.3 / (p. 5)
# セクション/図表引用も「引用箇所」として数える（実メモは Abstract/Fig/Conclusion 表記が多い）
SECTION_CITE_RE = re.compile(
    r"[（(]\s*(?:Abstract|Introduction|Methods?|Results?|Discussion|Conclusions?|"
    r"Fig(?:ure)?\.?\s?\d|Table\s?\d|[IVX]+\.\s|§)", re.IGNORECASE)
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")


def _split_frontmatter(text: str):
    """先頭の --- ... --- を (frontmatter, body) に分ける。無ければ ('', text)。"""
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def validate(path: str):
    """(problems, warnings) を返す。problems があれば exit 1（vault を汚す）。"""
    problems, warnings = [], []
    fn = os.path.basename(path)
    if not FILENAME_RE.match(fn):
        problems.append(f"ファイル名が規約に不一致: '{fn}' 期待='{{筆頭著者姓}}{{年}}_{{キーワード}}.md'（例 Parmentier2021_BrotulaReefSound.md）")

    if not os.path.exists(path):
        problems.append(f"ファイルが存在しない: {path}")
        return problems, warnings

    text = open(path, encoding="utf-8").read()
    fm, body = _split_frontmatter(text)
    if not fm:
        problems.append("frontmatter(--- で囲む YAML)が無い")
        return problems, warnings

    # 必須キーの存在（行頭 key:）
    present = set(re.findall(r"(?m)^([A-Za-z_]+)\s*:", fm))
    for k in REQUIRED_KEYS:
        if k not in present:
            problems.append(f"frontmatter 必須キー欠落: {k}")

    # tags に literature
    if "literature" not in fm:
        problems.append("tags に 'literature' が含まれていない")

    # status: read
    mstat = re.search(r"(?m)^status\s*:\s*(\S+)", fm)
    if mstat and mstat.group(1).strip().strip('"\'') != "read":
        problems.append(f"status が read でない: {mstat.group(1).strip()}")

    # read_date が絶対日付
    mrd = re.search(r"(?m)^read_date\s*:\s*(.+)$", fm)
    if not mrd or not DATE_RE.search(mrd.group(1)):
        problems.append("read_date が絶対日付(YYYY-MM-DD)でない/空")

    # Wikilink（frontmatter か本文に1つ以上）
    if not WIKILINK_RE.search(text):
        problems.append("[[Wikilink]] が1つも無い（related_concepts/関連論文は Wikilink 必須）")

    # 引用箇所の数（ページ番号＋セクション/図表引用の合計）＝ソフト警告のみ（弾かない）
    n_cite = len(PAGE_CITE_RE.findall(body)) + len(SECTION_CITE_RE.findall(body))
    if n_cite < 5:
        warnings.append(f"引用箇所が少なめ（{n_cite}箇所・目安5〜10。ページ番号 or 節/図表で）")

    return problems, warnings


def main(argv: list) -> int:
    if len(argv) < 2:
        print("usage: python3 validate_note.py <note.md> [<note2.md> ...]")
        return 2
    any_bad = False
    for path in argv[1:]:
        problems, warnings = validate(path)
        if problems:
            any_bad = True
            print(f"❌ {os.path.basename(path)} — 規約違反 {len(problems)} 件（要修正）:")
            for p in problems:
                print(f"   - {p}")
        else:
            print(f"✅ {os.path.basename(path)} — 規約OK")
        for w in warnings:
            print(f"   ⚠️ {w}")
    return 1 if any_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
