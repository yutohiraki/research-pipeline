# SPEC — 論文パイプライン 新仕様

ステータス: **ドラフト v0.1**（2026-06-05）／このSPECは [CLAUDE.md](CLAUDE.md) の as-to-be を具体化したもの。実装はこのSPECを正とする。

> ⚠️ **最新差分（2026-07-08）は §9 が正**。§2 / §4 STAGE3 / §8 Phase 3 に残る「15分ごとの headless promote（`claude -p`）」の記述は**廃止**され、深掘りは **Remote Control の対話セッション（サブスク内・無料）**に、選別は **Slack ぽちぽち**に置き換わっている。現行運用は §9 と [CLAUDE.md](CLAUDE.md) §7 を参照。

---

## 1. ゴールと設計原則

### ゴール
1. 引用を効率よく検索・実行するための**中身の理解**を作る
2. **最新論文**を追う
3. **古い高被引用の重要論文**も理解する
4. **関係ない論文で Obsidian vault を埋めない**

### 設計原則
- **トリアージとアーカイブを分離する。** 全候補は安く一覧化し、**深い処理（PDF取得＋深掘りメモ）は「採用した論文だけ」** に限定する。
- **選択の主導権はユーザー。** 自動で literature_notes を量産しない。
- **選択の真実の場所は1つ（Obsidian `_inbox.md`）。** 他サーフェス（Notion）は閲覧用ミラーで、双方向同期はしない。
- 既存資産（Notion DB, `enriched.bib`）は壊さず段階移行する。

---

## 2. 全体フロー（3ステージ）

```
┌── STAGE 1: INGEST（収集）───────────────────────────────┐
│ A. 最新:  Gmail アラート ＋ OpenAlex/Semantic Scholar/Crossref 検索 │
│ B. 古典:  OpenAlex で 研究KW × 高被引用数 を定期取得               │
│ → 正規化した候補(candidate)レコードに統一。DOIで重複排除。         │
└────────────────────────────────────────────────────────┘
                              ↓
┌── STAGE 2: TRIAGE（トリアージ）─────────────────────────┐
│ 各候補に「軽い概要」＋「関連度スコア」＋「OA可否」を付与          │
│ → Obsidian `_inbox.md` に候補テーブルとして書き出し（採用チェック欄つき）│
│ → Notion 閲覧ミラーDBにも反映（read-only）                       │
│ → Slack 個チャ(@Hiraki Yuto)に「inbox更新」通知（毎朝 8:00）       │
│ ※ここでは PDF全文は取らない（アブスト/TLDRベースで安く回す）       │
└────────────────────────────────────────────────────────┘
    ↓ [x] で選択 → 確定したら「✅ 採用（確定）」セクションへ行を移動して保存
   （launchd が15分おきに `_inbox.md` を定期チェック → 未処理の確定行があれば自動で次へ）
┌── STAGE 3: PROMOTE（採用→深掘り）= Claude Code に委任 ──┐
│ 「✅ 採用（確定）」内の行だけを Claude Code(Sonnet) が処理:        │
│ ※ 1日最大5件まで（暴走防止）                                     │
│ 1. PDF取得（OA自動 / 不可なら「要手動DL」で該当行を保留）         │
│ 2. PDF全文を通読して深掘りメモを literature_notes に生成          │
│ 3. concepts/ authors/ への [[Wikilink]] を張る                   │
│ 4. inbox から該当行を「取り込み済み」へ移動                       │
│ 5. Slack 個チャに「N件取り込んだ／M件は要手動DL」を通知           │
└────────────────────────────────────────────────────────┘
```

**重要な体験要件:** 採用後の「深掘りメモ」は現状の気に入っている品質を**維持・強化**する（PDFが無いと深掘りできないので、深掘りは必ず PROMOTE 段階で行う）。トリアージ段階のメモはあくまで取捨選択用の軽量サマリ。

---

## 3. データモデル

### 3.1 candidate（候補レコード／内部表現）
```yaml
id:              # DOI優先。無ければ正規化タイトルのハッシュ
title:
authors:         # リスト。可能な限り全員（メタAPIで補完）
year:
journal:
doi:
url:
source_feed:     # gmail_scholar | gmail_wos | openalex_recent | openalex_classic | s2
cited_by_count:  # 被引用数（古典判定・並び替え用）
is_oa:           # true/false（Unpaywallで判定）→ リストに表示
oa_pdf_url:      # OAのPDF直リンク（あれば）
abstract:        # トリアージ用の本文（アブスト or TLDR）
relevance_score: # 0–100。research_context との関連度
relevance_reason:# 1行。なぜ関連（しない）か
one_liner:       # 1–2文の客観サマリ（日本語）
tags:            # テーマタグ
status:          # candidate | promoted | dismissed
first_seen:      # YYYY-MM-DD
```

### 3.2 Obsidian `_inbox.md`（トリアージの真実の場所）
- 置き場所: vault 直下 `_inbox.md`（`literature_notes/` は汚さない）。
- **2段階の合図（重要）**: チェック `[x]` は「目印」にすぎず、**自動取り込みの発火条件は別の「確定の合図」**にする（途中保存で誤発火させないため）。
  - 候補テーブルで読みたいものに `[x]` を付ける（=選択）。
  - 取り込んでよいと**確定したら、その行を `## ✅ 採用（確定）` セクションへ移動**して保存する（=確定の合図）。
  - PROMOTE が処理するのは **`## ✅ 採用（確定）` 内の行だけ**。`[x]` だけで `## 新着`/`## 古典` に残っている行は処理しない。
- 形式案:

```markdown
# 📥 論文 Inbox

> 読みたいものに [x] → 取り込み確定したら「✅ 採用（確定）」へ行を移動して保存。
> 確定セクションに置いた行だけが自動で literature_notes に取り込まれます（1日最大5件）。

## ✅ 採用（確定） ← ここに移した行だけ自動取り込み
| スコア | OA | タイトル | 著者(筆頭) | 年 | 誌 | 一言 | リンク |
|----|----|----|----|----|----|----|----|
| 86 | ✅ | Reef fish call detection with CNN | McCammon | 2025 | JASA | YOLOでサンゴ礁魚鳴音を高速検出 | [doi](https://doi.org/...) |

## 新着 2026-06-06
| 採用 | スコア | OA | タイトル | 著者(筆頭) | 年 | 誌 | 一言 | リンク |
|----|----|----|----|----|----|----|----|----|
| [ ] | 41 | ⛔ | （関連薄）... | ... | ... | ... | 直接の関連は低い | [doi](...) |

## 古典・高被引用（KW: passive acoustic monitoring）
| 採用 | 被引用 | OA | タイトル | ... |

## 取り込み済み
（PROMOTE 完了後にここへ移動・日付つき）
```
- `OA` 列: `✅`=OAでPDF自動取得可 / `⛔`=要手動DL（paywall）。
- 関連度スコアで降順ソート。ノイズは下に沈める（消さずに残し、再表示しない仕組みは §6 未決）。

### 3.3 Notion 閲覧ミラー（任意・read-only運用）
- 既存 Notion DB をトリアージ候補の**閲覧用ビュー**として残す（DBのテーブル/フィルタ/ソートの視認性が欲しいという要望に対応）。
- **選択操作はObsidian側に一本化**し、Notionは見るだけ（双方向同期しない）。
- candidate を Notion にも push（スコア・OA・一言・タグ・関連理由）。採用済み/dismiss はステータスで色分け。
- ※「Notionでも選択したい」となった場合は §6 で双方向同期を検討（複雑化するため初期は非対応）。

---

## 4. ステージ別仕様

### STAGE 1: INGEST
- **最新（A）**
  - 既存 Gmail アラート取得は維持（`gmail_fetcher.py`）。
  - 追加で **OpenAlex / Semantic Scholar の最近の論文検索**を `research_context` のキーワードで実行し候補を増やす（アラート漏れ対策）。Crossref は書誌補完に使用。
  - メタdata（著者全員・年・誌・DOI・被引用数・OA）は**メールの推測抽出に頼らず API で正規化**する（著者情報が機能していない問題の根治）。
- **古典（B）— 今回スコープに含む**
  - OpenAlex で各テーマKW × `cited_by_count` 降順を **週1**取得。対象4テーマ:
    1. **魚類の音**（fish sound / fish vocalization / fish acoustics）
    2. **PAM**（passive acoustic monitoring）
    3. **eDNA**（environmental DNA）
    4. **Sciaenidae（ニベ科）**（Sciaenidae / croaker / drum fish）
  - 各テーマ上位N件を取得し、既に vault / inbox にあるものは除外。未取得の高被引用論文を `openalex_classic` として候補化。
  - 検索語・取得件数は `config.yaml` の `classic.queries` で設定（ハードコードしない）。
- 重複排除: DOI（無ければ正規化タイトル）で uniq。既に `literature_notes/` にあるDOIは候補から除外。

### STAGE 2: TRIAGE
- 各候補にアブスト/TLDR（**全文は取らない**）を付与。
- **関連度スコアリング**: `research_context` との関連を LLM で 0–100＋1行理由。低関連は正直に低スコア（現行プロンプトの「無理に関連づけない」方針を踏襲）。
- **OA判定**: Unpaywall で `is_oa` と `oa_pdf_url` を取得し、リストに `✅/⛔` 表示（採用前にDL可否が分かるように）。
- 実行タイミング: **毎朝 8:00**（launchd）。INGEST → TRIAGE を一括実行。
- 出力: `_inbox.md` 追記 → Notion ミラー push → Slack 個チャ通知。
- Slack 通知仕様:
  - 宛先: **個人DM（@Hiraki Yuto）**。旧「チャンネルへの今日のまとめ」ダイジェストは**廃止**。
  - 内容: 「inbox に N 件追加（新着X / 古典Y）。上位3件: …。→ `_inbox.md` を確認」程度の軽い通知。

### STAGE 3: PROMOTE（採用した論文だけ深掘り）= Claude Code に委任
**実行主体: Claude Code（headless）。** 深掘りメモ生成は Python の固定スクリプトではなく Claude Code に任せる（vault の CLAUDE.md 規約・テンプレートを読んで高品質メモを作れるため）。

**発火条件 = 確定の合図（誤発火させない）:**
- チェック `[x]` だけでは発火しない。**`## ✅ 採用（確定）` セクションに移動された行**のみを取り込み対象にする。
- 実装方式 = **定期ポーリング**（launchd `StartInterval` で15分おきに `_inbox.md` をチェック）。`WatchPaths`（ファイル変更の即時検知）は設定が繊細なため採用しない。確定行があれば起動スクリプトが
  `claude -p "SPEC.md と vault の CLAUDE.md に従い、_inbox.md の『✅ 採用（確定）』の未取り込み行を取り込んで"` 相当を headless 実行する（確定セクションに行を置いてから最大15分以内に取り込み）。
- **使用モデル: Claude Sonnet**（精度が大きく変わらなければ Sonnet を既定。品質が不足する場合のみ Opus に切替）。
- 安全策:
  - **1日最大5件**まで（暴走防止）。確定セクションに6件以上あっても当日は5件で打ち切り、残りは Slack で通知して翌日へ繰り越し。
  - 多重起動防止のロックファイル（処理中は再入しない）。短時間の連続保存はデバウンス。
  - **冪等性**: 既に `## 取り込み済み` にある／対応する literature_note が存在する行は再処理しない。
  - 失敗・要手動DLは確定セクションに残し、結果を Slack 個チャに通知。
- フォールバック: 毎朝 8:00 の定期実行時にも「確定セクションの未取り込み行」を拾う（WatchPaths が漏れた場合の保険）。

**Claude Code が行う手順（明示的・忘れないこと）:**
1. `## ✅ 採用（確定）` の未取り込み行を収集（当日上限5件）。
2. **PDF取得**:
   - OA(`✅`): `oa_pdf_url` から `papers/` に保存（命名は vault 規約に寄せる）。
   - 非OA(`⛔`): **自動取得せず「要手動DL」として保留**。ユーザーが `papers/` に置いたら次回の取り込みで再開。
3. **深掘りメモ生成**: 保存PDFの**全文を通読**（先頭8000字打ち切りをやめる、§5）。vault の `templates/literature_template.md` と CLAUDE.md 規約に従い `literature_notes/{筆頭著者姓}{年}_{KW}.md` を生成:
   - frontmatter 厳守（`status: read`, `read_date`=当日, `my_rating` は空）。
   - 要約 + 主要主張3〜5点 + 方法/結果/結論 + **引用したい箇所をページ番号付きで5〜10**。
4. **リンク付け**: 重要概念を `concepts/` に（無ければ作成）、著者を `authors/` に、`related_concepts` を `[[Wikilink]]` 化。逆リンクも張る（vault CLAUDE.md ワークフローB/C準拠）。
5. inbox の該当行を `## 取り込み済み` に移動。candidate.status = promoted。
6. 必要なら `enriched.bib` 再生成（Paperpile 同期）。
7. 結果を Slack 個チャに通知（取り込みN件／要手動DL M件）。

---

## 5. 「中身の理解」を上げるための技術変更（現状の根本原因への対処）

| 問題 | 現状 | 変更 |
|---|---|---|
| PDF先頭しか読まない | `paper_fetcher.extract_text_from_pdf_url(max_chars=8000)` | PROMOTE時は**全文抽出**（章ごと/全ページ）。長文はセクション分割して要約集約 |
| アブスト訳どまり | プロンプトが「アブストをそのまま日本語訳」 | PROMOTEでは**全文に基づく構造化深掘り**（方法・結果の数値・限界・引用箇所）。トリアージは軽量サマリと役割分離 |
| 著者が空欄/不正確 | メール本文から正規表現で推測 | OpenAlex/Crossref/S2 から**著者全員を取得** |
| ノイズが多い | 全件 Notion/Sheets へ | トリアージで**関連度スコア**、深掘りは採用分のみ |
| LLMの非力さ・運用負荷・コスト | Groq LLaMA3.3 70B（**週1でAPIキー更新が必要で面倒**） | **Groq・有料API を全廃。** TRIAGE も PROMOTE も **Claude Code（`claude -p` headless）= 既存サブスクで処理（追加課金なし）**。TRIAGE=全候補を1回の呼び出しでバッチ採点（model: haiku）、PROMOTE=全文深掘り（model: sonnet、不足時 opus）。APIキー不要 |

---

## 6. 未決事項（このSPECで詰めていく論点）

1. **inbox の肥大化対策**: dismiss した候補の再表示抑止、保持期間、アーカイブ方法。`## 取り込み済み` の肥大化時の切り出し。
2. **PDF命名規則**: vault `papers/` の既存命名（`{Author} et al. {Year} - {Title}.pdf`）に自動で寄せるか。
3. **定期ポーリングの実装詳細**: ロック方式、`claude -p` に渡す権限（vault と papers/ への書き込み許可）と作業ディレクトリ、headless のログイン維持。
6. **headless 実行の認証**: `claude` CLI のログイン維持・モデル指定・1回あたりの上限（暴走防止）。
7. **既存パイプラインの段階移行**: Sheets出力の停止時期、Slackダイジェスト停止時期、`notion_writer` の役割をミラーに付け替える順序。Groq 依存（`gemini_summarizer.py`）の撤去順。

---

## 7. 確定済みの決定（ユーザー回答 2026-06-05）

- トリアージ場所 = **Obsidian `_inbox.md`**（採用したものだけ深掘り）。深掘りメモは現状の品質を維持し PROMOTE 段階で生成。
- 通知 = **Slack 個チャ(@Hiraki Yuto)に inbox 更新通知のみ**。旧チャンネルダイジェストは廃止。
- **Google Sheets は廃止。**
- **Notion は閲覧用 DB ミラーとして残す**（DBビューの視認性が欲しいため）。選択操作は Obsidian に一本化。
- PDF = **OA自動DL ＋ 非OAは「要手動DL」マーク**。**リスト段階で OA 可否（✅/⛔）を表示**。
- **採用チェック → そのPDFだけ取得する明示ステップを必ず設ける。**
- **古い高被引用論文の追跡を本SPECに含める。**

### 追加決定（ユーザー回答 2026-06-06）
- **TRIAGE 通知は毎朝 8:00**（従来 9:00 から変更）。launchd の時刻を 8:00 に設定。
- **PROMOTE は Claude Code（headless）に委任。** Python の固定スクリプトで深掘りメモを作らない。
- **`_inbox.md` の保存を launchd WatchPaths で検知 → 自動で PROMOTE を起動**。毎朝 8:00 の定期実行を保険のフォールバックにする。
- **Groq は廃止**（週1のAPIキー更新が面倒）。深掘り=Claude Code、トリアージ=小型 Claude（Anthropic API）。
- **Notion は閲覧専用で確定**（双方向同期はしない）。

### 追加決定（ユーザー回答 2026-06-06 その2）
- **発火は「確定の合図」で行う**（保存即発火はしない）。`[x]` は選択の目印にとどめ、**`## ✅ 採用（確定）` セクションに移した行だけ**を自動取り込み対象にする。
- **PROMOTE は 1日最大5件**（暴走防止の上限）。超過分は翌日へ繰り越し、Slack で通知。
- **深掘りメモのモデルは Claude Sonnet**（精度が大きく変わらなければ Sonnet を既定、不足時のみ Opus に切替）。

### 追加決定（ユーザー回答 2026-06-06 その3）
- **INGEST/TRIAGE の1日あたり候補上限 = 10件**（トリアージに載せる新着の最大数）。
- **古典収集は週1**。対象4テーマ = 魚類の音 / PAM / eDNA / Sciaenidae(ニベ科)。検索語は `config.yaml` で管理。
- 自動取り込みの起動は **WatchPaths をやめて15分ごとの定期ポーリング**にする（設定が単純で扱いやすい）。

### 追加決定（ユーザー回答 2026-06-06 その4）
- **有料API を一切使わない。** トリアージも深掘りも **Claude Code（`claude -p`）= 既存サブスク内で処理＝追加課金ゼロ**。Anthropic API キーは不要。
- トリアージ = 全候補を**1回の `claude -p` 呼び出しでバッチ採点**（model: haiku）。深掘り = `claude -p`（model: sonnet）。
- launchd は最小PATHのため `claude` は**絶対パス**で呼ぶ（`config.yaml` の `claude.bin`）。前提: ユーザーが `claude` にログイン済みであること。
- Slack は無料（Bot Token 方式）。課金対象ではないため継続。

---

## 8. 移行ステップ（提案・段階的）

1. **Phase 0**: 本SPECレビュー、§6 の決定。
2. **Phase 1（トリアージ基盤）** ✅完了: INGEST 正規化（OpenAlex で DOI/タイトルからメタ補完）＋ OA判定＋関連度スコア → `_inbox.md` 出力。トリアージを **Groq → Claude Code（`claude -p`, 追加課金なし）** に置換。**launchd を 8:00 に設定**。
3. **Phase 2（深掘り＝Claude Code 委任）** ✅完了: PROMOTE を `claude -p`(sonnet) の headless 実行として実装。採用分のPDF取得（手持ち照合＋OA DL）＋**全文**深掘りメモ＋Wikilink。8000字打ち切りなし。MiFishで実証。
4. **Phase 3（自動トリガー）** ✅完了（方式変更）: WatchPaths ではなく **15分ごとの定期ポーリング**（`com.research-pipeline.promote.plist`）。ロック・5件/日・冪等性（literature_notes 存在チェック）あり。
5. **Phase 4（古典）** ✅完了: OpenAlex 高被引用4テーマを週1で inbox に統合。
6. **Phase 5（整理）** ⬜残: Slack Bot Token 設定。Sheets/旧Slack の正式停止、`gemini_summarizer.py`(Groq) 撤去。Notion 閲覧ミラー化。`enriched.bib` 連携確認。

### as-built（実装済みファイル）
- `candidate.py` 候補モデル / `ingest_recent.py` 最新(Gmail→OpenAlex正規化) / `openalex_classic.py` 古典
- `triage.py` claude -p バッチ採点 / `inbox_writer.py` `_inbox.md` 描画 / `triage_main.py` 8時本体
- `promote_check.py` 15分ごとの深掘り取り込み / `notify_slack_dm.py` Slack DM
- launchd: `com.research-pipeline.triage.plist`(8:00) / `com.research-pipeline.promote.plist`(900s)

---

## 9. スマホ駆動・Remote Control 版（2026-07-07 決定 / これが現行の正）

「inbox を Obsidian で開くのがだるい」「Mac がスリープだと動かない」への回答。**§8 Phase 3 の 15 分ごと headless promote は廃止**し、以下を現行仕様とする。

### 制約（確定）
- **有料API・従量課金は一切使わない**（サブスク内のみ）。深掘りメモは **Opus/Sonnet 必須**（Groq ドラフト案は品質不足で却下）。
- **vault は外に出さない**（完全ローカル・GitHub 化しない）。
- ユーザー端末は **Android**。

### 結論＝Remote Control 版
深掘り取り込みは **Claude Code の Remote Control** で行う：Mac で `claude remote-control` を起動 → スマホ（Claude Android アプリ Code タブ / Chrome の claude.ai/code）から同セッションを操作。**サブスク内＝無料**、vault はローカルのまま、Android 対応（公式に iOS/Android 両対応）。

```
毎朝8:00  Mac が pmset で自動起床 → triage_main.py（Groq採点・無料）→ _inbox.md 更新 → Slack DM 通知
日中      スマホ Slack で新着確認 → Claude Android アプリ / Chrome で Mac の remote-control セッションを開く
          → 「inbox の◯◯を取り込んで」（どれを、を会話で指定）
Mac       ローカルで promote_check.py --prepare → PDF全文読解 → literature_notes 生成(Sonnet/Opus) → --mark-done
各端末     Obsidian が同 vault を表示（ローカル。同期は各自の手段）
```

### 旧仕様からの変更（こちらが優先）
- **§8 Phase 3「15分ごとの headless promote（`claude -p`）」= 廃止**。理由: 2026-06-15 に `claude -p`(ヘッドレス) が従量課金化。深掘りは **対話セッション（Remote Control 経由でスマホから起動可）** に一本化＝サブスク内で無料。
- トリアージ採点は **Groq 無料枠**（`claude -p` ではない。CLAUDE.md §7 準拠）。Groq 不通時は Ollama→ルールベースに自動フォールバック。
- inbox 運用は **CLAUDE.md §7（2026-07-06 改訂）が正**: `[x]`＝取り込み待ち／`## 🗑️ 二度と出さない`へ行移動＝永久除外／重複は **DOI・タイトル両キー**で排除／要約は Groq 取りこぼしを1件ずつ自動再試行。

### スリープ対策
- **朝トリアージ**: `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00` で Mac が自分で起きる（launchd 8:00 の直前）。
- **取り込み**: ユーザー起動の操作なので実行時に Mac が起きていればよい。Remote Control は接続中に Mac が寝ると切断するが、Mac 復帰で自動再接続。
- 「**Mac 完全に寝たまま取り込みたい**」要件が出た時のみ、将来クラウド版（vault を private GitHub 化＋GitHub Actions トリアージ＋クラウドセッション取り込み）を検討。ただし **非OA（有料）論文＝本命 PDF がクラウドから取得できない**弱点があるため、現時点では採用しない。

### セットアップ手順（ユーザー作業）
1. **Slack Bot Token**（無料）: `config.yaml` の `slack.bot_token`(xoxb-) と `dm_user_id`(U…) を設定 → 朝の DM 通知が有効化。
2. **Mac 自動起床**: ターミナルで `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`（`pmset -g sched` で確認）。
3. **Remote Control**: Mac で `claude remote-control` を実行 → 表示 QR / セッション URL を Android の Claude アプリ or Chrome で開く。
4. **Android**: Claude アプリを**バッテリー最適化から除外**（通知遅延防止）。
5. 取り込み時に Mac が起きているようにする（在席時に実行、または省電力で日中スリープさせない）。

### Slack ぽちぽち（2026-07-08 実装済み）
「× を付けるのが面倒／inbox を開くのがだるい」への回答として、Slack のボタン操作を実装。
- **朝の通知**: `notify_slack_dm.notify_triage_buttons`（`slack.interactive: true`）が **1論文=1メッセージ**で ✅取り込む / 🗑️いらない ボタン付き（スコア順・要約・DOI）を DM 投稿。無効時は従来の片方向テキスト `notify_triage`。
- **受け口**: `cloudflare/worker.js`（無料 Cloudflare Worker）。Slack 署名検証→ KV キューに ✅/🗑️ を記録→ response_url でメッセージを「✅/🗑️済み」に更新。Mac が寝ていてもタップを拾える。
- **反映**: `slack_queue.sync_inbox`（`triage_main.py` 朝／`promote_check.py --prepare` 直前で自動実行）が Worker からキューを取得し、✅→ inbox の該当行を `[x]`、🗑️→ `dismissed.json` 登録＋ inbox から削除。**× を付ける手作業ゼロ**。
- 設定: `config.yaml: slack.{interactive, worker_url, pull_secret, digest_recent, digest_classic}`。手順は `cloudflare/SETUP.md`。
- 課金: Worker/KV とも無料枠。深掘り本体は従来どおり Remote Control（サブスク内・従量なし）。
</content>
