"""
intelligence_layer/research_target_planner/entity_resolver.py — Layer 6

Resolves candidate entity identity against the L3 entity_registry.
Assigns entity_id and confirmed metadata when found.
Does not fail or block if no match — resolution is enrichment only.

Design doc: docs/system_design_docs/layer_6.md §6 entity_resolver.py
"""

from __future__ import annotations
import re


def resolve_all(candidates: list[dict], entity_by_ticker: dict, entity_by_norm: dict) -> list[dict]:
    """
    Resolve entity identity for all candidates.
    Mutates and returns the candidate list.
    """
    for c in candidates:
        if c.get("target_type") not in ("listed_company", "private_unlisted_company", "unknown"):
            c["entity_id"]           = None
            c["resolution_status"]   = "not_applicable"
            continue
        _resolve_single(c, entity_by_ticker, entity_by_norm)
    return candidates


def _resolve_single(c: dict, entity_by_ticker: dict, entity_by_norm: dict) -> None:
    ticker_hint = (c.get("ticker_hint") or "").upper().strip()
    name        = (c.get("candidate_name") or "").strip()

    # 1. Lookup by ticker
    if ticker_hint:
        ent = entity_by_ticker.get(ticker_hint)
        if ent:
            _attach(c, ent, "resolved_by_ticker", 0.97)
            return

    # 2. Lookup by normalized name
    norm = _normalize_name(name)
    ent  = entity_by_norm.get(norm)
    if ent:
        _attach(c, ent, "resolved_by_name", 0.88)
        return

    # 3. Partial match — strip common suffixes and retry
    short = _strip_suffixes(norm)
    if short != norm:
        ent = entity_by_norm.get(short)
        if ent:
            _attach(c, ent, "resolved_by_stripped_name", 0.78)
            return

    c["entity_id"]           = None
    c["resolved_entity_name"] = name
    c["resolution_status"]   = "not_in_l3_registry"
    c["resolution_confidence"] = 0.0


def _attach(c: dict, ent: dict, status: str, conf: float) -> None:
    c["entity_id"]            = ent.get("entity_id")
    c["resolved_entity_name"] = ent.get("entity_name", c.get("candidate_name"))
    c["resolution_status"]    = status
    c["resolution_confidence"] = conf
    # Enrich with L3 metadata if not already set
    if not c.get("ticker_hint") and ent.get("ticker"):
        c["ticker_hint"] = ent["ticker"]
    c["l3_entity_type"]   = ent.get("entity_type", "")
    c["l3_market_status"] = ent.get("market_status", "")
    c["l3_exchange"]      = ent.get("exchange", "")
    c["l3_country"]       = ent.get("country", "")


def _normalize_name(name: str) -> str:
    return name.lower().strip()


def _strip_suffixes(norm: str) -> str:
    suffixes = [" ltd", " limited", " corp", " corporation", " inc",
                " pvt", " private", " (india)", " india", " technologies",
                " technology", " solutions", " services", " group"]
    s = norm
    for suf in suffixes:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s
