---
name: paper-note-writer
description: >
  採用した論文の PDF 全文を読み、Obsidian vault の規約に厳密準拠した深掘りメモ（literature_note
  ＋concepts/authors ノート＋[[Wikilink]]）を生成する。/paper-import から呼ばれる。
  「inbox の採用分を取り込んで」「この論文を深掘りメモにして」等のときに使う。
---

# paper-note-writer — 論文の深掘りメモ生成（Obsidian）

採用（`_inbox.md` でチェック `[x]`）された論文を、**PDF 全文を読んで** vault の規約通りの
深掘りメモにする。トリアージ段階の軽量サマリとは別物で、**ここが本システムの核心価値**。

> ⚠️ この作業は「対話セッションの Claude（あなた）」が実行主体。Python コードは PDF 確保と
> inbox 更新までしか行わない。メモ本文・概念/著者ノート・逆リンクの生成は**あなたが手で書く**。

---

## 2つの入口
- **(A) inbox 一括**: `_inbox.md` で `[x]` した論文をまとめて取り込む（下記「手順」）。`/paper-import` から。
- **(B) 単発・別プロジェクトから**: 「この論文（DOI/タイトル/手元PDF）を深掘り保存して」。この skill を
  **ユーザーレベルで入れておけばどのプロジェクトからでも**使える（`/plugin install` を user スコープ＋
  シェルに `export PAPER_CONFIG=<repo>/config.local.yaml` を設定して vault パスを解決）。手元PDFが無ければ:
  ```bash
  ${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/fetch_pdf.py" --doi "<DOI>"   # or --title "..."
  ```
  → PDFパスが返れば「手順3〜」へ。`MANUAL:` が返れば非OA/bot遮断で自動取得不可＝`papers/` に手動配置を依頼。
  取り込み前に **重複チェック**（`literature_notes/` に `{筆頭著者姓}{年}` があれば作らない）。
  ⚠️ **vault を関係ない論文で埋めない** — 保存価値をユーザーが判断してから作る。

## 手順

### 0. 準備（Python が済ませている前提。無ければ実行する）
作業リスト `/tmp/promote_worklist.json` を読む。無い／古い場合は先に:
```bash
${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/promote_check.py" --prepare --config "${PAPER_CONFIG:-config.local.yaml}"
```
worklist の各要素は store 非依存の dict:
`{doi, title, authors, year, journal, pdf_path, status}`。
`status == "ready"`（`pdf_path` あり）のものだけが取り込み対象。`pdf_path` が空のものは
**非OAで PDF 未取得**なので飛ばす（ユーザーが `papers/` に置いたら次回取り込める）。
1日の上限は config の `pipeline.promote_daily_limit`（既定5）。超過分は残す。

### 1. 規約の決定（優先順位を厳守）
1. **vault に `CLAUDE.md` があれば、それを最優先で読んで従う**（`pipeline.vault_dir/CLAUDE.md`）。
   命名・frontmatter・Wikilink・テンプレ・ワークフロー B/C はそのファイルが正。
2. vault に `templates/literature_template.md` 等があればその構造に合わせる。
3. どちらも無ければ、**本 skill 内蔵の既定規約（下記「内蔵既定規約」）** を使う。

vault CLAUDE.md と本 skill の規約が食い違う場合は **vault CLAUDE.md を優先**する
（配布先ごとに vault の運用が違うため。二重管理の事故を防ぐ）。

### 2. PDF 全文を読む
`pdf_path` の PDF を**全文**読む（先頭数ページで止めない）。長い場合はセクションごとに
読み進め、方法・結果の**具体的な数値**・限界・引用したい箇所を落とさない。

### 3. literature_note を生成
- 置き場所: `pipeline.vault_dir/literature_notes/`
- ファイル名: `{筆頭著者姓}{年}_{内容キーワード}.md`（例 `Parmentier2021_BrotulaReefSound.md`）。
  同名が既にあれば**新規作成せず追記・更新**。
- frontmatter（必須キーを全て。**推測で書誌を埋めない**。PDF から取れない項目は空欄）:
  `title / authors(YAMLリスト) / year / journal / doi / tags(必ず literature を含む) /
   status: read / read_date(当日YYYY-MM-DD) / research_field / related_concepts([[Wikilink]]のリスト) / my_rating(空)`
- 本文（vault テンプレの節に沿う）:
  - **要約** 300字以内（専門用語は残して平易に）
  - **主要な主張** 3〜5点
  - **方法**（実験設計・データ・モデル・評価指標）
  - **結論・知見**（主要な数値を含める）
  - **自分の研究との関連**（config の `user.research_context` の軸への接続を具体的に。
    該当が薄ければ無理に結びつけず「直接の関連は低い」と正直に書く）
  - **引用したい箇所** 5〜10箇所を**ページ番号付き**で
  - **関連論文**（重要・リンク切れを作らない）:
    - **vault に既にノートがある論文だけ `[[Wikilink]]`** にする（クリックで中身に飛べる）。
    - **まだ取り込んでいない引用文献は `[[ ]]` にしない**。素の引用にして、行き先のないリンクを作らない:
      `- 著者 (年), タイトル — 関連理由（本論の p.N で引用）· [🔍検索](https://scholar.google.com/scholar?q=著者+年+タイトル)`
      DOI が本文/参照リストから分かるなら検索リンクの代わりに `https://doi.org/…` を貼ってよい。
    - 迷ったら「vault にファイルが実在するか」で判断する。実在＝Wikilink、非実在＝素の引用＋リンク。

### 4. マルチファイル・グラフ変更（vault CLAUDE.md ワークフロー B/C。省略しない）
depth の核心はここ。単一メモで終わらせない:
1. 本文から重要概念を抽出 → `concepts/` に無ければ概念ノート新規作成（テンプレ準拠）。
2. `related_concepts` と本文の概念を `[[ ]]` で結ぶ。
3. 著者について `authors/` ノートを作成しリンク。
4. 各概念ノートの「関連する論文」に、この論文への**逆リンク**を追記。

### 5. 保存前バリデーション（vault を汚さないための自己検査）
メモを書いた後、保存前に自分でチェックし、欠けていれば直す:
- [ ] ファイル名が `{筆頭著者姓}{年}_{キーワード}.md` パターンに一致
- [ ] frontmatter に必須キーが全て存在（`title/authors/year/journal/doi/tags/status/read_date/research_field/related_concepts/my_rating`）
- [ ] `tags` に `literature` を含む
- [ ] `status: read`、`read_date` が当日の絶対日付（YYYY-MM-DD）
- [ ] `related_concepts` と本文の関連が `[[Wikilink]]` になっている（手動リンク禁止）
- [ ] 「引用したい箇所」にページ番号付きが5〜10箇所
- [ ] 推測で埋めた書誌情報が無い（取れない項目は空欄のまま）

補助スクリプトがあれば併用してよい（無くてもよい・目視でも可）:
```bash
${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/validate_note.py" "path/to/new_note.md" || echo "要修正"
```

### 6. 取り込み済みへ移動
1本仕上げるごとに、その論文を「取り込み済み」に移す:
```bash
${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/promote_check.py" --mark-done "<DOI>" --config "${PAPER_CONFIG:-config.local.yaml}"
```
DOI が無い論文はタイトルでも可（`--mark-done "論文タイトル"`）。

### 7. 報告
取り込んだ件数／要手動DL（非OA）で飛ばした件数を簡潔に報告する。

---

## 内蔵既定規約（vault に CLAUDE.md / templates が無い後輩向けフォールバック）

配布先の vault に規約ファイルが無くても、この skill だけで同じ品質を出すための既定。
上の「規約の決定」で vault 側が見つかればそちらが優先。

### literature_note（`literature_notes/{筆頭著者姓}{年}_{KW}.md`）
```markdown
---
title: "＜論文タイトル＞"
authors:
  - ＜著者1＞
  - ＜著者2＞
year: ＜年＞
journal: ＜誌名＞
doi: ＜DOI＞
tags:
  - literature
  - ＜内容タグ＞
status: read
read_date: ＜当日 YYYY-MM-DD＞
research_field: ＜分野＞
related_concepts:
  - "[[＜概念名＞]]"
my_rating:
---

# ＜タイトル＞

## 書誌情報
- **著者**: 
- **発表年**: 
- **掲載誌・出版社**: 
- **DOI**: 

## 要約
＜300字以内＞

## 主要な主張
1. …

## 方法
…

## 結論・知見
…

## 自分の研究との関連
…

## 引用したい箇所
- (p.＜頁＞) 「＜引用＞」

## 関連論文
- ＜vault にある論文＞ → [[著者年_キーワード]]
- ＜未取り込みの引用文献＞ → 著者 (年), タイトル — 関連理由（本論 p.N）· [🔍検索](https://scholar.google.com/scholar?q=...)

## メモ・疑問
```

### concept ノート（`concepts/＜概念名＞.md`）
frontmatter: `type: concept / domain / first_encountered / related_concepts / key_papers / tags:[concept]`。
節: 定義 / 起源・歴史 / 関連する論文（逆リンクを追記）/ 関連する概念 / 議論されている論点 / 未解決の問い。

### author ノート（`authors/＜First Last＞.md`）
frontmatter: `type: author / affiliation / research_field / tags:[author]`。
節: 所属・経歴 / 主要研究テーマ / 重要な論文（この論文へリンク）/ 関連著者。

### 守ること
- `templates/` は書き換えない。既存メモの本文を大きく削らない（追記中心）。
- 推測で書誌情報を埋めない。PDF から取れない項目は空欄のまま。
- 日付は常に絶対日付（YYYY-MM-DD）。
- `related_concepts`・関連論文は必ず `[[Wikilink]]`（リンク先が未作成でも貼ってよい）。

---

## 他のAI環境の後輩について（正直な線引き）
この skill は **Claude Code（ファイルを読み書きできる対話エージェント）** 前提。
ChatGPT/Gemini の web しか無い後輩は、この skill の**マルチファイル生成を実行できない**
（web LLM にはファイルを書く実行主体が無い）。その場合の深掘りは **copypaste 半自動**
（`/paper-import --export-prompt` で規約入りプロンプトを書き出し→ web に貼付→結果を貼り戻し）
で、**単一メモに劣化**する（concepts/authors/逆リンクのグラフは出ない）。詳細は SETUP.md。
