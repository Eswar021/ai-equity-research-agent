"""
intelligence_layer/canonical_intelligence_extraction/post_processors/contradiction_hint_detector.py — Layer 3

Detects early hints of contradiction between extracted intelligence objects.
Full contradiction checking happens in the cross-cutting Guardrails layer.
Layer 3 only flags OBVIOUS conflicts.

Examples (design doc §19):
  - Claim says "EPS revisions positive" but structured fact shows EPS revised down
  - Claim says "company is growing" but fact shows revenue declined
  - Claim says "market is bullish" but signal shows sustained FII net selling

Design doc: docs/system_design_docs/layer_3.md §19 contradiction_hint_detector.py
"""

from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_HINT_COUNTER = [0]

def _next_hint_id() -> str:
    _HINT_COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"CONTRA_{today}_{_HINT_COUNTER[0]:04d}"


def _norm_entity(name: str) -> str:
    s = re.sub(r'\b(ltd|limited|pvt|corp|inc|co)\b', '', name.lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).strip()


# ── Positive / negative keyword patterns ─────────────────────────────────────

_POS_PATTERNS = re.compile(
    r'\b(growth|growing|improving|positive|beat|above|strong|rising|upgraded|bullish|buying|net buy)\b',
    re.IGNORECASE,
)
_NEG_PATTERNS = re.compile(
    r'\b(decline|declining|miss|negative|below|weak|falling|downgraded|bearish|selling|net sell|pressure|loss|slowdown)\b',
    re.IGNORECASE,
)

def _sentiment(text: str) -> str:
    has_pos = bool(_POS_PATTERNS.search(text))
    has_neg = bool(_NEG_PATTERNS.search(text))
    if has_pos and not has_neg:
        return "positive"
    if has_neg and not has_pos:
        return "negative"
    return "mixed"


def detect(
    claims:  list[dict],
    facts:   list[dict],
    signals: list[dict],
) -> list[dict]:
    """
    Scan for obvious contradictions between claims and facts/signals.

    Returns:
        list of contradiction hint dicts:
        {
          "hint_id": str,
          "object_1": str,      # claim_id
          "object_2": str,      # fact_id or signal_id
          "reason": str,
          "severity": "low" | "medium" | "high",
          "action": "send_to_later_contradiction_checker",
        }
    """
    hints: list[dict] = []

    # Build entity → facts map for quick lookup
    entity_to_facts: dict[str, list[dict]] = {}
    for fact in facts:
        for ent in fact.get("entities", []):
            nent = _norm_entity(ent)
            entity_to_facts.setdefault(nent, []).append(fact)

    # Build entity → signals map
    entity_to_signals: dict[str, list[dict]] = {}
    for sig in signals:
        nent = _norm_entity(sig.get("signal_name", ""))
        entity_to_signals.setdefault(nent, []).append(sig)

    # Check each claim against facts about the same entities
    for claim in claims:
        claim_text = claim.get("claim_text", "") + " " + (claim.get("source_refs") or [{}])[0].get("supporting_text", "")
        claim_sent = _sentiment(claim_text)

        for ent_name in claim.get("entities", []):
            nent = _norm_entity(ent_name)
            related_facts = entity_to_facts.get(nent, [])

            for fact in related_facts:
                fact_sent = _sentiment(fact.get("fact_text", ""))
                if claim_sent == "positive" and fact_sent == "negative":
                    hints.append(_make_hint(
                        claim["claim_id"], fact["fact_id"],
                        f"Claim about {ent_name} appears positive but related fact is negative. "
                        f"Claim: '{claim.get('claim_text','')[:80]}'. "
                        f"Fact: '{fact.get('fact_text','')[:80]}'.",
                        "medium",
                    ))
                elif claim_sent == "negative" and fact_sent == "positive":
                    hints.append(_make_hint(
                        claim["claim_id"], fact["fact_id"],
                        f"Claim about {ent_name} appears negative but related fact is positive.",
                        "low",
                    ))

    # Specific pattern: FII claim vs FII signal
    fii_claims = [c for c in claims if any(
        e.lower() in ("fii", "foreign institutional investors", "fiis")
        for e in c.get("entities", [])
    )]
    fii_signals = [s for s in signals if "fii" in s.get("metric_name", "").lower()]

    for claim in fii_claims:
        claim_text = claim.get("claim_text", "")
        for sig in fii_signals:
            sig_dir    = sig.get("direction_hint", "neutral")
            claim_sent = _sentiment(claim_text)
            if claim_sent == "positive" and sig_dir == "negative":
                hints.append(_make_hint(
                    claim["claim_id"], sig["signal_id"],
                    f"Claim says market/FII is positive but FII signal shows net selling "
                    f"({sig.get('metric_value')} {sig.get('unit','')}).",
                    "high",
                ))
            elif claim_sent == "negative" and sig_dir == "positive":
                hints.append(_make_hint(
                    claim["claim_id"], sig["signal_id"],
                    f"Claim says FII/market is negative but signal shows net buying.",
                    "medium",
                ))

    return hints


def _make_hint(obj1: str, obj2: str, reason: str, severity: str) -> dict:
    return {
        "hint_id":    _next_hint_id(),
        "object_1":   obj1,
        "object_2":   obj2,
        "reason":     reason,
        "severity":   severity,
        "action":     "send_to_later_contradiction_checker",
    }
