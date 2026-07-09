---
name: paper-pipeline-setup
description: >
  research-pipeline を後輩の環境で初期セットアップする対話 wizard。config.local.yaml を作り、
  研究テーマ・Groq キー・Obsidian vault パスを埋め、健診まで通す。/paper-setup から呼ばれる。
  「セットアップして」「初期設定」「使い始めたい」のときに使う。
---

# paper-pipeline-setup — 初期セットアップ wizard

後輩が**ゼロから15分で回り始める**ための対話セットアップ。ユーザーに1問ずつ聞き、
`config.local.yaml` を生成する。**必須は3つだけ**に絞り、残りは任意で後回しにできる。

> 方針: 難しい設定（Gmail / Slack / Notion）は既定オフで飛ばし、まず古典（OpenAlex・認証不要）
> だけでも動く状態に到達させる。障壁を最小化して「動いた」を先に体験させる。

---

## ステップ0: 環境の見立て（最初に確認）
1. **config.local.yaml の用意**: 無ければテンプレをコピーする。
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT:-.}"
   [ -f config.local.yaml ] || cp config.example.yaml config.local.yaml
   ```
   以降、この `config.local.yaml` を編集する（**秘匿情報を含むので git 管理外**。共有しない）。
2. **AI 環境の分岐**（正直に案内する）:
   - あなたは今 **Claude Code** で動いている → 深掘りメモは**フル機能**（この wizard の対象）。
   - もし後輩が **ChatGPT/Gemini しか使えない** 場合 → 採点は各自の AI で代替できるが、
     深掘りは **copypaste で単一メモに劣化**する（グラフ副作用なし）。SETUP.md の「GPT/Gemini 経路」へ。
3. **メモ先**: 既定は **Obsidian**（推奨）。既に Notion で論文管理している後輩は SETUP.md の
   「Notion 経路」へ（現時点では候補ミラー中心・深掘りは Obsidian 推奨と伝える）。

---

## ステップ1〜3: 必須（これだけで動く）

### ① 研究テーマ（採点・要約の唯一の基準）
「あなたは何を研究していますか？ 中心テーマと関心キーワードを数行で」と聞き、
`config.local.yaml` の `user.research_context` を**その人自身の言葉**に置き換える
（テンプレのプレースホルダを消す）。具体的なほど採点が的確になると伝える。
続けて「主要キーワードを3〜5個」聞き、`classic.queries` を生成する
（各キーワードを OpenAlex 検索式 `"keyword" AND (context...)` の形に落とす。theme は表示名）。

### ② 採点エンジンと Groq キー
既定＝**Groq 無料枠**（推奨）。以下を案内:
- https://console.groq.com にアクセス → 無料アカウント作成（**クレジットカード不要**）→
  API Keys で新規キー（`gsk_...`）を発行 → `groq.api_key` に貼る。
- **⚠️ キーは各自で発行する。オーナー（先輩）のキーを使い回さない**
  （規約違反＋レート枯渇で全員が止まる）。
- Groq を使いたくない/オフラインがよい → `scoring_engine: ollama`（`brew install ollama` を案内）。
- キーを今用意できない → `scoring_engine: rule`（LLMなし・鍵ゼロで動く。要約はテンプレになる）で開始し、後で切替。

### ③ Obsidian vault パス ＋ 構成の自動セットアップ
まず Obsidian の準備を確認:
- Obsidian 未導入なら https://obsidian.md からDL（無料）→「Create new vault」で新規vault作成。
- 「Community plugins → Dataview」を Enable（ダッシュボードの表描画に必要）と案内。

vault の**絶対パス**を聞く（取得方法も教える）:
- Obsidian でvault名を右クリック → 「Reveal in Finder / Show in system explorer」→ 開いたフォルダが vault。
- macOS: Finder でそのフォルダを選び **⌘⌥C**（パスをコピー）。／ ターミナルにフォルダをドラッグでもパスが入る。

パスを得たら `pipeline.vault_dir` と `pipeline.inbox_path`（= `<vault>/_inbox.md`）を設定し、
**フォルダ構成とスターターを自動作成**する（既存は上書きしない）:
```bash
VAULT="<聞き取った vault の絶対パス>"
mkdir -p "$VAULT"/literature_notes "$VAULT"/papers "$VAULT"/concepts "$VAULT"/authors "$VAULT"/templates
SRC="${CLAUDE_PLUGIN_ROOT:-.}/vault_starter"
for f in "CLAUDE.md" "📊 Research Dashboard.md" "🗂 論文ビュー（テーマ別）.md"; do
  [ -e "$VAULT/$f" ] || cp "$SRC/$f" "$VAULT/$f"
done
cp -n "$SRC/templates/"*.md "$VAULT/templates/" 2>/dev/null || true
```
コピー後、**`<vault>/CLAUDE.md` の §7「研究フォーカス」をユーザーの研究に書き換える**よう促す
（①で聞いた `research_context` と同じ内容を反映するとよい）。これで後輩は Obsidian 構成をゼロから手作業で作らなくて済む。

さらに `claude.bin` を実環境に合わせる（`which claude` の結果を貼る。見つからなければ `"claude"` のまま）。

---

## ステップ4〜5: 任意（飛ばしてよい）

### ④ Gmail アラート（最新論文の収集元）
「Google Scholar / WoS のアラートメールから最新論文も拾いますか？」
- 使う → 2段階認証をON → アプリパスワード(16桁)を発行
  （https://myaccount.google.com/apppasswords）→ `gmail.address` / `gmail.app_password` を設定。
- 使わない → **空のままでよい**。古典（OpenAlex）だけで開始できる（後輩の障壁を最小化）。

### ⑤ Slack スマホ通知
Phase1 は**スキップ推奨**と明示。やりたい人だけ `cloudflare/SETUP.md` に誘導し
`slack.enabled: true` ＋ `bot_token` ＋（ぽちぽちまでやるなら）Worker 設定。

### ⑥ 別プロジェクトからも使う（任意）
「他のリポジトリで作業中に出た参考文献も vault に取り込みたい」人には、
シェル設定（`~/.zshrc` 等）に `export PAPER_CONFIG="<このリポジトリ>/config.local.yaml"` を1行追加する案内。
プラグインを user スコープで入れておけば、どのプロジェクトからでも「この論文を深掘り保存して」が効く（SETUP.md §6）。

---

## ステップ6: 健診（/paper-doctor）
設定を書き終えたら健診を実行し、緑になるまで直す:
```bash
${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/promote_check.py" --dry-run --config config.local.yaml  # 到達性の粗チェック
```
`/paper-doctor` があればそれを使う（python/依存・Groq 疎通・vault 到達・書込テスト）。

## ステップ7: ハッピーパス実演
最後に通しで1回体験させる:
```bash
export PAPER_CONFIG="$(pwd)/config.local.yaml"
${PAPER_PYTHON:-python3} "${CLAUDE_PLUGIN_ROOT:-.}/triage_main.py" --preview --no-slack   # /tmp/_inbox.md に生成（vault不可侵）
```
生成された `/tmp/_inbox.md` を一緒に見て、「本番は `/paper-triage`、採用は `[x]`、
取り込みは `/paper-import`」の流れを説明して wizard 完了。

---

## 完了条件
- `config.local.yaml` に research_context / scoring_engine（＋鍵）/ vault パスが入っている。
- `triage_main.py --preview` が `/tmp/_inbox.md` を生成できる。
- ユーザーが「採点 `[x]` → 取り込み `/paper-import`」の流れを理解した。
