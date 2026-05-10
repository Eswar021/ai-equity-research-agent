"""
intelligence_layer/market_opportunity_intelligence/layer5_guardrail_precheck.py — Layer 5

Prevents unsupported or overconfident opportunity hypotheses from forwarding to Layer 6.

Rules:
  - No supporting_refs → quarantine (no source grounding)
  - Hypothesis strength "low" AND source_diversity < 2 → downgrade to speculative
  - No likely_beneficiaries_or_targets → theme_only (not actionable as opportunity)
  - Only 1 source ref AND no memory_refs → downgrade
  - Otherwise → pass

Also applies guardrails to cross-domain chains.

Design doc: docs/system_design_docs/layer_5.md §13 layer5_guardrail_precheck.py
"""

from __future__ import annotations

_WEAK_SOURCE_DOMAINS = {
    "twitter", "reddit", "whatsapp", "telegram", "blog", "opinion", "social_media"
}


def check_all(hypotheses: list[dict], cross_domain_chains: list[dict],
              strength_scores: list[dict], signal_groups: list[dict]) -> list[dict]:
    """
    Run guardrails on all hypotheses and chains.
    Returns list of guardrail_result dicts.
    """
    grp_by_id = {g["signal_group_id"]: g for g in signal_groups}
    score_by_opp = {s["opportunity_id"]: s for s in strength_scores}

    results: list[dict] = []

    for hyp in hypotheses:
        result = _check_hypothesis(hyp, grp_by_id, score_by_opp)
        results.append(result)

    for chain in cross_domain_chains:
        results.append(_check_chain(chain))

    return results


def _check_hypothesis(hyp: dict, grp_by_id: dict, score_by_opp: dict) -> dict:
    opp_id      = hyp.get("opportunity_id", "")
    src_refs    = hyp.get("supporting_refs") or []
    beneficiaries = hyp.get("likely_beneficiaries_or_targets") or []
    hyp_strength  = hyp.get("hypothesis_strength", "medium")
    memory_refs   = (hyp.get("origin") or {}).get("memory_refs") or []

    origin = hyp.get("origin") or {}
    grp_id = origin.get("signal_group_id", "")
    grp    = grp_by_id.get(grp_id, {})
    source_div = grp.get("source_diversity_count", 0)

    score_entry = score_by_opp.get(opp_id, {})
    total_score = score_entry.get("hypothesis_strength_score", 50)

    issues: list[str] = []
    action = ""

    # Rule 1: no source refs → quarantine
    if not src_refs:
        issues.append("No supporting_refs — hypothesis has no source grounding.")
        return {
            "object_id":   opp_id,
            "object_type": "opportunity_hypothesis",
            "status":      "quarantined",
            "issues":      issues,
            "action":      "reject_no_sources",
        }

    # Rule 2: no beneficiary mapping → theme_only
    if not beneficiaries:
        issues.append("No likely_beneficiaries_or_targets — cannot identify investable targets.")
        return {
            "object_id":   opp_id,
            "object_type": "opportunity_hypothesis",
            "status":      "theme_only",
            "issues":      issues,
            "action":      "keep_as_theme_not_opportunity",
        }

    # Rule 3: only one weak source and no memory → downgrade
    if len(src_refs) == 1 and not memory_refs:
        issues.append("Single source with no memory corroboration.")
        return {
            "object_id":   opp_id,
            "object_type": "opportunity_hypothesis",
            "status":      "downgraded",
            "issues":      issues,
            "action":      "mark_as_speculative_watch_only",
        }

    # Rule 4: low hypothesis strength and low source diversity → downgrade
    if hyp_strength == "low" and source_div < 2:
        issues.append("Hypothesis strength is 'low' and source diversity < 2.")
        return {
            "object_id":   opp_id,
            "object_type": "opportunity_hypothesis",
            "status":      "downgraded",
            "issues":      issues,
            "action":      "mark_as_speculative_watch_only",
        }

    # Rule 5: strength score below threshold even with sources → watch only
    if total_score < 45 and len(src_refs) < 2:
        issues.append(f"Strength score {total_score} < 45 with limited sources.")
        return {
            "object_id":   opp_id,
            "object_type": "opportunity_hypothesis",
            "status":      "downgraded",
            "issues":      issues,
            "action":      "mark_as_speculative_watch_only",
        }

    return {
        "object_id":   opp_id,
        "object_type": "opportunity_hypothesis",
        "status":      "pass",
        "issues":      [],
        "action":      "",
    }


def _check_chain(chain: dict) -> dict:
    chain_id = chain.get("chain_id", "")
    causal   = chain.get("causal_chain") or []
    issues: list[str] = []

    # Chains without any supporting refs in any step → downgrade
    has_refs = any(step.get("supporting_refs") for step in causal)
    if not has_refs:
        issues.append("No supporting_refs in any causal chain step.")
        return {
            "object_id":   chain_id,
            "object_type": "cross_domain_chain",
            "status":      "downgraded",
            "issues":      issues,
            "action":      "mark_as_speculative_watch_only",
        }

    return {
        "object_id":   chain_id,
        "object_type": "cross_domain_chain",
        "status":      "pass",
        "issues":      [],
        "action":      "",
    }


def apply_guardrail_decisions(hypotheses: list[dict],
                               guardrail_results: list[dict]) -> list[dict]:
    """
    Returns hypotheses list with guardrail status attached.
    Does NOT remove quarantined/downgraded items — caller decides routing.
    """
    result_by_id = {r["object_id"]: r for r in guardrail_results}
    for hyp in hypotheses:
        opp_id = hyp.get("opportunity_id", "")
        gr = result_by_id.get(opp_id, {})
        hyp["guardrail_status"] = gr.get("status", "pass")
        hyp["guardrail_action"] = gr.get("action", "")
        hyp["guardrail_issues"] = gr.get("issues", [])
    return hypotheses
