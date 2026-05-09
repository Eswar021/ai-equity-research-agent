"""
intelligence_layer/research_target_planner/target_ranker.py  —  Layer 6, Target Ranker

Combines signals from news_signal_extractor + regime from market_regime_agent
+ bulk/block deal data to produce a ranked candidate list for targeted deep-dive (Layer 7).

All scoring is deterministic (no LLM). Stocks are ranked by signal
strength, source diversity, and sector alignment with the current regime.

Inputs:
  output/{date}/phaseB/signals/signals_{date}.json       (from Layer 3)
  output/{date}/phaseB/market_regime/market_regime_{date}.json  (from Layer 5)
  output/{date}/phaseA/bulk_deals/bulk_block_deals_*.json  (direct from Layer 1)

Output:
  output/{date}/phaseB/candidates/candidates_{date}.json

Standalone test:
  python intelligence_layer/research_target_planner/target_ranker.py
"""

import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    SIGNALS_OUTPUT_DIR, MARKET_REGIME_OUTPUT_DIR,
    BULK_DEALS_OUTPUT_DIR, CANDIDATES_OUTPUT_DIR,
)

_IST = timezone(timedelta(hours=5, minutes=30))

# ── Scoring weights ───────────────────────────────────────────────────────────

# How much a single signal from each source contributes to the base score.
# Higher = more credible/impactful source.
_SOURCE_WEIGHT: dict[str, float] = {
    "moneycontrol":   3.0,
    "economic_times": 3.0,
    "rss":            2.0,
    "newsdata_io":    1.5,
    "mediastack":     1.5,
    "gmail":          2.0,
    "youtube":        1.0,
}

# How much severity multiplies the base score.
_SEVERITY_WEIGHT: dict[str, float] = {
    "high":   3.0,
    "medium": 2.0,
    "low":    1.0,
}

# Sentiment shifts the score sign.
# Neutral gets 0.4 — the stock is being talked about, just directionally unclear.
_SENTIMENT_MOD: dict[str, float] = {
    "positive":  1.0,
    "negative": -1.0,
    "neutral":   0.4,
}

# Bulk deals are institutional money in motion — strong signal.
_BULK_BUY_SCORE  =  5.0
_BULK_SELL_SCORE = -5.0

# Sector alignment with regime adds/subtracts from final score.
_SECTOR_BONUS  =  4.0
_SECTOR_PENALTY = -3.0

# Candidates with |final_score| below this are filtered out.
_MIN_SCORE_THRESHOLD = 3.0

# Maximum candidates to return.
_MAX_CANDIDATES = 25

# Minimum relevance score for thematic (non-listed) entities to appear in output.
_MIN_THEMATIC_SCORE = 1.5


# ── NSE sector label → index name mapping (used to align with regime sectors) ─
# Regime sectors use short names ('it', 'pharma'); we need to match against
# the sector labels that the LLM or yfinance might provide.
_SECTOR_ALIASES: dict[str, list[str]] = {
    "it":        ["information technology", "it", "tech", "software", "nifty it"],
    "banking":   ["banking", "bank", "financial services", "nifty bank"],
    "pharma":    ["pharma", "pharmaceutical", "healthcare", "nifty pharma"],
    "fmcg":      ["fmcg", "consumer staples", "consumer goods", "nifty fmcg"],
    "auto":      ["auto", "automobile", "automotive", "nifty auto"],
    "metal":     ["metal", "mining", "steel", "nifty metal"],
    "realty":    ["realty", "real estate", "nifty realty"],
    "infra":     ["infrastructure", "infra", "construction", "nifty infra"],
    "oil_gas":   ["oil", "gas", "energy", "petroleum", "nifty oil"],
    "psu_bank":  ["psu bank", "public sector bank"],
    "fmcg":      ["fmcg", "consumer staples", "nifty fmcg"],
}

def _sector_key(sector_label: str) -> str | None:
    """Map a free-form sector label → regime sector key (e.g. 'it', 'pharma')."""
    if not sector_label:
        return None
    sl = sector_label.lower()
    for key, aliases in _SECTOR_ALIASES.items():
        if any(alias in sl or sl in alias for alias in aliases):
            return key
    return None


# ── Loaders ───────────────────────────────────────────────────────────────────

def _latest_file(dir_path: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(dir_path.glob(pattern))
    return files[-1] if files else None

def _load_json(path: Path | None) -> dict | list:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def load_signals(signals_file: str | Path | None = None) -> dict:
    """Load latest (or specified) signals file from phaseB/signals/."""
    if signals_file:
        f = Path(signals_file)
    else:
        f = _latest_file(SIGNALS_OUTPUT_DIR)
    return _load_json(f) if f else {}


def load_regime(regime_file: str | Path | None = None) -> dict:
    """Load latest (or specified) regime file from phaseB/market_regime/."""
    if regime_file:
        f = Path(regime_file)
    else:
        f = _latest_file(MARKET_REGIME_OUTPUT_DIR)
    return _load_json(f) if f else {}


def load_bulk_deals() -> list[dict]:
    """Load latest bulk + block deals from Phase A output."""
    f = _latest_file(BULK_DEALS_OUTPUT_DIR)
    if not f:
        return []
    data = _load_json(f)
    if not isinstance(data, dict):
        return []
    return data.get("bulk_deals", []) + data.get("block_deals", [])


# ── Bulk deal signal builder ──────────────────────────────────────────────────

def _build_bulk_signals(deals: list[dict]) -> dict[str, dict]:
    """
    Aggregate bulk/block deals by ticker → {score, deal_count, actions, source_file}.
    NSE symbols from bulk deals are raw (e.g. 'AATECH') → converted to 'AATECH.NS'.
    """
    agg: dict[str, dict] = defaultdict(lambda: {
        "score": 0.0, "deal_count": 0, "buys": 0, "sells": 0,
        "clients": [], "source": "bulk_deals",
    })

    for deal in deals:
        sym = deal.get("symbol", "")
        if not sym:
            continue
        ticker = f"{sym}.NS"
        action = deal.get("buy_sell", "").upper()

        if action == "BUY":
            agg[ticker]["score"] += _BULK_BUY_SCORE
            agg[ticker]["buys"]  += 1
        elif action == "SELL":
            agg[ticker]["score"] += _BULK_SELL_SCORE
            agg[ticker]["sells"] += 1
        else:
            continue

        agg[ticker]["deal_count"] += 1
        client = deal.get("client", "")
        if client and client not in agg[ticker]["clients"]:
            agg[ticker]["clients"].append(client)
        agg[ticker]["company_name"] = deal.get("scrip_name", sym)
        agg[ticker]["deal_date"]    = deal.get("date", "")

    return dict(agg)


# ── Core scoring ──────────────────────────────────────────────────────────────

def score_candidates(
    signals_data: dict,
    regime:       dict,
    bulk_signals: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Score and rank candidate tickers from LLM signals + bulk deals + regime.

    Returns a list of candidate dicts sorted by abs(final_score) desc.
    """
    if bulk_signals is None:
        bulk_signals = {}

    favored_sectors = set(regime.get("sectors", {}).get("favored", []))
    avoid_sectors   = set(regime.get("sectors", {}).get("avoid",   []))

    # ── Loop 1: Accumulate per-ticker data from listed LLM signals ───────────
    ticker_data: dict[str, dict] = defaultdict(lambda: {
        "score":        0.0,
        "signal_count": 0,
        "sources":      set(),
        "event_types":  [],
        "key_signals":  [],
        "company":      None,
    })

    # ── Loop 2: Accumulate thematic (non-listed) entity data ──────────────────
    # Keyed by lowercased entity_name for deduplication; preserves original name.
    thematic_data: dict[str, dict] = defaultdict(lambda: {
        "entity_name":     "",
        "entity_type":     "",
        "relevance_score": 0.0,
        "mention_count":   0,
        "sources":         set(),
        "event_types":     [],
        "key_events":      [],
    })

    for item in signals_data.get("items", []):
        for sig in item.get("signals", []):
            if "_error" in sig:
                continue

            ticker      = sig.get("ticker")
            entity_type = sig.get("entity_type", "listed")
            src         = sig.get("source", "")
            severity    = sig.get("severity", "low")
            sentiment   = sig.get("sentiment", "neutral")

            sw = _SOURCE_WEIGHT.get(src, 1.0)
            ev = _SEVERITY_WEIGHT.get(severity, 1.0)
            sm = _SENTIMENT_MOD.get(sentiment, 0.4)

            # Loop 1: listed company with a resolved NSE ticker
            if entity_type == "listed" and ticker:
                contribution = sw * ev * sm
                td = ticker_data[ticker]
                td["score"]        += contribution
                td["signal_count"] += 1
                td["sources"].add(src)

                etype = sig.get("event_type", "other")
                if etype not in td["event_types"]:
                    td["event_types"].append(etype)

                td["key_signals"].append({
                    "source":     src,
                    "event_type": etype,
                    "sentiment":  sentiment,
                    "severity":   severity,
                    "key_claim":  sig.get("key_claim", ""),
                    "item_title": sig.get("item_title", ""),
                    "item_url":   sig.get("item_url", ""),
                    "_score":     abs(contribution),
                })
                td["key_signals"].sort(key=lambda x: x["_score"], reverse=True)
                td["key_signals"] = td["key_signals"][:3]

                if not td["company"] and sig.get("company"):
                    td["company"] = sig["company"]

            # Loop 2: non-listed entity OR unresolved listed
            elif entity_type != "listed" or not ticker:
                entity_name = sig.get("entity_name") or sig.get("company") or ""
                if not entity_name:
                    continue

                relevance = sw * ev * abs(sm)   # abs() — negative macro still relevant
                key = entity_name.lower().strip()
                th = thematic_data[key]

                if not th["entity_name"]:
                    th["entity_name"] = entity_name
                    th["entity_type"] = entity_type

                th["relevance_score"] += relevance
                th["mention_count"]   += 1
                th["sources"].add(src)

                etype = sig.get("event_type", "other")
                if etype not in th["event_types"]:
                    th["event_types"].append(etype)

                th["key_events"].append({
                    "source":     src,
                    "event_type": etype,
                    "sentiment":  sentiment,
                    "severity":   severity,
                    "key_claim":  sig.get("key_claim", ""),
                    "item_title": sig.get("item_title", ""),
                    "_score":     relevance,
                })
                th["key_events"].sort(key=lambda x: x["_score"], reverse=True)
                th["key_events"] = th["key_events"][:3]

    # ── Merge bulk deal signals into Loop 1 ───────────────────────────────────
    for ticker, bd in bulk_signals.items():
        td = ticker_data[ticker]
        td["score"]        += bd["score"]
        td["signal_count"] += bd["deal_count"]
        td["sources"].add("bulk_deals")
        if bd["score"] > 0:
            td["event_types"].insert(0, "bulk_buy")
        else:
            td["event_types"].insert(0, "bulk_sell")
        if not td["company"]:
            td["company"] = bd.get("company_name", ticker)
        td["bulk_deal"] = {
            "deals": bd["deal_count"],
            "buys":  bd["buys"],
            "sells": bd["sells"],
            "clients": bd["clients"][:3],
            "date":  bd.get("deal_date", ""),
        }

    # ── Build listed candidates list ──────────────────────────────────────────
    candidates: list[dict] = []
    for ticker, td in ticker_data.items():
        base_score  = td["score"]
        final_score = base_score  # sector adj added in Phase C

        candidates.append({
            "ticker":          ticker,
            "company":         td["company"] or ticker,
            "score":           round(base_score, 2),
            "sector_adj":      0.0,
            "final_score":     round(final_score, 2),
            "signal_count":    td["signal_count"],
            "source_count":    len(td["sources"]),
            "sources":         sorted(td["sources"]),
            "event_types":     list(dict.fromkeys(td["event_types"])),
            "key_signals":     [{k: v for k, v in s.items() if k != "_score"}
                                for s in td["key_signals"]],
            "bulk_deal":       td.get("bulk_deal"),
            "regime_posture":  regime.get("market_posture", "unknown"),
        })

    candidates.sort(key=lambda c: abs(c["final_score"]), reverse=True)
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    listed_targets: list[dict] = []
    for c in candidates:
        above_threshold = abs(c["final_score"]) >= _MIN_SCORE_THRESHOLD
        in_top_n        = c["rank"] <= _MAX_CANDIDATES
        c["selected_for_phase_c"] = above_threshold and in_top_n
        if c["selected_for_phase_c"]:
            listed_targets.append(c)

    # ── Build thematic targets list ───────────────────────────────────────────
    thematic_targets: list[dict] = []
    for key, th in thematic_data.items():
        if th["relevance_score"] < _MIN_THEMATIC_SCORE:
            continue
        thematic_targets.append({
            "entity_name":     th["entity_name"],
            "entity_type":     th["entity_type"],
            "relevance_score": round(th["relevance_score"], 2),
            "mention_count":   th["mention_count"],
            "source_count":    len(th["sources"]),
            "sources":         sorted(th["sources"]),
            "event_types":     list(dict.fromkeys(th["event_types"])),
            "key_events":      [{k: v for k, v in e.items() if k != "_score"}
                                for e in th["key_events"]],
        })
    thematic_targets.sort(key=lambda t: t["relevance_score"], reverse=True)

    return {
        "all_candidates":   candidates,
        "listed_targets":   listed_targets,
        "thematic_targets": thematic_targets,
    }


def save_candidates(
    scored_result: dict,
    regime:        dict,
    signals_file:  str,
    bulk_file:     str | None = None,
) -> str:
    """Save scored result (all_candidates + listed_targets + thematic_targets) to phaseB/candidates/."""
    all_candidates   = scored_result.get("all_candidates", [])
    listed_targets   = scored_result.get("listed_targets", scored_result.get("selected", []))
    thematic_targets = scored_result.get("thematic_targets", [])

    CANDIDATES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    out_file = CANDIDATES_OUTPUT_DIR / f"candidates_{today}.json"

    output = {
        "generated_at":   datetime.now(_IST).isoformat(),
        "market_posture": regime.get("market_posture", "unknown"),

        "selection_rules": {
            "min_abs_score_for_deep_dive": _MIN_SCORE_THRESHOLD,
            "max_selected_for_phase_c":    _MAX_CANDIDATES,
            "min_thematic_relevance":      _MIN_THEMATIC_SCORE,
        },

        "all_candidates_count":   len(all_candidates),
        "listed_targets_count":   len(listed_targets),
        "thematic_targets_count": len(thematic_targets),

        # Full source provenance for downstream modules
        "phase_b_inputs": {
            "signals_file":    signals_file,
            "regime_file":     str(_latest_file(MARKET_REGIME_OUTPUT_DIR) or ""),
            "bulk_deals_file": bulk_file or str(_latest_file(BULK_DEALS_OUTPUT_DIR) or ""),
        },

        "scoring_config": {
            "source_weights":   _SOURCE_WEIGHT,
            "severity_weights": _SEVERITY_WEIGHT,
            "bulk_buy_score":   _BULK_BUY_SCORE,
            "bulk_sell_score":  _BULK_SELL_SCORE,
            "sector_bonus":     _SECTOR_BONUS,
            "sector_penalty":   _SECTOR_PENALTY,
        },

        "regime_summary": {
            "posture":         regime.get("market_posture"),
            "signals":         regime.get("signals", {}),
            "favored_sectors": regime.get("sectors", {}).get("favored", []),
            "avoid_sectors":   regime.get("sectors", {}).get("avoid", []),
        },

        # All scored listed tickers — used for trend tracking
        "all_candidates":    all_candidates,
        # Top listed tickers passed to Phase C deep dive
        "listed_targets":    listed_targets,
        # Backward-compat alias for run_phase_c.py
        "selected_for_phase_c": listed_targets,
        # Non-listed thematic entities: private companies, sector themes, macro/policy events
        "thematic_targets":  thematic_targets,
    }

    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return str(out_file)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  candidate_scorer — standalone test")
    print("  Uses latest signals + regime files from phaseB/")
    print("=" * 60)

    signals_data = load_signals()
    regime       = load_regime()
    deals        = load_bulk_deals()

    if not signals_data:
        print("\n  No signals file found — run news_signal_extractor first")
        print("  (or run_phase_b.py for the full pipeline)\n")
        sys.exit(0)

    if not regime:
        print("\n  No regime file found — run market_regime first")
        sys.exit(0)

    bulk_sigs = _build_bulk_signals(deals)

    print(f"\n  Market posture   : {regime.get('market_posture', 'unknown').upper()}")
    print(f"  Signals loaded   : {signals_data.get('stats', {}).get('total_signals', 0)}")
    print(f"  Bulk deals loaded: {len(deals)}")
    print(f"  Bulk tickers     : {len(bulk_sigs)}\n")

    scored           = score_candidates(signals_data, regime, bulk_sigs)
    all_candidates   = scored["all_candidates"]
    listed_targets   = scored["listed_targets"]
    thematic_targets = scored["thematic_targets"]

    print(f"\n  All scored tickers : {len(all_candidates)}")
    print(f"  Listed (Phase C)   : {len(listed_targets)}")
    print(f"  Thematic targets   : {len(thematic_targets)}\n")
    print(f"  {'Rank':4}  {'Ticker':20}  {'Score':7}  {'Signals':8}  {'Sources':6}  {'Sel':4}  Top Event")
    print("  " + "-" * 82)
    for c in all_candidates:
        score_str = f"{c['final_score']:+.1f}"
        sel_mark  = "✓" if c["selected_for_phase_c"] else " "
        print(f"  {c['rank']:4}  {c['ticker']:20}  {score_str:7}  "
              f"{c['signal_count']:8}  {c['source_count']:6}  {sel_mark:4}  "
              f"{c['event_types'][0] if c['event_types'] else '—'}")
        if c.get("key_signals") and c["selected_for_phase_c"]:
            ks = c["key_signals"][0]
            print(f"        ↳ {ks['key_claim'][:70]}")

    if thematic_targets:
        print(f"\n  Top Thematic Targets:")
        print(f"  {'Type':8}  {'Score':7}  {'Mentions':8}  Entity")
        print("  " + "-" * 65)
        for t in thematic_targets[:10]:
            print(f"  {t['entity_type']:8}  {t['relevance_score']:7.1f}  "
                  f"{t['mention_count']:8}  {t['entity_name'][:45]}")
            if t.get("key_events"):
                print(f"        ↳ {t['key_events'][0].get('key_claim','')[:65]}")

    signals_path = str(_latest_file(SIGNALS_OUTPUT_DIR) or "")
    saved = save_candidates(scored, regime, signals_path)
    print(f"\n  Saved → {saved}")
