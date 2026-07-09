"""
gmail_fetcher.py
Gmail API でアラートメールを取得し、論文情報を抽出する
"""

import base64
import datetime
import imaplib
import os
import re
from email import message_from_bytes
from email.header import decode_header, make_header
from html.parser import HTMLParser

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


# ──────────────────────────────────────────────
# 取得方式の自動切替（IMAP 推奨 / 旧 Gmail API）
# ──────────────────────────────────────────────

def collect_alert_emails(gmail_cfg: dict) -> list:
    """config の use_imap に応じて IMAP か Gmail API でアラートメールを取得する。
    どちらも同じ形の dict（subject/sender/body/links/id）のリストを返す。"""
    # use_imap=true でも app_password 未設定なら旧OAuthに自動フォールバック（移行を滑らかに）
    if gmail_cfg.get("use_imap", True) and gmail_cfg.get("app_password", "").strip():
        M = get_imap(gmail_cfg["address"], gmail_cfg.get("app_password", ""))
        try:
            return fetch_alert_emails_imap(
                M,
                days=int(gmail_cfg.get("imap_days", 7)),
                senders=gmail_cfg.get("senders"),
                max_results=int(gmail_cfg.get("max_emails", 20)),
            )
        finally:
            try:
                M.logout()
            except Exception:
                pass
    # 旧 Gmail API 方式（OAuth）
    service = get_gmail_service(gmail_cfg["credentials_file"], gmail_cfg["token_file"])
    return fetch_alert_emails(service, gmail_cfg["search_query"],
                              gmail_cfg.get("max_emails", 20))


# ──────────────────────────────────────────────
# IMAP（アプリパスワード方式・トークン失効なし）
# ──────────────────────────────────────────────

def get_imap(address: str, app_password: str):
    """Gmail に IMAP over SSL でログイン。app_password は16桁アプリパスワード（スペース無視）。"""
    if not app_password:
        raise RuntimeError("gmail.app_password が未設定です。"
                           "https://myaccount.google.com/apppasswords で発行して config.yaml に貼ってください。")
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(address, app_password.replace(" ", ""))
    return M


def _all_mail_folder(M) -> str:
    """ロケールに依存せず \\All 特殊属性から「すべてのメール」フォルダ名を見つける。無ければ INBOX。"""
    try:
        typ, folders = M.list()
        for f in folders or []:
            line = f.decode("utf-8", "replace") if isinstance(f, bytes) else str(f)
            if "\\All" in line:
                m = re.search(r'"([^"]+)"\s*$', line) or re.search(r'([^ ]+)\s*$', line)
                if m:
                    return '"%s"' % m.group(1)
    except Exception:
        pass
    return "INBOX"


def _imap_criteria(days: int, senders: list) -> str:
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
    froms = [f'FROM "{s}"' for s in (senders or [])]
    if not froms:
        return f"SINCE {since}"
    expr = froms[0]
    for f in froms[1:]:
        expr = f"OR {expr} {f}"      # 前置OR: (a OR b OR ...)
    return f"SINCE {since} {expr}"   # SINCE と AND 結合


def fetch_alert_emails_imap(M, days: int = 7, senders: list = None,
                            max_results: int = 20) -> list:
    senders = senders or ["scholaralerts-noreply@google.com",
                          "alerts-noreply@clarivate.com"]
    M.select(_all_mail_folder(M), readonly=True)
    typ, data = M.search(None, _imap_criteria(days, senders))
    ids = (data[0].split() if data and data[0] else [])[-max_results:]
    print(f"[Gmail/IMAP] {len(ids)} 件のメールを取得")

    emails = []
    for mid in reversed(ids):
        typ, msg_data = M.fetch(mid, "(RFC822)")
        if not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        email_obj = message_from_bytes(raw)
        text, links = _extract_body(email_obj)
        emails.append({
            "subject": str(make_header(decode_header(email_obj.get("Subject", "")))),
            "sender": str(make_header(decode_header(email_obj.get("From", "")))),
            "body": text,
            "links": links,
            "id": mid.decode() if isinstance(mid, bytes) else str(mid),
        })
    return emails


# ──────────────────────────────────────────────
# 認証
# ──────────────────────────────────────────────

def get_gmail_service(credentials_file: str, token_file: str):
    # google系ライブラリは旧OAuth方式でのみ必要。IMAP運用では未インストールでも動くよう遅延import。
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ──────────────────────────────────────────────
# HTMLパーサー（リンクテキストと本文を抽出）
# ──────────────────────────────────────────────

class MailHTMLParser(HTMLParser):
    """HTMLメールからテキストとリンクを抽出"""
    def __init__(self):
        super().__init__()
        self.texts = []
        self.links = []
        self._current_href = None
        self._in_link = False
        self._link_parts = []  # リンク内のテキストを蓄積
        self._skip_tags = {"style", "script", "head"}
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            self._current_href = href
            self._in_link = True
            self._link_parts = []
        if tag in ("br", "p", "div", "tr", "td", "li", "h1", "h2", "h3"):
            self.texts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False
        if tag == "a":
            if self._in_link and self._current_href and self._link_parts:
                full_text = " ".join(self._link_parts).strip()
                if full_text:
                    self.links.append((full_text, self._current_href))
            self._in_link = False
            self._current_href = None
            self._link_parts = []

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        self.texts.append(text)
        if self._in_link and self._current_href:
            self._link_parts.append(text)

    def get_text(self):
        text = " ".join(self.texts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()


def parse_html_mail(html: str) -> tuple:
    """HTMLメールをパースしてテキストとリンク一覧を返す"""
    parser = MailHTMLParser()
    parser.feed(html)
    return parser.get_text(), parser.links


# ──────────────────────────────────────────────
# メール取得
# ──────────────────────────────────────────────

def fetch_alert_emails(service, search_query: str, max_results: int = 20) -> list:
    result = service.users().messages().list(
        userId="me", q=search_query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    print(f"[Gmail] {len(messages)} 件のメールを取得")

    emails = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="raw"
        ).execute()
        raw = base64.urlsafe_b64decode(msg_data["raw"])
        email_obj = message_from_bytes(raw)
        text, links = _extract_body(email_obj)
        subject = email_obj.get("Subject", "")
        sender = email_obj.get("From", "")
        emails.append({
            "subject": subject,
            "sender": sender,
            "body": text,
            "links": links,
            "id": msg["id"],
        })

    return emails


def _extract_body(email_obj) -> tuple:
    """メール本文をテキストとリンク一覧で返す"""
    plain = None
    html = None

    if email_obj.is_multipart():
        for part in email_obj.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and plain is None:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = payload.decode("utf-8", errors="replace")
            elif ct == "text/html" and html is None:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="replace")
    else:
        payload = email_obj.get_payload(decode=True)
        if payload:
            decoded = payload.decode("utf-8", errors="replace")
            # 単一パートでもHTMLならparse_html_mailに渡す
            if decoded.strip().lower().startswith("<!doctype") or decoded.strip().lower().startswith("<html"):
                html = decoded
            else:
                plain = decoded

    if html:
        text, links = parse_html_mail(html)
        if plain and len(plain.strip()) > 100:
            text = plain.strip()
        return text, links

    return (plain or ""), []


# ──────────────────────────────────────────────
# 論文情報の抽出
# ──────────────────────────────────────────────

def extract_papers_from_emails(emails: list) -> list:
    papers = []
    seen_urls = set()

    for email in emails:
        sender = email["sender"].lower()
        if "scholaralerts" in sender or "google.com" in sender:
            extracted = _parse_scholar(email)
        else:
            extracted = _parse_wos(email)

        for p in extracted:
            url = p.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            papers.append(p)

    print(f"[Gmail] {len(papers)} 件の論文を抽出")
    return papers


_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def _extract_published_date(text: str) -> str:
    """テキストから出版年月を抽出して YYYY-MM-DD 形式で返す"""
    # "MAR 2024" / "March 2024" / "2024 Mar" などの月+年
    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"[\s\-,]*"
        r"(20[1-2]\d)\b",
        text, re.IGNORECASE
    )
    if not m:
        # "2024 Mar" 順
        m = re.search(
            r"\b(20[1-2]\d)\b[\s\-,]*"
            r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)",
            text, re.IGNORECASE
        )
        if m:
            year = m.group(1)
            month = _MONTH_MAP.get(m.group(2).lower()[:3], "01")
            return f"{year}-{month}-01"
    if m:
        month = _MONTH_MAP.get(m.group(1).lower()[:3], "01")
        year = m.group(2)
        return f"{year}-{month}-01"
    # 年のみ
    y = re.search(r"\b(20[1-2]\d)\b", text)
    return f"{y.group(1)}-01-01" if y else ""


def _parse_scholar(email: dict) -> list:
    """Google Scholar アラートから論文リストを抽出"""
    papers = []
    links = email.get("links", [])
    body = email.get("body", "")

    paper_links = []
    skip_texts = ["update alert", "unsubscribe", "view all", "see more", "fewer", "relevant results", "manage alert"]

    for text, href in links:
        text_clean = re.sub(r"^\[(HTML|PDF|CITATION)\]\s*", "", text).strip()
        if any(skip in text_clean.lower() for skip in skip_texts):
            continue
        if "scholar" in href and len(text_clean) > 20:
            actual_url_match = re.search(r"[?&]url=([^&]+)", href)
            actual_url = actual_url_match.group(1) if actual_url_match else href
            actual_url = actual_url.replace("%3A", ":").replace("%2F", "/").replace("%3F", "?")
            paper_links.append((text_clean, actual_url))
        elif len(text_clean) > 20 and not any(skip in href for skip in ["google.com/alert", "unsubscribe", "mailto", "scholar.google.com/scholar?q"]):
            paper_links.append((text_clean, href))

    lines = [l.strip() for l in body.split("\n") if l.strip()]

    for title, url in paper_links[:5]:
        authors = ""
        abstract_snippet = ""
        published_date = ""
        for i, line in enumerate(lines):
            if title[:20] in line:
                if i + 1 < len(lines):
                    candidate = lines[i + 1]
                    if not candidate.startswith("http") and len(candidate) < 300:
                        authors = candidate
                        # Scholar の著者行: "Smith J, Jones A - Nature, 2024 - nature.com"
                        published_date = _extract_published_date(candidate)
                if i + 2 < len(lines):
                    snippet = lines[i + 2]
                    if len(snippet) > 30:
                        abstract_snippet = snippet
                        if not published_date:
                            published_date = _extract_published_date(snippet)
                break

        papers.append({
            "title": title[:300],
            "authors": authors[:200],
            "url": url,
            "doi": _extract_doi(url),
            "published_date": published_date,
            "pdf_url": "",
            "source": "Google Scholar",
            "raw_body": f"Title: {title}\nAuthors: {authors}\nAbstract snippet: {abstract_snippet}\n\nFull email body:\n{body[:2000]}",
        })

    if not papers:
        doi_pattern = re.compile(r"10\.\d{4,}/[^\s\]>\"]+")
        dois = doi_pattern.findall(body)
        if dois:
            papers.append({
                "title": email.get("subject", "")[:300],
                "authors": "",
                "url": f"https://doi.org/{dois[0]}",
                "doi": dois[0],
                "published_date": _extract_published_date(body),
                "pdf_url": "",
                "source": "Google Scholar",
                "raw_body": body[:2000],
            })

    return papers


def _parse_wos(email: dict) -> list:
    """Web of Science アラートから論文リストを抽出"""
    papers = []
    links = email.get("links", [])
    body = email.get("body", "")
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    # WoSリンクからタイトル候補を収集
    # リンク先はログイン必須のため、DOIを抽出して doi.org URLに変換する
    skip_texts = ["sign in", "login", "unsubscribe", "view all", "manage alert",
                  "web of science", "clarivate", "endnote"]
    title_candidates = []
    for text, href in links:
        text_clean = text.strip()
        if len(text_clean) > 20 and not any(s in text_clean.lower() for s in skip_texts):
            if "webofscience" in href or "wos" in href.lower() or "doi.org" in href:
                doi = _extract_doi(href) or _extract_doi(text_clean)
                title_candidates.append((text_clean, doi))

    for title, doi_from_link in title_candidates[:5]:
        authors = ""
        published_date = ""
        source = ""
        doi = doi_from_link

        # タイトル周辺の行からメタデータを抽出
        for j, line in enumerate(lines):
            if title[:30] in line:
                # 著者行
                if j + 1 < len(lines):
                    candidate = lines[j + 1]
                    if not candidate.startswith("http") and len(candidate) < 400:
                        authors = candidate
                # Source行・DOI行（タイトルから5行以内）
                for k in range(j + 1, min(j + 6, len(lines))):
                    lk = lines[k]
                    if not doi:
                        doi = _extract_doi(lk)
                    if not published_date:
                        published_date = _extract_published_date(lk)
                    # ジャーナル名候補（大文字多め・短め）
                    if not source and len(lk) < 150 and re.search(r"[A-Z]{3,}", lk):
                        source = lk.split(",")[0].strip().title()
                break

        # doi.org URLを優先（WoSレコードはログイン必須のため）
        url = f"https://doi.org/{doi}" if doi else ""

        papers.append({
            "title": title[:300],
            "authors": authors[:200],
            "url": url,
            "doi": doi,
            "published_date": published_date,
            "pdf_url": "",
            "source": source or "Web of Science",
            "raw_body": f"Title: {title}\nAuthors: {authors}\n\nFull email body:\n{body[:2000]}",
        })

    # フォールバック: DOIのみ
    if not papers:
        doi_pattern = re.compile(r"10\.\d{4,}/[^\s\]>\"]+")
        dois = doi_pattern.findall(body)
        for doi in dois[:3]:
            papers.append({
                "title": "",
                "authors": "",
                "url": f"https://doi.org/{doi}",
                "doi": doi,
                "published_date": _extract_published_date(body),
                "pdf_url": "",
                "source": "Web of Science",
                "raw_body": body[:2000],
            })

    return papers


def _extract_doi(text: str) -> str:
    # 通常パターン: URLやテキスト中の 10.xxxx/xxx
    match = re.search(r"10\.\d{4,}/[^\s\]>\"&]+", text)
    if match:
        return match.group(0)

    # Nature 系: nature.com/articles/{slug} → 10.1038/{slug}
    m = re.search(r"nature\.com/articles/(s\d{5}-[\w-]+)", text)
    if m:
        return f"10.1038/{m.group(1)}"

    return ""