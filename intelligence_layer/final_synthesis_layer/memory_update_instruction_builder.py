"""
intelligence_layer/final_synthesis_layer/memory_update_instruction_builder.py — Layer 10

Generates memory update instructions for Layer 4 (watch_memory, thesis_memory).
Pure Python, no LLM. Layer 4 consumes this in the next run.

Instruction types:
  add_watch_memory       — add target to short/medium-term watch
  update_thesis          — update thesis confidence / status
  archive_rejected       — archive weak or speculative targets
  store_report_summary   — store daily report summary in long-term memory
"""

from __future__ import annotations
from datetime import date, timedelta


def build_all(final_cards: list[dict], research_run_id: str, today: str) -> list[dict]:
    instructions = []
    seq = 1
    for card in final_cards:
        instrs = _build_for_target(card, research_run_id, today, seq)
        instructions.extend(instrs)
        seq += len(instrs)
    return instructions


def _build_for_target(card: dict, run_id: str, today: str, seq: int) -> list[dict]:
    tid    = card["target_id"]
    name   = card.get("target_name", "")
    ticker = card.get("ticker", "")
    label  = card.get("action_label", "watchlist")
    conf   = card.get("final_confidence", card.get("overall_specialist_confidence", 0.5))
    thesis_status = card.get("thesis_status", "")
    summary = card.get("final_summary", "")[:300]
    scenario = card.get("scenario_analysis", {})
    triggers = scenario.get("monitoring_triggers", [])[:3]
    inv_conds = scenario.get("invalidation_conditions", [])[:3]
    today_date = date.fromisoformat(today)

    results: list[dict] = []

    if label in ("research_candidate", "watchlist", "wait_for_confirmation"):
        retain_days = 90 if label == "research_candidate" else 60
        results.append({
            "instruction_id":    f"MEM_UPDATE_{today.replace('-', '')}_{seq:04d}",
            "research_run_id":   run_id,
            "memory_action":     "add_watch_memory",
            "target_id":         tid,
            "target_name":       name,
            "ticker":            ticker,
            "title":             f"{name} ({label.replace('_', ' ')})",
            "summary":           summary,
            "action_label":      label,
            "thesis_status":     thesis_status,
            "monitoring_triggers": triggers,
            "invalidation_conditions": inv_conds,
            "confidence":        round(conf, 3),
            "retention_days":    retain_days,
            "expires_on":        (today_date + timedelta(days=retain_days)).isoformat(),
        })

    if thesis_status in ("well_supported", "partially_supported", "mixed_support"):
        results.append({
            "instruction_id":  f"MEM_UPDATE_{today.replace('-', '')}_{seq + 1:04d}",
            "research_run_id": run_id,
            "memory_action":   "update_thesis",
            "target_id":       tid,
            "target_name":     name,
            "ticker":          ticker,
            "thesis_status":   thesis_status,
            "new_confidence":  round(conf, 3),
            "monitoring_triggers": triggers,
            "invalidation_conditions": inv_conds,
            "summary":         summary,
        })

    if label in ("avoid_for_now", "too_speculative"):
        results.append({
            "instruction_id":  f"MEM_UPDATE_{today.replace('-', '')}_{seq + 2:04d}",
            "research_run_id": run_id,
            "memory_action":   "archive_rejected",
            "target_id":       tid,
            "target_name":     name,
            "ticker":          ticker,
            "action_label":    label,
            "reason":          (card.get("action_reasons") or ["Insufficient evidence"])[0],
            "confidence":      round(conf, 3),
        })

    return results
