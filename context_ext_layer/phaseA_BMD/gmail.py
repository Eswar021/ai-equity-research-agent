import imaplib
import email
import json
import os
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import GMAIL_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

load_dotenv()
_EMAIL    = os.getenv("GMAIL_EMAIL")
_PASSWORD = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")


def _decode_str(value: str) -> str:
    parts = decode_header(value or "")
    out = []
    for part, enc in parts:
        out.append(part.decode(enc or "utf-8", errors="ignore") if isinstance(part, bytes) else part)
    return " ".join(out)


def _extract_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                raw = part.get_payload(decode=True).decode(errors="ignore")
                body = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True)
                break
            if ct == "text/plain" and not body:
                body = part.get_payload(decode=True).decode(errors="ignore")
    else:
        raw = msg.get_payload(decode=True).decode(errors="ignore")
        body = BeautifulSoup(raw, "html.parser").get_text(separator=" ", strip=True)
    return body.strip()


def fetch_newsletters(from_domain: str = None, subject_keyword: str = None, limit: int = 5) -> list[dict]:
    conn = imaplib.IMAP4_SSL("imap.gmail.com")
    conn.login(_EMAIL, _PASSWORD)
    conn.select("inbox")

    if from_domain:
        _, msg_ids = conn.search(None, f'FROM "{from_domain}"')
    elif subject_keyword:
        _, msg_ids = conn.search(None, f'SUBJECT "{subject_keyword}"')
    else:
        raise ValueError("Provide either from_domain or subject_keyword")

    ids = msg_ids[0].split()[-limit:]

    results = []
    for mid in reversed(ids):
        _, data = conn.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        results.append({
            "subject": _decode_str(msg.get("Subject", "")),
            "sender":  _decode_str(msg.get("From", "")),
            "date":    msg.get("Date", ""),
            "body":    _extract_body(msg),
        })

    conn.logout()
    return results


def save_newsletters(from_domain: str = None, subject_keyword: str = None, limit: int = 5) -> str:
    newsletters = fetch_newsletters(from_domain, subject_keyword, limit)

    GMAIL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    slug     = (from_domain or subject_keyword or "newsletter").replace(" ", "_").lower()[:40]
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{slug}_{today}.json"

    output = {
        "from_domain":      from_domain,
        "subject_keyword":  subject_keyword,
        "fetched_at":       datetime.now(_IST).isoformat(),
        "total":            len(newsletters),
        "newsletters":      newsletters,
    }

    output_file = GMAIL_OUTPUT_DIR / filename
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(output_file)


if __name__ == "__main__":
    saved_path = save_newsletters(from_domain="busline.hindugroup.org", limit=3)
    print(f"Saved to: {saved_path}\n")

    with open(saved_path) as f:
        data = json.load(f)

    print(f"Found: {data['total']} emails\n")
    for n in data["newsletters"]:
        print(f"Subject: {n['subject']}")
        print(f"From:    {n['sender']}")
        print(f"Date:    {n['date']}")
        print(f"Body ({len(n['body'])} chars): {n['body'][:300]}")
        print()
