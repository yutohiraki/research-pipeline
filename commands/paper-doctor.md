---
description: セットアップの健診（Python・設定・Groq疎通・Obsidian vault 到達・書込テスト）
argument-hint: (引数なし)
allowed-tools: Bash Read
---

`research-paper-triage` が動く状態か健診します。次の Bash を実行し、結果を分かりやすく報告してください（✅/⚠️/❌ で項目ごとに）。

```bash
cd "${CLAUDE_PLUGIN_ROOT}"
CFG="${PAPER_CONFIG:-${CLAUDE_PLUGIN_ROOT}/config.local.yaml}"
${PAPER_PYTHON:-python3} - "$CFG" <<'PY'
import sys, os, json, urllib.request
print("python:", sys.version.split()[0])
try:
    import yaml
except Exception as e:
    print("NG yaml 未導入 → pip install pyyaml"); sys.exit(0)
cfgp = sys.argv[1]
if not os.path.exists(cfgp):
    print(f"NG config が無い: {cfgp} → /paper-setup を実行"); sys.exit(0)
cfg = yaml.safe_load(open(cfgp, encoding="utf-8")) or {}
print("config:", cfgp)

# 研究テーマ
rc = (cfg.get("user", {}) or {}).get("research_context", "") or ""
print("research_context:", "OK" if rc.strip() and "（例）" not in rc else "未設定/例のまま → /paper-setup")

# 採点エンジン
eng = (cfg.get("scoring_engine") or "").lower()
print("scoring_engine:", eng or "未設定")
if eng == "groq":
    key = (cfg.get("groq", {}) or {}).get("api_key") or os.environ.get("GROQ_API_KEY", "")
    if not key:
        print("  groq.api_key: 空 → 未設定なら Ollama/ルールに自動フォールバック")
    else:
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}",
                         "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})
            with urllib.request.urlopen(req, timeout=15) as r:
                json.loads(r.read()); print("  groq 疎通: OK")
        except Exception as e:
            print(f"  groq 疎通: NG ({str(e)[:80]}) → キー有効性/429/UA を確認")

# note-store / vault
ns = (cfg.get("note_store") or "obsidian").lower()
print("note_store:", ns)
pipe = cfg.get("pipeline", {}) or {}
vd = pipe.get("vault_dir", "")
if ns == "obsidian":
    if vd and os.path.isdir(vd):
        w = os.path.join(vd, ".paper_doctor_write_test")
        try:
            open(w, "w").write("ok"); os.remove(w); print("  vault 書込: OK", vd)
        except Exception as e:
            print(f"  vault 書込: NG ({str(e)[:60]})")
        for sub in ("literature_notes", "papers", "concepts", "authors"):
            print(f"    {sub}/:", "有" if os.path.isdir(os.path.join(vd, sub)) else "無(作成推奨)")
        print("    vault CLAUDE.md:", "有(最優先で参照)" if os.path.exists(os.path.join(vd,'CLAUDE.md')) else "無(skill内蔵規約で動作)")
    else:
        print(f"  vault_dir: NG（存在しない）: {vd} → /paper-setup")

# claude CLI
import shutil
cb = (cfg.get("claude", {}) or {}).get("bin", "claude")
print("claude bin:", cb if (shutil.which(cb) or os.path.exists(cb)) else f"未検出({cb}) → which claude で確認")
print("---\n健診おわり。NG/未設定があれば /paper-setup で直す。")
PY
```

報告の最後に、緑（実行可能）なら「`/paper-triage --preview` を試しましょう」、赤があれば「`/paper-setup` で直しましょう」と促してください。
