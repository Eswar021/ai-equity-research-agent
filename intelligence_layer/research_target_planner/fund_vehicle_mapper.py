"""
intelligence_layer/research_target_planner/fund_vehicle_mapper.py — Layer 6

Maps fund_etf unresolved targets to investable vehicles.
Deferred: no fund/ETF data layer exists yet.
Returns empty list — same pattern as cross_domain_mapper in Layer 5.

Design doc: docs/system_design_docs/layer_6.md §11 fund_vehicle_mapper.py
"""

from __future__ import annotations


def map_fund_vehicles(unresolved: list[dict]) -> list[dict]:
    """Deferred. Returns [] until a fund/ETF data layer is built."""
    return []
