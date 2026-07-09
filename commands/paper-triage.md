---
description: 論文を収集して関連度採点し、Obsidian の _inbox.md を更新する（毎朝の自動処理を手動実行）
argument-hint: [--preview] [--force-classic] [--no-slack] [--no-score]
allowed-tools: Bash Read
---

論文トリアージ（収集→採点→inbox 更新）を実行します。

次の Bash を実行してください（config は `PAPER_CONFIG` があればそれ、無ければプラグイン同梱の `config.local.yaml`）。ユーザーが渡した引数 `$ARGUMENTS` をそのまま付ける（既定は本番実行・引数なし）:

```bash
cd "${CLAUDE_PLUGIN_ROOT}"
${PAPER_PYTHON:-python3} triage_main.py --config "${PAPER_CONFIG:-${CLAUDE_PLUGIN_ROOT}/config.local.yaml}" $ARGUMENTS
```

実行後:
- 生成された `_inbox.md`（本番は vault 直下 / `--preview` は `/tmp/_inbox.md`）を読み、**関連度上位の新着を数件、スコア＋一言サマリ付きで要約**して報告する。
- 何件の新着／古典が載ったか、採点エンジン（groq/ollama/rule）が何を使ったかを伝える。
- 次アクション（要る論文に `[x]` を付けて `/paper-import` で取り込む）を一言添える。

補足:
- 初回や動作確認は `--preview`（vault に触れず `/tmp/_inbox.md` に出力）を勧める。
- 古典（高被引用）は本来 週1（月曜）。今すぐ古典も見たいなら `--force-classic`。
- Groq が 429/未設定なら自動で Ollama→ルールベースに落ちる（全件0にはならない）。エラー時はログの該当行を示す。
