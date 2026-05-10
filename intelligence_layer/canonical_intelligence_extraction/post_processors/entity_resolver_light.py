"""
intelligence_layer/canonical_intelligence_extraction/post_processors/entity_resolver_light.py — Layer 3

Light entity enrichment: attaches NSE tickers to extracted entities where possible.

"This is not final research target selection. It only adds: ticker if obvious,
market if obvious, entity type, aliases, resolved/unresolved status." — design doc §16

Uses the existing lookup_ticker() from context_ext_layer.utils.ticker_extractor.
Only attempts resolution for entity_type == "listed_company".
Non-listed entities (private, sector, macro, person) are preserved as-is.

Design doc: docs/system_design_docs/layer_3.md §16 entity_resolver_light.py
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

try:
    from context_ext_layer.utils.ticker_extractor import lookup_ticker, extract_tickers
    from context_ext_layer.utils.nse_symbols import load_symbols as _load_symbols
    _NSE_SYMBOLS: dict = _load_symbols()
    _RESOLVER_AVAILABLE = True
except ImportError:
    _RESOLVER_AVAILABLE = False
    _NSE_SYMBOLS        = {}

_RESOLUTION_THRESHOLD = 82   # fuzzy match threshold (same as news_signal_extractor.py)


def resolve(entity: dict) -> dict:
    """
    Attempt to resolve one entity to its NSE ticker.
    Modifies and returns the entity dict (ticker, resolution_status, aliases).

    Args:
        entity: entity dict from entity_extractor.format_entities()

    Returns:
        enriched entity dict with ticker and resolution_status filled in.
    """
    entity_type = entity.get("entity_type", "")
    entity_name = entity.get("entity_name", "")
    ticker_hint = entity.get("ticker_hint") or ""

    # Only attempt resolution for listed companies
    if entity_type != "listed_company":
        entity["resolution_status"] = _non_listed_status(entity_type)
        entity["ticker"]            = None
        return entity

    if not _RESOLVER_AVAILABLE:
        entity["resolution_status"] = "resolver_unavailable"
        return entity

    ticker, company = _resolve_ticker(ticker_hint or entity_name)

    if ticker:
        entity["ticker"]            = ticker
        entity["normalized_name"]   = company or entity_name
        entity["aliases"]           = list({entity_name, ticker_hint, company} - {None, ""})
        entity["resolution_status"] = "resolved"
        entity["exchange"]          = "NSE"
        entity["country"]           = "India"
    else:
        entity["resolution_status"] = "unresolved_no_ticker"
        entity["ticker"]            = None

    return entity


def resolve_all(entities: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Resolve all entities. Returns (resolved_entities, unresolved_entities).
    Both lists are returned so the runner can write unresolved_entities.json.
    """
    resolved   = []
    unresolved = []
    for entity in entities:
        enriched = resolve(entity)
        if enriched.get("resolution_status") == "resolved":
            resolved.append(enriched)
        else:
            unresolved.append(enriched)
    return resolved + unresolved, unresolved  # full list + unresolved separately


def _resolve_ticker(name: str) -> tuple[str | None, str | None]:
    if not name or len(name) < 2:
        return None, None

    # Pass 0: direct NSE symbol lookup
    hint_clean = name.upper().replace(".NS", "").replace(".BO", "").strip()
    direct     = _NSE_SYMBOLS.get(hint_clean + ".NS")
    if direct:
        return direct["ticker"], direct["name"]

    # Pass 1: alias dictionary
    found = extract_tickers(name)
    if found:
        return found[0]["ticker"], found[0]["company"]

    # Pass 2: fuzzy match
    result = lookup_ticker(name, threshold=_RESOLUTION_THRESHOLD)
    if result:
        return result["ticker"], result["name"]

    return None, None


def _non_listed_status(entity_type: str) -> str:
    return {
        "private_company":   "unresolved_private_company",
        "business_group":    "unresolved_business_group",
        "sector":            "not_applicable_sector",
        "technology_theme":  "not_applicable_theme",
        "regional_theme":    "not_applicable_theme",
        "macro_indicator":   "not_applicable_macro",
        "policy":            "not_applicable_policy",
        "regulator":         "not_applicable_regulator",
        "government_body":   "not_applicable_gov",
        "person":            "not_applicable_person",
        "commodity":         "not_applicable_commodity",
        "currency":          "not_applicable_currency",
        "index":             "resolved_index",
        "mutual_fund":       "not_applicable_fund",
        "etf":               "not_applicable_fund",
        "reit":              "not_applicable_reit",
        "invit":             "not_applicable_invit",
    }.get(entity_type, "unresolved_unknown")
