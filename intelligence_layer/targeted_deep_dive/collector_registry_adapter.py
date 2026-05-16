"""
intelligence_layer/targeted_deep_dive/collector_registry_adapter.py — Layer 7

Maps Layer 7 module names to Phase C fetch functions.
Each entry: callable + a param-builder that extracts kwargs from task params.

ADR-L7-003: We call fetch_* functions (not save_*) so Layer 7 controls output path.
ADR-L7-004: screener_in URL is derived from ticker since extract_company() takes URL.

Design doc: docs/system_design_docs/layer_7.md §10.5 collector_registry_adapter.py
"""

from __future__ import annotations
import re


def _bare(ticker: str) -> str:
    """Strip .NS / .BO suffix — used for screener URL and exchange_filings symbol."""
    return re.sub(r"\.(NS|BO)$", "", ticker.upper())


# Registry: module_name → {"fn": callable, "build_kwargs": Callable[[params, ctx], dict]}
# Populated lazily to avoid importing all collectors at module import time.
_REGISTRY: dict[str, dict] = {}


def _ensure_registry() -> None:
    if _REGISTRY:
        return

    from context_ext_layer.phaseC_CDD import market_data as _md
    from context_ext_layer.phaseC_CDD import price_history as _ph
    from context_ext_layer.phaseC_CDD import screener_in as _si
    from context_ext_layer.phaseC_CDD import peer_comparison as _pc
    from context_ext_layer.phaseC_CDD import analyst_estimates as _ae
    from context_ext_layer.phaseC_CDD import exchange_filings as _ef

    _REGISTRY["market_data"] = {
        "fn": _md.fetch_stock,
        "build_kwargs": lambda params, ctx: {
            "ticker": params.get("ticker") or ctx["ticker"],
        },
        "source_type": "market_snapshot",
    }
    _REGISTRY["price_history"] = {
        "fn": _ph.fetch_history,
        "build_kwargs": lambda params, ctx: {
            "ticker": params.get("ticker") or ctx["ticker"],
            "period": params.get("period", "1y"),
        },
        "source_type": "price_history",
    }
    _REGISTRY["screener_in"] = {
        "fn": _si.extract_company,
        "build_kwargs": lambda params, ctx: {
            "url": (
                params.get("screener_url")
                or f"https://www.screener.in/company/{_bare(params.get('ticker') or ctx['ticker'])}/"
            ),
        },
        "source_type": "company_fundamentals",
    }
    _REGISTRY["peer_comparison"] = {
        "fn": _pc.fetch_peer_comparison,
        "build_kwargs": lambda params, ctx: {
            "ticker": params.get("ticker") or ctx["ticker"],
            "max_peers": params.get("max_peers", 15),
        },
        "source_type": "peer_comparison",
    }
    _REGISTRY["analyst_estimates"] = {
        "fn": _ae.fetch_analyst_estimates,
        "build_kwargs": lambda params, ctx: {
            "ticker": params.get("ticker") or ctx["ticker"],
        },
        "source_type": "analyst_estimates",
    }
    _REGISTRY["exchange_filings"] = {
        "fn": _ef.fetch_announcements,
        "build_kwargs": lambda params, ctx: {
            "ticker": params.get("ticker") or ctx["ticker"],
            "limit":  params.get("limit", 50),
            "material_only": params.get("material_only", False),
        },
        "source_type": "exchange_filings",
    }


def get(module: str) -> dict | None:
    """Return registry entry for module, or None if not registered."""
    _ensure_registry()
    return _REGISTRY.get(module)


def is_registered(module: str) -> bool:
    _ensure_registry()
    return module in _REGISTRY


def registered_modules() -> list[str]:
    _ensure_registry()
    return list(_REGISTRY.keys())


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    print("Registered modules:", registered_modules())
    entry = get("market_data")
    print("market_data fn:", entry["fn"].__name__)
    entry2 = get("screener_in")
    # simulate param building for TCS
    fake_params = {"ticker": "TCS.NS"}
    fake_ctx    = {"ticker": "TCS.NS"}
    kwargs = entry2["build_kwargs"](fake_params, fake_ctx)
    print("screener_in kwargs:", kwargs)
