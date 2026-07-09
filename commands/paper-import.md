---
description: _inbox.md で採用[x]した論文の PDF を確保し、全文を読んで Obsidian に規約準拠の深掘りメモを生成する
argument-hint: (引数なし。採用[x]済みを自動で拾う)
allowed-tools: Bash Read Write Edit
---

`_inbox.md` で採用（`[x]`）した論文を深掘りメモに取り込みます。**これが本システムの核心**。

### 手順

1. **準備**（PDF確保＋作業リスト出力。Slackタップも先に同期される）:
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}"
   ${PAPER_PYTHON:-python3} promote_check.py --prepare --config "${PAPER_CONFIG:-${CLAUDE_PLUGIN_ROOT}/config.local.yaml}"
   ```
   これで `/tmp/promote_worklist.json`（取り込み可能な論文の一覧）と、要手動DL（非OA）の件数が出る。

2. **深掘りメモ生成**: **paper-note-writer スキルに従って**、`/tmp/promote_worklist.json` の
   `status == "ready"` の各論文について:
   - `pdf_path` の PDF を**全文**読む。
   - vault の `CLAUDE.md`/`templates` があれば最優先で従い、無ければ paper-note-writer 内蔵の既定規約に従う。
   - `literature_notes/{筆頭著者姓}{年}_{KW}.md` を生成（frontmatter 必須キー・要約・主要主張・方法・結論・自分の研究との関連・**ページ番号付き引用5〜10**）。
   - concepts/ authors/ ノートを作成/更新し `[[Wikilink]]` と逆リンクを張る（マルチファイル・グラフ変更。省略しない）。
   - **保存前バリデーション**（必須キー・命名・Wikilink）を通す。`validate_note.py` があれば併用。

3. **取り込み済みへ移動**（1本ごと）:
   ```bash
   ${PAPER_PYTHON:-python3} promote_check.py --mark-done "<DOI>" --config "${PAPER_CONFIG:-${CLAUDE_PLUGIN_ROOT}/config.local.yaml}"
   ```

4. **報告**: 取り込んだ件数と、要手動DL（非OA でPDF未取得）の件数を伝える。非OA は `papers/` にPDFを置けば次回取り込めると案内する。

### 注意
- 1日の上限は config の `pipeline.promote_daily_limit`（既定5）。超過分は残す。
- `[x]` を付けただけでは取り込まれない（Obsidian の打ち消し線は装飾）。実際の取り込みはこのコマンド。
- 採用が1件も無ければ「チェック済みの論文はありません」と出る。先に `/paper-triage` → `_inbox.md` で `[x]`。
