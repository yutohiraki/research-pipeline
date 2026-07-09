# _legacy — 旧 as-is パイプライン（アーカイブ）

ここは **旧世代（Notion / Google Sheets 中心）のパイプライン**を保管する場所です。
現行フロー（Gmail/OpenAlex 収集 → 関連度採点 → Obsidian `_inbox.md` トリアージ → 採用分だけ深掘りメモ）に
置き換えられ、**現在は使用していません**。削除ではなく隔離＝後戻り可能にするために残しています。

## 中身
| ファイル | 旧役割 |
|---|---|
| `main.py` | 旧オーケストレーション（Gmail→要約→Notion/Sheets/Slack を一括） |
| `gemini_summarizer.py` | 旧要約（名前はGeminiだが実体はGroq。アブスト訳どまり） |
| `sheets_writer.py` | Google Sheets 書き込み（廃止） |
| `slack_notifier.py` | 旧 webhook 方式の Slack 通知（現行は `notify_slack_dm.py`） |
| `notion_enricher.py` | Notion 未読論文の後追いエンリッチ |
| `notion_to_paperpile.py` / `paperpile_importer.py` | Notion ↔ BibTeX(enriched.bib) 連携 |
| `com.research-pipeline.plist` | 旧・毎朝9時に `main.py` を実行（廃止） |
| `com.research-pipeline.promote.plist` | 旧・15分ごとの headless promote（2026-06-15 に `claude -p` 従量課金化で廃止） |

## 注意
- これらは**本線から一切 import されていません**（監査済み）。移動しても現行パイプラインは動きます。
- ⚠️ ここへ移したことで、これらの内部 import（`from notion_writer import …` 等）は**このフォルダからは解決しません**。
  万一再利用する場合はリポジトリ直下にコピーして実行してください。
- `notion_writer.py` は将来の Notion 対応（DISTRIBUTION.md Phase2/3）で使うため**直下に残して**あります。

現行の使い方・仕様は リポジトリ直下の [README.md](../README.md) / [SETUP.md](../SETUP.md) / [SPEC.md](../SPEC.md) / [DISTRIBUTION.md](../DISTRIBUTION.md) を参照。
