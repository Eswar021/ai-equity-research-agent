"""
portfolio_layer/portfolio_fit_agent.py  —  Layer 10, Portfolio Fit Agent

Evaluates how each opportunity fits the user's existing portfolio:
concentration risk, sector overlap, correlation, available capital.
Requires config/portfolio.json.

Design doc: docs/system_design_docs/layer_6.md (Layer 10 section)
"""


def evaluate_portfolio_fit(opportunity: dict, portfolio: dict, llm) -> dict:
    """Returns {fit_score, action, rationale}. Stub."""
    raise NotImplementedError
