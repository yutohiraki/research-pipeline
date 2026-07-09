# research_vault — Claude Code 運用ルール（スターター）

このファイルは Claude Code がこの Obsidian vault で論文メモを作るときに従う規約です。
`/paper-setup` が初回にあなたの vault へコピーします（既にある場合は上書きしません）。
**自分の研究に合わせて §7 の「研究フォーカス」だけは書き換えてください。**

---

## 1. フォルダ構成
```
（あなたのvault）/
├── literature_notes/   各論文のメモ（1論文=1ファイル）
├── papers/             PDF原本
├── concepts/           研究概念ノート（1概念=1ファイル）
├── authors/            著者ノート（1著者=1ファイル）
├── templates/          Markdownテンプレート（編集しない）
├── 📊 Research Dashboard.md   全体ダッシュボード（Dataview）
├── 🗂 論文ビュー（テーマ別）.md  テーマ別ビュー（Dataview）
└── CLAUDE.md           このファイル
```

## 2. ファイル命名規則
- 論文メモ: `{筆頭著者姓}{年}_{内容キーワード}.md`（例 `Parmentier2021_BrotulaReefSound.md`。姓のハイフンは除去）
- 概念ノート: 概念名そのまま（例 `Passive Acoustic Monitoring.md`）
- 著者ノート: `{First Last}.md`（例 `Ziqi Huang.md`）
- 既存ファイルがあれば**新規作成せず追記・更新**する

## 3. frontmatter 規約（Dataview でクエリするので厳守）
論文メモの frontmatter は必ず以下のキーを持つ:
```yaml
title:            # 引用符で囲む
authors:          # YAMLリスト（PDFから全員）
year:             # 数値
journal:
doi:
tags:             # 必ず literature を含む + 内容タグ
status:           # unread | reading | read
read_date:        # YYYY-MM-DD（絶対日付）
research_field:
related_concepts: # [[Wikilink]] のYAMLリスト
my_rating:        # n/5（空でよい）
```

## 4. 標準ワークフロー
### A. 論文を読み込んでメモ化
1. `papers/` のPDFを**全文**読む（先頭だけで済ませない）
2. `templates/literature_template.md` の構造で `literature_notes/` にメモ生成
3. 要約300字以内、主要主張3〜5点、方法・結果・結論、**引用箇所はページ番号付きで5〜10**
4. `status: read`、`read_date` に当日

### B. リンク・概念抽出（グラフ化）
1. メモから重要概念を抽出 → `concepts/` に無ければ新規作成（`templates/concept_template.md`）
2. `related_concepts` と本文を `[[ ]]` で結ぶ
3. 著者も `authors/` を作成・リンク
4. 概念ノートの「関連する論文」にこの論文を逆リンクで追記

### C. 関連論文リンクの規約（重要・リンク切れを作らない）
- **vault に既にある論文だけ `[[Wikilink]]`**（クリックで中身に飛べる）
- **未取り込みの引用文献は素の引用**にする（`[[ ]]` にしない）:
  `- 著者 (年), タイトル — 関連理由（本論 p.N）· [🔍検索](https://scholar.google.com/scholar?q=...)`

## 5. 守ること
- `templates/` は書き換えない。既存メモの本文を大きく削らない（追記中心）
- **推測で書誌情報を埋めない**。PDFから取れない項目は空欄
- 日付は常に絶対日付（YYYY-MM-DD）
- `related_concepts`・関連論文（vault実在分）は必ず `[[ ]]` Wikilink

## 6. 深掘りメモの「自分の研究との関連」の書き方
`## 自分の研究との関連` セクションは、まず §7 の研究フォーカスへの接続を具体的に書く。
該当が薄い論文は無理に結びつけず「直接の関連は低い」と正直に書く。

## 7. 研究フォーカス（← ここを自分の研究に書き換える）
> 例（PAM×魚類音響の研究者の場合）:
> 1. 魚類の音響による種同定
> 2. 既知魚類音のレファレンス収集
> 3. …
>
> ↑ を消して、あなたの研究テーマ・関心キーワードを箇条書きで書いてください。
> ここが深掘りメモの「自分の研究との関連」を書く基準になります。
