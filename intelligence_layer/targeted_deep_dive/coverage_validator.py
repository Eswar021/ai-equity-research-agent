"""
intelligence_layer/targeted_deep_dive/coverage_validator.py — Layer 7

Checks whether collected data covers the research questions from Layer 6.
Keyword-based mapping: question text → modules that would answer it.

ADR-L7-009: keyword dict approach — no semantic NLP needed for predictable question types.

Design doc: docs/system_design_docs/layer_7.md §10.11 coverage_validator.py
"""

from __future__ import annotations

# Question keyword → modules that provide coverage
# Ordered from most specific to most generic
_QUESTION_COVERAGE_MAP: list[tuple[list[str], list[str]]] = [
    (["management", "concall", "commentary", "transcript", "cfo", "ceo", "guidance"],
     ["filing_docs"]),
    (["margin", "nim", "profitability", "earnings", "revenue", "growth", "cagr", "roe"],
     ["screener_in", "analyst_estimates"]),
    (["valuation", "pe", "price", "peer", "relative", "comparison", "sector average"],
     ["peer_comparison", "market_data", "screener_in"]),
    (["analyst", "estimate", "target", "consensus", "rating", "buy", "sell"],
     ["analyst_estimates"]),
    (["price", "stock", "52-week", "return", "momentum", "trend", "high", "low"],
     ["market_data", "price_history"]),
    (["history", "historical", "1y", "3m", "performance"],
     ["price_history"]),
    (["fundamental", "balance sheet", "debt", "cash flow", "equity"],
     ["screener_in"]),
    (["announcement", "filing", "exchange", "disclosure", "regulatory"],
     ["exchange_filings"]),
    (["corporate action", "dividend", "buyback", "split", "bonus"],
     ["corporate_actions"]),
    (["proxy", "supply chain", "supplier", "customer", "partner"],
     ["exchange_filings", "screener_in"]),
]


def _covering_modules(question: str) -> list[str]:
    q = question.lower()
    for keywords, modules in _QUESTION_COVERAGE_MAP:
        if any(kw in q for kw in keywords):
            return modules
    return []  # no specific coverage rule → not mappable


def validate_coverage(ctx: dict, task_results: list[dict]) -> dict:
    """
    Returns per-question coverage + overall coverage_status.
    """
    succeeded_modules = {r["module"] for r in task_results if r["status"] == "success"}
    questions         = ctx.get("questions_to_answer", [])

    question_coverage = []
    covered_count = 0

    for q in questions:
        needed = _covering_modules(q)
        if not needed:
            # question doesn't map to any module we track — mark as unknown
            question_coverage.append({
                "question":          q,
                "coverage":          "unknown",
                "available_modules": [],
                "missing_modules":   [],
                "notes":             "No module mapping for this question type",
            })
            continue

        available = [m for m in needed if m in succeeded_modules]
        missing   = [m for m in needed if m not in succeeded_modules]

        if available:
            covered_count += 1
            coverage = "available" if not missing else "partial"
        else:
            coverage = "missing"

        question_coverage.append({
            "question":          q,
            "coverage":          coverage,
            "available_modules": available,
            "missing_modules":   missing,
            "notes":             (
                f"No transcript available — management commentary gap"
                if "filing_docs" in missing else
                ""
            ),
        })

    total = len(questions)
    if total == 0:
        overall = "no_questions"
    elif covered_count == total:
        overall = "full"
    elif covered_count == 0:
        overall = "missing"
    else:
        overall = "partial"

    return {
        "target_id":        ctx["target_id"],
        "coverage_status":  overall,
        "covered_questions": covered_count,
        "total_questions":   total,
        "question_coverage": question_coverage,
    }


def validate_all_coverage(contexts: list[dict], all_task_results: dict[str, list[dict]]) -> list[dict]:
    return [
        validate_coverage(ctx, all_task_results.get(ctx["target_id"], []))
        for ctx in contexts
    ]
