"""
triage.py
TRIAGE: 各 candidate に「関連度スコア(0-100)」「1行理由」「一言サマリ」「タグ」を付ける。

SPEC.md §4 STAGE2。**有料API を使わず Claude Code（claude -p）で処理**（追加課金なし）。
全候補を1回の `claude -p` 呼び出しでまとめて採点する（呼び出し回数を最小化）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request


def claude_env(claude_cfg: dict = None) -> dict:
    """claude -p をユーザーのサブスク認証で動かすための環境を作る。
    - 親プロセス(対話中のClaude Codeセッション等)由来の認証ゲートウェイ変数を除去
    - config に oauth_token があれば CLAUDE_CODE_OAUTH_TOKEN として注入
      （launchd 等のヘッドレス実行用。`claude setup-token` で発行＝サブスク内・課金なし）
    """
    env = dict(os.environ)
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
              "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE"):
        env.pop(k, None)
    tok = (claude_cfg or {}).get("oauth_token", "") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if tok:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    return env


def _build_prompt(candidates: list, research_context: str, themes: list) -> str:
    theme_list = [t for t in themes if t != "その他"]
    themes_str = ", ".join(theme_list)
    # id は配列の通し番号(1始まり)。モデルが長い文字列idを写し間違える事故を防ぐ。
    items = [
        {
            "id": i + 1,
            "title": c.title,
            "year": c.year,
            "abstract": (c.abstract or "")[:1200],
        }
        for i, c in enumerate(candidates)
    ]
    papers_json = json.dumps(items, ensure_ascii=False)
    n = len(items)

    return f"""あなたは研究者のトリアージ補助です。各論文が下記の研究者の関心にどれだけ関連するかを評価してください。

研究者の関心（これだけを関連度の基準にする。無理に関連づけない）:
{research_context}

タグ語彙（tags はこの中からのみ選ぶ。該当なしは空配列）:
[{themes_str}]

採点ルール（正直に・甘くしない）:
- score は 0〜100 の整数。強く直結=80以上、関連あり=55〜75、ややかすめる=35〜50、無関係=20以下。
- **研究者の中心テーマは2本柱。どちらかに該当すれば総説でも55以上（明確なら75以上）**:
  (A) 魚類の音響系 = 魚類の発音/生物音響/魚類コーラス/Sciaenidae(ニベ科・グチ類)の音/PAM/**背景ノイズが魚の鳴音に与える影響**。
  (B) 環境DNA系 = **eDNA/メタバーコーディングによる魚類・生物群集解析（特に駿河湾・深海・表層広域）**。←音響でなくてもeDNAなら中心テーマなので高評価する。
- 一方、海洋哺乳類(鯨・イルカ・アザラシ)・鳥・コウモリ・昆虫・陸上動物・人間の消費/疫学など、(A)(B)いずれにも当たらないものは必ず20以下（"音響""海洋"の語が出ても対象が魚でなければ無関係）。

要約(one_liner)と理由(reason)の書き方（重要・品質を上げる）:
- **必ず自然な日本語**（英語・中国語・機械翻訳調は禁止）。
- one_liner は「**何を対象に・どんな手法で・何を明らかにした/何が主眼か**」を具体的に1〜2文。
  対象種・海域・データ種別・手法名・主な結果など、**具体語**を必ず入れる。
  - 良い例:「駿河湾の深海堆積物のeDNAメタバーコーディングで魚類群集を解析し、水深で群集組成が変わることを示した。」
  - 悪い例（禁止・抽象的すぎ）:「環境DNAを用いた研究。」「〜に関する研究である。」
- 研究者テーマとの距離が遠い場合も、**内容の要約を書いてから**「テーマ①(魚類音響)/⑤(eDNA)との関連は薄い」等と一言添える。
- 情報が乏しく要約できない時は、推測で埋めず「タイトルのみ・要約保留」とだけ書く。

論文一覧(JSON, id は通し番号):
{papers_json}

出力は次の形の **JSON オブジェクトのみ**（前後に文章・コードフェンスを付けない）。
results には入力の**全{n}件**を、入力と同じ id を付けて**漏れなく**含める:
{{"results": [{{"id": 1, "score": <0-100整数>, "reason": "<日本語1行>", "one_liner": "<日本語1-2文>", "tags": [<語彙から0個以上>]}}]}}"""


def _run_claude(prompt: str, claude_cfg: dict) -> str:
    claude_bin = claude_cfg.get("bin", "claude")
    model = claude_cfg.get("triage_model", "haiku")
    cmd = [claude_bin, "-p", prompt, "--model", model, "--output-format", "text"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                          env=claude_env(claude_cfg))
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()[:300]
        raise RuntimeError(f"claude -p 失敗(rc={proc.returncode}): {msg}")
    return proc.stdout.strip()


def _parse_json_array(raw: str) -> list:
    """モデル出力から「辞書のリスト」を頑健に取り出す。
    対応: 素の[...] / {"data":[...]} 等のラッパ / 単一オブジェクト / コードフェンス。
    余計な文字列要素は捨てる（_apply_results が r.get で落ちないように）。"""
    raw = (raw or "").strip()
    if "```" in raw:
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
    obj = None
    try:
        obj = json.loads(raw)                      # まず全体をJSONとして解釈
    except Exception:
        s, e = raw.find("["), raw.rfind("]")        # ダメなら最外の配列を切り出す
        if s != -1 and e != -1 and e > s:
            try:
                obj = json.loads(raw[s:e + 1])
            except Exception:
                obj = None
    if obj is None:
        raise ValueError("JSON parse failed")
    if isinstance(obj, dict):
        # 1) 既知ラッパキー {"results":[...]} / {"data":[...]} 等
        for k in ("results", "data", "papers", "items", "scores", "output", "list",
                  "evaluations", "papers_list", "articles"):
            if isinstance(obj.get(k), list):
                obj = obj[k]
                break
        else:
            # 2) 未知キーでも「値がリスト」の項目があればそれを採用
            list_vals = [v for v in obj.values() if isinstance(v, list)]
            if len(list_vals) == 1:
                obj = list_vals[0]
            # 3) id をキーにした辞書 {"1":{...},"2":{...}} → id を注入してリスト化
            elif obj and all(isinstance(v, dict) for v in obj.values()):
                out = []
                for kk, vv in obj.items():
                    if "id" not in vv:
                        try:
                            vv = {**vv, "id": int(str(kk).strip())}
                        except (TypeError, ValueError):
                            pass
                    out.append(vv)
                obj = out
            else:
                obj = [obj]                         # 単一オブジェクト → 1要素リスト
    if not isinstance(obj, list):
        return []
    return [r for r in obj if isinstance(r, dict)]  # 辞書要素だけ


# ──────────────────────────────────────────────────────────────────────────
# 採点エンジン: ローカル Ollama（既定）/ ルールベース保険 / claude（任意）
#   設計: 必ず先にルールベースで非ゼロのベースラインを当て、その上に LLM 採点を
#   上書きする。LLM が落ちても「全件スコア0」にはならない（旧仕様の弱点を解消）。
# ──────────────────────────────────────────────────────────────────────────

# 「核」キーワード（これが無ければ高得点にしない）＝魚類音響 or eDNA に直結
_CORE = ["fish sound", "fish vocal", "fish chorus", "fish call", "fish acoustic",
         "fish bioacoustic", "soniferous", "sound production by fish", "sciaenid",
         "croaker", "drumming", "sonic muscle", "spawning sound", "fish drum",
         "environmental dna", "edna", "metabarcoding", "mifish", "sedimentary dna"]
# 魚の文脈（核が無くても魚なら少し加点）
_FISH_CTX = ["fish ", "fishes", "reef fish", "teleost", "larval fish", "fisher",
             "larimichthys", "spawning aggregation"]
# 二次キーワード（核 or 魚文脈があるときに効く）。(語群, 重み)
_SECONDARY = {
    "soundscape": (["soundscape", "passive acoustic", "acoustic monitoring", "ambient noise",
                    "anthropogenic noise", "vessel noise", "underwater noise", "masking",
                    "acoustic index", "hydrophone"], 0.7),
    "storm": (["typhoon", "cyclone", "hurricane", "storm", "upwelling", "marine heatwave",
               "sea surface temperature"], 0.8),
    "deepsea": (["deep-sea", "deep sea", "mesopelagic", "bathyal", "suruga", "vertical distribution"], 0.6),
    "ml": (["machine learning", "deep learning", "neural network", "random forest",
            "convolutional", "classifier"], 0.4),
}
_MARINE_GENERIC = ["marine", "ocean", "underwater", "coastal", "reef", "estuar", "aquatic", "sea "]
# 海洋哺乳類: 魚の核が無ければ減点（ユーザーは魚が対象。鯨類・鰭脚類は対象外）
_MAMMAL = ["whale", "cetacean", "dolphin", "porpoise", "pinniped", " seal", "sea lion",
           "manatee", "beluga", "odontocete", "baleen", "sperm whale"]
# 明確にテーマ外（核が無ければ強く減点）
_OFFTOPIC = ["lion", "polar bear", " bear ", "bat ", " bats", "bird", "frog", "insect",
             "rabies", "leptospiros", "shellfish poison", "consumption", "licence", "license",
             "blood cell", "respiratory rate", "wildfire", "crayfish", "dung beetle", "serum",
             "ultrastructure", "citri", "terrestrial", "zoolog"]


def _text_of(c) -> str:
    return ((c.title or "") + " " + (c.abstract or "")).lower()


def _matched_keywords(t: str) -> list:
    out = [k.strip() for k in _CORE if k in t]
    for _g, (kws, _w) in _SECONDARY.items():
        out += [k.strip() for k in kws if k in t]
    return sorted(set(out))


def _rule_based(candidates: list, themes: list):
    """LLM不在/失敗時の保険＆前さばき。魚/eDNAの核が無ければ高得点にしない厳しめ採点。
    必ず非ゼロ整数・日本語テンプレ要約を付ける（全件0を避ける）。"""
    for c in candidates:
        t = _text_of(c)
        core = sum(1 for k in _CORE if k in t)
        fishctx = any(k in t for k in _FISH_CTX)
        score = 0.0
        # 核（魚類音響/eDNA）: 強く加点
        score += min(core, 4) * 20            # 最大 +80
        # 二次キーワード: 核 or 魚文脈があるときに本効力、無いと弱い
        gain = 1.0 if (core or fishctx) else 0.25
        for _g, (kws, w) in _SECONDARY.items():
            n = sum(1 for k in kws if k in t)
            if n:
                score += gain * w * (8 + 7 * min(n, 3))
        if fishctx:
            score += 12
        if any(h in t for h in _MARINE_GENERIC):
            score += 4
        # 減点: 海洋哺乳類・テーマ外（魚/eDNAの核が無いとき）
        if core == 0 and any(m in t for m in _MAMMAL):
            score -= 45
        if core == 0 and any(o in t for o in _OFFTOPIC):
            score -= 50
        # 核も魚文脈も無ければ上限を抑える（高関連にはしない）
        if core == 0 and not fishctx:
            score = min(score, 30)
        c.relevance_score = int(max(0, min(100, round(score))))
        c.relevance_reason = "キーワード自動判定（LLM要約なし）"
        # LLM要約が付かなかった時だけ表示される保険テキスト。
        # 以前の「【自動・要LLM】」は分かりにくかったので、素直な日本語に変更。
        # 通常は _score_with_* が本物の要約で上書きする（取りこぼし時のみ残る）。
        kws = _matched_keywords(t)
        if kws:
            c.one_liner = f"（自動分類・要約保留）関連語: {', '.join(kws[:4])}".strip()
        else:
            c.one_liner = "（自動分類・要約保留）テーマ関連語は薄め"
        tags = [th for th in themes if th != "その他" and th.lower() in t]
        if tags:
            c.tags = tags


def _run_ollama(prompt: str, ollama_cfg: dict) -> str:
    """ローカル Ollama (/api/generate) を叩く。課金・ネット送信なし・無制限。
    format=json で有効なJSONを強制（小型モデルの暴走/不正JSONを防ぐ）。"""
    host = (ollama_cfg.get("host") or "http://localhost:11434").rstrip("/")
    payload = {
        "model": ollama_cfg.get("model", "qwen2.5:3b"),
        "prompt": prompt,
        "stream": False,
        "format": "json",                # 有効なJSONで出力＆完了で停止（暴走防止）
        "options": {
            "temperature": 0.1,
            "num_ctx": int(ollama_cfg.get("num_ctx", 4096)),
            "num_predict": int(ollama_cfg.get("num_predict", 3072)),  # 出力上限（暴走防止）
        },
    }
    req = urllib.request.Request(
        host + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=int(ollama_cfg.get("timeout", 180))) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out.get("response", "")


def _run_groq(prompt: str, groq_cfg: dict) -> str:
    """Groq 無料枠（OpenAI互換API・LLaMA3.3 70B等）を叩く。課金なし・超過は429で止まるだけ。
    429(レート制限)は指定回数までバックオフ再試行する。"""
    key = groq_cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("groq.api_key 未設定")
    model = groq_cfg.get("model", "llama-3.3-70b-versatile")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    retries = int(groq_cfg.get("retries", 4))
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}",
                     # ブラウザUA必須: 無いと Cloudflare が Python-urllib を error 1010 で弾く
                     "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0 Safari/537.36"})
        try:
            with urllib.request.urlopen(req, timeout=int(groq_cfg.get("timeout", 120))) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            return out["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                wait = float(e.headers.get("retry-after", "") or (2 ** attempt))
                time.sleep(min(wait, 20))
                continue
            raise


def _apply_one(r: dict, c, valid_themes: set):
    """1件の結果 dict を candidate c に反映。"""
    try:
        c.relevance_score = max(0, min(100, int(r.get("score", 0) or 0)))
    except (TypeError, ValueError):
        pass
    rl = str(r.get("reason", "")).strip()
    if rl:
        c.relevance_reason = rl
    ol = str(r.get("one_liner", "")).strip()
    if ol:
        c.one_liner = ol
    tags = r.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    ftags = [t for t in tags if t in valid_themes]
    if ftags:
        c.tags = ftags


def _apply_results(results: list, chunk: list, valid_themes: set) -> set:
    """results を chunk に適用し、**適用できた chunk インデックス集合**を返す。
    1) まず id(通し番号1始まり)で対応付け。
    2) id で埋まらず、件数が一致するなら**並び順で補完**（モデルがidを落とす事故に強い）。
    返り値で「取りこぼした件」を呼び出し側が個別再試行できる。"""
    applied = set()
    for r in results:
        try:
            idx = int(r.get("id", 0)) - 1
        except (TypeError, ValueError):
            idx = -1
        if 0 <= idx < len(chunk) and idx not in applied:
            _apply_one(r, chunk[idx], valid_themes)
            applied.add(idx)
    # id 対応が不完全 & 件数一致 → 並び順で残りを埋める
    if len(applied) < len(chunk) and len(results) == len(chunk):
        for i, r in enumerate(results):
            if i not in applied:
                _apply_one(r, chunk[i], valid_themes)
                applied.add(i)
    return applied


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), max(1, n)):
        yield lst[i:i + n]


def _score_with_ollama(candidates: list, ollama_cfg: dict,
                       research_context: str, themes: list):
    """7Bの文脈長対策でバッチ分割し、各バッチをローカルOllamaで採点して上書き。
    バッチ失敗時はルールベースのベースライン値を維持（全件0にしない）。"""
    valid_themes = set(themes)
    batch = int(ollama_cfg.get("batch", 10))
    ok = 0
    chunks = list(_chunks(candidates, batch))
    for i, chunk in enumerate(chunks, 1):
        prompt = _build_prompt(chunk, research_context, themes)
        try:
            results = _parse_json_array(_run_ollama(prompt, ollama_cfg))
            _apply_results(results, chunk, valid_themes)
            ok += 1
        except Exception as e:
            print(f"  [Triage/Ollama] バッチ{i}/{len(chunks)}失敗（ルールベース維持）: {str(e)[:120]}")
    print(f"  [Triage/Ollama] {ok}/{len(chunks)} バッチ成功（model={ollama_cfg.get('model','qwen2.5:7b')}）")


def _score_with_groq(candidates: list, groq_cfg: dict,
                     research_context: str, themes: list):
    """Groq無料枠(LLaMA3.3 70B)でバッチ採点。70Bなので日本語・判定が高品質。
    レート制限(TPM/RPM)に配慮しバッチ間に小休止。失敗バッチはルールベース維持。"""
    valid_themes = set(themes)
    batch = int(groq_cfg.get("batch", 4))
    pause = float(groq_cfg.get("pause", 2.0))
    ok = 0
    missed_total = 0
    chunks = list(_chunks(candidates, batch))
    for i, chunk in enumerate(chunks, 1):
        prompt = _build_prompt(chunk, research_context, themes)
        applied = set()
        try:
            applied = _apply_results(_parse_json_array(_run_groq(prompt, groq_cfg)),
                                     chunk, valid_themes)
            ok += 1
        except Exception as e:
            print(f"  [Triage/Groq] バッチ{i}/{len(chunks)}失敗（1件ずつ再試行）: {str(e)[:120]}")
        # 取りこぼした件（バッチ失敗 or モデルがidを落とした）は1件ずつ再試行し、
        # 【自動・要LLM】プレースホルダをできる限り本物の要約で置き換える。
        missing = [c for j, c in enumerate(chunk) if j not in applied]
        for c in missing:
            try:
                got = _apply_results(_parse_json_array(_run_groq(
                    _build_prompt([c], research_context, themes), groq_cfg)), [c], valid_themes)
                if not got:
                    missed_total += 1
            except Exception:
                missed_total += 1
            time.sleep(min(pause, 1.0))
        if i < len(chunks):
            time.sleep(pause)
    tail = f"・要約補完できず {missed_total} 件（ルールベース維持）" if missed_total else ""
    print(f"  [Triage/Groq] {ok}/{len(chunks)} バッチ成功{tail}"
          f"（model={groq_cfg.get('model','llama-3.3-70b-versatile')}）")
    return ok


def _score_with_claude(candidates: list, claude_cfg: dict,
                       research_context: str, themes: list):
    """任意エンジン: claude -p で1回バッチ採点（要 oauth_token・2026-06-15以降メーター課金）。"""
    valid_themes = set(themes)
    prompt = _build_prompt(candidates, research_context, themes)
    try:
        _apply_results(_parse_json_array(_run_claude(prompt, claude_cfg)), candidates, valid_themes)
    except Exception as e:
        print(f"  [Triage/claude] 採点失敗（ルールベース維持）: {str(e)[:120]}")


def score_all(cfg_or_claude: dict, *args, **kwargs):
    """全 candidate を採点（破壊的更新）。
    新シグネチャ: score_all(candidates, cfg, research_context, themes)
      cfg = config全体（scoring_engine / ollama / claude を参照）
    旧シグネチャ: score_all(candidates, claude_cfg, research_context, themes) も後方互換で受ける。
    """
    # 引数の互換処理（第1引数が candidates）
    candidates = cfg_or_claude
    cfg = args[0] if len(args) >= 1 else kwargs.get("cfg", {})
    research_context = args[1] if len(args) >= 2 else kwargs.get("research_context", "")
    themes = args[2] if len(args) >= 3 else kwargs.get("themes", ["その他"])
    if not candidates:
        return candidates

    # 旧呼び出し（claude_cfgだけ）の互換: claude設定っぽい辞書なら包む
    if not any(k in cfg for k in ("scoring_engine", "ollama", "claude", "user")):
        cfg = {"claude": cfg, "scoring_engine": "claude"}
    engine = (cfg.get("scoring_engine") or "ollama").lower()

    # 1) ルールベースのベースライン（必ず非ゼロ＋日本語テンプレ要約）
    _rule_based(candidates, themes)
    if engine in ("none", "rule", "rules"):
        print("  [Triage] エンジン=ルールベースのみ")
        return candidates

    # 2) LLM採点で上書き
    if engine == "groq":
        ok = _score_with_groq(candidates, cfg.get("groq", {}), research_context, themes)
        if not ok and cfg.get("ollama"):
            # Groqが全滅（キー失効/403等）→ ローカルOllamaに自動フォールバック
            print("  [Triage] Groq不通→Ollamaにフォールバック")
            _score_with_ollama(candidates, cfg.get("ollama", {}), research_context, themes)
    elif engine == "ollama":
        _score_with_ollama(candidates, cfg.get("ollama", {}), research_context, themes)
    elif engine == "claude":
        _score_with_claude(candidates, cfg.get("claude", {}), research_context, themes)
    else:
        print(f"  [Triage] 未知のscoring_engine={engine}→ルールベースのまま")
    return candidates


if __name__ == "__main__":
    # 単体テスト: 古典を数件取得して採点
    import yaml
    from openalex_classic import fetch_classic_for_query

    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mailto = cfg.get("unpaywall", {}).get("email", "")
    cands = fetch_classic_for_query("passive acoustic monitoring fish", "PAM", 4, mailto=mailto)
    research = cfg.get("user", {}).get("research_context", "")
    themes = cfg.get("sheets", {}).get("themes", [])
    score_all(cands, cfg.get("claude", {}), research, themes)
    for c in cands:
        print(f"[{c.relevance_score:>3}] {c.first_author} {c.year} | {c.one_liner[:60]}")
        print(f"      理由: {c.relevance_reason[:70]} | tags={c.tags}")
