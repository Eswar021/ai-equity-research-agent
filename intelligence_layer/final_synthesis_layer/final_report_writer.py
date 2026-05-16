"""
intelligence_layer/final_synthesis_layer/final_report_writer.py — Layer 10

Writes the daily investor report in both Markdown and JSON formats.
Pure Python, no LLM. All narrative comes from upstream LLM synthesis.

Report sections:
  1. Executive Summary
  2. Market View
  3. Top Ranked Opportunities (table)
  4. Target Recommendation Cards (one per target)
  5. Watchlist Actions
  6. Avoid / Too Speculative
  7. Key Risks
  8. Data Gaps and Confidence Limitations
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_ACTION_EMOJI = {
    "research_candidate":    "🔍",
    "watchlist":             "👀",
    "wait_for_confirmation": "⏳",
    "avoid_for_now":         "⚠️",
    "too_speculative":       "❌",
}


def write_report(
    final_cards: list[dict],
    market_summary: dict,
    watchlist_actions: list[dict],
    research_run_id: str,
    date_str: str,
    layer10_dir,
) -> tuple[str, dict]:
    """Write markdown + JSON report. Returns (md_path, report_json)."""
    from pathlib import Path
    layer10_dir = Path(layer10_dir)

    # ── Split by action label ─────────────────────────────────────────────────
    research   = [c for c in final_cards if c.get("action_label") == "research_candidate"]
    watchlist  = [c for c in final_cards if c.get("action_label") in ("watchlist", "wait_for_confirmation")]
    avoid      = [c for c in final_cards if c.get("action_label") in ("avoid_for_now", "too_speculative")]

    # ── Collect all risk flags ────────────────────────────────────────────────
    all_high_risks: list[str] = []
    for card in final_cards:
        for rf in (card.get("scorecard", {}).get("top_risks") or [])[:2]:
            if isinstance(rf, str) and rf not in all_high_risks:
                all_high_risks.append(rf[:120])

    # ── Collect data gaps ─────────────────────────────────────────────────────
    gap_summary: dict[str, int] = {}
    for card in final_cards:
        for g in card.get("critical_gaps_summary") or []:
            gap_summary[g[:80]] = gap_summary.get(g[:80], 0) + 1

    # ── Build Markdown ────────────────────────────────────────────────────────
    now_ist = datetime.now(_IST).strftime("%Y-%m-%d %H:%M IST")
    lines: list[str] = []

    lines.append(f"# Daily Investor Intelligence Report — {date_str}")
    lines.append(f"*Generated: {now_ist} | Run: {research_run_id}*")
    lines.append("")

    # 1. Executive Summary
    lines.append("## 1. Executive Summary")
    lines.append(f"**Market Posture:** {market_summary.get('final_market_posture','').replace('_',' ').title()}")
    lines.append(f"> {market_summary.get('summary','')}")
    lines.append("")
    lines.append(f"- **Research candidates:** {len(research)}")
    lines.append(f"- **Watchlist candidates:** {len(watchlist)}")
    lines.append(f"- **Avoid / too speculative:** {len(avoid)}")
    lines.append("")

    # 2. Market View
    lines.append("## 2. Market View")
    lines.append(f"| Dimension | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Regime | {market_summary.get('regime','?')} |")
    lines.append(f"| Risk level | {market_summary.get('risk_level','?')} |")
    lines.append(f"| Trend | {market_summary.get('trend_state','?')} |")
    lines.append(f"| Valuation | {market_summary.get('valuation_state','?')} |")
    lines.append(f"| Liquidity | {market_summary.get('liquidity_flow_state','?')} |")
    lines.append(f"| Volatility | {market_summary.get('volatility_state','?')} |")
    if market_summary.get("favored_sectors"):
        lines.append(f"| Favored sectors | {', '.join(market_summary['favored_sectors'])} |")
    if market_summary.get("avoid_sectors"):
        lines.append(f"| Avoid sectors | {', '.join(market_summary['avoid_sectors'])} |")
    for pt in market_summary.get("key_points", [])[:3]:
        if pt:
            lines.append(f"> {pt[:160]}")
    lines.append("")

    # 3. Ranked Opportunities Table
    lines.append("## 3. Ranked Opportunities")
    lines.append("| Rank | Ticker | Name | Label | Score | Confidence |")
    lines.append("|------|--------|------|-------|-------|------------|")
    for card in final_cards:
        emoji = _ACTION_EMOJI.get(card.get("action_label",""), "")
        lines.append(
            f"| {card.get('rank','-')} "
            f"| {card.get('ticker','')} "
            f"| {card.get('target_name','')[:35]} "
            f"| {emoji} {card.get('action_label','').replace('_',' ')} "
            f"| {card.get('final_opportunity_score',0):.0f} "
            f"| {card.get('confidence_label','?')} |"
        )
    lines.append("")

    # 4. Target Cards
    lines.append("## 4. Target Recommendation Cards")
    for card in final_cards:
        lines.append(f"### {card.get('rank','?')}. {card.get('target_name','')} ({card.get('ticker','')})")
        emoji = _ACTION_EMOJI.get(card.get("action_label",""), "")
        lines.append(f"**{emoji} {card.get('action_label','').replace('_',' ').title()}** | "
                     f"Score: {card.get('final_opportunity_score',0):.0f} | "
                     f"Confidence: {card.get('confidence_label','?')} ({card.get('final_confidence',0):.2f}) | "
                     f"Time horizon: {card.get('time_horizon','?')}")
        lines.append("")
        lines.append(card.get("final_summary", ""))
        lines.append("")

        sup = card.get("supporting_points", [])
        if sup:
            lines.append("**Supportive:**")
            for p in sup[:3]:
                lines.append(f"  - {p}")
        wk = card.get("weakening_points", [])
        if wk:
            lines.append("")
            lines.append("**Weakening:**")
            for p in wk[:3]:
                lines.append(f"  - {p}")

        sc_obj = card.get("scenario_analysis", {})
        if sc_obj:
            lines.append("")
            lines.append(f"**Bull:** {sc_obj.get('bull_case','')}")
            lines.append(f"**Base:** {sc_obj.get('base_case','')}")
            lines.append(f"**Bear:** {sc_obj.get('bear_case','')}")
            inv = sc_obj.get("invalidation_conditions", [])
            if inv:
                lines.append(f"**Invalidated if:** {' | '.join(str(c)[:80] for c in inv[:2])}")

        reasons = card.get("action_reasons", [])
        if reasons:
            lines.append("")
            lines.append(f"**Why this label:** {reasons[0]}")

        lines.append("")
        lines.append("---")
        lines.append("")

    # 5. Watchlist Actions
    lines.append("## 5. Watchlist Actions")
    lines.append("| Action | Ticker | Label | Review Date |")
    lines.append("|--------|--------|-------|-------------|")
    for wa in watchlist_actions:
        lines.append(
            f"| {wa.get('action_type','').replace('_',' ')} "
            f"| {wa.get('ticker','')} "
            f"| {wa.get('action_label','').replace('_',' ')} "
            f"| {wa.get('review_date','')} |"
        )
    lines.append("")

    # 6. Avoid List
    if avoid:
        lines.append("## 6. Avoid / Too Speculative")
        for card in avoid:
            reasons = card.get("action_reasons", [])
            reason_str = reasons[0] if reasons else ""
            lines.append(f"- **{card.get('target_name','')} ({card.get('ticker','')})** "
                         f"[{card.get('action_label','').replace('_',' ')}]: {reason_str}")
        lines.append("")

    # 7. Key Risks
    if all_high_risks:
        lines.append("## 7. Key Risks")
        for r in all_high_risks[:6]:
            lines.append(f"- {r}")
        lines.append("")

    # 8. Data Gaps & Limitations
    if gap_summary:
        lines.append("## 8. Data Gaps and Confidence Limitations")
        for gap, count in sorted(gap_summary.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- {gap} *(affects {count} target(s))*")
        lines.append("")

    lines.append("---")
    lines.append("*This report is for research and decision-support only. "
                 "It does not constitute financial advice or a trade execution instruction.*")

    md_content = "\n".join(lines)
    md_path = layer10_dir / f"final_daily_report_{date_str}.md"
    md_path.write_text(md_content, encoding="utf-8")

    # ── Build JSON ────────────────────────────────────────────────────────────
    report_json = {
        "report_id":          f"FINAL_REPORT_{date_str.replace('-','')}",
        "research_run_id":    research_run_id,
        "created_at":         datetime.now(_IST).isoformat(),
        "date":               date_str,
        "executive_summary": {
            "market_posture": market_summary.get("final_market_posture"),
            "summary":        market_summary.get("summary"),
            "research_candidates": len(research),
            "watchlist_candidates": len(watchlist),
            "avoid_count":    len(avoid),
        },
        "market_summary":     market_summary,
        "ranked_opportunities": [
            {
                "rank":               c.get("rank"),
                "target_id":          c.get("target_id"),
                "target_name":        c.get("target_name"),
                "ticker":             c.get("ticker"),
                "action_label":       c.get("action_label"),
                "final_opportunity_score": c.get("final_opportunity_score"),
                "confidence_label":   c.get("confidence_label"),
                "final_confidence":   c.get("final_confidence"),
            }
            for c in final_cards
        ],
        "target_recommendation_cards": final_cards,
        "watchlist_actions":  watchlist_actions,
        "key_risks":          all_high_risks[:8],
        "data_gaps_summary":  gap_summary,
        "not_trade_execution": True,
    }

    json_path = layer10_dir / f"final_daily_report_{date_str}.json"
    import json
    json_path.write_text(json.dumps(report_json, indent=2, ensure_ascii=False, default=str),
                         encoding="utf-8")

    return str(md_path), report_json
