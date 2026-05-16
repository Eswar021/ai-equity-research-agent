"""Gmail scraper — pulls newsletters/alerts via IMAP."""

import email
import imaplib
import os
from email.header import decode_header

from bs4 import BeautifulSoup

_IMAP_HOST = "imap.gmail.com"


def _decode_str(val: str | bytes | None) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return str(val)
    return str(val)


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_body(msg: email.message.Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    body = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            ct = msg.get_content_type()
            text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            if ct == "text/html":
                body = BeautifulSoup(text, "html.parser").get_text(separator="\n", strip=True)
            else:
                body = text
    return body.strip()


def _build_search_criterion(source: dict) -> str:
    src_type = source["type"]
    value    = source["value"]
    if src_type == "from_domain":
        return f'FROM "@{value}"'
    elif src_type == "subject_keyword":
        return f'SUBJECT "{value}"'
    raise ValueError(f"Unknown gmail source type: {src_type}")


def collect(cfg: dict) -> list[dict]:
    gmail_user = os.getenv("GMAIL_EMAIL", "").strip()
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not gmail_user or not gmail_pass:
        raise RuntimeError("GMAIL_EMAIL or GMAIL_APP_PASSWORD env vars not set")

    max_per_source = cfg.get("max_per_source", 5)
    sources        = cfg.get("sources", [])
    if not sources:
        raise ValueError("gmail config missing 'sources' list")

    records = []

    with imaplib.IMAP4_SSL(_IMAP_HOST) as imap:
        imap.login(gmail_user, gmail_pass)
        imap.select("INBOX")

        for source in sources:
            try:
                criterion = _build_search_criterion(source)
                status, data = imap.search(None, criterion)
                if status != "OK":
                    continue
                msg_ids = data[0].split()
                msg_ids = msg_ids[-max_per_source:]  # most recent N

                for msg_id in reversed(msg_ids):
                    status, raw = imap.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        continue
                    msg = email.message_from_bytes(raw[0][1])

                    subject = _decode_header_value(msg.get("Subject", ""))
                    sender  = _decode_header_value(msg.get("From", ""))
                    date_str = msg.get("Date", "")
                    body    = _extract_body(msg)

                    records.append({
                        "source":       "gmail",
                        "source_type":  "newsletter",
                        "title":        subject,
                        "url":          None,
                        "published_at": date_str or None,
                        "content":      body,
                        "metadata": {
                            "sender":  sender,
                            "subject": subject,
                        },
                    })
            except Exception as e:
                print(f"  [gmail] source {source} failed: {e}")

    return records
