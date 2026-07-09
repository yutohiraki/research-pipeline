---
description: research-pipeline の初期セットアップ（研究テーマ・Groqキー・Obsidian vault を対話で設定）
argument-hint: (引数なし)
allowed-tools: Bash Read Edit Write
---

`research-paper-triage` プラグインを、この後輩の環境で使えるようにセットアップします。

**paper-pipeline-setup スキルの手順に厳密に従ってください。** 要点:

1. `config.example.yaml` を `config.local.yaml` にコピー（無ければ）。以降このファイルを編集する（秘匿情報を含むので **git 管理外・共有しない**）。
2. 必須3項目だけ先に埋める:
   - **研究テーマ** → `user.research_context`（本人の言葉に置換）＋ `classic.queries`（主要KW 3〜5個から生成）
   - **採点エンジンと Groq キー** → 既定 `scoring_engine: groq`。console.groq.com で各自が無料キー発行（**先輩のキーを使い回さない**）。キーが無ければ `rule` で開始可。
   - **Obsidian vault パス** → `pipeline.vault_dir` と `pipeline.inbox_path`。`which claude` で `claude.bin` も合わせる。
3. Gmail / Slack / Notion は任意（既定オフ）。古典（OpenAlex・認証不要）だけでも動くので、まず飛ばして「動いた」を体験させる。
4. 最後に `/paper-doctor` で健診し、`triage_main.py --preview` でハッピーパスを1回通す。

⚠️ もし後輩が Claude Code ではなく **ChatGPT/Gemini しか使えない** なら、採点は代替できるが深掘りは copypaste で単一メモに劣化する。[SETUP.md](../SETUP.md) の該当節へ案内すること。
