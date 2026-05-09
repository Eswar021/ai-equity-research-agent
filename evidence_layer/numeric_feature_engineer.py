"""
evidence_layer/numeric_feature_engineer.py  —  Layer 8, Numeric Feature Engineer

Computes derived numeric features from raw Phase C data:
price_vs_52w_high_pct, 1y_return, max_drawdown, revenue_cagr_5y, profit_cagr_5y.
Pure Python — no LLM. Output feeds evidence_card_builder.

Design doc: docs/system_design_docs/layer_5.md (Evidence Builder section)
"""


def engineer_features(price_history: dict, fundamentals: dict) -> dict:
    """Returns computed features dict. Stub."""
    raise NotImplementedError
