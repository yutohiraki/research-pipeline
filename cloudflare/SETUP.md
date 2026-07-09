# Slack ぽちぽち セットアップ手順（Cloudflare Worker）

Slack の ✅取り込む / 🗑️いらない ボタンを、Mac が寝ていても拾えるようにする。所要 15〜20分・全部無料。

全体像:
```
朝  Mac → Slackに1論文=1メッセージ（✅/🗑️ボタン）を投稿
昼  スマホ Slackで ✅/🗑️ をタップ
    → Cloudflare Worker が署名検証して KV に記録＋メッセージを「✅/🗑️済み」に更新
夜  Remote Controlで「取り込んで」→ Mac が Worker からキュー取得
       ✅ → inboxを [x] に → 深掘り取り込み
       🗑️ → dismissed.json に登録＋inboxから削除（＝×作業ゼロ）
```

---

## A. Cloudflare 側（Worker を置く）

1. **無料アカウント作成**: https://dash.cloudflare.com/sign-up （クレカ不要）。
2. **KV 名前空間を作る**: ダッシュボード左メニュー **Storage & Databases → KV → Create a namespace**。名前は `research-queue` 等。作成。
3. **Worker を作る**: **Workers & Pages → Create → Workers → Create Worker**。名前 `research-slack` 等 → **Deploy**（雛形が出る）→ **Edit code**。
4. **コードを貼る**: エディタの中身を全消しして、このリポジトリの [`worker.js`](worker.js) の**全文を貼り付け** → **Deploy**。
5. **KV をバインド**: Worker の **Settings → Bindings → Add → KV namespace**。
   - Variable name: **`QUEUE`**（この名前で固定）
   - KV namespace: さっき作った `research-queue`
   - Save。
6. **Secret を2つ登録**: **Settings → Variables and Secrets → Add**（type=Secret）。
   - `SLACK_SIGNING_SECRET` … （下の B-2 で取得する Slack の Signing Secret）
   - `PULL_SECRET` … 好きな長い合言葉（例: `openssl rand -hex 24` の出力）。**メモしておく**。
   - Save し、Worker を **Deploy** し直す。
7. **Worker の URL を控える**: Worker のトップに出る `https://research-slack.<あなた>.workers.dev`。

---

## B. Slack 側（ボタンの送り先を Worker に）

Slack App 管理画面: https://api.slack.com/apps → 既存の「論文Bot」アプリを開く。

1. **Interactivity を ON**: 左メニュー **Interactivity & Shortcuts** → トグル ON →
   **Request URL** に **Worker の URL**（A-7）をそのまま貼る → **Save Changes**。
2. **Signing Secret を取得**: 左メニュー **Basic Information → App Credentials → Signing Secret** の「Show」→ コピー →
   これを A-6 の `SLACK_SIGNING_SECRET` に入れて Worker を Deploy。
3. （権限）Bot に `chat:write` があればOK（既に DM 通知が飛んでいるなら付いています）。

---

## C. Mac 側（config.yaml）

`config.yaml` の `slack:` を編集:
```yaml
slack:
  interactive: true                      # ← ボタン付き通知を有効化
  worker_url: "https://research-slack.<あなた>.workers.dev"   # A-7
  pull_secret: "……"                     # A-6 の PULL_SECRET と“完全一致”
```

---

## D. 動作テスト

```bash
cd /Users/tonn/Desktop/Project/research-pipeline
# 1) Worker 疎通（ok と出れば生きてる）
curl -s https://research-slack.<あなた>.workers.dev/ ; echo
# 2) pull 認証（[]（空配列）が返ればOK。401なら pull_secret 不一致）
curl -s -H "Authorization: Bearer <PULL_SECRET>" https://research-slack.<あなた>.workers.dev/pull/want ; echo
# 3) 朝の通知をボタン付きで手動送信（Slackを確認）
/Users/tonn/matlab_pyenv312/bin/python3 triage_main.py --preview --no-slack   # まず中身確認
#    本番でボタン通知したい時（vaultも更新される）:
#    /Users/tonn/matlab_pyenv312/bin/python3 triage_main.py --force-classic
# 4) スマホSlackで ✅/🗑️ をタップ → メッセージが「✅/🗑️済み」に変われば成功
# 5) タップ結果を取り込みに反映:
/Users/tonn/matlab_pyenv312/bin/python3 slack_queue.py --sync    # ✅→[x] / 🗑️→除外
```

以降は自動:
- 毎朝の `triage_main.py` が「前日までのタップ」を反映してから inbox を作り、新着をボタン付きで通知。
- `promote_check.py --prepare`（＝Remote Controlで「取り込んで」した時）も先に同期するので、✅した論文がそのまま取り込み対象になる。

---

## メモ
- 通知は **1論文=1メッセージ**。多いと感じたら `config.yaml` の `slack.digest_recent`/`digest_classic` を下げる。
- 🗑️ をタップした論文は次回以降**二度と出ない**（`dismissed.json` 永久登録）。× を付ける作業は不要。
- Worker/KV は無料枠（1日 write 1,000・read 100,000）で個人用途は余裕。
- `wrangler` CLI 派は [`wrangler.toml`](wrangler.toml) を使って `wrangler deploy` でも可。
