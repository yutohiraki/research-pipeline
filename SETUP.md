# SETUP — 後輩向けセットアップ手順

論文を自動収集→関連度採点→Obsidian に一覧化し、**採用した論文だけ**を PDF 全文から
規約準拠の深掘りメモにするパイプライン。**採点は Groq 無料枠、深掘りは Claude サブスク内**（従量課金なし）。

> このファイルは「他人が読んで再現できる」ための手順。運用ルールの正は [CLAUDE.md](CLAUDE.md)、
> 設計の正は [DISTRIBUTION.md](DISTRIBUTION.md)。

---

## 0. まず自分の環境を確認（どのレーンか）

| あなたの環境 | 採点 | 深掘りメモ | 品質 |
|---|---|---|---|
| **Claude Code ＋ Obsidian**（推奨・本命） | Groq無料枠 | Claude が PDF全文→規約準拠**マルチファイル**生成 | ◎ フル（concepts/authors/逆リンクのグラフ込み） |
| **ChatGPT/Gemini ＋ Obsidian** | 各自のGPT/Gemini | **copypaste 半自動**（web に貼る） | △ 単一メモに劣化（グラフ副作用なし）※Phase2で提供予定 |
| **Notion 派** | Groq等 | 当面は Obsidian 推奨 | Notion 深掘りは今後（候補ミラーから） |

**Claude Code が使えるなら迷わず「Claude Code ＋ Obsidian」レーン**が一番簡単で高品質。以下その手順。

---

## 1. インストール（Claude Code ＋ Obsidian レーン）

```bash
# 1) 取得（研究室の共有 git / zip を clone or 展開）
git clone <この research-pipeline のURL>  research-pipeline
cd research-pipeline

# 2) Python 依存（自分の python3 に）
python3 -m pip install -r requirements.txt   # 最低限 pyyaml があれば動く

# 3) Claude Code にプラグインとして登録（このリポ自身が marketplace）
#    Claude Code 内で:
#      /plugin marketplace add ./research-pipeline
#      /plugin install research-paper-triage
```

> Python が複数ある人（pyenv/conda 等）は、依存を入れた python を使わせるため
> `export PAPER_PYTHON=/path/to/your/python3` を設定しておくと確実。

## 2. セットアップ wizard

Claude Code で:

```
/paper-setup
```

対話で **3つだけ**埋めれば動く:
1. **研究テーマ**（採点・要約の唯一の基準。自分の言葉で）＋主要キーワード3〜5個
2. **採点エンジンと Groq キー** — https://console.groq.com で**各自が無料キーを発行**（クレカ不要）。
   ⚠️ **先輩のキーを使い回さない**（規約違反＋レート枯渇で全員止まる）。キーが無ければ `rule` で開始も可。
3. **Obsidian vault の絶対パス**

Gmail アラート／Slack 通知／Notion は任意（既定オフ）。古典（OpenAlex・認証不要）だけでも始められる。

## 3. 健診

```
/paper-doctor
```
python・設定・Groq 疎通・vault 書込を点検。緑になったら次へ。

## 4. 毎日の流れ

```
/paper-triage --preview     # まず /tmp に出して動作確認（vault に触れない）
/paper-triage               # 本番: vault の _inbox.md を更新
```
→ Obsidian で `_inbox.md` を開く → **要る論文に `[x]`**（チェック）→

```
/paper-import               # [x] した論文の PDF全文を読み、深掘りメモを生成
```

- **`[x]` を付けただけでは取り込まれない**（打ち消し線は装飾）。実際の生成は `/paper-import`。
- **二度と出したくない論文** → その行を `## 🗑️ 二度と出さない` 見出しの下へ移動（次回から永久除外）。
- 放置した新着は14日で自動消滅。
- 1日の深掘り上限は5件（`pipeline.promote_daily_limit`）。

## 5. 自動化（任意・OS別）

毎朝の自動トリアージは OS の仕組みで（**launchd 固定にしない**）:
- macOS: launchd（`com.research-pipeline.triage.plist` を参考に絶対パスを自分用に）。スリープ対策 `sudo pmset repeat wakeorpoweron MTWRFSU 07:55:00`。
- Linux: cron / systemd timer。
- Windows: タスクスケジューラ。
手動運用（`/paper-triage` を自分で叩く）でも全く問題ない。

### PDF 自動先取り（任意・往復を減らす）
✅した論文のOA PDFを日中に自動取得しておくと、取り込み時に「PDFを取ってから再依頼」の往復が消える。
テンプレ `com.research-pipeline.prefetch.plist.template` の `__PYTHON__`/`__REPO__` を自分の値に置換し:
```bash
# 置換後、~/Library/LaunchAgents/com.research-pipeline.prefetch.plist として保存し
launchctl load ~/Library/LaunchAgents/com.research-pipeline.prefetch.plist
```
中身は `promote_check.py --prepare`（**LLMなし・非課金**のPDF確保＋Slackタップ同期）だけ。Linux/Winは同コマンドをcron/タスクで。

## 6. 別プロジェクトから参考文献を取り込む（全プロジェクト共通）

別のリポジトリ/プロジェクトで作業中に出てきた参考文献も、そのまま vault に深掘りメモ化できる:
1. プラグインを **user スコープで** 入れる（`/plugin install` 時に user を選ぶ）＝どのプロジェクトでも `paper-note-writer` が効く。
2. シェルの設定（`~/.zshrc` 等）に **`export PAPER_CONFIG="/absolute/path/to/config.local.yaml"`** を追加＝cwd に依存せず自分の vault を解決。
3. 作業中に「**この論文を深掘り保存して**」（DOI/タイトル/手元PDF）→ skill が OA を自動DL（`fetch_pdf.py`）→ 全文読解 → vault にメモ生成。重複は自動チェック。
- ⚠️ **無差別に取り込まない**（vault を関係ない論文で埋めない）。保存価値を自分で判断してから。非OAは `papers/` に手動配置。

---

## GPT/Gemini 経路（Claude Code を使えない後輩・正直な説明）

**採点は代替できる**（各自の GPT/Gemini キー。Phase2 で `scoring_engine: openai` 等を提供予定）。
**深掘りは非対称に劣化する**。理由: 深掘りメモ生成は「ファイルを複数書く対話エージェント」が
PDF と規約を読んで literature_note＋concepts＋authors＋逆リンクを作る作業で、
**ChatGPT/Gemini の web にはその実行主体が無い**。

現実的な選択肢（優先順）:
1. **copypaste 半自動（無料・Phase2 提供予定）**: `/paper-import --export-prompt` が規約入りの
   完成プロンプトを書き出す → web LLM に貼付 → 生成メモを貼り戻す → 保存前バリデーションを通す。
   ただし **concepts/authors/逆リンクのグラフは出ず単一メモに劣化**、PDF 全文が長いとトークン超過、手数も多い。
2. **研究室の Claude 保有者に頼む**: Mac で `claude remote-control` を起動してもらい、スマホ/ブラウザから
   「◯◯を取り込んで」。品質は最高だが、その人に依存する。
3. 従量 API 自動化は**作らない**（無料方針に反し、単発 API 呼び出しではグラフ副作用を出せない）。

→ **Claude Code が使えるなら使うのが圧倒的に楽**。使えないなら「採点は自分のAI・深掘りは copypaste で単一メモ」と割り切る。

## Notion 経路（既に Notion で論文管理している後輩）

現時点は **Obsidian を推奨**。Notion は今後 `note_store: notion` で
**候補一覧のミラー**から対応予定（深掘りメモの Notion 完全対応は Obsidian と同等にはならない＝
本文ブロックや concept/author relation の追加開発が要る）。詳細は [DISTRIBUTION.md](DISTRIBUTION.md) §4b。

---

## 秘匿情報の扱い（重要）

- `config.local.yaml`（各自のキー・パス）と `config.yaml`・`credentials.json`・`token.json` は
  **git 管理外**（`.gitignore` 済み）。**チャット・コミット・共有ドライブに貼らない**。
- 初回コミット前に `git status` で秘匿ファイルが staged に無いことを必ず確認する。
- 配布時に共有するのは `config.example.yaml`（キーを剥がしたテンプレ）だけ。
