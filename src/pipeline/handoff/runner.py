"""
Handoff module — packages pipeline output into markdown files for manual AI analysis.

Two profiles:

  after_l4  — checkpoint review before L5 hypothesis generation
              Reads:  output/{date}/L4/memory_context.json
                      output/{date}/L1/raw_records.json  (FII/macro context)
              Writes: output/{date}/handoff/after_l4/
                        01_brief.md         role + run context + task description
                        02_signals.md       entities ranked by signal weight + signal breakdown

  after_l8  — deep analysis handoff (replaces L9 + L10)
              Reads:  output/{date}/L8/evidence_packets.json
              Writes: output/{date}/handoff/after_l8/
                        01_brief.md         role + run context + scoring guide + targets overview
                        02_targets.md       one section per target (thesis, market data, news signals)
                        03_output_template.md  blank template for the AI to fill in

Usage:
    python -m src.pipeline.handoff.runner --profile after_l4
    python -m src.pipeline.handoff.runner --profile after_l8
    python -m src.pipeline.handoff.runner --profile after_l8 --date 2026-06-09
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, load_manifest, output_dir, today


def run(profile: str, run_date: str | None = None) -> Path:
    date = run_date or today()
    if profile not in ("after_l4", "after_l8"):
        raise ValueError(f"Unknown profile {profile!r}. Use 'after_l4' or 'after_l8'.")

    load_manifest(date)  # fail hard if no manifest

    out_dir = output_dir(date) / "handoff" / profile
    out_dir.mkdir(parents=True, exist_ok=True)

    if profile == "after_l4":
        files = _build_after_l4(date, out_dir)
    else:
        files = _build_after_l8(date, out_dir)

    print(f"\nHandoff package written: {out_dir}")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    print()
    return out_dir


# ---------------------------------------------------------------------------
# after_l4
# ---------------------------------------------------------------------------

def _build_after_l4(date: str, out_dir: Path) -> list[Path]:
    l4_path = output_dir(date) / "L4" / "memory_context.json"
    if not l4_path.exists():
        raise FileNotFoundError(f"L4 output not found: {l4_path} — run L4 first")

    l4      = json.loads(l4_path.read_text())
    records = l4["records"]
    recalled = l4.get("memory", [])

    fii_row, nifty_change, india_vix = _load_l1_market_context(date)

    entity_signals: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        for cand in rec.get("memory_candidates", []):
            if cand.get("worth_storing"):
                entity = (cand.get("entity") or "").strip()
                if entity:
                    entity_signals[entity].append({
                        "type":      cand.get("object_type", ""),
                        "text":      cand.get("title", ""),
                        "direction": cand.get("direction", ""),
                        "score":     cand.get("total_score", 0),
                        "source":    rec.get("source", ""),
                    })

    ranked = sorted(
        entity_signals.items(),
        key=lambda x: sum(s["score"] for s in x[1]),
        reverse=True,
    )

    worth_records = sum(
        1 for r in records
        if any(c.get("worth_storing") for c in r.get("memory_candidates", []))
    )

    f1 = out_dir / "01_brief.md"
    f2 = out_dir / "02_signals.md"
    f1.write_text(
        _l4_brief(date, len(records), worth_records, len(ranked), fii_row, nifty_change, india_vix, ranked[:10]),
        encoding="utf-8",
    )
    f2.write_text(_l4_signals(date, ranked, recalled), encoding="utf-8")
    return [f1, f2]


def _load_l1_market_context(date: str) -> tuple[dict, float | None, float | None]:
    path = output_dir(date) / "L1" / "raw_records.json"
    if not path.exists():
        return {}, None, None

    records     = json.loads(path.read_text()).get("records", [])
    fii_row     = {}
    nifty_change: float | None = None
    india_vix:   float | None = None

    for rec in records:
        if rec.get("source") == "fii_dii":
            rows = rec.get("metadata", {}).get("data", {}).get("data", [])
            if rows:
                fii_row = rows[0]
        if rec.get("source") == "india_macro":
            snap = rec.get("metadata", {}).get("data", {})
            for idx in snap.get("nse_indices", []):
                if idx.get("name") == "NIFTY 50":
                    nifty_change = idx.get("change_pct")
                    break
            india_vix = (snap.get("market_rates") or {}).get("india_vix", {}).get("value")

    return fii_row, nifty_change, india_vix


def _l4_brief(
    date: str,
    total: int,
    worth: int,
    entities: int,
    fii_row: dict,
    nifty_change: float | None,
    india_vix: float | None,
    top_entities: list,
) -> str:
    ts  = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    fii = fii_row.get("fii", {})
    dii = fii_row.get("dii", {})

    fii_net   = fii.get("net_cr")
    dii_net   = dii.get("net_cr")
    fii_label = "buying" if (fii_net or 0) > 500 else ("selling" if (fii_net or 0) < -500 else "neutral")

    fii_str   = f"₹{fii_net:+,.0f} cr ({fii_label})" if fii_net is not None else "N/A"
    dii_str   = f"₹{dii_net:+,.0f} cr"               if dii_net is not None else "N/A"
    nifty_str = f"{nifty_change:+.2f}%"               if nifty_change is not None else "N/A"
    vix_str   = f"{india_vix:.1f}"                     if india_vix is not None else "N/A"

    top_table = "\n".join(
        f"  {i+1:2d}. {ent:40s} {len(sigs):3d} signals  "
        f"({sum(1 for s in sigs if s['direction']=='bullish')}↑ "
        f"{sum(1 for s in sigs if s['direction']=='bearish')}↓)"
        for i, (ent, sigs) in enumerate(top_entities)
    )

    return f"""# Signal Review Briefing — {date}
**Generated:** {ts}
**Profile:** after_l4 (checkpoint before L5 hypothesis generation)

---

## Your Role

You are reviewing pre-processed investment signal data from an automated pipeline that
scraped and extracted signals from {total} articles, newsletters, and market feeds on {date}.

**Your job:**
- Identify the 5–10 most promising investment themes or entities worth deep research today
- For each, explain in 2–3 sentences WHY the signals suggest it is worth pursuing
- Flag any themes that look like noise, lack credibility, or duplicate each other
- Note any surprising gaps — important market events that should appear here but don't

**What happens next:** After your review, the pipeline will run L5 (hypothesis generation)
via API. Your observations help the operator decide whether to adjust analysis focus or
config before committing to expensive L7/L8 data collection.

---

## Run Context

| Field                   | Value        |
|-------------------------|--------------|
| Date                    | {date}       |
| FII Net Flow            | {fii_str}    |
| DII Net Flow            | {dii_str}    |
| Nifty 50                | {nifty_str}  |
| India VIX               | {vix_str}    |
| Total records processed | {total}      |
| Records with signals    | {worth}      |
| Unique investable entities | {entities} |

---

## Top Entities by Signal Count

```
{top_table}
```

Full signal breakdown in `02_signals.md`.

---

## Instructions

1. Read `02_signals.md` for the complete signal breakdown per entity
2. Write your review (which themes are worth pursuing, which are noise, what's missing)
3. Share with the operator before running L5

**Do NOT write price targets or position sizes in this review.**
"""


def _l4_signals(date: str, ranked: list, recalled: list) -> str:
    lines = [f"# Signal Data — {date}", ""]
    lines.append(f"{len(ranked)} entities with worth-storing signals.\n")

    for entity, sigs in ranked:
        bull = sum(1 for s in sigs if s["direction"] == "bullish")
        bear = sum(1 for s in sigs if s["direction"] == "bearish")
        lines.append(f"---\n\n### {entity}")
        lines.append(f"**{len(sigs)} signals** — {bull} bullish, {bear} bearish\n")
        for s in sorted(sigs, key=lambda x: -x["score"]):
            icon = "↑" if s["direction"] == "bullish" else ("↓" if s["direction"] == "bearish" else "→")
            lines.append(
                f"- {icon} [{s['type']}] {s['text']}"
                f"  *(score: {s['score']}, source: {s['source']})*"
            )
        lines.append("")

    lines.append("---\n\n## Recalled Past Memory\n")
    if recalled:
        for m in recalled[:10]:
            summary = m.get("summary") or m.get("title") or ""
            lines.append(
                f"- [{m.get('memory_type','?')}] **{m.get('entity','')}** — {summary[:120]}"
            )
        if len(recalled) > 10:
            lines.append(f"\n... and {len(recalled) - 10} more.")
    else:
        lines.append("No past memories recalled (first run or empty index).")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# after_l8
# ---------------------------------------------------------------------------

def _build_after_l8(date: str, out_dir: Path) -> list[Path]:
    l8_path = output_dir(date) / "L8" / "evidence_packets.json"
    if not l8_path.exists():
        raise FileNotFoundError(f"L8 output not found: {l8_path} — run L8 first")

    packets = json.loads(l8_path.read_text())["packets"]

    f1 = out_dir / "01_brief.md"
    f2 = out_dir / "02_targets.md"
    f3 = out_dir / "03_output_template.md"
    f1.write_text(_l8_brief(date, packets),    encoding="utf-8")
    f2.write_text(_l8_targets(date, packets),  encoding="utf-8")
    f3.write_text(_l8_template(date, packets), encoding="utf-8")
    return [f1, f2, f3]


def _l8_brief(date: str, packets: list) -> str:
    ts = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    macro = {}
    for p in packets:
        mc = p.get("macro_context")
        if mc:
            macro = mc
            break

    regime    = macro.get("regime", "unknown")
    fii_net   = macro.get("fii_net_cr")
    nifty_chg = macro.get("nifty_change_pct")
    fii_str   = f"₹{fii_net:+,.0f} cr" if fii_net is not None else "N/A"
    nifty_str = f"{nifty_chg:+.2f}%"   if nifty_chg is not None else "N/A"

    regime_base = {"bull": 75, "bear": 25, "sideways": 50, "uncertain": 50}.get(regime, 50)
    fii_adj     = "+10" if (fii_net or 0) > 500 else ("-10" if (fii_net or 0) < -500 else "0")

    tbl_rows = []
    for i, p in enumerate(packets, 1):
        res      = p.get("resolution", {})
        res_type = res.get("type", "?")
        tickers  = ", ".join(res.get("tickers", [])[:3]) or "—"
        tbl_rows.append(
            f"| {i} | {p['target_entity'][:30]:30s} | {p.get('time_horizon','?'):12s} "
            f"| {p.get('bucket','?'):10s} | {str(p.get('score','?')):>5} "
            f"| {res_type:12s} | {tickers} |"
        )
    tbl = (
        "| # | Entity                         | Horizon      | Bucket     | Score | Type         | Tickers |\n"
        "|---|--------------------------------|--------------|------------|-------|--------------|----------|\n"
        + "\n".join(tbl_rows)
    )

    return f"""# Investment Analysis Handoff — {date}
**Generated:** {ts}
**Profile:** after_l8 (replaces L9 specialist agents + L10 report)

---

## Your Role

You are a senior investment analyst reviewing {len(packets)} deep-dive research targets
identified from Indian market signals on {date}. Each target has been fully assembled:
live market data, financial fundamentals, shareholding patterns, and pre-extracted news
intelligence are in `02_targets.md`.

**Produce a complete investment analysis for each target.** This replaces the automated
pipeline analysis. Be more nuanced than a formulaic model — use judgment, and flag
explicitly when data is thin or contradicts the thesis.

---

## Market Context

| Field    | Value                |
|----------|----------------------|
| Date     | {date}               |
| Regime   | **{regime.upper()}** |
| FII Net  | {fii_str}            |
| Nifty 50 | {nifty_str}          |

**Market alignment base score:** {regime_base}/100
FII adjustment: {fii_adj} points applied when |FII net| > ₹500 cr.

---

## Targets Overview

{tbl}

---

## How to Use These Files

1. Read this brief
2. Read `02_targets.md` — all evidence per target
3. Fill in `03_output_template.md` with your analysis
4. Save the filled file → run the importer to register it as the final report:
   `python -m src.pipeline.handoff.importer --date {date} --response <path>`

---

## Scoring Guide

Assign 4 component scores (0–100) per target:

| Score | What it measures | 80+ | 50–79 | <50 |
|-------|-----------------|-----|-------|-----|
| **F** (Fundamental) | Business quality | Strong growth, high ROE, clean balance sheet | Adequate | Weak or no data |
| **V** (Valuation) | Price attractiveness | Clearly undervalued vs peers/history | Fair | Stretched or no data |
| **R** (Risk) | Downside risk (INVERTED in composite) | High risk | Moderate | Low risk |
| **T** (Thesis) | Evidence strength | Strongly supported | Mixed | Contradicted |

**Composite = F×0.25 + V×0.20 + T×0.20 + (100−R)×0.20 + market_alignment×0.15**

**Recommendations:**
- ≥ 70 → strong_buy
- 62–69 → buy
- 55–61 → watch
- < 55 → avoid (also avoid if thesis is actively contradicted)

**For unresolved targets** (geopolitical risk, regulatory themes — no NSE ticker):
- Set entry_range = n/a — no listed instrument
- Set stop_loss = n/a
- Still provide full analysis — these affect sector allocation and portfolio risk framing
"""


def _l8_targets(date: str, packets: list) -> str:
    lines = [f"# Target Evidence — {date}", ""]

    for i, p in enumerate(packets, 1):
        entity = p["target_entity"]
        thesis = p.get("thesis", {})
        res    = p.get("resolution", {})
        mdata  = p.get("market_data", {}) or {}
        news   = p.get("supporting_news", [])
        gaps   = p.get("evidence_gaps", p.get("data_gaps", []))
        memory = p.get("past_context", {})

        lines.append(f"---\n\n## {i}. {entity}")
        lines.append(
            f"**Horizon:** {p.get('time_horizon','?')} | "
            f"**Bucket:** {p.get('bucket','?')} | "
            f"**L6 Score:** {p.get('score','?')}"
        )

        # Thesis
        lines.append("\n### Thesis\n")
        lines.append(thesis.get("hypothesis") or "*(no hypothesis)*")

        questions = thesis.get("deep_dive_questions", [])
        if questions:
            lines.append("\n**Research Questions:**")
            for q in questions:
                lines.append(f"- {q}")

        conditions = thesis.get("invalidating_conditions", [])
        if conditions:
            lines.append("\n**Invalidating Conditions:**")
            for c in conditions:
                lines.append(f"- {c}")

        # Resolution
        lines.append("\n### Resolution\n")
        lines.append(f"- **Type:** {res.get('type', 'unknown')}")
        tickers = res.get("tickers", [])
        if tickers:
            lines.append(f"- **Tickers:** {', '.join(tickers)}")
        if res.get("note"):
            lines.append(f"- **Note:** {res['note']}")

        # Market data
        if mdata:
            lines.append("\n### Market Data\n")
            for ticker, td in mdata.items():
                if not td or td.get("collection_status") == "failed":
                    lines.append(f"**{ticker}** — *data collection failed*\n")
                    continue

                price = td.get("price") or {}
                fund  = td.get("fundamentals") or {}
                own   = td.get("ownership") or {}
                ac    = td.get("analyst_consensus") or {}

                cur = price.get("current")
                if cur is None:
                    lines.append(f"**{ticker}** — *no price data*\n")
                    continue

                lines.append(f"**{ticker}** — ₹{cur}")
                lines.append(
                    f"  Returns: 30d={_pct(price.get('return_30d_pct'))}  "
                    f"90d={_pct(price.get('return_90d_pct'))}"
                )
                lines.append(
                    f"  RSI-14={_val(price.get('rsi_14'))}  "
                    f"vs 50DMA={_pct(price.get('pct_above_50dma'))}  "
                    f"vs 200DMA={_pct(price.get('pct_above_200dma'))}"
                )
                lines.append(
                    f"  52w: H=₹{_val(price.get('52w_high'))} / L=₹{_val(price.get('52w_low'))}  "
                    f"({_pct(price.get('pct_from_52w_high'))} from high)"
                )
                lines.append(
                    f"  PE={_val(fund.get('pe_ttm'))}  "
                    f"PB={_val(fund.get('pb'))}  "
                    f"ROE={_pct(fund.get('roe_pct'))}  "
                    f"ROCE={_pct(fund.get('roce_pct'))}  "
                    f"DivYield={_pct(fund.get('dividend_yield_pct'))}"
                )
                lines.append(
                    f"  RevGrowth={_pct(fund.get('revenue_growth_ttm_pct'))}  "
                    f"PATGrowth={_pct(fund.get('pat_growth_ttm_pct'))}  "
                    f"MktCap=₹{_cr(fund.get('market_cap_cr'))} cr"
                )
                if own:
                    lines.append(
                        f"  Promoter={_pct(own.get('promoter_pct'))} "
                        f"(pledge={_pct(own.get('promoter_pledge_pct'))})  "
                        f"FII={_pct(own.get('fii_pct'))} "
                        f"(QoQ={_pct(own.get('fii_change_qoq_pct'))})  "
                        f"DII={_pct(own.get('dii_pct'))}"
                    )
                if ac:
                    lines.append(
                        f"  AnalystTarget=₹{_val(ac.get('target_price_mean'))}  "
                        f"Upside={_pct(ac.get('upside_pct'))}  "
                        f"{_val(ac.get('analyst_count'))} analysts  "
                        f"RecMean={_val(ac.get('recommendation_mean'))} (1=StrongBuy)"
                    )
                lines.append("")
        else:
            lines.append("\n### Market Data\n\n*No market data (unresolved target — no NSE ticker)*\n")

        # News intelligence
        if news:
            lines.append("### News Intelligence\n")
            primary = [n for n in news if n.get("relevance_type") == "hypothesis_source"]
            related = [n for n in news if n.get("relevance_type") != "hypothesis_source"]

            for n in primary + related:
                label = "▶ primary" if n.get("relevance_type") == "hypothesis_source" else "  related"
                pub   = (n.get("published_at") or "")[:10]
                lines.append(f"{label} | **{n.get('title') or '(no title)'}**")
                lines.append(
                    f"  *{n.get('source','')} | {pub} | "
                    f"reliability: {n.get('source_reliability','')}*"
                )

                sigs = n.get("market_signals", [])
                if sigs:
                    lines.append("  Signals:")
                    for s in sigs[:4]:
                        icon = "↑" if s.get("direction") == "bullish" else ("↓" if s.get("direction") == "bearish" else "→")
                        lines.append(f"    {icon} {s.get('text','')} [{s.get('confidence','')}]")

                facts = n.get("key_facts", [])
                if facts:
                    lines.append("  Facts:")
                    for f in facts[:3]:
                        val = f" = {f['value']}" if f.get("value") else ""
                        lines.append(f"    • {f.get('text','')}{val} ({f.get('entity','')})")

                events = n.get("key_events", [])
                if events:
                    lines.append("  Events:")
                    for e in events[:2]:
                        lines.append(
                            f"    ★ [{e.get('event_type','')}] {e.get('text','')} — {e.get('entity','')}"
                        )

                lines.append("")

        # Data gaps
        gap_list = gaps if isinstance(gaps, list) else []
        if gap_list:
            lines.append("### Data Gaps\n")
            for g in gap_list:
                if isinstance(g, dict):
                    field  = g.get("field") or g.get("type", "?")
                    impact = g.get("impact") or g.get("description", "")
                    lines.append(f"- **{field}**: {impact}")
                else:
                    lines.append(f"- {g}")
            lines.append("")

        # Past memory
        mem_entries: list = []
        if isinstance(memory, dict):
            mem_entries = memory.get("entries") or memory.get("recalled") or []
        elif isinstance(memory, list):
            mem_entries = memory
        if mem_entries:
            lines.append("### Past Memory\n")
            for m in mem_entries[:3]:
                summary = m.get("summary") or m.get("title") or ""
                lines.append(
                    f"- [{m.get('memory_type','?')}] {m.get('entity','')} — {summary[:100]}"
                )
            lines.append("")

        lines.append("")

    return "\n".join(lines)


def _l8_template(date: str, packets: list) -> str:
    ts    = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    lines = [
        f"# Investment Analysis — {date}",
        f"*Fill in every section marked with [ ]. Keep all section headers intact.*",
        f"*Generated: {ts}*",
        "",
        "---",
        "",
        "## Market Context Assessment",
        "",
        "*2–3 sentences: does today's regime support new entries or caution?*",
        "",
        "[YOUR ASSESSMENT HERE]",
        "",
        "---",
        "",
    ]

    for p in packets:
        entity  = p["target_entity"]
        horizon = p.get("time_horizon", "?")
        res     = p.get("resolution", {})
        has_tickers = bool(res.get("tickers"))

        price_hint = ""
        if has_tickers:
            for td in (p.get("market_data") or {}).values():
                cur = (td.get("price") or {}).get("current") if td else None
                if cur:
                    ticker = res["tickers"][0]
                    price_hint = f"  *(current: ₹{cur} — {ticker})*"
                    break

        lines += [
            f"## {entity} — [STRONG_BUY | BUY | WATCH | AVOID]",
            "",
            "**Scores:** Composite=[ ] | F=[ ] | V=[ ] | R=[ ] | T=[ ]",
            f"**Time Horizon:** {horizon}",
            "",
            "**Analysis:**",
            "",
            "[Paragraph 1: What the evidence shows — key facts, signals, alignment with thesis]",
            "",
            "[Paragraph 2: Fundamental quality and valuation — PE vs peers/history, growth, ROE]",
            "",
            "[Paragraph 3: Key risks — what could go wrong, how close are invalidating conditions]",
            "",
            "[Paragraph 4: Timing — why now vs wait, what would change your view]",
            "",
        ]

        if has_tickers:
            lines += [
                f"**Entry Range:** [₹X–Y on dips]{price_hint}",
                "**Stop Loss:** [₹X — key support level, -N% from entry]",
            ]
        else:
            lines += [
                "**Entry Range:** n/a — no listed instrument",
                "**Stop Loss:** n/a",
            ]

        lines += [
            "",
            "**Catalysts:**",
            "- [near-term catalyst 1]",
            "- [near-term catalyst 2]",
            "- [near-term catalyst 3]",
            "",
            "**Exit Triggers:**",
            "- [invalidating condition 1]",
            "- [invalidating condition 2]",
            "- [invalidating condition 3]",
            "",
            "---",
            "",
        ]

    lines += [
        "## Watchlist Summary",
        "",
        "| Entity | Recommendation | Composite Score | Entry | One-line Note |",
        "|--------|---------------|-----------------|-------|---------------|",
    ]
    for p in packets:
        lines.append(
            f"| {p['target_entity']} | [strong_buy/buy/watch/avoid] | [ ] | [₹X–Y or n/a] | [one line] |"
        )

    lines += [
        "",
        "---",
        "",
        "<!-- END OF ANALYSIS -->",
        f"<!-- Save this file, then register it with: -->",
        f"<!-- python -m src.pipeline.handoff.importer --date {date} --response <path-to-this-file> -->",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _pct(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):+.1f}%"
    except (TypeError, ValueError):
        return str(v)


def _val(v) -> str:
    return "N/A" if v is None else str(v)


def _cr(v) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate AI handoff files from pipeline output")
    parser.add_argument(
        "--profile",
        required=True,
        choices=["after_l4", "after_l8"],
        help="after_l4: checkpoint review  |  after_l8: deep analysis (replaces L9+L10)",
    )
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.profile, args.date)
