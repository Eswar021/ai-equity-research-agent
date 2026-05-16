"""
intelligence_layer/final_synthesis_layer — Layer 10

Portfolio Intelligence + Final Report.
Consumes Layer 9 specialist scorecards and upstream context to produce
final action labels, ranked opportunities, and the daily investor report.
"""

from intelligence_layer.final_synthesis_layer import (
    final_input_loader,
    final_context_assembler,
    market_posture_synthesizer,
    target_synthesis_engine,
    opportunity_ranker,
    recommendation_policy_engine,
    risk_confidence_calibrator,
    scenario_and_invalidation_builder,
    watchlist_action_builder,
    memory_update_instruction_builder,
    final_report_writer,
    final_guardrail_validator,
)

__all__ = [
    "final_input_loader",
    "final_context_assembler",
    "market_posture_synthesizer",
    "target_synthesis_engine",
    "opportunity_ranker",
    "recommendation_policy_engine",
    "risk_confidence_calibrator",
    "scenario_and_invalidation_builder",
    "watchlist_action_builder",
    "memory_update_instruction_builder",
    "final_report_writer",
    "final_guardrail_validator",
]
