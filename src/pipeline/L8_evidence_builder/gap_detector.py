"""
Detects two kinds of evidence gaps per target:

  1. Data gaps   — null/missing fields in L7 ticker data that block specific analyses.
     Field → impact mappings come from l8_config.yaml gap_impacts dict.

  2. Question gaps — deep_dive_questions with no keyword match in supporting news signals/facts.
     A question with fewer than 2 keyword matches in the evidence text is flagged.

Output: list of gap dicts — surfaced in the evidence packet so L9 agents know
what they cannot conclude and why.
"""

from __future__ import annotations

_FUNDAMENTAL_FIELDS = [
    "pe_ttm", "pb", "roe_pct", "roce_pct",
    "revenue_growth_ttm_pct", "pat_growth_ttm_pct",
    "net_npa_pct", "nim_pct", "dividend_yield_pct",
]

_OWNERSHIP_FIELDS = ["promoter_pledge_pct", "fii_change_qoq_pct"]

# Words too short or common to be meaningful question keywords
_STOP_WORDS = {"what", "when", "will", "does", "this", "that", "from", "with", "have", "been"}


def detect(
    bundle: dict,
    target: dict,
    supporting_news: list[dict],
    cfg: dict,
) -> list[dict]:
    """Return evidence gap list for one target."""
    gap_impacts = cfg.get("gap_impacts", {})
    gaps: list[dict] = []

    # Data gaps — scan each ticker's L7 fundamentals and ownership
    for ticker, tdata in bundle.get("ticker_data", {}).items():
        status = tdata.get("collection_status", "")

        if status == "failed":
            gaps.append({
                "type":   "collection_failed",
                "ticker": ticker,
                "impact": "no market data available for this ticker",
            })
            continue

        if status == "partial":
            gaps.append({
                "type":   "collection_partial",
                "ticker": ticker,
                "impact": "either price data or fundamental data is missing",
            })

        fundamentals = tdata.get("fundamentals") or {}
        for field in _FUNDAMENTAL_FIELDS:
            if fundamentals.get(field) is None and field in gap_impacts:
                gaps.append({
                    "type":   "missing_field",
                    "ticker": ticker,
                    "field":  field,
                    "impact": gap_impacts[field],
                })

        ownership = tdata.get("ownership") or {}
        for field in _OWNERSHIP_FIELDS:
            if ownership.get(field) is None and field in gap_impacts:
                gaps.append({
                    "type":   "missing_field",
                    "ticker": ticker,
                    "field":  field,
                    "impact": gap_impacts[field],
                })

    # Question gaps — check keyword coverage in supporting news
    evidence_text = " ".join(
        sig.get("text", "").lower()
        for rec in supporting_news
        for sig in rec.get("market_signals", [])
    ) + " " + " ".join(
        f.get("text", "").lower()
        for rec in supporting_news
        for f in rec.get("key_facts", [])
    )

    for q in target.get("deep_dive_questions", []):
        keywords = [
            w.lower() for w in q.split()
            if len(w) > 4 and w.lower() not in _STOP_WORDS
        ]
        if not keywords:
            continue
        hits = sum(1 for w in keywords if w in evidence_text)
        if hits < 2:
            gaps.append({
                "type":     "unanswered_question",
                "question": q,
                "impact":   (
                    f"no news evidence found for this deep-dive question "
                    f"({hits}/{len(keywords)} keywords matched in supporting news)"
                ),
            })

    return gaps
