"""
intelligence_layer/source_canonicalization/freshness_validator.py — Layer 2

Marks freshness and staleness for canonical records. Freshness types
carry forward from Layer 1's bundler metadata; this module adds:
  - is_stale flag (is the data too old to be actionable?)
  - data_date (best-effort extraction from published_at / collected_at)
  - requires_history_sync (true for today_only and live_snapshot sources)

Stale thresholds (design heuristics for Indian equity research):
    news_article / rss_item / newsletter → stale if > 7 days old
    youtube_transcript                   → stale if > 30 days old
    macro_snapshot                       → stale if > 1 day old
    market_snapshot / price_history      → stale if > 1 day old
    institutional_flow / bulk deals      → today_only; stale if != today
    derivatives_snapshot                 → live_snapshot; stale if > 3h old
    fundamentals (screener, peers, etc.) → stale if > 30 days old

Design doc: docs/system_design_docs/layer_2.md  §27 freshness_validator.py
"""

from datetime import datetime, date, timezone, timedelta
import re

_IST = timezone(timedelta(hours=5, minutes=30))

# freshness_type → requires_history_sync
_REQUIRES_SYNC: dict[str, bool] = {
    "today_only":           True,
    "live_snapshot":        True,
    "historical_available": False,
}

# source_type / record_type → max age in days before marking stale
_STALE_THRESHOLD_DAYS: dict[str, int] = {
    "news_article":         7,
    "rss_item":             7,
    "newsletter":           7,
    "news_api":             7,
    "youtube_transcript":  30,
    "generic_web":         14,
    "macro_snapshot":       1,
    "market_snapshot":      1,
    "price_history":        1,
    "institutional_flow":   0,   # must be today
    "bulk_block_deals":     0,   # must be today
    "derivatives_snapshot": 0,   # live snapshot — stale after same day
    "fundamental_data":    30,
    "peer_data":           30,
    "analyst_consensus":   30,
    "regulatory_filing":   90,
    "filing_document":     90,
    "corporate_action":    30,
}
_DEFAULT_STALE_DAYS = 14


def _parse_date(date_str: str | None) -> date | None:
    """Parse ISO-format date strings into date objects."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%d %b %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str[:len(fmt)+5], fmt).date()
        except ValueError:
            continue
    # Try regex for partial ISO strings like "2026-05-09T08:12:00+05:30"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return None


def validate_freshness(
    freshness_type: str,
    source_type: str = "",
    published_at: str | None = None,
    collected_at: str | None = None,
    run_date: date | None = None,
) -> dict:
    """
    Validate and annotate freshness for one record.

    Args:
        freshness_type: from Layer 1 bundler metadata
        source_type:    canonical source type string
        published_at:   ISO date string from collector (may be None)
        collected_at:   ISO date string when we fetched the data
        run_date:       the pipeline run date (defaults to today IST)

    Returns:
        {
            "freshness_type":        str,
            "data_date":             str | None,   # YYYY-MM-DD
            "is_stale":              bool,
            "requires_history_sync": bool,
            "staleness_days":        int | None
        }
    """
    today = run_date or datetime.now(_IST).date()

    # Best-effort data_date: prefer published_at, fall back to collected_at
    data_date = _parse_date(published_at) or _parse_date(collected_at)
    data_date_str = data_date.isoformat() if data_date else None

    requires_sync = _REQUIRES_SYNC.get(freshness_type, False)
    threshold = _STALE_THRESHOLD_DAYS.get(source_type, _DEFAULT_STALE_DAYS)

    is_stale = False
    staleness_days: int | None = None

    if data_date is not None:
        staleness_days = (today - data_date).days
        is_stale = staleness_days > threshold
    elif freshness_type in ("today_only", "live_snapshot"):
        # No date available but must be today — assume stale to be safe
        is_stale = True

    return {
        "freshness_type":        freshness_type,
        "data_date":             data_date_str,
        "is_stale":              is_stale,
        "requires_history_sync": requires_sync,
        "staleness_days":        staleness_days,
    }
