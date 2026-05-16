"""
intelligence_layer/research_target_planner/deep_dive_module_mapper.py — Layer 6

Maps each selected target (type + depth) to the Layer 7 collector modules to run.
Each module entry is an executable task spec consumed by layer7_runner.

Module names correspond to existing Layer 7 / Phase C collectors:
  market_data, price_history, screener_in, peer_comparison,
  analyst_estimates, exchange_filings, filing_docs,
  targeted_news, sector_theme_research, macro_data

Design doc: docs/system_design_docs/layer_6.md §17 deep_dive_module_mapper.py
"""

from __future__ import annotations

# Routing table: target_type → depth → ordered list of module specs
_MODULE_ROUTES: dict[str, dict[str, list[dict]]] = {
    "listed_company": {
        "light": [
            {"module": "market_data",    "function": "save_market_snapshot",   "criticality": "high"},
            {"module": "price_history",  "function": "save_price_history",      "criticality": "high"},
        ],
        "standard": [
            {"module": "market_data",          "function": "save_market_snapshot",      "criticality": "high"},
            {"module": "price_history",        "function": "save_price_history",         "criticality": "high"},
            {"module": "screener_in",          "function": "save_company_fundamentals",  "criticality": "high"},
            {"module": "peer_comparison",      "function": "save_peer_comparison",       "criticality": "medium"},
            {"module": "analyst_estimates",    "function": "save_analyst_estimates",     "criticality": "medium"},
            {"module": "exchange_filings",     "function": "save_exchange_filings",      "criticality": "medium"},
        ],
        "deep": [
            {"module": "market_data",          "function": "save_market_snapshot",      "criticality": "high"},
            {"module": "price_history",        "function": "save_price_history",         "criticality": "high"},
            {"module": "screener_in",          "function": "save_company_fundamentals",  "criticality": "high"},
            {"module": "peer_comparison",      "function": "save_peer_comparison",       "criticality": "medium"},
            {"module": "analyst_estimates",    "function": "save_analyst_estimates",     "criticality": "medium"},
            {"module": "exchange_filings",     "function": "save_exchange_filings",      "criticality": "medium"},
            {"module": "filing_docs",          "function": "save_filing_docs",           "criticality": "low"},
        ],
    },
    "private_unlisted_company": {
        "light":    [{"module": "targeted_news", "function": "save_targeted_news", "criticality": "high"}],
        "standard": [
            {"module": "targeted_news",  "function": "save_targeted_news",  "criticality": "high"},
            {"module": "proxy_research", "function": "save_proxy_research",  "criticality": "medium"},
        ],
        "deep":     [
            {"module": "targeted_news",  "function": "save_targeted_news",  "criticality": "high"},
            {"module": "proxy_research", "function": "save_proxy_research",  "criticality": "medium"},
        ],
    },
    "sector_theme": {
        "light":    [{"module": "targeted_news",         "function": "save_targeted_news",         "criticality": "high"}],
        "standard": [
            {"module": "targeted_news",          "function": "save_targeted_news",         "criticality": "high"},
            {"module": "sector_theme_research",  "function": "save_sector_theme_research",  "criticality": "medium"},
        ],
        "deep":     [
            {"module": "targeted_news",          "function": "save_targeted_news",         "criticality": "high"},
            {"module": "sector_theme_research",  "function": "save_sector_theme_research",  "criticality": "medium"},
        ],
    },
    "macro_theme": {
        "light":    [{"module": "macro_data",              "function": "save_macro_data",              "criticality": "high"}],
        "standard": [
            {"module": "macro_data",               "function": "save_macro_data",              "criticality": "high"},
            {"module": "sector_sensitivity_research", "function": "save_sector_sensitivity",   "criticality": "medium"},
        ],
        "deep":     [
            {"module": "macro_data",               "function": "save_macro_data",              "criticality": "high"},
            {"module": "sector_sensitivity_research", "function": "save_sector_sensitivity",   "criticality": "medium"},
        ],
    },
}

# Default for unknown types
_DEFAULT_MODULES = [{"module": "targeted_news", "function": "save_targeted_news", "criticality": "low"}]


def map_modules(target: dict) -> list[dict]:
    """
    Return the list of task specs for a target given its type and depth.
    Each spec gets a task_id and target-specific params injected.
    """
    ttype  = target.get("target_type", "unknown")
    depth  = target.get("deep_dive_depth", "standard")
    ticker = target.get("ticker") or ""
    name   = target.get("target_name", "")
    t_id   = target.get("target_id", "")

    route = _MODULE_ROUTES.get(ttype, {}).get(depth, _DEFAULT_MODULES)

    tasks: list[dict] = []
    for spec in route:
        module = spec["module"]
        task_id = f"DD_{_ticker_slug(ticker or name)}_{module.upper()}"
        params  = _build_params(module, ticker, name)
        tasks.append({
            "task_id":     task_id,
            "target_id":   t_id,
            "layer":       "L7",
            "module":      module,
            "function":    spec["function"],
            "params":      params,
            "criticality": spec["criticality"],
        })

    return tasks


def _ticker_slug(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "").replace(".", "").replace("&", "AND").upper()[:12]


def _build_params(module: str, ticker: str, name: str) -> dict:
    bare = ticker.replace(".NS", "").replace(".BO", "") if ticker else ""
    p: dict = {}
    if module == "market_data":
        p = {"ticker": ticker}
    elif module == "price_history":
        p = {"ticker": ticker, "period": "1y", "interval": "1d"}
    elif module == "screener_in":
        p = {"ticker": bare or name}
    elif module == "peer_comparison":
        p = {"ticker": ticker, "max_peers": 15}
    elif module == "analyst_estimates":
        p = {"ticker": ticker}
    elif module == "exchange_filings":
        p = {"ticker": bare or name, "limit": 50, "material_only": True}
    elif module == "filing_docs":
        p = {"ticker": bare or name, "transcripts": 4, "presentations": 2}
    elif module in ("targeted_news", "sector_theme_research", "macro_data",
                    "sector_sensitivity_research", "proxy_research"):
        p = {"query": name, "limit": 20}
    return p
