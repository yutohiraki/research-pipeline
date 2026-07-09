"""
inbox_writer.py
TRIAGE 出力: candidate 群を Obsidian `_inbox.md` に **クリック可能なチェックリスト**で描画する。

SPEC.md §3.2。Obsidian では表セル内のチェックボックスはクリックできず、`- [ ]`（タスク）だけが
クリック可能なので、各候補を1タスク行で描く。ユーザーは要る論文の `[ ]` を**ポチッと押すだけ**。

**蓄積方式（2026-06-12〜）**: 新着候補は上書きせず**日付つきで蓄積**し、`retention_days`（既定14日）
保持する。これにより数日チェックできなくても候補が消えない。期限切れの未チェック候補のみ自動で落ちる。
チェック済み(`[x]`)・取り込み済みは常に保持。

セクション:
- `## ✅ 取り込み待ち（チェック済み）` … チェックした未取り込み行
- `## 新着 YYYY-MM-DD`（複数日ぶん蓄積）   … 最新候補。古い日付は retention で自動削除
- `## 古典・高被引用`                       … 古典候補（テーマ別）。収集日(週1)に更新、それ以外は保持
- `## 取り込み済み`                         … 取り込み完了の記録（保持）
"""

from __future__ import annotations

import datetime
import json
import os
import re

from candidate import candidate_id, normalize_doi

HEADER = "# 📥 論文 Inbox"
INTRO = (
    "> **使い方は2つだけ**\n"
    "> - ✅ **要る** → チェックボックスを **`[x]`** にする → Claude Code で「**inboxの採用分を取り込んで**」と言う（全文を読んだ深掘りメモが `literature_notes/` に作られます・1日最大5件）。\n"
    "> - 🗑️ **二度と出したくない** → その行を下の **「🗑️ 二度と出さない」見出しの下へ移動**（ドラッグ／切り取り→貼り付け）。次回更新でDOI・タイトルごと永久除外され、消えます。\n"
    "> - どうでもいい論文は**放置でOK**。約2週間で自動的に消えます（Tasksプラグインの `-` はもう不要）。\n"
)
SEC_PENDING = "## ✅ 取り込み待ち（[x]にした・まだ未取り込み）"
SEC_DISMISS = "## 🗑️ 二度と出さない（ここへ移した行は永久に除外されます）"
SEC_DONE = "## 取り込み済み"
SEC_CLASSIC = "## 古典・高被引用"

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _esc(text: str) -> str:
    return (text or "").replace("\n", " ").replace("|", "/").strip()


def _doi_link(c) -> str:
    doi = normalize_doi(c.doi)
    if doi:
        return f"[doi](https://doi.org/{doi})"
    if c.url:
        return f"[link]({c.url})"
    return ""


def task_line(c, classic: bool = False) -> str:
    """1候補を1タスク行に。先頭は必ず `- [ ] `（Obsidianでクリック可能）。"""
    head = f"**[{c.relevance_score}]** {c.oa_mark} {_esc(c.title)}"
    meta = []
    if c.one_liner:
        meta.append(_esc(c.one_liner))
    who = " ".join(x for x in [c.first_author, str(c.year)] if x)
    if who:
        meta.append(who)
    if classic and c.cited_by_count:
        meta.append(f"{c.cited_by_count}cites")
    elif c.journal:
        meta.append(_esc(c.journal))
    link = _doi_link(c)
    line = f"- [ ] {head}"
    if meta:
        line += " — " + " · ".join(meta)
    if link:
        line += " · " + link
    return line


def _line_doi(line: str) -> str:
    m = re.search(r"doi\.org/([^\s\)\]]+)", line)
    return normalize_doi(m.group(1)) if m else ""


def _line_title(line: str) -> str:
    """タスク行/取り込み済み行からタイトル部分だけを取り出す（比較・重複排除用）。"""
    t = re.sub(r"^\s*[-*]\s*\[.\]\s*", "", line)   # "- [ ] " / "- [x] " 等
    t = re.sub(r"^\s*[-*]\s+", "", t)               # 取り込み済みの "- " 箇条書き
    t = re.sub(r"^\s*\d{4}-\d{2}-\d{2}\s+", "", t)  # 取り込み済み行頭の日付
    t = re.sub(r"\*\*\[\d+\]\*\*", "", t)           # **[score]**
    for ch in ("✅", "⛔", "🗑️", "❌"):
        t = t.replace(ch, "")
    t = re.split(r" — | · ", t)[0]
    return t.strip()


def _line_key(line: str) -> str:
    """行の一意キー（DOIがあれば doi:、無ければ title:ハッシュ）。candidate_id と一致。"""
    return candidate_id(_line_doi(line), _line_title(line))


def _line_keys(line: str) -> set:
    """行の**両方**のキー {doi:..., title:...} を返す。
    同一論文が「DOI付き」と「リンクのみ」で別々に載る事故を、タイトルキーで1本化する。"""
    ks = set()
    dk = candidate_id(_line_doi(line), "")
    if dk:
        ks.add(dk)
    tk = candidate_id("", _line_title(line))
    if tk:
        ks.add(tk)
    return ks


def _cand_keys(c) -> set:
    """candidate の {doi:..., title:...} 両キー。"""
    ks = set()
    dk = candidate_id(c.doi, "")
    if dk:
        ks.add(dk)
    tk = candidate_id("", c.title)
    if tk:
        ks.add(tk)
    return ks


def _filter_block(block: str, exclude: set) -> str:
    """ブロック内の“論文タスク行”のうち、キーが exclude に入るものを落とす（見出しは温存）。"""
    if not block:
        return block
    out = []
    for l in block.splitlines():
        st = l.strip()
        if (st.startswith("- [") or st.startswith("* [")) and (_line_keys(l) & exclude):
            continue
        out.append(l)
    return "\n".join(out).rstrip()


def _load_dismissed_keys() -> set:
    """dismissed.json の全キー（'doi:...' / 'title:...'）を集合で返す。"""
    try:
        ids = json.load(open(os.path.join(_PROJECT_DIR, "dismissed.json"), encoding="utf-8"))
    except Exception:
        ids = []
    return {i for i in ids if isinstance(i, str) and i}


def harvest_dismissed_from_inbox(existing: str) -> int:
    """「🗑️ 二度と出さない」見出しの下の行＋旧 `- [-]` 行を DOI/タイトルごと
    dismissed.json へ永久追記。追加件数を返す（DOIが無くてもタイトルで除外できる）。"""
    new = set()
    in_dismiss = False
    for l in (existing.splitlines() if existing else []):
        if l.startswith("## "):
            in_dismiss = l.startswith(SEC_DISMISS) or l.startswith("## 🗑️")
            continue
        st = l.strip()
        is_task = st.startswith("- [") or st.startswith("* [")
        # 🗑️ 見出しの下の“論文行”、または旧方式の `- [-]` を回収
        if (in_dismiss and is_task) or st.startswith("- [-]") or st.startswith("* [-]"):
            k = _line_key(l)
            if k:
                new.add(k)
    if not new:
        return 0
    path = os.path.join(_PROJECT_DIR, "dismissed.json")
    try:
        ids = json.load(open(path, encoding="utf-8"))
    except Exception:
        ids = []
    merged = set(ids) | new
    if len(merged) == len(ids):
        return 0
    json.dump(sorted(merged), open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return len(merged) - len(ids)


def _classic_block(classics) -> str:
    parts = [SEC_CLASSIC]
    if classics:
        themes = {}
        for c in classics:
            themes.setdefault(c.classic_theme or "その他", []).append(c)
        for theme, items in themes.items():
            parts.append(f"### {theme}")
            for c in sorted(items, key=lambda x: x.cited_by_count, reverse=True):
                parts.append(task_line(c, classic=True))
            parts.append("")
    else:
        parts.append("（古典なし）")
    return "\n".join(parts).rstrip()


def build_inbox(recent: list, classics: list, existing: str = "",
                date_str: str = "", retention_days: int = 14) -> str:
    date_str = date_str or datetime.date.today().isoformat()
    today = datetime.date.fromisoformat(date_str)
    dismissed = _load_dismissed_keys()

    # ── 既存inboxを走査 ──
    checked_raw = []             # [(key, line)] チェック済み（後で取込済/除外/重複を整理）
    backlog = []                 # 未チェック新着: (date, key, line)
    done_lines, classic_lines = [], []
    in_done = in_classic = in_dismiss = False
    sec_date = None
    for l in (existing.splitlines() if existing else []):
        if l.startswith("## "):
            in_done = l.startswith(SEC_DONE)
            in_classic = l.startswith(SEC_CLASSIC)
            in_dismiss = l.startswith(SEC_DISMISS) or l.startswith("## 🗑️")
            if l.startswith("## 新着"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", l)
                try:
                    sec_date = datetime.date.fromisoformat(m.group(1)) if m else today
                except Exception:
                    sec_date = today
            else:
                sec_date = None
            if in_done:
                done_lines = [l]
            if in_classic:
                classic_lines = [l]
            continue
        st = l.strip()
        # 🗑️ セクションの行は harvest 済み → 再描画しない（キーは dismissed に入っている）
        if in_dismiss:
            continue
        # 旧方式 `- [-]`（興味なし）：どこにあっても描画しない
        if st.startswith("- [-]") or st.startswith("* [-]"):
            continue
        # 取り込み済みセクションはそのまま保持
        if in_done:
            done_lines.append(l)
            continue
        # チェック済み `- [x]`：どのセクション（古典含む）でも「取り込み待ち」へ集約
        if st.startswith("- [x]") or st.startswith("- [X]"):
            checked_raw.append((_line_key(l), l))
            continue
        if in_classic:
            classic_lines.append(l)
            continue
        if st.startswith("- [ ]"):
            backlog.append((sec_date or today, _line_key(l), l))

    done_block = "\n".join(done_lines).rstrip() if done_lines else \
        f"{SEC_DONE}\n（取り込み完了後にここへ記録）"
    classic_block_existing = "\n".join(classic_lines).rstrip() if classic_lines else ""
    done_keys = set()
    for l in done_block.splitlines():
        done_keys |= _line_keys(l)

    # ── チェック済みの整理: 取り込み済み/除外済みを外し、重複を排除（自己修復）──
    checked, checked_keys = [], set()
    for _k, l in checked_raw:
        ks = _line_keys(l)
        if ks & (done_keys | dismissed):
            continue          # もう取り込んだ/除外した → 待ちには出さない
        if ks & checked_keys:
            continue          # 重複したチェック行
        checked_keys |= ks
        checked.append(l)

    # ── 重複・除外・期限切れの判定（DOI無しでもタイトルキーで効く）──
    seen = set(done_keys) | set(checked_keys) | set(dismissed)
    seen.discard("")
    cutoff = today - datetime.timedelta(days=retention_days)

    kept_backlog, aged = [], 0
    for d, _k, l in backlog:
        ks = _line_keys(l)
        if ks & seen:
            continue          # 重複・既出（別日の同一論文もここで1本化）
        if d < cutoff:
            aged += 1
            continue
        seen |= ks
        kept_backlog.append((d, l))

    # ── 本日の新着（recent）を追加（既出は除外）──
    new_lines = []
    for c in sorted(recent, key=lambda x: x.relevance_score, reverse=True):
        ks = _cand_keys(c)
        if ks & seen:
            continue
        new_lines.append(task_line(c))
        seen |= ks

    # ── 日付ごとにまとめる（本日＝新着＋本日ぶんの既存backlog）──
    bydate = {today: list(new_lines)}
    for d, l in kept_backlog:
        bydate.setdefault(d, []).append(l)

    # ── 描画 ──
    parts = [HEADER, "", INTRO, SEC_PENDING]
    parts.extend(checked if checked else
                 ["（まだありません。下の一覧で、要る論文のチェックボックスに `[x]` を付けてください）"])
    parts.append("")
    parts.append(SEC_DISMISS)
    parts.append("（いらない論文の行をこの見出しの下へ移動すると、次回更新で永久に消えます）")
    parts.append("")
    for d in sorted(bydate.keys(), reverse=True):
        parts.append(f"## 新着 {d.isoformat()}")
        parts.extend(bydate[d] if bydate[d] else ["（この日の新着なし）"])
        parts.append("")
    # 古典: 収集日(classics非空)は更新、それ以外は既存を保持。
    # どちらも「取り込み待ち/取り込み済み/除外」に既にある論文は落として重複を防ぐ。
    classic_exclude = set(done_keys) | set(checked_keys) | set(dismissed)
    classic_exclude.discard("")
    if classics:
        parts.append(_filter_block(_classic_block(classics), classic_exclude))
    elif classic_block_existing:
        parts.append(_filter_block(classic_block_existing, classic_exclude))
    else:
        parts.append(SEC_CLASSIC + "\n（古典なし）")
    parts.append("")
    parts.append(done_block.rstrip())
    parts.append("")
    if aged:
        parts.append(f"<!-- retention: 期限切れの未チェック候補 {aged} 件を削除（{retention_days}日経過） -->")
    return "\n".join(parts)


def write_inbox(path: str, recent: list, classics: list, date_str: str = "",
                retention_days: int = 14):
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = f.read()
    # 「🗑️ 二度と出さない」の行を永久除外へ確定（build前→以後の収集でも再出現しない）
    n_dismissed = harvest_dismissed_from_inbox(existing)
    if n_dismissed:
        print(f"🗑️ いらない論文 {n_dismissed} 件を永久除外に追加")
    text = build_inbox(recent, classics, existing=existing, date_str=date_str,
                       retention_days=retention_days)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


if __name__ == "__main__":
    import yaml
    from openalex_classic import fetch_classics
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mailto = cfg.get("unpaywall", {}).get("email", "")
    classics = fetch_classics(cfg.get("classic", {}), mailto=mailto)
    out = "/tmp/_inbox_tasks.md"
    write_inbox(out, recent=[], classics=classics)
    print(f"→ {out}")
