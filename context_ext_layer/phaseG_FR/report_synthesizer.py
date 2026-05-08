"""
context_ext_layer/phaseG_FR/report_synthesizer.py  —  Phase G, Layer 7

Aggregates all analyst views (Phase F) into a daily research report.
Pure Python — no LLM. Produces:
  - report_{date}.md  : human-readable, with cited source URLs
  - report_{date}.json: machine-readable for downstream/UI/email

Sections:
  - Market Regime header
  - Top Buys (high & medium conviction)
  - Top Avoids
  - Watchlist Movers
  - Portfolio Review (only if config/portfolio.json exists)
  - New Themes Worth Monitoring
  - Data Gaps

Standalone test:
  python context_ext_layer/phaseG_FR/report_synthesizer.py
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    ANALYST_OUTPUT_DIR, MARKET_REGIME_OUTPUT_DIR, CANDIDATES_OUTPUT_DIR,
    PHASE_G_DIR, PORTFOLIO_FILE,
)
from context_ext_layer.utils.portfolio import load_portfolio

_IST = timezone(timedelta(hours=5, minutes=30))

_CONVICTION_RANK = {"high": 3, "medium": 2, "low": 1}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _latest(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


def _conviction_score(view: dict) -> tuple:
    """Sort key: (conviction rank desc, |signal_score| desc)."""
    return (
        _CONVICTION_RANK.get(view.get("conviction", "low"), 0),
        abs(view.get("signal_score", 0) or 0),
    )


def _format_sources(urls: list[str], limit: int = 3) -> str:
    """Return space-separated markdown links to the first N URLs."""
    pieces = []
    for i, url in enumerate(urls[:limit], 1):
        if not url:
            continue
        pieces.append(f"[src{i}]({url})")
    return " ".join(pieces) if pieces else "_(no source URL)_"


def _bulletize(items: list[str], indent: str = "  ") -> str:
    if not items:
        return f"{indent}_(none)_"
    return "\n".join(f"{indent}- {it}" for it in items)


def _md_table_row(view: dict) -> str:
    upside = ""
    return (f"| {view.get('ticker',''):20s} "
            f"| {view.get('conviction','?'):6s} "
            f"| {view.get('price_action','?'):13s} "
            f"| {view.get('time_horizon','?'):6s} "
            f"| {view.get('thesis','')[:90]} |")


# ── Section builders ──────────────────────────────────────────────────────────

def _build_regime_section(regime: dict) -> str:
    posture = regime.get("market_posture", "?").upper()
    sigs    = regime.get("signals", {}) or {}
    raw     = regime.get("raw_data", {}) or {}
    sectors = regime.get("sectors", {}) or {}

    return (
f"""## Market Regime

**Posture: {posture}**

- Breadth A/D ratio: {raw.get('ad_ratio','?')} ({sigs.get('breadth','?')})
- FII net: ₹{raw.get('fii_net_cr','?')} cr ({sigs.get('fii','?')})
- VIX India: {raw.get('vix_india','?')} ({sigs.get('vix','?')})
- Crude Brent: ${raw.get('crude_brent_usd','?')} ({sigs.get('crude','?')})
- USD/INR: {raw.get('usd_inr','?')} ({sigs.get('usd_inr','?')})

**Favored sectors:** {', '.join(sectors.get('favored', [])) or '_(none)_'}
**Avoid sectors:**  {', '.join(sectors.get('avoid', [])) or '_(none)_'}
""")


def _build_table(views: list[dict], title: str) -> str:
    if not views:
        return f"## {title}\n\n_(none)_\n"
    lines = [f"## {title}\n",
             "| Ticker | Conviction | Price Action | Horizon | Thesis |",
             "|---|---|---|---|---|"]
    for v in views:
        lines.append(_md_table_row(v))

    lines.append("")
    for v in views:
        lines.append(f"### {v['ticker']} — {v.get('company','')}")
        lines.append(f"_Sector: {v.get('sector','?')} • Price: ₹{v.get('price','?')} • "
                     f"Conviction: **{v['conviction']}**_\n")
        lines.append(f"**Thesis:** {v['thesis']}\n")
        lines.append("**Drivers:**")
        lines.append(_bulletize(v.get("key_drivers", [])))
        lines.append("\n**Risks:**")
        lines.append(_bulletize(v.get("key_risks", [])))
        lines.append(f"\n**Sources:** {_format_sources(v.get('sources_cited', []))}")
        if v.get("data_gaps"):
            lines.append(f"\n_Data gaps: {', '.join(v['data_gaps'])}_")
        lines.append("")
    return "\n".join(lines)


def _build_portfolio_review(views_by_ticker: dict) -> str:
    if not PORTFOLIO_FILE.exists():
        return ""

    portfolio = load_portfolio()
    holdings  = portfolio.get("holdings", []) or []
    watchlist = portfolio.get("watchlist", []) or []
    if not holdings and not watchlist:
        return ""

    lines = ["## Portfolio Review\n"]

    if holdings:
        lines.append("### Holdings\n")
        lines.append("| Ticker | Qty | Avg Price | Today's View | Action |")
        lines.append("|---|---|---|---|---|")
        for h in holdings:
            t = h.get("ticker", "")
            view = views_by_ticker.get(t)
            if view:
                rec = f"**{view['recommendation']}** ({view['conviction']})"
                action = view["price_action"]
            else:
                rec = "_(not analyzed today)_"
                action = "—"
            lines.append(f"| {t} | {h.get('qty','?')} | ₹{h.get('avg_price','?')} | {rec} | {action} |")
        lines.append("")

    if watchlist:
        lines.append("### Watchlist Updates\n")
        for t in watchlist:
            view = views_by_ticker.get(t)
            if view:
                lines.append(f"- **{t}**: {view['recommendation']} ({view['conviction']}) — "
                             f"{view['thesis'][:120]}")
            else:
                lines.append(f"- {t}: _(no signal today)_")
        lines.append("")

    return "\n".join(lines)


def _build_themes_section(candidates_data: dict) -> str:
    themes = candidates_data.get("thematic_targets", []) or []
    if not themes:
        return ""
    top = themes[:8]
    lines = ["## New Themes Worth Monitoring\n"]
    for t in top:
        lines.append(f"- **[{t.get('entity_type','?')}] {t.get('entity_name','?')}** "
                     f"— relevance={t.get('relevance_score',0):.1f}, "
                     f"mentions={t.get('mention_count',0)}")
        events = t.get("key_events", [])
        if events:
            claim = events[0].get("key_claim", "")[:140]
            if claim:
                lines.append(f"  ↳ _{claim}_")
    lines.append("")
    return "\n".join(lines)


def _build_data_gaps(views: list[dict]) -> str:
    from collections import Counter
    counter: Counter = Counter()
    for v in views:
        for gap in v.get("data_gaps", []) or []:
            counter[gap] += 1

    if not counter:
        return "## Data Gaps\n\n_All Phase C modules returned data for every ticker._\n"

    lines = ["## Data Gaps\n",
             "Modules that returned no data for one or more tickers:"]
    for module, count in counter.most_common():
        lines.append(f"- **{module}**: missing for {count} ticker(s)")
    lines.append("")
    return "\n".join(lines)


# ── Top-level synthesis ───────────────────────────────────────────────────────

def synthesize() -> dict:
    """Read all analyst views + regime + candidates, produce the report."""
    if not ANALYST_OUTPUT_DIR.exists():
        return {"error": "no analyst views"}

    view_files = sorted(ANALYST_OUTPUT_DIR.glob("*.json"))
    views: list[dict] = []
    for f in view_files:
        v = _load_json(f)
        if v and "recommendation" in v:
            views.append(v)

    regime_file = _latest(MARKET_REGIME_OUTPUT_DIR, "market_regime_*.json")
    regime      = _load_json(regime_file) if regime_file else {}

    cand_file = _latest(CANDIDATES_OUTPUT_DIR, "candidates_*.json")
    cand_data = _load_json(cand_file) if cand_file else {}

    # Group by recommendation
    invests = sorted([v for v in views if v["recommendation"] == "invest"],
                     key=_conviction_score, reverse=True)
    avoids  = sorted([v for v in views if v["recommendation"] == "avoid"],
                     key=_conviction_score, reverse=True)
    watches = sorted([v for v in views if v["recommendation"] == "watch"],
                     key=_conviction_score, reverse=True)

    views_by_ticker = {v["ticker"]: v for v in views}
    today = datetime.now(_IST).strftime("%Y-%m-%d %a, %d %b %Y")

    # Build markdown
    md_parts = [
        f"# Daily Stock Research — {today}\n",
        f"_Generated at {datetime.now(_IST).strftime('%I:%M %p IST')}_\n",
        f"_Tickers analyzed: **{len(views)}** • "
        f"Buys: **{len(invests)}** • Watches: **{len(watches)}** • "
        f"Avoids: **{len(avoids)}**_\n",
        "---\n",
        _build_regime_section(regime),
        "---\n",
        _build_table(invests, "Top Buys"),
        "---\n",
        _build_table(avoids, "Top Avoids"),
        "---\n",
        _build_table(watches[:10], "Watchlist Movers"),
    ]

    portfolio_md = _build_portfolio_review(views_by_ticker)
    if portfolio_md:
        md_parts += ["---\n", portfolio_md]

    themes_md = _build_themes_section(cand_data)
    if themes_md:
        md_parts += ["---\n", themes_md]

    md_parts += ["---\n", _build_data_gaps(views)]

    md_text = "\n".join(md_parts)

    PHASE_G_DIR.mkdir(parents=True, exist_ok=True)
    today_short = datetime.now(_IST).strftime("%Y-%m-%d")
    md_file   = PHASE_G_DIR / f"report_{today_short}.md"
    json_file = PHASE_G_DIR / f"report_{today_short}.json"

    md_file.write_text(md_text)

    json_file.write_text(json.dumps({
        "generated_at": datetime.now(_IST).isoformat(),
        "regime":       regime,
        "summary": {
            "tickers_analyzed": len(views),
            "invests":          len(invests),
            "watches":          len(watches),
            "avoids":           len(avoids),
        },
        "invests":          invests,
        "watches":          watches,
        "avoids":           avoids,
        "thematic_targets": cand_data.get("thematic_targets", []),
    }, ensure_ascii=False, indent=2))

    return {
        "md_file":   str(md_file),
        "json_file": str(json_file),
        "counts": {
            "tickers_analyzed": len(views),
            "invests":          len(invests),
            "watches":          len(watches),
            "avoids":           len(avoids),
        },
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  report_synthesizer — standalone test")
    print("=" * 60)

    result = synthesize()
    if "error" in result:
        print(f"  ✗  {result['error']}")
    else:
        print(f"  Tickers analyzed : {result['counts']['tickers_analyzed']}")
        print(f"    invests        : {result['counts']['invests']}")
        print(f"    watches        : {result['counts']['watches']}")
        print(f"    avoids         : {result['counts']['avoids']}")
        print(f"\n  Markdown report → {result['md_file']}")
        print(f"  JSON report     → {result['json_file']}")
