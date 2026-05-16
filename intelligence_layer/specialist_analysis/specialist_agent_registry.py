"""
intelligence_layer/specialist_analysis/specialist_agent_registry.py — Layer 9

Maps agent_type → run function. Lazy import to avoid circular deps.
"""

from __future__ import annotations


def get_agent_fn(agent_type: str):
    """Returns the run(packet, context, llm) function for the given agent_type."""
    if agent_type == "fundamental_agent":
        from intelligence_layer.specialist_analysis.agents import company_fundamental_agent
        return company_fundamental_agent.run
    if agent_type == "valuation_agent":
        from intelligence_layer.specialist_analysis.agents import valuation_agent
        return valuation_agent.run
    if agent_type == "risk_agent":
        from intelligence_layer.specialist_analysis.agents import risk_agent
        return risk_agent.run
    if agent_type == "thesis_agent":
        from intelligence_layer.specialist_analysis.agents import thesis_validation_agent
        return thesis_validation_agent.run
    raise ValueError(f"No agent registered for type: {agent_type}")


REGISTERED_AGENT_TYPES = ["fundamental_agent", "valuation_agent", "risk_agent", "thesis_agent"]
