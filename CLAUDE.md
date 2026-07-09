# research-pipeline — Claude Code 運用ガイド

論文を自動収集し、**「候補を一覧 → 概要で取捨選択 → 必要なものだけ Obsidian に深く取り込む」** ためのパイプライン。
このファイルは現状(as-is)の把握と運用ルール。**これから作る新仕様は [SPEC.md](SPEC.md) を正とする。**

---

## 0. これは何を解決するためのものか

研究者（このリポジトリのオーナー）のゴール:

1. **引用を効率よく検索・実行したい** → そのために論文の**中身の理解**が必要
2. **最新論文を追いたい**
3. **古い高被引用の重要論文も理解したい**
4. Obsidian で論文をまとめている。**関係ない論文で vault を埋めたくない**

→ 結論として目指す形:「最新＋古典の候補を一覧化 → 概要を見て**自分が要るものだけチェック** → それだけ PDF を取得して Obsidian に深掘りメモ化」。

### 現状の不満（= 改善対象）
- 要約がうまくいかない。**実質アブストだけ／PDF 先頭だけ**を読んで満足している
- 著者情報などのメタdata が機能していない（メール本文からの推測抽出で空欄になりやすい）
- Notion・スプレッドシートにまとめても**関係ない論文が多くノイズ**になっている
- Obsidian へは「PDF を入れる」だけで、その先の深掘りメモ生成と連携できていない

---

## 1. 現状アーキテクチャ (as-is)

```
Gmail (Scholar / WoS アラート)
   ↓ gmail_fetcher.py        メール本文をHTMLパース→タイトル/著者/DOI/URLを抽出（推測ベース）
   ↓ paper_fetcher.py        DOI→Unpaywall OA PDF（先頭8000字まで）or Semantic Scholar アブスト
   ↓ gemini_summarizer.py    Groq(LLaMA3.3 70B)で要約・構造化（実体はアブストの日本語訳が主）
   ├→ notion_writer.py       Notion DB に登録
   ├→ sheets_writer.py       Google Sheets テーマ別タブに追記
   └→ slack_notifier.py      Slack に「今日の論文まとめ」投稿
   ＋ notion_enricher.py      Notion の未読論文を後追いで再エンリッチ（1日2件）
   ＋ notion_to_paperpile.py  Notion → enriched.bib（Paperpile 同期用）
毎朝9時に launchd で自動実行（com.research-pipeline.plist）
```

### ファイルの役割
| ファイル | 役割 |
|---|---|
| `main.py` | パイプライン全体のオーケストレーション |
| `config.yaml` | **設定の唯一の入口**（APIキー・研究テーマ・テーマタグ・プロパティ名） |
| `gmail_fetcher.py` | Gmail取得＋論文メタ抽出（Scholar用 `_parse_scholar` / WoS用 `_parse_wos`） |
| `paper_fetcher.py` | 本文取得（Unpaywall→PDF / Semantic Scholar→アブスト） |
| `gemini_summarizer.py` | Groq 要約・構造化（ファイル名は旧称、中身は Groq） |
| `notion_writer.py` / `notion_enricher.py` | Notion 書き込み・再エンリッチ |
| `sheets_writer.py` | Google Sheets 書き込み |
| `slack_notifier.py` | Slack 通知 |
| `notion_to_paperpile.py` | BibTeX エクスポート |

### 根本原因（なぜ「最初のページだけ」になるか）
- `paper_fetcher.py`: PDF テキストを **`max_chars=8000`（≒先頭2〜3ページ）で打ち切り**。
- `gemini_summarizer.py`: Groq へ渡すのは **`raw_body[:6000]`**、かつプロンプトが **「アブストをそのまま日本語訳」** 主体 → 本文を通読した理解になっていない。
- 多くの論文は OA PDF が取れず **Semantic Scholar のアブストのみ** で要約している。
- 著者は Gmail 本文の隣接行から正規表現で拾うため不正確／空欄。

---

## 2. 連携先 Obsidian vault

`/Users/tonn/Documents/research_vault`（独自の [CLAUDE.md](/Users/tonn/Documents/research_vault/CLAUDE.md) で運用規約あり）

```
research_vault/
├── literature_notes/   1論文=1メモ（frontmatter厳守・Dataviewでクエリ）
├── papers/             PDF原本
├── concepts/           研究概念ノート
├── authors/            著者ノート
├── templates/          Markdownテンプレート（編集禁止）
└── 📊 Research Dashboard.md
```

- 命名: `{筆頭著者姓}{年}_{キーワード}.md`（例 `Huang2025_SoniferousFish.md`）
- frontmatter 必須キー: `title / authors / year / journal / doi / tags / status / read_date / research_field / related_concepts / my_rating`
- `related_concepts`・関連論文は必ず `[[Wikilink]]`。**深掘りメモはこの規約に従って生成する。**

**重要:** 新パイプラインで Obsidian に書き込むときは、vault 側 CLAUDE.md の規約・テンプレートを必ず読み、それに従うこと。

---

## 3. 研究テーマ（要約・関連度判定の基準）

`config.yaml` の `user.research_context`:
- 主テーマ: 海洋中の不明音源の音源種同定（Passive Acoustic Monitoring, PAM）
- 関連: 環境DNA(eDNA)×PAM による海洋生物モニタリング手法の開発
- 関心KW: 水中音響, 生物音, 機械学習による音源分類, 深層学習, soundscape ecology, 海洋生物多様性

テーマタグ候補（`sheets.themes`）: environmental DNA / Soundscape / fish sound / Machine learning / Deep learning / Ocean / その他

---

## 4. 実行方法

**現行フローは §7（as-built）を正とする。** 下記の旧 `main.py`（Notion/Sheets 中心の as-is）は
`_legacy/` へ隔離済み・非使用（[_legacy/README.md](_legacy/README.md)）。

```bash
# 現行（新パイプライン）— 詳細は §7
python3 triage_main.py --preview --no-slack   # プレビュー（/tmp に出力・vault不可侵）
python3 triage_main.py                         # 本番（vault の _inbox.md 更新）
python3 promote_check.py --prepare             # 取り込み準備（PDF確保＋作業リスト）

# 旧 as-is（参考・非使用）: python3 _legacy/main.py（要リポジトリ直下へコピー）
```
- 自動実行: `com.research-pipeline.triage.plist`（毎朝 / launchd）。旧 `com.research-pipeline.plist` は `_legacy/`。
- ログ: `triage.log`（現行）／ `pipeline.log`（旧）

---

## 5. Claude Code への作業指示（このリポジトリで守ること）

- **設定値の変更は基本 `config.yaml` だけで完結させる**（ハードコード禁止）。
- 秘匿情報（`config.yaml` の APIキー, `credentials.json`, `token.json`）は**ログ・コミット・外部送信に出さない**。git 管理外。
- Obsidian vault に書き込む処理を実装・実行するときは、**必ず vault の CLAUDE.md 規約に従う**（frontmatter・命名・Wikilink・テンプレート編集禁止）。
- **vault を関係ない論文で埋めない。** Obsidian への深掘り取り込みは「ユーザーが採用チェックした論文のみ」。自動で literature_notes を量産しない。
- 推測で書誌情報を埋めない。取れない項目は空欄のまま。日付は絶対日付(YYYY-MM-DD)。
- これから実装する新フローは [SPEC.md](SPEC.md) を正とする。as-is コードと矛盾する場合は SPEC を優先し、移行は段階的に行う。

---

## 6. 目指す姿（要約）

```
収集（最新＋古典）→ トリアージ（Obsidian _inbox.md に候補一覧／OA可否表示）
   → Slack個チャに「inbox更新」通知
   → ユーザーが要るものだけチェック
   → チェックした論文だけ PDF 取得 → 深掘りメモを literature_notes に生成
```
詳細・データモデル・未決事項は [SPEC.md](SPEC.md)。

---

## 7. 現在の運用 (as-built / 2026-06-08〜)

新パイプラインが稼働中。**有料API不要**（トリアージ採点＝**Groq無料枠**、深掘り＝**Claudeサブスク内の対話/Remote Control**）。

### 日々の流れ（2026-06-11 改訂: チェックボックス化＋深掘りは対話セッションで無料化）
1. **毎朝8:00**（`com.research-pipeline.triage.plist`）: 最新(Gmail→OpenAlex正規化)＋古典(週1/月曜)を収集 → **LLMで関連度採点＋日本語要約** → vault の `_inbox.md` を**クリック可能なチェックリスト**で更新 →（Slack設定時）個チャ通知。
   - **採点エンジン**(`config.yaml: scoring_engine`)＝**`groq`（既定・推奨）**: 無料枠の LLaMA3.3 70B。日本語・判定が最良（駿河湾eDNA=95, 不明音源→種同定=85, コウモリ=10 と的確）。課金なし（超過は429で止まるだけ・クレカ不要）。`groq.api_key` 必須（console.groq.com で無料発行）。**⚠️ Cloudflare対策でリクエストにブラウザUAヘッダ必須**（無いと error 1010 で弾かれる＝過去「Groqが動かない」の真因。Slack Worker への pull も同様）。実装済み。
   - フォールバック: `ollama`（ローカルQwen・完全無料オフラインだが小型ゆえ日本語はGroqに劣る。`brew services start ollama`）／`rule`（LLMなし保険）。**Groq不通なら自動でOllama→ルールベースに落ちる**ので全件0にならない。
   - **採点エンジン**(`config.yaml: scoring_engine`)＝`ollama`（既定・課金ゼロ・ローカル）/`claude`(メーター課金・非推奨)/`rule`(LLMなし保険)。**まずルールベースで非ゼロのベースラインを当て、その上にLLMで上書き**するので、LLMが落ちても全件0にならない（旧仕様の弱点を解消, 2026-06-27）。
   - **Gmail取得**(`config.yaml: gmail.use_imap: true`)＝**IMAP+アプリパスワード**（OAuthトークン失効問題を回避）。`gmail.app_password` 必須。
   - 最高品質で採点し直したいときは対話で「**新着を採点して**」（サブスク内・無料）。
   - **（2026-07-06 修正）要約取りこぼしの根治**: Groqは `response_format=json_object` で配列をオブジェクトに包むため、以前は想定外のラッパー形状だとバッチ丸ごと適用に失敗し、ルールベースの穴埋め（旧「【自動・要LLM】」）が inbox に漏れていた。対策として ①`_parse_json_array` を任意ラッパーキー/`{"1":{...}}`形式に対応、②`_apply_results` を id対応＋並び順フォールバックに、③取りこぼした件は **1件ずつ自動再試行**、④プロンプトで「results に全件を漏れなく・具体的な日本語要約で」と明示。フォールバック文言も `（自動分類・要約保留）` に変更。
2. ユーザーは `_inbox.md`（閲覧ビュー）を開き判定する（**2026-07-06 改訂**）：
   - **要る** → チェックボックスを左クリック `[x]`（取り込む）。
   - **二度と出したくない** → その行を **`## 🗑️ 二度と出さない` 見出しの下へ移動**（ドラッグ／切り取り→貼り付け）。次回更新で `harvest_dismissed_from_inbox` が **DOIとタイトル**の両方を `dismissed.json` に永久登録し、本文からも古典からも消える。**Obsidian Tasks プラグインは不要**（旧 `[-]` 方式は壊れやすかったので廃止。旧 `- [-]` 行も後方互換で回収する）。
   - どうでもいいものは**放置でOK**（`inbox_retention_days`＝既定14日で自動消滅）。
   - ※チェック済み `[x]` はどのセクション（古典含む）でも「取り込み待ち」へ自動集約。重複は **DOIまたはタイトル**で1本化（DOI無しの同一論文が別日に再掲される問題を解消）。取り込み済み/除外済みになった `[x]` は「取り込み待ち」から自動で消える（自己修復）。
   - ⚠️ **`[x]`＝チェックしただけでは取り込まれない**（Obsidian の打ち消し線＝チェック装飾にすぎない）。実際の深掘りメモ生成は次の 3.（対話セッション）で行う。取り込むまで「取り込み待ち」に残るのは正常。
3. **取り込み（対話セッション・無料。スマホからは Remote Control 経由）**: Claude Code（Mac、またはスマホ→`claude remote-control`）で「**inboxの採用分を取り込んで**」と言う → 対話中の Claude が `promote_check.py --prepare`（Slackタップを先に同期）でPDF確保＋作業リスト取得 → **PDF全文を読んで** `literature_notes/` に深掘りメモ＋[[Wikilink]]生成（vault CLAUDE.md準拠, 1日最大5件）→ `promote_check.py --mark-done` で「取り込み済み」へ移動。
   - **なぜ対話か**: 2026-06-15 から `claude -p`(ヘッドレス) は別建ての月額クレジット/API課金に移行するため、深掘りは**サブスク内で非課金の対話セッション**で行う。自動の15分promoteジョブは廃止。

### スマホ運用: Slack ぽちぽち ＋ Remote Control（2026-07-08 追加。詳細 SPEC.md §9 / cloudflare/SETUP.md）
「inbox を開くのがだるい／× を付けるのが面倒／Mac がスリープだと動かない」への回答。
- **通知**: `config.yaml: slack.interactive: true` で、朝の新着を **1論文=1メッセージ・✅取り込む/🗑️いらない ボタン付き**で Slack DM 送信（`notify_triage_buttons`）。false なら従来の片方向テキスト（`notify_triage`）。
- **タップの受け口**: `cloudflare/worker.js`（無料 Cloudflare Worker）。Slack 署名検証→ KV キューに記録→ タップされたメッセージを「✅/🗑️済み」に更新。**Mac が寝ていてもタップを拾える**。
- **反映**: `slack_queue.py` が Worker からキュー取得（朝のトリアージ／`promote_check --prepare` 直前に自動同期）→ ✅→ inbox の該当行を `[x]`、🗑️→ `dismissed.json` 登録＋ inbox から削除。**× を付ける手作業ゼロ**。⚠️ Worker への pull もブラウザ UA 必須（Cloudflare error 1010 対策、Groq と同様）。
- **取り込み（深掘り）**: スマホ Claude アプリ／Chrome の claude.ai/code から **Mac 上の `claude remote-control` セッション**に「◯◯を取り込んで」＝サブスク内・無料・vault ローカルのまま。Mac は使う時に起きていればよい（公式に iOS/Android 両対応）。
- **✅の意味**: 「取り込み待ちに積む（いつか取り込む・消えない）」。`promote_daily_limit`（5/日）は処理速度の上限で超過分は待ちに残る。**勝手に消えるのは 🗑️ と "放置(14日)" だけ**。
- **朝トリアージのスリープ対策**: `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`（Mac が 07:55 に自動起床）。

### 主要ファイル（新）
`candidate.py` / `ingest_recent.py` / `openalex_classic.py` / `triage.py` / `inbox_writer.py` / `triage_main.py`（8時本体）/ `promote_check.py`（取り込み準備・確定）/ `notify_slack_dm.py`（Slack通知・ボタン）/ `slack_queue.py`（Slackタップ→inbox反映）/ `cloudflare/`（Worker＋SETUP.md）

### 手動実行・確認
```bash
cd /Users/tonn/Desktop/Project/research-pipeline
# トリアージをプレビュー（vault不可侵、/tmp/_inbox.md に出力）
/Users/tonn/matlab_pyenv312/bin/python3 triage_main.py --preview --no-slack
# 本番トリアージ（vault の _inbox.md を更新。古典も強制取得）
/Users/tonn/matlab_pyenv312/bin/python3 triage_main.py --force-classic
# 採点なしでinbox生成（claude認証不要・スコア0）
/Users/tonn/matlab_pyenv312/bin/python3 triage_main.py --force-classic --no-score
# チェック済み論文のPDF確保＋作業リスト（対話セッションでメモ生成前に実行）
/Users/tonn/matlab_pyenv312/bin/python3 promote_check.py --prepare
# メモ生成後、取り込み済みへ移動
/Users/tonn/matlab_pyenv312/bin/python3 promote_check.py --mark-done "10.xxxx/yyy"
# ログ
tail -f triage.log
```

### 残タスク（ユーザー手元）
- **Slack Bot Token / dm_user_id**: 設定済み（DM 通知は稼働）。
- **Slack ぽちぽち（実装済み・要デプロイ）**: `cloudflare/SETUP.md` に沿って Cloudflare Worker をデプロイし、`config.yaml: slack.{interactive:true, worker_url, pull_secret}` を設定（本セッションで設定・動作確認済みなら不要）。
- **朝トリアージのスリープ対策（任意）**: `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`。
- 設定は `config.yaml` に集約。`pipeline.*` / `classic.queries` / `slack.*` / `groq.*` / `scoring_engine` を参照。

### 設定の要点（config.yaml 抜粋）
- `pipeline.inbox_path` = vault の `_inbox.md` / `pipeline.promote_daily_limit: 5` / `pipeline.daily_candidate_limit: 10`
- `claude.triage_model: haiku` / `claude.promote_model: sonnet`
- `classic.weekday: 0`（月曜）/ `classic.queries`（魚類の音・PAM・eDNA・Sciaenidae）
</content>
</invoke>
