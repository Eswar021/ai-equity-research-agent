"""
intelligence_layer/research_target_planner/ticker_resolver.py  —  Layer 6, Ticker Resolver

Wraps context_ext_layer.utils.ticker_extractor with enrichment:
confirms the ticker is NSE-listed, liquid, and not on any exclusion list.

Design doc: docs/system_design_docs/layer_6.md
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from context_ext_layer.utils.ticker_extractor import lookup_ticker


def resolve_ticker(company_name: str, threshold: int = 82) -> str | None:
    """Returns NSE ticker string or None. Wraps lookup_ticker with validation."""
    return lookup_ticker(company_name, threshold=threshold)
