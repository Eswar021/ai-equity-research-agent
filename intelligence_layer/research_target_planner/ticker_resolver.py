"""
intelligence_layer/research_target_planner/ticker_resolver.py — Layer 6

Resolves listed_company candidates to confirmed NSE tickers.
Ticker resolution is optional enrichment — not a gate.

Priority:
  1. L5 ticker_hint ending in .NS / .BO  → accept directly
  2. L3 entity resolution already found a ticker → use it
  3. existing ticker_extractor.lookup_ticker() fuzzy match

Design doc: docs/system_design_docs/layer_6.md §7 ticker_resolver.py
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from context_ext_layer.utils.ticker_extractor import lookup_ticker
    _HAS_EXTRACTOR = True
except ImportError:
    _HAS_EXTRACTOR = False


_NS_RE = re.compile(r'^[A-Z0-9&%\-\.]+\.(NS|BO|BSE)$', re.IGNORECASE)


def resolve_all(candidates: list[dict]) -> list[dict]:
    """
    Resolve tickers for all listed_company candidates.
    Mutates and returns the candidate list.
    """
    for c in candidates:
        if c.get("target_type") != "listed_company":
            c["ticker"]                   = None
            c["exchange"]                 = None
            c["ticker_resolution_status"] = "not_applicable"
            continue
        _resolve_single(c)
    return candidates


def _resolve_single(c: dict) -> None:
    hint   = (c.get("ticker_hint") or "").strip()
    name   = c.get("resolved_entity_name") or c.get("candidate_name") or ""

    # 1. Ticker hint already has exchange suffix → accept as-is
    if hint and _NS_RE.match(hint):
        c["ticker"]                   = hint.upper()
        c["exchange"]                 = "NSE" if hint.upper().endswith(".NS") else "BSE"
        c["ticker_resolution_status"] = "resolved_from_l5_hint"
        return

    # 2. Entity resolver already populated a ticker via L3 lookup
    if hint and not _NS_RE.match(hint):
        # bare symbol without exchange suffix — assume NSE
        c["ticker"]                   = hint.upper() + ".NS"
        c["exchange"]                 = "NSE"
        c["ticker_resolution_status"] = "assumed_nse_from_bare_symbol"
        return

    # 3. Fuzzy lookup via ticker_extractor
    if _HAS_EXTRACTOR and name:
        result = lookup_ticker(name, threshold=82)
        if result:
            c["ticker"]                   = result
            c["exchange"]                 = "NSE" if result.endswith(".NS") else "BSE"
            c["ticker_resolution_status"] = "fuzzy_matched"
            return

    c["ticker"]                   = None
    c["exchange"]                 = None
    c["ticker_resolution_status"] = "not_found"
