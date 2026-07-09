"""
groq_summarizer.py (旧: gemini_summarizer.py)
Groq API で論文要約・構造化情報抽出・テーマ振り分けを行う
"""

import json
import re
import time
import urllib.error
import urllib.request


def _call_groq(api_key: str, model: str, prompt: str, retries: int = 3) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0.1,
    }).encode("utf-8")

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt * 5
                print(f"  [Groq API] レート制限。{wait}秒待ってリトライ ({attempt+1}/{retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Groq API: リトライ上限に達しました")


def assign_tags(paper: dict, groq_cfg: dict, themes: list) -> list:
    """タイトル+アブストラクトからタグのみをGroqで高速判定する（フル要約なし）"""
    api_key = groq_cfg["api_key"]
    model = groq_cfg.get("model", "llama-3.3-70b-versatile")
    candidate_themes = [t for t in themes if t != "その他"]
    themes_str = ", ".join(candidate_themes)
    title = paper.get("title", "")
    body = (paper.get("abstract", "") or paper.get("raw_body", "") or paper.get("summary", ""))[:600]

    prompt = f"""Based on the paper below, select all applicable tags from this list: [{themes_str}]
Output ONLY a comma-separated list of matching tags (English or Japanese as-is from the list). If none match, output: その他

Title: {title}
Abstract: {body}"""

    try:
        raw = _call_groq(api_key, model, prompt)
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        valid = [t for t in tags if t in themes]
        return valid if valid else ["その他"]
    except Exception:
        return ["その他"]


def enrich_paper(paper: dict, groq_cfg: dict, themes: list, research_context: str = "") -> dict:
    api_key = groq_cfg["api_key"]
    model = groq_cfg.get("model", "llama-3.3-70b-versatile")
    themes_str = ", ".join(themes)
    title = paper.get("title", "")
    body = paper.get("raw_body", "")[:6000]

    prompt = f"""Analyze the following paper and output a single JSON object. All values in Japanese except author names, tags, and source.

STRICT RULES:
- "summary": Translate the abstract into Japanese AS-IS. Do NOT add any interpretation, context, or connection to other topics. Translate only what is written. If no abstract is available, write an objective 4-6 sentence summary based solely on the paper content.
- "relevance": Write a connection to the researcher's background ONLY if the paper itself explicitly mentions or directly relates to those topics. If the connection is weak or absent, write "直接的な関連は低い。" Never fabricate or force a connection to eDNA or PAM if the paper does not discuss them.

Title: {title}
Content: {body}

Researcher's background (use ONLY for the relevance field):
{research_context}

Output exactly this JSON (no extra text):
{{
  "authors_clean": "全著者名をカンマ区切りで（わかる範囲で全員）",
  "published_date": "出版年月日をYYYY-MM-DD形式で。月日不明ならYYYY-01-01。不明なら空文字",
  "summary": "アブストラクトをそのまま忠実に日本語訳。内容を変えたり補足したりしない。アブストラクトがない場合のみ客観的な要約",
  "methods": "使用した手法・機器・解析ツール・アルゴリズムの詳細（3〜5文）。ツール名・ソフトウェア名・モデル名を必ず具体的に記載",
  "sampling": "調査地点・対象種・サンプル数など",
  "main_results": "主要な数値・発見・比較結果を含む詳細な結果（4〜6文）",
  "novelty": "この研究の新規性・独自の貢献・既存研究との差別化ポイント（2〜3文）",
  "limitations": "この研究の限界・制約・注意点（2〜3文）",
  "future_work": "著者が示す今後の課題・研究の方向性（2〜3文）",
  "data_availability": "データ・コードの公開状況（例: GitHubで公開、Zenodo DOI付き、公開なし、不明）",
  "relevance": "論文の内容に基づき研究者の背景との直接的な関連のみ記載。関連が薄い場合は「直接的な関連は低い。」",
  "tags": "Select all that apply from [{themes_str}], comma-separated",
  "source": "Journal or publisher name (not Google Scholar or Web of Science)",
  "slack_summary": "2文の客観的な要約"
}}"""

    raw = _call_groq(api_key, model, prompt)
    raw = raw.strip()

    # コードブロック除去
    if "```" in raw:
        raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()

    # JSON部分を抽出
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        enriched = json.loads(raw)
    except json.JSONDecodeError:
        enriched = {
            "authors_clean": paper.get("authors", ""),
            "published_date": "",
            "summary": "要約失敗",
            "methods": "",
            "sampling": "",
            "main_results": "",
            "novelty": "",
            "limitations": "",
            "future_work": "",
            "data_availability": "",
            "relevance": "",
            "tags": "その他",
            "source": paper.get("source", ""),
            "slack_summary": title[:60],
        }

    # tags を文字列→リストに変換
    raw_tags = enriched.get("tags", "")
    if isinstance(raw_tags, str):
        enriched["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]

    # title を書き換えないよう元のタイトルを保護
    original_title = paper.get("title", "")
    enriched.pop("title", None)
    enriched.pop("title_ja", None)

    paper.update(enriched)
    paper["title"] = original_title
    return paper
