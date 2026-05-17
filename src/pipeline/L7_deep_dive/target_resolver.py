"""
Resolves L6 targets to NSE tickers before data collection.

Resolution order (first match wins):
  1. commodity   — word-boundary keyword match → affected NSE tickers from l7_config
  2. entity_centric targets → direct company lookup (fuzzy name → specific ticker)
  3. theme_centric targets  → sector keyword match → top-N constituents from l7_config
  4. unresolved  — no match found; target is skipped in collection

Routing by group_type ensures named companies (entity_centric) get their specific ticker
while theme targets (theme_centric) get a sector basket.
Word-boundary matching prevents "it" from matching inside "volatility".

Returns (resolution_type, [ticker_list], resolution_note).
Tickers are bare NSE symbols (no .NS suffix) — collectors add .NS themselves.
"""

from __future__ import annotations

import re

from .nse_symbols import lookup_ticker


def _sector_match(entity: str, sector_map: dict) -> tuple[str, list[str]] | None:
    """Return (key, tickers) for first word-boundary sector match, or None."""
    for key, tickers in sector_map.items():
        keyword = key.replace("_", " ")
        if re.search(r"\b" + re.escape(keyword) + r"\b", entity):
            return key, list(tickers)[:5]
    return None


def resolve(
    target: dict,
    symbols: dict[str, str],
    cfg: dict,
    aliases: dict[str, str] | None = None,
) -> tuple[str, list[str], str]:
    """
    Returns (resolution_type, tickers, note).
    resolution_type: "direct" | "commodity" | "sector" | "unresolved"
    aliases: loaded from l7_config.yaml company_aliases, passed through to lookup_ticker.
    """
    entity        = target.get("target_entity", "").lower().strip()
    group_type    = target.get("group_type", "theme_centric")
    commodity_map = cfg.get("commodity_mappings", {})
    sector_map    = cfg.get("sector_mappings", {})

    # 1. Commodity keyword match (always first, regardless of group_type)
    for key, mapping in commodity_map.items():
        keyword = key.replace("_", " ")
        if re.search(r"\b" + re.escape(keyword) + r"\b", entity):
            primary   = mapping.get("primary", [])
            secondary = mapping.get("secondary", [])
            tickers   = (primary + secondary)[:5]
            note = (
                f"{key} → primary: {primary} (direct exposure); "
                f"secondary: {secondary} (indirect exposure)"
            )
            return "commodity", tickers, note

    # 2. Route by group_type
    if group_type == "entity_centric":
        # Named company target → direct ticker lookup first
        ticker = lookup_ticker(target.get("target_entity", ""), symbols, aliases)
        if ticker:
            return "direct", [ticker], f"fuzzy name match → {ticker}"
        # Fallback: sector basket if entity lookup fails
        sm = _sector_match(entity, sector_map)
        if sm:
            key, tickers = sm
            return "sector", tickers, f"{key} sector fallback for unresolved entity"

    else:
        # Theme target → sector keyword match first
        sm = _sector_match(entity, sector_map)
        if sm:
            key, tickers = sm
            return "sector", tickers, f"{key} sector → top {len(tickers)} constituents by market cap"
        # Fallback: direct company lookup if no sector keyword matched
        ticker = lookup_ticker(target.get("target_entity", ""), symbols, aliases)
        if ticker:
            return "direct", [ticker], f"fuzzy name match → {ticker}"

    return "unresolved", [], "no commodity/sector keyword match and no fuzzy name match"
