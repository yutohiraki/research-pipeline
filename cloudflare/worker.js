/**
 * research-pipeline Slack ボタン受け口（Cloudflare Worker・単一ファイル）
 *
 * 役割:
 *   1) Slack Interactivity（✅取り込む / 🗑️いらない のタップ）を受け、署名検証して KV キューに積む。
 *      タップされたメッセージは response_url で「✅ 取り込み待ち / 🗑️ 二度と出さない」に更新する。
 *   2) Mac から Bearer 認証で GET /pull/want・/pull/dismiss → 溜まったキューを返して**その場でクリア**。
 *
 * 必要な設定（Cloudflare ダッシュボード）:
 *   - KV Namespace を作り、この Worker に **変数名 QUEUE** でバインド。
 *   - 環境変数(Secret): SLACK_SIGNING_SECRET（Slackアプリの Signing Secret）
 *                       PULL_SECRET（Mac が pull する時の任意の合言葉。config.yaml と一致させる）
 *   - Slackアプリ → Interactivity & Shortcuts の Request URL に、この Worker の URL を設定。
 *
 * ボタンの value は JSON 文字列: {"k":"<candidate_id>","t":"<title>","a":"want"|"dismiss"}
 *   k = 一意キー（"doi:..." または "title:..."）。Mac 側はこれで inbox 行/除外を特定する。
 */

const QUEUES = { want: "q:want", dismiss: "q:dismiss" };

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // --- health check ---
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("research-pipeline slack worker: ok", { status: 200 });
    }

    // --- Mac からのキュー取得（取得＋クリア）---
    if (request.method === "GET" && url.pathname.startsWith("/pull/")) {
      const kind = url.pathname.slice("/pull/".length); // want | dismiss
      if (!QUEUES[kind]) return json({ error: "unknown queue" }, 404);
      const auth = request.headers.get("Authorization") || "";
      if (!env.PULL_SECRET || auth !== `Bearer ${env.PULL_SECRET}`) {
        return json({ error: "unauthorized" }, 401);
      }
      const raw = await env.QUEUE.get(QUEUES[kind]);
      const items = raw ? JSON.parse(raw) : [];
      await env.QUEUE.put(QUEUES[kind], "[]"); // 取得したら空にする
      return json({ items });
    }

    // --- Slack Interactivity（ボタンタップ）---
    if (request.method === "POST") {
      const body = await request.text();
      const ts = request.headers.get("X-Slack-Request-Timestamp") || "";
      const sig = request.headers.get("X-Slack-Signature") || "";
      if (!(await verifySlack(env.SLACK_SIGNING_SECRET, ts, body, sig))) {
        return new Response("bad signature", { status: 401 });
      }
      // 5分より古いリクエストは拒否（リプレイ対策）
      if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) {
        return new Response("stale", { status: 401 });
      }

      const params = new URLSearchParams(body);
      const payload = JSON.parse(params.get("payload") || "{}");
      const action = (payload.actions && payload.actions[0]) || {};
      let v;
      try { v = JSON.parse(action.value || "{}"); } catch { v = {}; }
      const kind = v.a === "dismiss" ? "dismiss" : "want";

      // KV キューへ追記（read-modify-write。単一ユーザ想定で十分）
      const key = QUEUES[kind];
      const raw = await env.QUEUE.get(key);
      const items = raw ? JSON.parse(raw) : [];
      items.push({
        k: v.k || "", t: v.t || "",
        user: (payload.user && payload.user.id) || "",
        ts: Math.floor(Date.now() / 1000),
      });
      await env.QUEUE.put(key, JSON.stringify(items));

      // タップされたメッセージを更新（response_url は事前認証済み）
      const label = kind === "dismiss"
        ? `🗑️ *二度と出さない* に登録: ${v.t || ""}`
        : `✅ *取り込み待ち* に追加: ${v.t || ""}（Claude で「取り込んで」）`;
      if (payload.response_url) {
        ctx.waitUntil(fetch(payload.response_url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replace_original: true, text: label }),
        }));
      }
      return new Response("", { status: 200 });
    }

    return new Response("not found", { status: 404 });
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status, headers: { "Content-Type": "application/json" },
  });
}

// Slack 署名検証: X-Slack-Signature == 'v0=' + HMAC_SHA256(signingSecret, `v0:${ts}:${body}`)
async function verifySlack(secret, ts, body, sig) {
  if (!secret || !ts || !sig) return false;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`v0:${ts}:${body}`));
  const hex = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return timingSafeEqual(`v0=${hex}`, sig);
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}
