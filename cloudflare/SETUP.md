# Slack ぽちぽち セットアップ（Cloudflare Worker・研究室共有モデル）

Slack の ✅取り込む / 🗑️いらない ボタンで論文を選別（Mac が寝ていても拾える）。全部無料。

**研究室モデル（推奨）**: **管理者（先輩）が Worker を1個だけ立てて共有** → **後輩は config を貼るだけ**（Cloudflare も Slack アプリ作成も不要）。
Worker はタップを **Slackユーザーごとのキュー**に分けるので、1つを全員で共有しても混ざりません。

```
朝  各自の Mac → 自分のSlack DMに ✅/🗑️ ボタン付きで新着を投稿
昼  スマホSlackで ✅/🗑️ タップ → 共有Workerが署名検証してユーザ別キューに記録＋メッセージ更新
夜  「取り込んで」→ 各自のMacが自分のキューだけ取得（✅→[x] / 🗑️→dismissed）
```

---

> **既に旧版の Worker を立てている人の更新（1回だけ）**: KV と Secret はそのまま、コードだけ差し替えます。
> Cloudflare ダッシュボード → **Workers & Pages → 自分の Worker → Edit code** → エディタを全消し →
> [`worker.js`](worker.js) の新全文を貼付 → **Deploy**。これでユーザ別キュー（共有モデル）が有効になります。
> `wrangler` 派は `cd cloudflare && wrangler deploy`。

# 【管理者（先輩）が1回だけ】Worker と Slack アプリを用意

## A. Cloudflare Worker（ラボに1個）
1. **無料アカウント**: https://dash.cloudflare.com/sign-up （クレカ不要）。
2. **KV 名前空間**: 左メニュー **Storage & Databases → KV → Create a namespace**（名前 `research-queue` 等）。
3. **Worker 作成**: **Workers & Pages → Create → Workers → Create Worker**（名前 `research-slack` 等）→ **Deploy** → **Edit code**。
4. **コード貼付**: エディタを全消し → このリポジトリの [`worker.js`](worker.js) を**全文貼付** → **Deploy**。
5. **KV バインド**: Worker **Settings → Bindings → Add → KV namespace**。Variable name = **`QUEUE`**（固定）／namespace = `research-queue` → Save。
6. **Secret 2つ**: **Settings → Variables and Secrets → Add**（type=Secret）。
   - `SLACK_SIGNING_SECRET` … B-2 で取得する Slack の Signing Secret
   - `PULL_SECRET` … 好きな長い合言葉（例 `openssl rand -hex 24`）。**後輩に配る**のでメモ。
   - Save → 再 **Deploy**。
7. **Worker URL を控える**: `https://research-slack.<ラボ>.workers.dev`。

## B. Slack アプリ（ラボに1個・後輩全員が同じワークスペースに入る）
1. https://api.slack.com/apps → 「論文Bot」アプリ → **Interactivity & Shortcuts** を ON → **Request URL** に Worker URL（A-7）→ Save。
2. **Basic Information → App Credentials → Signing Secret** をコピー → A-6 の `SLACK_SIGNING_SECRET` に入れて再 Deploy。
3. Bot に `chat:write`（DM 通知に必要）。後輩がDMを受け取れるよう、後輩を同じワークスペースに追加。
4. **Bot User OAuth Token（`xoxb-…`）** を控える（後輩に配る）。

## C. 後輩に配る3つの値（共有）
セットアップ後、後輩に渡す（1回作れば全員同じ）:
- **bot_token**（`xoxb-…`）／ **worker_url**（`https://…workers.dev`）／ **pull_secret**（A-6 の合言葉）

---

# 【後輩（各自）】config を貼るだけ（Cloudflare 不要・Slackアプリ作成不要）

1. ラボの Slack ワークスペースに参加。
2. **自分のメンバーIDを取得**: Slack 自分のプロフィール →「…」→「メンバーIDをコピー」（`U…`）。
3. `config.local.yaml` の `slack:` に貼る（3つは配られた共有値、`dm_user_id` だけ自分の）:
```yaml
slack:
  enabled: true
  interactive: true
  bot_token: "<ラボの bot_token（xoxb-…）>"
  dm_user_id: "<自分のメンバーID（U…）>"
  worker_url: "<ラボの worker_url>"
  pull_secret: "<ラボの pull_secret>"
```
これだけで、朝の通知にボタンが付き、タップが**自分の**inboxに反映されます（他人のと混ざりません）。

---

# 動作テスト（管理者・後輩とも）
```bash
# 1) Worker 疎通（ok が返れば生きてる）
curl -s https://research-slack.<ラボ>.workers.dev/ ; echo
# 2) pull 認証＋ユーザ別（自分のIDで []（空配列）が返ればOK。401=pull_secret不一致 / 400=userなし）
curl -s -H "Authorization: Bearer <PULL_SECRET>" "https://research-slack.<ラボ>.workers.dev/pull/want?user=<自分のU…>" ; echo
# 3) 朝の通知をボタン付きで送る（本番・vaultも更新）
python3 triage_main.py --force-classic       # ${PAPER_PYTHON:-python3} を使う環境も可
# 4) スマホSlackで ✅/🗑️ タップ → メッセージが「✅/🗑️済み」に変われば成功
# 5) タップを取り込みに反映
python3 slack_queue.py --sync                 # ✅→[x] / 🗑️→除外
```
以降は自動: 毎朝の `triage_main.py` と「取り込んで」（`promote_check.py --prepare`）が、実行前に自分のタップを同期します。

---

## メモ
- 通知は **1論文=1メッセージ**。多ければ `slack.digest_recent`/`digest_classic` を下げる。
- 🗑️ タップは次回以降**二度と出ない**（`dismissed.json` 永久登録）。× 作業ゼロ。
- Worker/KV は無料枠で研究室ぶんも余裕（write 1,000/日・read 100,000/日）。
- 個人で1つずつ持ちたい人は、A・B・C を自分用に立ててもOK（同じ手順）。
- `wrangler` CLI 派は [`wrangler.toml`](wrangler.toml) で `wrangler deploy` も可。
