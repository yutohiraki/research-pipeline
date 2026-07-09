# DISTRIBUTION — 配布設計（確定版）

最終更新: 2026-07-08。このファイルは [HANDOFF.md](HANDOFF.md) §4 の「skill化 vs アプリ化」検討を、**ユーザーの回答で確定した前提に基づいて具体化した実装計画の正**。
運用ルールの正は [CLAUDE.md](CLAUDE.md)、仕様の正は [SPEC.md](SPEC.md)、これらと矛盾する配布固有の判断は本ファイルを優先する。

---

## 0. 確定した前提（2026-07-08 ユーザー回答）

- **対象** = 研究室の後輩。**第一対象 = Claude Code を使う後輩**。使えない後輩は **GPT/Gemini で代替**できる機構にしたい。
- **フェーズ順序** = 「**Claude Code ユーザー first → その後 他AI(GPT/Gemini)ユーザーへ拡張**」。
- **メモ先** = **Obsidian 優先**（後輩に易しい）。ただし一部後輩は既に **Notion** 運用中 → Notion も選べるように。
- **核心価値** = 「深掘りメモが各自の自分のストアに**規約通り貯まる**」＋「可能な限り**無料・ローカル**」。
- **実装方針** = いきなり SaaS 化しない。**既存 Python 資産を再パッケージ**。後戻り可能に。

---

## 1. 結論（推奨アーキテクチャ）

**research-pipeline 自身を Claude Code Plugin 化する**（self-marketplace 構成）。既存 `.py` は**無改造**のまま、薄い `commands/` ラッパと核心 `skills/` 2本、対話 wizard で再パッケージする。config は `PAPER_CONFIG` 環境変数で差し替え、個人依存は `config.local.yaml`（git 管理外）に集約する。

第一対象は **Claude Code × Obsidian** の後輩。採点エンジン（groq/ollama/rule）と note-store（obsidian/notion）は**完全直交**に保ち、「Claude Code first → 他AI拡張」を**後戻りなく**伸ばせる境界を Phase1 の時点で確保する（ただし器だけの抽象化は作らない＝過剰設計回避）。

### ⚠️ 最重要の現実（隠さず線引きする）

**深掘りメモを生成する Python コードは存在しない。** `literature_notes/*.md` を書く `.py` はゼロ、`/tmp/promote_worklist.json` を読む consumer もゼロ。深掘りは **100% 対話 Claude エージェント**が PDF と vault の CLAUDE.md を読み、**複数ファイル**（literature_note＋concepts/＋authors/＋逆リンク＋ページ番号付き引用）を手で書く即興作業で成立している。つまり:

- **核心価値「規約通り貯まる」はコードで保証されておらず、エージェントの実行に依存する。**
- **エージェントが居ない環境（GPT/Gemini の web）には「ファイルを読み書きする実行主体」そのものが無い。**

→ 帰結: **Claude Code 後輩以外への配布では、深掘りは非対称に劣化する**。これを最初から正直に明示する（期待値管理）。詳細は §4。

---

## 2. 3レーン・モデル（採点エンジン × note-store × 深掘り実行主体）

| レーン | 採点 | 深掘りメモ生成 | note-store | フェーズ | 深掘り品質 |
|---|---|---|---|---|---|
| **① Claude Code × Obsidian**（本命） | Groq無料枠 | 対話 Claude が PDF全文→規約準拠**マルチファイル**生成 | Obsidian vault | **Phase1** | ◎ フル（グラフ込み） |
| **② Claude Code × Notion** | Groq無料枠 | 対話 Claude が Notion API 経由 | Notion（候補ミラー→深掘り） | Phase2/3 | ○→△ |
| **③ GPT/Gemini × Obsidian** | 各自のGPT/Gemini | **copypaste 半自動**（web に貼る）or 研究室Claudeに remote-control | Obsidian vault | Phase2 | △ 単一メモに劣化 |

**直交性が鍵**: 採点エンジン（`scoring_engine`）と note-store（`note_store`）と深掘り実行主体は独立して差し替わる。だから ① を出荷しても ②③ を後付けできる。

---

## 3. フェーズ計画

### Phase 0 — 配布の前提条件（最優先・独立作業）
現状 **git リポジトリですらない**＋`config.yaml` に生キー約20行直書き。ここを整えないと配布は成立しない。

- [x] `git init`＋初回コミット（**2026-07-09 完了**・commit `7bb0506`「Initial: research-paper-triage plugin (Phase1)」48ファイル）。コミット前に追跡対象を秘匿スキャン（gsk_/xoxb-/ntn_/署名secret/pull_secret 等ゼロ）＋ `.gitignore` に `_backup/`/`.Rhistory`/`.claude/settings.local.json` 追加。フレッシュクローン検証で「後輩が受け取る内容＝秘匿ゼロ・構造完備・JSON有効」を確認。**→ Phase0 完了。**
- [x] `.gitignore` 作成（config.yaml / config.local.yaml / credentials.json / token.json / dismissed.json / promote_state.json / *.log / README.html / __pycache__）
- [x] `config.example.yaml` 作成（実キーを空＋コメント化、`user.research_context`・`classic.queries`・vaultパスを記入例プレースホルダに一般化）
- [x] 旧 as-is 資産の `_legacy/` 隔離（**2026-07-09 完了**・削除ではなく隔離）。本線未参照を Python で厳密監査してから移動: `main.py` / `gemini_summarizer.py` / `sheets_writer.py` / `slack_notifier.py` / `notion_enricher.py` / `notion_to_paperpile.py` / `paperpile_importer.py` / 旧 `com.research-pipeline.plist` / 旧 `com.research-pipeline.promote.plist`＋`_legacy/README.md`。**残した**もの: `paper_fetcher.py`(promoteが使用)・`notion_writer.py`(Phase2 Notionアダプタ)・`gmail_fetcher.py`・`score_assist.py`。移動後に本線14モジュール import 回帰OK。

### Phase 1 — Claude Code × Obsidian（今日出荷ライン）
- [ ] `.claude-plugin/{plugin.json, marketplace.json}`（self-marketplace）
- [ ] `commands/{paper-setup, paper-triage, paper-import, paper-doctor}.md`（既存 `.py` を `${CLAUDE_PLUGIN_ROOT}`＋`PAPER_CONFIG` 経由で叩く薄いラッパ）
- [ ] `skills/paper-pipeline-setup/SKILL.md`（wizard。必須3問＝Groqキー／研究テーマ／Obsidian vaultパス）
- [ ] `skills/paper-note-writer/SKILL.md`（**核心**。worklist＋PDF全文→vault規約準拠マルチファイル生成。**vault CLAUDE.md があれば最優先で読む**、無ければ skill 内蔵の既定規約）
- [ ] **保存前バリデーション**（frontmatter 必須キー／命名 `{筆頭著者姓}{年}_{KW}.md`／`[[Wikilink]]` 欠落チェック＝vault 汚染防止）
- [ ] note-store=obsidian のみ実装。Slack/Cloudflare は `slack.enabled=false` 既定。採点は groq/ollama/rule のみ（GPT/Gemini は config にコメント境界だけ）

### Phase 2 — GPT/Gemini 拡張＋Notion 候補ミラー
- [ ] 採点に **OpenAI互換**（GPT／Gemini の OpenAI互換パス）を `_run_openai(prompt, cfg)` 1本追加＋`score_all` に `elif`。※Gemini ネイティブ REST(`generateContent`) は `response_format`/`choices[]` が無く別実装＝「30行コピペ」は Gemini には誤り。まず OpenAI互換のみ先行。
- [ ] **GPT/Gemini 後輩の深掘り = copypaste 半自動**: `/paper-import --export-prompt` で worklist＋PDF全文＋規約＋frontmatter雛形を1つの `.md` に書き出す → 後輩が web LLM に貼付 → 生成物を貼り戻す → `--collect` で保存前バリデーションを通して保存。**限界を SETUP に明記**（PDF全文のトークン超過／concept・author グラフは出ず単一メモに劣化／5件で約25手と重い）。
- [ ] **Notion 候補ミラー**: 既存 `notion_writer.add_paper_to_notion`（`is_duplicate`＋プロパティ書込は完成）をトリアージ層のミラーとして有効化。`note_store=notion` の分岐は inbox 描画側にだけ。

### Phase 3 — Notion 深掘り parity ほか（需要確認後）
- [ ] Notion 深掘り parity は「既存120行流用」では届かず**新規開発4点**が必要と認識する: ①page children ブロック生成（rich_text 2000字上限に本文は収まらない）②深掘りフィールド（summary/methods/…）の供給元＝結局エージェント深掘り③Notion版規約の策定④author/concept relation 解決。やっても Obsidian のグラフ価値と完全 parity にはならない。
- [ ] `engines/` 3ファクトリ抽象は **2人目の実需が出てから**（それまで直接呼びで後戻り可能）。
- [ ] 従量 API 自動深掘り（`generation:api`）は無料 ethos と衝突＋単発呼び出しでグラフ副作用を出せず**既定では作らない**。明示オプトイン要望が出た時のみ。
- [ ] marketplace 公開（研究室内 git 限定 → public）は secrets 完全分離・`_legacy` 撤去・maintainer 確定が前提。

---

## 4. GPT/Gemini 後輩への正直な線引き（本命の設計判断）

- **採点は完全代替できる**（各自の GPT/Gemini キー）。`_rule_based` が常に先に走るので鍵不在でも全件0にはならない。
- **深掘りは3択、優先順で正直に提示する**:
  1. **最推奨=copypaste 半自動（無料）**: グラフ副作用（concepts/authors/逆リンク）は出ず**単一メモに劣化**。手数も重い。それでも「規約通りの1メモ」は保存前バリデーションで担保。
  2. **最も確実=研究室の Claude 保有者に remote-control で頼む**: 品質最高だが自立配布にならない（Claude 保有者がボトルネック）。
  3. **従量 API 自動=Phase3 保留**: 無料 ethos 衝突＋単発呼び出しでグラフ副作用不能＝作る価値が薄い。
- **結論**: GPT/Gemini 後輩には「**採点は自分のAIで・深掘りは copypaste で単一メモ（グラフは諦める）、グラフまで欲しければ研究室 Claude に remote-control**」を SETUP で隠さず明記する。

## 4b. Notion 後輩への正直な線引き

- **候補ミラーは即・低コスト**（`is_duplicate`＋プロパティ書込は完成済み）。
- **深掘り parity は劣化版**（本文をトグルブロックに流すだけ、concept/author グラフは無し）。Obsidian の Dataview/Wikilink 網とは完全 parity にならない。→ だからこそ「メモ先は Obsidian 優先」が正しい。Notion は既存 Notion 運用者の救済策。

---

## 5. 差し替え境界（最終設計）

- **採点エンジン境界（既存・追加最小）**: 入口 `triage.score_all(candidates, cfg, research_context, themes)`。切替 `config.scoring_engine: groq|ollama|claude|rule`（Phase1）＋`openai|gemini`（Phase2）。`_build_prompt`/`_parse_json_array`/`_apply_results`/`_rule_based` は全エンジン共有＝改修不要。
- **note-store 境界（新設不要）**: `promote_check.prepare()` の `/tmp/promote_worklist.json` は**既に store 非依存**（`{doi,title,authors,year,journal,pdf_path,status}`）。分岐は `skills/paper-note-writer` 内（obsidian＝Phase1完成／notion＝Phase3）。切替 `config.note_store: obsidian|notion`。
- **深掘り生成境界（コード保証ゼロを明示）**: 誰が `literature_notes/*.md` を書くか。(1)claude_agent＝現状・Phase1 (2)copypaste＝Phase2 (3)api＝Phase3保留。入力契約は worklist.json 形式で固定。
- **config パス境界**: `PAPER_CONFIG` で config 実体差し替え（既存 `.py` は全て `--config` を受けるので追加コード不要）。⚠️ `promote_state.json`/`dismissed.json` が `__file__` 相対のため Phase1 は「**1人1clone**」前提を README に明示。

---

## 6. Plugin 構造

```
research-pipeline/                     # 既存ディレクトリ = プラグインルート（Phase0 で git init）
├── .claude-plugin/
│   ├── plugin.json                    # name: research-paper-triage。commands・skills 自動検出
│   └── marketplace.json               # self-marketplace
├── commands/
│   ├── paper-setup.md                 # → skills/paper-pipeline-setup 起動
│   ├── paper-triage.md                # python3 "${CLAUDE_PLUGIN_ROOT}/triage_main.py" --config "${PAPER_CONFIG:-...}"
│   ├── paper-import.md                # promote_check --prepare → worklist読解 → paper-note-writer → --mark-done
│   └── paper-doctor.md                # 依存/キー疎通/vault到達/書込テストの健診
├── skills/
│   ├── paper-pipeline-setup/SKILL.md  # ★wizard
│   └── paper-note-writer/SKILL.md     # ★核心: 規約準拠マルチファイル生成＋保存前バリデーション
├── (既存 .py 群: triage.py candidate.py ingest_recent.py openalex_classic.py
│    inbox_writer.py triage_main.py promote_check.py — 無改造で再利用)
├── paper_fetcher.py                   # ⚠️本線が fetch_unpaywall_pdf_url を使用＝残す
├── notify_slack_dm.py slack_queue.py cloudflare/   # 任意(Phase1は slack.enabled=false)
├── notion_writer.py                   # 旧120行・Phase2ミラー/Phase3深掘りの土台
├── config.example.yaml                # ★新規: キー剥がしテンプレ（追跡対象）
├── config.local.yaml                  # 各自の秘匿設定（.gitignore・追跡外）
├── .gitignore                         # ★新規
├── README.md / SETUP.md               # 3経路を書き分け
└── _legacy/                           # 旧as-is隔離（paper_fetcher は除く）
```

---

## 7. ユーザーに確認すべき分岐（§8 で回答待ち）

1. **深掘り品質はコード保証ゼロ・対話 Claude 依存という事実を受け入れ、GPT/Gemini 後輩には「深掘りが劣化する」と最初から正直に線引きする方針でよいか。**
2. **GPT/Gemini 後輩の深掘り**を copypaste 手貼り（無料・単一メモ劣化）で妥協するか、従量 API 自動化まで踏み込むか（＝従量課金を払ってでも自動化したい後輩が実在するか）。
3. **config の置き場所**: 各 clone 内 `config.local.yaml`（今日出荷・1人1clone明示）か、`~/.research-pipeline/config.yaml` ホーム集約（複数マシンに強いが状態ファイルの小改修が要る）か。
4. **配布チャネル**: 研究室内 git（private/共有ドライブ）限定か、public marketplace まで出すか。

## 8. 次の具体ステップ（順序）

1. `git init` → `.gitignore` 済 → `config.example.yaml` 済 → 秘匿ファイル untracked を目視確認して初回コミット
2. 旧 as-is を `_legacy/` へ（paper_fetcher を除く）
3. `.claude-plugin/` ＋ `commands/` 4本を薄いラッパで
4. `skills/paper-note-writer/SKILL.md`（規約内包＋保存前バリデーション）
5. `skills/paper-pipeline-setup/SKILL.md`（必須3問 wizard）
6. オーナー環境で in-place スモークテスト（既定 groq/claude_agent/obsidian が退行しないこと）
7. Claude Code 後輩1人に配って `git clone → /paper-setup → 回る`まで実地検証（Phase1 受け入れ基準）

## 9. 追記（2026-07-09）: 配布物に反映済みの改善

実運用で見つかった課題を配布物にも一般化して反映済み:
- **PDF取得の底上げ**（`promote_check.py`）: OpenAlex/Unpaywall がPDF直リンクでなくランディングHTMLを返す問題に対し、`citation_pdf_url` メタタグ追跡＋ブラウザUAを追加（PLOS/arXiv 等の行儀の良いOA出版社は自動取得可に）。有料誌・MDPI/Zenodo/HAL の強い遮断は突破不可＝手動DLは残る。
- **`fetch_pdf.py`（新規）**: DOI/タイトル→OA PDFを `papers/` に取得する単体ツール。`PAPER_CONFIG`→`config.local.yaml`→`config.yaml` の順で config 解決。単発・別プロジェクト取り込みに使う。
- **深掘りメモの関連論文リンク規約**（`skills/paper-note-writer`）: **vaultに実在する論文だけ `[[Wikilink]]`、未取り込みの引用文献は素の引用＋🔍検索/DOIリンク**にする（「クリックしたら空」の未解決リンク量産を防止）。`validate_note.py` は命名・frontmatter・Wikilink欠落をハード判定、引用数はソフト警告。
- **別プロジェクトからの取り込み（全プロジェクト共通）**: プラグインを user スコープで入れ、シェルに `export PAPER_CONFIG=<repo>/config.local.yaml` を設定すると、`paper-note-writer` skill がどのプロジェクトからでも「この論文を深掘り保存して」で使える。手順は SETUP.md §6。**無差別取り込み防止**（vaultを関係ない論文で埋めない）を skill に内包。
- **PDF自動先取り（任意）**: `com.research-pipeline.prefetch.plist.template`（プレースホルダ版）を追加。`promote_check.py --prepare`（LLMなし・非課金）を日中数回走らせ、✅済み論文のOA PDFを先取り→取り込み時の往復を削減。SETUP.md §5。
- **Gmail取得リトライ**（`ingest_recent.py`）: IMAP本文フェッチの瞬断(Broken pipe)を最大3回リトライ（認証エラーは即諦め）。`gmail.fetch_retries`（既定2）。一発の瞬断で「空の一日」になる事故を防止。
- ⚠️ オーナー個人の `~/.claude/skills/paper-note-writer/`（絶対パス直書き）は**個人用**で配布対象外。後輩は上記の user スコープ・プラグイン経由を使う。
- **Slack ぽちぽちの研究室共有モデル対応**（`cloudflare/worker.js` ＋ `slack_queue.py`）: Worker の KV キューを **SlackユーザーIDごと**に分割（`q:{kind}:{userID}`）、pull は `?user=<自分のメンバーID>` で自分のキューだけ取得。→ **管理者が Worker を1個立てれば、後輩は Cloudflare/Slackアプリ不要で config に共有値＋自分のIDを貼るだけ**でぽちぽち選別が使える。単一ユーザ運用とも後方互換（旧デプロイのWorkerは user パラメータを無視して従来動作）。手順は `cloudflare/SETUP.md`（管理者1回／後輩貼るだけ に刷新）。
- **最新論文の入口を Gmail 非依存に**（`openalex_classic.py` に `fetch_recents`＋`triage_main` で合流）: `classic.queries` のキーワードで OpenAlex から「最近の論文」も取得（発行日降順・直近days日、429回避の小休止付き）。→ **後輩は Scholar/WoS アラートを設定しなくても、`/paper-setup` のキーワードだけで最新が毎日集まる**。Gmail は任意の追加ソースに格下げ。`config: recent.{enabled,days,per_query}`（既定 enabled=true、queries 省略時は classic.queries 流用）。実測: Gmail 63＋OpenAlex最新36→合流83。
- **旧 as-is の `_legacy/` 隔離＋README一般化 完了**（Phase0/1 のこの2項目を消化）: 本線未参照を Python 監査 → 7モジュール＋旧plist2つを `_legacy/`（＋`_legacy/README.md`）へ。`paper_fetcher`/`notion_writer`/`gmail_fetcher`/`score_assist` は直下維持。README.md は個人パス/実キー除去・SETUP.md 誘導・現構成のファイル表に刷新。CLAUDE.md §4 の旧実行例も修正。移動後 本線 import 回帰OK。**残る Phase0 = `git init`＋初回コミット（秘匿 untracked 確認）**。
