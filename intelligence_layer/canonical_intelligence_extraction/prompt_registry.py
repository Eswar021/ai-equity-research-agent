"""
intelligence_layer/canonical_intelligence_extraction/prompt_registry.py — Layer 3

Stores strict JSON extraction prompts and the Pydantic output schemas they produce.

Each extraction profile maps to:
  - A system prompt with strict JSON-only instructions
  - A Pydantic schema (DocumentExtractionResult) that the LLM must satisfy

One LLM call per document chunk extracts ALL intelligence types at once:
  entities, facts, claims, events, themes

This is more efficient than 5 separate calls and follows the design doc pattern:
  document_router → extraction_chunker → prompt_registry → [entity/fact/claim/event/theme extractors]
  (prompt_registry provides the template; extractors format the returned data)

Design doc: docs/system_design_docs/layer_3.md §6 prompt_registry.py
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


# ── Pydantic schemas for structured LLM output ───────────────────────────────

class EntityItem(BaseModel):
    entity_name:    str
    entity_type:    Literal[
        "listed_company", "private_company", "business_group",
        "sector", "industry", "index", "commodity", "currency",
        "macro_indicator", "policy", "regulator", "government_body",
        "person", "product", "technology_theme", "regional_theme",
        "mutual_fund", "etf", "reit", "invit", "unknown",
    ]
    ticker_hint:    str | None        # raw text the LLM thinks is the ticker
    market:         Literal["india", "us", "global", "unknown"] = "india"
    confidence:     float             # 0.0–1.0
    supporting_text: str              # exact quote from the source


class FactItem(BaseModel):
    fact_text:       str
    fact_type:       Literal[
        "macro_policy_fact", "earnings_fact", "revenue_fact",
        "market_snapshot_fact", "institutional_flow_fact",
        "analyst_fact", "corporate_action_fact", "regulatory_fact",
        "management_statement_fact", "other_fact",
    ]
    entities:        list[str]        # entity names mentioned
    metric_name:     str | None       # e.g. "repo_rate", "revenue_yoy"
    metric_value:    str | None       # raw value as string
    unit:            str | None       # e.g. "%", "INR crore"
    supporting_text: str
    confidence:      float


class ClaimItem(BaseModel):
    claim_text:           str
    claim_type:           Literal[
        "opinion", "forecast", "rumor", "analyst_view",
        "management_guidance", "market_commentary", "promotional_claim",
    ]
    entities:             list[str]
    requires_verification: bool
    evidence_strength:    Literal["high", "medium", "low", "unknown"]
    supporting_text:      str
    confidence:           float


class EventItem(BaseModel):
    event_type:    Literal[
        "earnings_beat", "earnings_miss", "guidance_raise", "guidance_cut",
        "margin_pressure", "revenue_growth", "revenue_decline",
        "large_order_win", "capex_announcement", "merger_acquisition",
        "divestment", "management_change", "regulatory_action", "legal_issue",
        "fraud_or_accounting_concern", "credit_rating_change",
        "dividend", "buyback", "split_bonus", "bulk_deal", "block_deal",
        "policy_change", "rate_decision", "inflation_data",
        "currency_move", "commodity_move", "sector_rotation",
        "analyst_upgrade", "analyst_downgrade", "ipo_news",
        "private_company_funding", "industrial_corridor",
        "real_estate_policy", "other",
    ]
    event_title:    str
    event_summary:  str
    entities:       list[str]
    impact_scope:   list[Literal["company", "sector", "macro", "commodity", "asset_class", "region", "cross_domain"]]
    initial_sentiment:          Literal["positive", "negative", "neutral", "mixed", "unknown"]
    business_impact:            Literal["positive", "negative", "neutral", "mixed", "unknown"]
    severity:                   Literal["high", "medium", "low"]
    time_horizon:               Literal["short_term", "medium_term", "long_term", "unknown"]
    temporary_or_structural_hint: Literal["temporary", "structural", "unknown"]
    supporting_text:            str
    confidence:                 float


class ThemeItem(BaseModel):
    theme_name:         str
    theme_type:         Literal[
        "sector_theme", "macro_theme", "policy_theme", "technology_theme",
        "regional_theme", "commodity_theme", "cross_domain_theme", "other",
    ]
    description:        str
    related_entities:   list[str]
    time_horizon_hint:  Literal["short_term", "medium_term", "long_term", "unknown"]
    confidence:         float


class DocumentExtractionResult(BaseModel):
    entities: list[EntityItem]
    facts:    list[FactItem]
    claims:   list[ClaimItem]
    events:   list[EventItem]
    themes:   list[ThemeItem]


# ── Batch schema for headline packing (N short docs → 1 LLM call) ────────────

class PerArticleResult(BaseModel):
    article_index: int
    entities: list[EntityItem] = []
    facts:    list[FactItem]   = []
    claims:   list[ClaimItem]  = []
    events:   list[EventItem]  = []
    themes:   list[ThemeItem]  = []

class BatchExtractionResult(BaseModel):
    articles: list[PerArticleResult]


# ── System prompts by extraction profile ─────────────────────────────────────

_BASE_RULES = """Rules:
- Return JSON only. Do not add any explanation outside the JSON.
- Do not make buy/sell recommendations.
- Do not infer beyond what is explicitly stated in the text.
- Do not invent tickers. If entity is unresolved, leave ticker_hint null.
- Separate facts (verifiable statements) from claims (opinions/forecasts/rumors).
- Every extracted object must include supporting_text — an exact or near-exact quote.
- If evidence is weak or ambiguous, use lower confidence (0.0–0.4).
- If not enough information for a field, use "unknown" or null.
- Extract ALL investment-relevant items. Do not summarize or filter."""

_PROMPTS: dict[str, str] = {
    "news_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing a news article. Extract all investment-relevant intelligence.

{_BASE_RULES}

Focus on:
- Listed and private companies mentioned
- Any verifiable financial facts (earnings, revenue, guidance, rates, flows)
- Analyst opinions, forecasts, and commentary (mark as claims, not facts)
- Discrete market events (earnings, M&A, regulatory actions, management changes)
- Emerging themes or sector trends

Extract entities, facts, claims, events, and themes from the text below.""",

    "newsletter_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing a market newsletter or curated commentary. Newsletters often contain opinions and forecasts — classify carefully.

{_BASE_RULES}

Focus on:
- Claims and opinions (the author's views — mark as claims, not facts)
- Themes the author is highlighting
- Any entities mentioned with specific context
- Occasional factual statements (earnings, data points) — mark those as facts

Extract entities, facts, claims, events, and themes from the text below.""",

    "transcript_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing a YouTube video or podcast transcript from a market analyst or commentator.

{_BASE_RULES}

Treat all speaker statements as claims unless they cite official data sources.
Official data (RBI data, NSE data, exchange filings) cited in speech can be facts.

Focus on:
- Companies and sectors discussed
- Speaker's views and predictions (mark as claims)
- Any data points cited (mark as facts if sourced, claims if unsourced)
- Themes being discussed

Extract entities, facts, claims, events, and themes from the text below.""",

    "concall_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing an earnings call or investor relations transcript. This is management speaking directly.

{_BASE_RULES}

Management statements about future guidance, capex, margins, and revenue are management_guidance claims.
Historical numbers cited in the call are facts if they match prior disclosures.

Focus on:
- Guidance changes (raise/cut) — mark as events
- Management commentary on outlook — mark as management_guidance claims
- Historical data mentioned — mark as facts
- Any surprises vs expectations (beat/miss) — mark as events

Extract entities, facts, claims, events, and themes from the text below.""",

    "filing_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing an exchange filing, SEBI disclosure, NSE announcement, or investor presentation.

{_BASE_RULES}

Filings are official documents — statements here are high-confidence facts.
Corporate actions, regulatory approvals, management changes are events.

Focus on:
- Official announcements (dividends, buybacks, M&A, management changes)
- Financial disclosures (revenue, profit, EPS)
- Regulatory actions or compliance items
- Forward-looking statements in presentations (mark as management_guidance claims)

Extract entities, facts, claims, events, and themes from the text below.""",

    "headline_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing a short news headline or RSS summary. Extract what you can — these are short.

{_BASE_RULES}

Focus on: entities mentioned and the primary event type. Skip facts/claims if text is too short.
Extract entities and events. Add facts and claims only if clearly present.

Extract entities, facts, claims, events, and themes from the text below.""",

    "generic_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing a general web article or scraped content.

{_BASE_RULES}

Extract entities, facts, claims, events, and themes from the text below.""",

    "batch_headline_extraction": f"""You are an investment intelligence extraction model specializing in Indian financial markets.
You are processing multiple short news headlines. Each is prefixed with "=== Article N ===".

{_BASE_RULES}

For EACH article:
- Extract entities and events (primary value from headlines)
- Add facts and claims only if clearly stated
- Use article_index = N from the prefix
- Keep supporting_text short (the headline itself is usually enough)
- Return an empty list for a type if nothing is present

Return the "articles" array with one entry per article, each with its article_index.""",
}


def get_system_prompt(extraction_profile: str) -> str:
    """Return system prompt for a given extraction profile."""
    return _PROMPTS.get(extraction_profile, _PROMPTS["generic_extraction"])


def get_schema() -> type[DocumentExtractionResult]:
    """Return the Pydantic schema for structured LLM output."""
    return DocumentExtractionResult


def get_batch_schema() -> type[BatchExtractionResult]:
    """Return the Pydantic schema for batch headline extraction."""
    return BatchExtractionResult
