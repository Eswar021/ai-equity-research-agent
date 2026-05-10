"""
intelligence_layer/source_canonicalization/text_cleaner.py — Layer 2

Cleans raw text from any collector without changing factual meaning.

Design doc: docs/system_design_docs/layer_2.md  §22 text_cleaner.py
"""

import re

# Newsletter / web boilerplate patterns — source-agnostic
_BOILERPLATE_PATTERNS = [
    r"(?i)unsubscribe\s+from\s+this\s+list.*",
    r"(?i)click\s+here\s+to\s+unsubscribe.*",
    r"(?i)you\s+(are\s+receiving|received)\s+this\s+(email|newsletter).*",
    r"(?i)to\s+stop\s+receiving\s+(these\s+)?(emails?|newsletters?).*",
    r"(?i)view\s+this\s+email\s+in\s+your\s+browser.*",
    r"(?i)if\s+you\s+no\s+longer\s+wish\s+to\s+receive.*",
    r"(?i)copyright\s+\©?\s*\d{4}.*all\s+rights\s+reserved.*",
    r"(?i)^(click\s+to\s+read\s+(more|full\s+story)|read\s+more\s+at\b).*$",
    r"(?i)^(advertisement|sponsored\s+content|paid\s+partnership)$",
    r"(?i)^share\s+(this\s+)?(article|story|post)\s*[:\-]?\s*$",
    r"(?i)^(follow\s+us\s+on|connect\s+with\s+us)\s*[:\-]?\s*$",
]
_BOILERPLATE_RE = [re.compile(p, re.MULTILINE) for p in _BOILERPLATE_PATTERNS]

# HTML tag removal — covers <tag>, </tag>, self-closing <tag />
_HTML_TAG_RE  = re.compile(r"<[^>]+>")
# HTML entities
_HTML_ENTITY_RE = re.compile(r"&[a-zA-Z]{2,8};|&#\d+;")
_ENTITY_MAP = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&apos;": "'", "&nbsp;": " ", "&ndash;": "–", "&mdash;": "—",
    "&ldquo;": "“", "&rdquo;": "”", "&lsquo;": "‘",
    "&rsquo;": "’",
}
# Repeated punctuation / separator lines (─────, =====, .......)
_SEPARATOR_RE = re.compile(r"^[\s\-=_*\.]{5,}$", re.MULTILINE)
# Multiple blank lines → single blank line
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _strip_html(text: str) -> tuple[str, bool]:
    if "<" not in text:
        return text, False
    # Resolve common entities first
    for entity, char in _ENTITY_MAP.items():
        text = text.replace(entity, char)
    text = _HTML_ENTITY_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    return text, True


def _remove_boilerplate(text: str) -> tuple[str, bool]:
    original = text
    for pattern in _BOILERPLATE_RE:
        text = pattern.sub("", text)
    return text, text != original


def _normalize_whitespace(text: str) -> str:
    text = _SEPARATOR_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line or (lines.index(line) > 0 and lines[lines.index(line)-1]))
    return text.strip()


def clean_text(raw_text: str | None, source_type: str = "") -> dict:
    """
    Clean raw text for any collector output.

    Returns:
        {
            "clean_text": str,
            "cleaning_notes": list[str]  # e.g. ["html_removed", "boilerplate_removed"]
        }
    """
    if not raw_text:
        return {"clean_text": "", "cleaning_notes": ["empty_input"]}

    notes: list[str] = []
    text = str(raw_text)

    text, html_found = _strip_html(text)
    if html_found:
        notes.append("html_removed")

    text, boilerplate_found = _remove_boilerplate(text)
    if boilerplate_found:
        notes.append("boilerplate_removed")

    cleaned = _normalize_whitespace(text)
    if cleaned != text.strip():
        notes.append("whitespace_normalized")

    return {"clean_text": cleaned, "cleaning_notes": notes}
