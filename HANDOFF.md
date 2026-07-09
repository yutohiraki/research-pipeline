# HANDOFF — 引き継ぎ資料（次セッション用）

最終更新: 2026-07-08。このファイルは「次の新しいセッション」で、**現状を素早く把握し、"他者に配る（skill化 or アプリ化）" を決める**ための資料。
運用ルールの正は [CLAUDE.md](CLAUDE.md)、仕様の正は [SPEC.md](SPEC.md)。

---

## 0. 30秒サマリ

論文を毎朝自動収集→Groq(無料)で関連度採点＋日本語要約→Obsidian の `_inbox.md` に一覧→**スマホの Slack でポチポチ選別**（Cloudflare Worker 経由・Mac が寝ていても拾う）→「取り込んで」で **Claude が PDF全文を読んで深掘りメモを vault に生成**。
**有料API課金ゼロ**（採点=Groq無料枠、深掘り=Claude サブスク内）。個人（研究者本人＝オーナー）の Mac + Obsidian vault + Android 前提で完成・稼働中。

次にやりたいこと: **これを他の研究者に配りたい。skill 化 or アプリ化を決める。**

---

## 1. このセッション(2026-07-06〜08)でやったこと（changelog）

1. **要約バグの根治**（`triage.py`）: Groq が `response_format=json_object` で配列を包むため、想定外形状だとバッチ丸ごと適用に失敗し「【自動・要LLM】」プレースホルダが inbox に漏れていた。→ パース堅牢化（任意ラッパーキー/id辞書対応）＋ id/並び順フォールバック＋**取りこぼしは1件ずつ自動再試行**＋プロンプト具体化。フォールバック文言を `（自動分類・要約保留）` に。
2. **重複ゼロ化＋「いらない」刷新**（`inbox_writer.py`）: 重複排除を **DOI＋タイトルの両キー**に（DOI無しの同一論文が別日に再掲する事故を解消）。Obsidian Tasks の `[-]` 方式は壊れやすく廃止 → **`## 🗑️ 二度と出さない` に行を移す**方式（DOI無しでもタイトルで永久除外）。取り込み済み/除外済みの `[x]` は待ちから自動で消える（自己修復）。古典も待ち/済みと重複しないよう除外。
3. **ライブ `_inbox.md` の掃除**: 重複除去・新レイアウト化・【自動・要LLM】32件を Groq で再要約（スコアも是正: 陸上植物eDNA 79→20 等）。
4. **本命8本を実際に取り込み**（`literature_notes/` に深掘りメモ生成→取り込み済みへ）: Anggawangsa(マグロ音響)/Kasmi(ヒラメeDNA qPCR)/Boulais(幼魚×音響再生)/Böttner(HydroMoth校正)/Dulo(漏洩PAM)/**Parmentier(Brotula不明礁音→種同定=本命⭐)**/Clippele(PAM×洋上風力)/Scheuerman(深海魚の分類解像度)。
5. **配信レイヤの設計確定＝Remote Control 版**（SPEC.md §9）: 深掘りはスマホ→`claude remote-control`→Mac（サブスク内・無料・vaultローカル）。従量課金は不採用。クラウド版(GitHub化)は非OA本命PDFが取れず不採用。
6. **Slack 通知の刷新**（`notify_slack_dm.py`）: 片方向ダイジェスト（関連度順・要約・DOIリンク）＋**ボタン付き(✅取り込む/🗑️いらない)**。
7. **Slack ぽちぽち実装＆動作確認**（`cloudflare/worker.js` + `slack_queue.py`）: タップ→Worker(署名検証→KV→メッセージ更新)→Mac が取得して inbox 反映（✅→[x] / 🗑️→dismissed）。**エンドツーエンドでテスト成功**。Cloudflare error 1010 対策で pull にブラウザUA付与。
8. **ドキュメント整理**: README を現行に全面刷新、CLAUDE.md §7 に配信レイヤ追記、SPEC.md §9 実装済み反映、本 HANDOFF 作成。

---

## 2. 現状アーキテクチャ（as-built）

```
毎朝8:00 (launchd: com.research-pipeline.triage.plist)  ── triage_main.py
   ├ slack_queue.sync_inbox : 前日までの Slack タップを反映（✅→[x] / 🗑️→dismissed）
   ├ ingest_recent.py       : Gmail(IMAP)→OpenAlex 正規化（著者/年/誌/OA/abstract）
   ├ openalex_classic.py    : 高被引用の古典（週1/月曜, 4テーマ）
   ├ triage.py              : 関連度採点＋日本語要約（Groq無料枠→Ollama→ルールベース）
   ├ inbox_writer.py        : _inbox.md をチェックリストで更新（🗑️除外・重複排除・retention）
   └ notify_slack_dm.py     : Slack DM 通知（interactive:true でボタン付き）

スマホ ── Slack で ✅/🗑️ タップ
   └ cloudflare/worker.js (無料・常時起動) : 署名検証→KVキュー→メッセージ更新（Macが寝てても拾う）

取り込み ── 「inboxの◯◯取り込んで」（Mac or スマホ→claude remote-control）
   └ promote_check.py : slack_queue同期 → PDF確保(手持ち照合+OA DL) → [対話ClaudeがPDF全文読解]
                         → literature_notes/ に深掘りメモ＋[[Wikilink]] → mark-done で取り込み済みへ
```

連携先 vault: `/Users/tonn/Documents/research_vault`（`literature_notes/` `papers/` `concepts/` `authors/` ＋独自 CLAUDE.md 規約）。

**主要ファイルは [README.md](README.md) の「主要ファイル」表を参照。**

---

## 3. 動くもの / 保留 / 既知の限界

**動く（確認済み）**
- 収集→採点→要約→inbox更新→Slack通知の毎朝フロー（Groq 32/32バッチ等で稼働）
- Slack ぽちぽち: タップ→Worker→Mac反映（E2Eテスト成功）
- 深掘り取り込み: PDF全文→規約準拠メモ（本セッションで計8本実証）

**保留 / 要ユーザー作業**
- `pmset repeat wakeorpoweron ...` （朝トリアージのスリープ対策・任意）
- Slack digest 件数（`digest_recent/classic`）の好み調整
- 取り込み待ち27件の大半は**非OAでPDF未取得**（＝消えてない・PDF入手待ち）

**既知の限界（配布時に効く）**
- **非OA(有料)論文のPDFは自動取得不可** → 本命ほど手動DLが要る。これは配布形態に依らず残る本質的制約。
- **深掘りの質＝Claude依存**（Opus/Sonnet 必須。Groqドラフトは品質不足で不採用）。無料で回すには「対話セッション（Remote Control）」が前提＝**各ユーザーが Claude Code サブスクを持つ**必要。
- **ハードコード多数**（配布前に要修正・§5）: 絶対パス `/Users/tonn/...`、python 実体 `/Users/tonn/matlab_pyenv312/bin/python3`、vault パス、`config.yaml` に実キー、`user.research_context` が本人固有。

---

## 4. 配布方針の検討: skill化 vs アプリ化（← 次セッションの本題）

### まず決める2つの前提
- **Q1: "みんな" とは誰？** (a) Claude Code を使う（or 使ってよい）研究者 か、(b) 非技術者含む一般の研究者 か。→ ここで最適解がほぼ決まる。
- **Q2: Obsidian 前提を維持するか？** 本システムの核心価値は「**深掘りメモが自分の Obsidian vault に規約通り貯まる**」こと。これを維持するなら手元実行（skill/plugin）が自然。手放すなら別プロダクト（アプリ）になる。

### 選択肢の比較

| 観点 | A. Claude Code **Skill/Plugin** | B. **Webアプリ/SaaS** | C. **Obsidian プラグイン** |
|---|---|---|---|
| 対象 | Claude Code ユーザー（研究者） | 誰でも（非技術者含む） | Obsidian ユーザー |
| Obsidian連携(核心価値) | ◎ 手元で vault に直接生成 | △ 別UI or 要プラグイン | ◎ vault ネイティブ |
| 深掘りの推論費用 | ◎ 各自の Claude サブスク内(実質無料) | ✕ 事業側が従量負担 or ユーザー課金 | △ 各自のAPIキー(従量) |
| 収集(Gmail)＋通知(Slack) | 各自セットアップ（wizardで軽減可） | サービス側が集約(OAuth) | プラグイン＋各自キー |
| 実装コスト | **小〜中**（既存資産を再パッケージ） | **大**（認証/マルチテナント/ホスティング/推論費） | 中（TS/plugin＋バックエンド） |
| 配布 | plugin marketplace / git | 公開URL | Obsidian community plugins |
| 原本ethos(無料/ローカル/プライベート)との整合 | ◎ | ✕（クラウド・課金前提に転換） | ○ |

### 所感（決定ではなく叩き台）
- **Q1=(a) Claude Codeユーザー狙いなら → A の Claude Code Plugin が最有力**。理由: 既存の Python 資産（triage/inbox/promote）＋「PDF全文→規約準拠メモ」ロジックを **skill＋スラッシュコマンド**（例 `/paper-triage` `/paper-import`）＋セットアップwizardとして再パッケージするだけ。**推論費が各自サブスク内＝原本の"無料"ethosを保てる**。Obsidian もローカルのまま。まず自分＋数人が入れて回すのが最短の検証。
- **Q1=(b) 一般狙いなら → B のアプリ**。ただし①Obsidian核心価値をどう残すか（別UI or 連携プラグイン必須）②推論費を誰が持つか、を再設計する必要があり、**別プロダクトとして作り直しに近い**。原本の強み（無料・ローカル・プライベート）は薄れる。
- **段階戦略の推奨**: いきなりアプリ化せず、**まず"再利用可能な核"を Skill/Plugin に切り出す**（triage採点・note生成skill・inbox規約・wizard）。少人数で価値と需要を検証 → 手応え次第でアプリ化を判断。低コストで後戻り可能。

### 「配る前に必要な脱・個人依存」チェックリスト（A/B/C共通）
- [ ] 絶対パスを config 駆動に（vault パス・python 実体・プロジェクトdir）
- [ ] `config.yaml` から実キーを剥がし、`.env`/secrets ＋ `config.example.yaml` を用意（現状キーは git 管理外前提）
- [ ] `user.research_context`・`classic.queries`・vault規約 を「テンプレ＋ユーザー入力」に一般化
- [ ] セットアップ wizard（Groq/Gmail/Slack/Cloudflare/vault を対話で通す。skill 化に好適）
- [ ] launchd を OS 非依存の説明に（Linux は cron/systemd、Win はタスクスケジューラ）
- [ ] `main.py`/`notion_writer.py`/`sheets_writer.py`/`gemini_summarizer.py`（旧Notion/Sheets）を撤去 or legacy隔離
- [ ] README/SETUP を「他人が読んで再現できる」水準に（このセッションで一次整備済み）

---

## 5. 次セッションの入り方（推奨手順）

1. この HANDOFF と [SPEC.md](SPEC.md) §9 を読む。
2. **Q1/Q2 を決める**（対象ユーザー・Obsidian維持）。→ A/B/C を選択。
3. A（推奨・低コスト検証）を採る場合:
   - `skill-creator` で「PDF→規約準拠 literature_note 生成」skill を切り出し
   - `/paper-triage`（triage_main ラッパ）・`/paper-import`（promote_check＋PDF読解）のコマンド化
   - セットアップ wizard skill（キー類・パス・vault規約の初期化）
   - §4 の脱・個人依存チェックリストを実施
4. まず自分の環境で新パッケージが回るか回帰確認 → 数人に配ってフィードバック。

---

## 6. 補足メモ
- Slack ボタンは **1論文=1メッセージ**。多い時は `slack.digest_recent/classic` を下げる。将来ページング/集約も可。
- Cloudflare Worker/KV は無料枠で個人用途は余裕。多人数配布時は各自が自分の Worker を持つ設計（現状の `cloudflare/SETUP.md` がそのまま個別手順になる）。
- 深掘りメモの品質基準は vault 側 CLAUDE.md（frontmatter必須キー・命名・[[Wikilink]]・テンプレ編集禁止）。skill 化する時はこの規約を skill 本体に内包すると良い。
