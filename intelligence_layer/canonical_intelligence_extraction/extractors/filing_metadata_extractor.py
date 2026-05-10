"""
intelligence_layer/canonical_intelligence_extraction/extractors/filing_metadata_extractor.py — Layer 3

Rule-based extractor: converts exchange filing metadata and corporate action
records into event cards. Official filings are high-reliability sources.

"Use keyword/rule mapping for filing subjects. Official source = high reliability." — design doc §15

Design doc: docs/system_design_docs/layer_3.md §15 filing_metadata_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_event_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"FEVT_{today}_{_COUNTER[0]:04d}"


# ── Keyword → event_type mapping ──────────────────────────────────────────────
# Keys are lowercase substrings to check against the filing subject/type.
_SUBJECT_TO_EVENT: list[tuple[str, str, str]] = [
    # (keyword, event_type, severity)
    ("dividend",         "dividend",          "low"),
    ("bonus",            "split_bonus",       "low"),
    ("split",            "split_bonus",       "low"),
    ("buyback",          "buyback",           "medium"),
    ("rights issue",     "capex_announcement","medium"),
    ("acquisition",      "merger_acquisition","high"),
    ("merger",           "merger_acquisition","high"),
    ("amalgamation",     "merger_acquisition","high"),
    ("demerger",         "divestment",        "high"),
    ("divestment",       "divestment",        "high"),
    ("stake sale",       "divestment",        "high"),
    ("resignation",      "management_change", "high"),
    ("appointment",      "management_change", "medium"),
    ("director",         "management_change", "medium"),
    ("md ",              "management_change", "high"),
    ("ceo",              "management_change", "high"),
    ("cfo",              "management_change", "medium"),
    ("penalty",          "regulatory_action", "high"),
    ("sebi",             "regulatory_action", "high"),
    ("nse notice",       "regulatory_action", "medium"),
    ("bse notice",       "regulatory_action", "medium"),
    ("delisting",        "regulatory_action", "high"),
    ("fraud",            "fraud_or_accounting_concern", "high"),
    ("qualified institutional", "bulk_deal",  "medium"),
    ("qip",              "bulk_deal",         "medium"),
    ("preferential",     "bulk_deal",         "medium"),
    ("annual general",   "other",             "low"),
    ("agm",              "other",             "low"),
    ("board meeting",    "other",             "low"),
    ("credit rating",    "credit_rating_change", "high"),
    ("downgrade",        "credit_rating_change", "high"),
    ("upgrade",          "credit_rating_change", "medium"),
    ("ipo",              "ipo_news",          "high"),
    ("results",          "earnings_beat",     "medium"),   # will be refined by LLM later
    ("financial results","earnings_beat",     "medium"),
    ("quarterly results","earnings_beat",     "medium"),
]


def _classify_filing_subject(subject: str) -> tuple[str, str]:
    """Return (event_type, severity) from a filing subject string."""
    s = subject.lower()
    for keyword, etype, sev in _SUBJECT_TO_EVENT:
        if keyword in s:
            return etype, sev
    return "other", "low"


def extract(record: dict) -> list[dict]:
    """
    Extract event cards from corporate_actions or regulatory filing records.
    """
    rec_type = (record.get("record_type") or "").lower()
    data     = record.get("data") or {}
    ticker   = (record.get("target_context") or {}).get("ticker") or data.get("ticker", "")
    entity   = (record.get("target_context") or {}).get("entity_name") or ticker or ""
    rec_id   = record.get("record_id", "")
    source_id = (record.get("lineage") or {}).get("source_module", "")

    events = []

    # ── NSE corporate actions ──────────────────────────────────────────────────
    for action in (data.get("nse_actions") or []):
        subject = action.get("purpose") or action.get("series") or ""
        ex_date = action.get("exDate") or action.get("exdate") or ""
        etype, sev = _classify_filing_subject(subject)

        events.append({
            "event_id":     _next_event_id(),
            "event_type":   etype,
            "event_title":  f"{ticker}: {subject}",
            "event_summary": f"{entity} announced {subject} with ex-date {ex_date}.",
            "entities": [{"entity_name": entity, "entity_type": "listed_company", "ticker": ticker}],
            "impact_scope":   ["company"],
            "initial_sentiment": "neutral",
            "business_impact":   "neutral",
            "severity":          sev,
            "time_horizon":      "short_term",
            "temporary_or_structural_hint": "unknown",
            "source_refs": [{
                "record_id":         rec_id,
                "source_id":         source_id,
                "supporting_text":   f"{subject} on {ex_date}",
                "source_reliability": "high",
            }],
            "source_reliability": "high",
            "published_at":       ex_date,
            "confidence":         0.90,
        })

    # ── SEC filing metadata ────────────────────────────────────────────────────
    for filing in (data.get("recent_filings") or {}).get("recent_10k", []) + \
                  (data.get("recent_filings") or {}).get("recent_10q", []) + \
                  (data.get("recent_filings") or {}).get("recent_8k", []):
        form   = filing.get("form", "")
        filed  = filing.get("filed", "")
        if form in ("10-K", "10-Q", "8-K"):
            etype = "earnings_beat" if form in ("10-K", "10-Q") else "regulatory_action"
            events.append({
                "event_id":     _next_event_id(),
                "event_type":   etype,
                "event_title":  f"{ticker}: {form} filing submitted",
                "event_summary": f"{entity} filed {form} on {filed}.",
                "entities": [{"entity_name": entity, "entity_type": "listed_company", "ticker": ticker}],
                "impact_scope":   ["company"],
                "initial_sentiment": "neutral",
                "business_impact":   "neutral",
                "severity":          "medium",
                "time_horizon":      "short_term",
                "temporary_or_structural_hint": "unknown",
                "source_refs": [{
                    "record_id":         rec_id,
                    "source_id":         source_id,
                    "supporting_text":   f"{form} filed on {filed}",
                    "source_reliability": "high",
                }],
                "source_reliability": "high",
                "published_at":       filed,
                "confidence":         0.93,
            })

    return events
