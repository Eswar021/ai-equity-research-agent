"""
intelligence_layer/specialist_analysis/agent_task_planner.py — Layer 9

Creates one executable agent task per (target, agent_type) pair from L8 packets.
Thesis validation agent is always planned last — it synthesizes other assessments.

ADR-L9-002: agent_packet_validator not built — basic checks inline here.
"""

from __future__ import annotations

# Agents that must run before thesis validation
_PREREQUISITE_AGENTS = {"fundamental_agent", "valuation_agent", "risk_agent"}

# All agent types we run (in order: prerequisites first, thesis last)
_AGENT_ORDER = ["fundamental_agent", "valuation_agent", "risk_agent", "thesis_agent"]


def plan_tasks(inputs: dict) -> list[dict]:
    """
    Returns list of agent task dicts:
    {
        agent_task_id, target_id, agent_type, packet_id,
        packet, priority, run_after (list of agent_task_ids)
    }
    """
    packets_by_target = inputs["packets_by_target"]
    packs_by_target   = inputs["packs_by_target"]

    tasks: list[dict] = []
    task_ids_by_target: dict[str, dict[str, str]] = {}  # target_id → agent_type → task_id

    for tid, agent_packets in packets_by_target.items():
        pack = packs_by_target.get(tid, {})
        if not pack.get("ready_for_agents", False):
            continue

        task_ids_by_target[tid] = {}
        priority = "high" if pack.get("coverage_pct", 0) >= 0.8 else "medium"

        for agent_type in _AGENT_ORDER:
            pkt = agent_packets.get(agent_type)
            if pkt is None:
                continue

            # Basic inline validation
            if not pkt.get("packet_id") or not pkt.get("target_id"):
                continue

            task_id = f"AGTASK_{tid}_{agent_type.upper()}"
            task_ids_by_target[tid][agent_type] = task_id

            # Thesis agent runs after all others
            run_after: list[str] = []
            if agent_type == "thesis_agent":
                run_after = [
                    task_ids_by_target[tid][a]
                    for a in _PREREQUISITE_AGENTS
                    if a in task_ids_by_target.get(tid, {})
                ]

            tasks.append({
                "agent_task_id": task_id,
                "target_id":     tid,
                "target_name":   pack.get("target_name", ""),
                "ticker":        pack.get("ticker", ""),
                "agent_type":    agent_type,
                "packet_id":     pkt["packet_id"],
                "packet":        pkt,
                "priority":      priority,
                "run_after":     run_after,
            })

    return tasks
