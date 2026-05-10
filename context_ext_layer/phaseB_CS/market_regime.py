"""
context_ext_layer/phaseB_CS/market_regime.py  —  Phase B, Module B1

Reads the most recent Phase A macro outputs and computes a structured
market regime — all rule-based thresholds, no LLM.

Inputs (latest file from each dir):
  output/phaseA/macro_data/india_macro_*.json
  output/phaseA/macro_data/us_macro_*.json
  output/phaseA/fii_dii/fii_dii_*.json
  output/phaseA/fno_data/NIFTY_fno_*.json   (optional — empty outside market hours)

Output:
  output/phaseB/market_regime/market_regime_{date}.json

Standalone test:
  python context_ext_layer/phaseB_CS/market_regime.py
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    MACRO_OUTPUT_DIR, FII_DII_OUTPUT_DIR, FNO_OUTPUT_DIR,
    MARKET_REGIME_OUTPUT_DIR,
)

_IST = timezone(timedelta(hours=5, minutes=30))


# ── Signal thresholds ─────────────────────────────────────────────────────────
# Each function maps a raw number → a labelled signal string used downstream.

def _breadth_signal(ad_ratio: float | None) -> str:
    """NIFTY 500 advance/decline ratio."""
    if ad_ratio is None: return "unknown"
    if ad_ratio < 0.6:   return "bearish"
    if ad_ratio < 1.4:   return "neutral"
    return "bullish"

def _vix_signal(vix: float | None) -> str:
    """India VIX — market fear gauge."""
    if vix is None: return "unknown"
    if vix > 25:    return "fear"
    if vix > 18:    return "elevated"
    if vix > 13:    return "moderate"
    return "calm"

def _fii_signal(net_crore: float | None) -> str:
    """FII net flows in ₹ crore (negative = selling)."""
    if net_crore is None:  return "unknown"
    if net_crore < -5000:  return "heavy_selling"
    if net_crore < -1000:  return "selling"
    if net_crore < 500:    return "flat"
    return "buying"

def _crude_signal(brent_usd: float | None) -> str:
    """Brent crude price — input cost / inflation signal."""
    if brent_usd is None: return "unknown"
    if brent_usd > 110:   return "high"
    if brent_usd > 90:    return "elevated"
    if brent_usd > 70:    return "normal"
    return "low"

def _usd_inr_signal(rate: float | None) -> str:
    """USD/INR rate — rupee strength signal."""
    if rate is None: return "unknown"
    if rate > 95:    return "very_weak"
    if rate > 90:    return "weak"
    if rate > 85:    return "mild_weakness"
    return "stable"

def _yield_curve_signal(spread_10y_2y: float | None) -> str:
    """US 10Y-2Y spread — recession risk indicator."""
    if spread_10y_2y is None: return "unknown"
    if spread_10y_2y < 0:     return "inverted"
    if spread_10y_2y < 0.3:   return "flat"
    return "normal"

def _rate_env_signal(us_10y: float | None) -> str:
    """US 10-year yield — global rate environment for EM flows."""
    if us_10y is None: return "unknown"
    if us_10y > 4.5:   return "high"
    if us_10y > 3.5:   return "elevated"
    return "normal"

def _pe_signal(pe: float | None, index_name: str = "NIFTY 50") -> str:
    """PE-based valuation signal using historical bands per index."""
    if pe is None: return "unknown"
    # Historical fair-value PE bands (approximate)
    bands = {
        "NIFTY 50":     (16, 24),
        "NIFTY IT":     (18, 32),
        "NIFTY BANK":   (12, 20),
        "NIFTY PHARMA": (22, 38),
        "NIFTY FMCG":   (30, 50),
        "NIFTY AUTO":   (14, 26),
        "NIFTY METAL":  (8,  16),
        "NIFTY REALTY": (20, 40),
    }
    lo, hi = bands.get(index_name.upper(), (15, 25))
    if pe < lo:  return "cheap"
    if pe > hi:  return "expensive"
    return "fair"


# ── Posture derivation ────────────────────────────────────────────────────────

def _derive_posture(breadth: str, fii: str, vix: str) -> str:
    """Combine top-level signals into a single market posture label."""
    if vix == "fear":
        return "wait"
    if breadth == "bullish" and fii in ("buying", "flat"):
        return "risk_on"
    if breadth == "bearish" and fii in ("heavy_selling", "selling"):
        return "defensive"
    return "selective"


# ── Sector recommendations ────────────────────────────────────────────────────

_POSTURE_BASE: dict[str, dict] = {
    "risk_on":   {"favored": ["banking", "auto", "metal", "realty", "infra"],
                  "avoid":   ["pharma"]},
    "selective": {"favored": ["banking", "pharma", "it"],
                  "avoid":   ["metal", "realty"]},
    "defensive": {"favored": ["pharma", "fmcg", "it"],
                  "avoid":   ["metal", "realty", "auto", "psu_bank"]},
    "wait":      {"favored": ["pharma", "fmcg"],
                  "avoid":   ["metal", "realty", "auto", "banking", "infra"]},
}

def _derive_sectors(posture: str, crude: str, usd_inr: str,
                    fii: str, yield_curve: str) -> dict:
    """Adjust base sector recommendations with macro overlay signals."""
    base    = _POSTURE_BASE.get(posture, _POSTURE_BASE["selective"])
    favored = list(base["favored"])
    avoid   = list(base["avoid"])

    # Weak rupee → IT earns in USD; better export margins
    if usd_inr in ("weak", "very_weak") and "it" not in favored:
        favored.insert(0, "it")

    # High crude → auto faces input cost pressure; upstream oil_gas benefits
    if crude in ("high", "elevated"):
        if "auto" not in avoid:
            avoid.append("auto")
        if "oil_gas" not in favored:
            favored.append("oil_gas")

    # Normal yield curve + FII buying → banking structurally bullish
    if yield_curve == "normal" and fii == "buying" and "banking" not in favored:
        favored.insert(0, "banking")

    # Deduplicate, keep favored clean of avoid
    seen: set = set()
    favored = [s for s in favored if not (s in seen or seen.add(s))]  # type: ignore
    avoid   = [s for s in dict.fromkeys(avoid) if s not in favored]

    return {"favored": favored, "avoid": avoid}


# ── Data loaders ──────────────────────────────────────────────────────────────

def _latest_file(dir_path: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(dir_path.glob(pattern))
    return files[-1] if files else None

def _load_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def _find_index(indices: list, name: str) -> dict | None:
    for idx in indices:
        if isinstance(idx, dict) and idx.get("name", "").upper() == name.upper():
            return idx
    return None


# ── Main computation ──────────────────────────────────────────────────────────

def compute_regime() -> dict:
    """
    Compute market regime from latest Phase A macro files.
    Returns a fully self-contained dict (all source files recorded for traceability).
    """
    india_file = _latest_file(MACRO_OUTPUT_DIR, "india_macro_*.json")
    us_file    = _latest_file(MACRO_OUTPUT_DIR, "us_macro_*.json")
    fii_file   = _latest_file(FII_DII_OUTPUT_DIR)
    fno_file   = _latest_file(FNO_OUTPUT_DIR, "NIFTY_fno_*.json")

    india = _load_json(india_file)
    us    = _load_json(us_file)
    fii   = _load_json(fii_file)
    fno   = _load_json(fno_file)

    # ── Extract raw numbers ──────────────────────────────────────────────────
    breadth     = india.get("market_breadth", {})
    rates       = india.get("market_rates", {})
    commodities = india.get("commodity_prices", {})
    nse_indices = india.get("nse_indices", [])

    ad_ratio  = breadth.get("ad_ratio")
    vix       = rates.get("vix_india", {}).get("value")
    nifty_val = rates.get("nifty_50",  {}).get("value")
    usd_inr   = rates.get("usd_inr",   {}).get("value")
    brent     = commodities.get("crude_brent_usd", {}).get("value")
    gold      = commodities.get("gold_usd",        {}).get("value")

    fii_net   = fii.get("fii", {}).get("net")
    dii_net   = fii.get("dii", {}).get("net")
    fii_buy   = fii.get("fii", {}).get("buy")
    fii_sell  = fii.get("fii", {}).get("sell")

    us_10y    = us.get("us_10y_treasury", {}).get("latest_value")
    us_2y     = us.get("us_2y_treasury",  {}).get("latest_value")
    fed_rate  = us.get("fed_funds_rate",  {}).get("latest_value")
    yield_crv = us.get("yield_curve_10y_2y", {}).get("latest_value")
    us_cpi    = us.get("us_cpi",          {}).get("latest_value")

    pcr       = fno.get("pcr")
    max_pain  = fno.get("max_pain")
    atm_iv    = fno.get("atm_iv")

    nifty50   = _find_index(nse_indices, "NIFTY 50")
    nifty_pe  = nifty50.get("pe") if nifty50 else None
    nifty_pb  = nifty50.get("pb") if nifty50 else None

    # ── Compute signals ──────────────────────────────────────────────────────
    sig_breadth = _breadth_signal(ad_ratio)
    sig_vix     = _vix_signal(vix)
    sig_fii     = _fii_signal(fii_net)
    sig_crude   = _crude_signal(brent)
    sig_inr     = _usd_inr_signal(usd_inr)
    sig_curve   = _yield_curve_signal(yield_crv)
    sig_rates   = _rate_env_signal(us_10y)
    sig_pe      = _pe_signal(nifty_pe, "NIFTY 50")

    posture = _derive_posture(sig_breadth, sig_fii, sig_vix)
    sectors = _derive_sectors(posture, sig_crude, sig_inr, sig_fii, sig_curve)

    # ── Sector PE snapshot (useful context for Phase C) ───────────────────────
    sector_pe: dict = {}
    for idx in nse_indices:
        if not isinstance(idx, dict):
            continue
        name = idx.get("name", "")
        pe   = idx.get("pe")
        if name and pe:
            sector_pe[name] = {
                "pe":           pe,
                "pb":           idx.get("pb"),
                "pe_signal":    _pe_signal(pe, name),
                "change_pct":   idx.get("change_pct"),
                "change_1y":    idx.get("change_pct_1y"),
                "advances":     idx.get("advances"),
                "declines":     idx.get("declines"),
            }

    return {
        "generated_at":   datetime.now(_IST).isoformat(),

        # Full source provenance — every downstream module can trace back
        "sources": {
            "india_macro": str(india_file) if india_file else None,
            "us_macro":    str(us_file)    if us_file    else None,
            "fii_dii":     str(fii_file)   if fii_file   else None,
            "fno_nifty":   str(fno_file)   if fno_file   else None,
        },

        # Raw numbers as-is from Phase A (for auditability)
        "raw_data": {
            "nifty_50":          nifty_val,
            "nifty_pe":          nifty_pe,
            "nifty_pb":          nifty_pb,
            "ad_ratio":          ad_ratio,
            "breadth_index":     breadth.get("index"),
            "advances":          breadth.get("advances"),
            "declines":          breadth.get("declines"),
            "unchanged":         breadth.get("unchanged"),
            "vix_india":         vix,
            "fii_net_cr":        fii_net,
            "fii_buy_cr":        fii_buy,
            "fii_sell_cr":       fii_sell,
            "dii_net_cr":        dii_net,
            "usd_inr":           usd_inr,
            "crude_brent_usd":   brent,
            "gold_usd":          gold,
            "fed_funds_rate":    fed_rate,
            "us_10y_yield":      us_10y,
            "us_2y_yield":       us_2y,
            "us_cpi":            us_cpi,
            "yield_curve_10y2y": yield_crv,
            "nifty_pcr":         pcr,
            "nifty_max_pain":    max_pain,
            "nifty_atm_iv":      atm_iv,
        },

        # Labelled signals — what the numbers mean
        "signals": {
            "breadth":     sig_breadth,
            "vix":         sig_vix,
            "fii":         sig_fii,
            "crude":       sig_crude,
            "usd_inr":     sig_inr,
            "yield_curve": sig_curve,
            "rate_env":    sig_rates,
            "nifty_pe":    sig_pe,
        },

        # Top-level posture and sector recommendations
        "market_posture": posture,
        "sectors":        sectors,

        # Per-sector PE snapshot for Phase C context
        "sector_pe": sector_pe,
    }


def save_regime() -> str:
    """Compute and save market regime to output/phaseB/market_regime/."""
    regime = compute_regime()
    MARKET_REGIME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    out_file = MARKET_REGIME_OUTPUT_DIR / f"market_regime_{today}.json"
    out_file.write_text(json.dumps(regime, ensure_ascii=False, indent=2))
    return str(out_file)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Computing market regime from latest Phase A data...\n")
    regime = compute_regime()

    print(f"  Market posture : {regime['market_posture'].upper()}")
    print(f"\n  Signals:")
    for k, v in regime["signals"].items():
        print(f"    {k:15s}  →  {v}")

    rd = regime["raw_data"]
    print(f"\n  Key numbers:")
    print(f"    Nifty 50      : {rd['nifty_50']}  (PE {rd['nifty_pe']}, PB {rd['nifty_pb']})")
    print(f"    A/D ratio     : {rd['ad_ratio']}  ({rd['advances']} adv / {rd['declines']} dec)")
    print(f"    India VIX     : {rd['vix_india']}")
    print(f"    FII net (₹cr) : {rd['fii_net_cr']}")
    print(f"    DII net (₹cr) : {rd['dii_net_cr']}")
    print(f"    USD/INR       : {rd['usd_inr']}")
    print(f"    Brent crude   : {rd['crude_brent_usd']} USD")
    print(f"    US 10Y yield  : {rd['us_10y_yield']}%")
    print(f"    Yield curve   : {rd['yield_curve_10y2y']} (10Y-2Y)")

    print(f"\n  Sector recommendations:")
    print(f"    Favoured : {regime['sectors']['favored']}")
    print(f"    Avoid    : {regime['sectors']['avoid']}")

    print(f"\n  Top sector PE:")
    for name, data in list(regime["sector_pe"].items())[:6]:
        print(f"    {name:25s}  PE={data['pe']:6.1f}  [{data['pe_signal']}]  1Y={data['change_1y']}%")

    saved = save_regime()


# ── Layer 5 integration ───────────────────────────────────────────────────────

def build_layer5_market_view(market_signals: list[dict],
                              memory_context: dict,
                              run_id: str = "") -> dict:
    """
    Build the Layer 5 market_view.json output.

    Calls compute_regime() for the base rule-based regime, then enriches
    with Layer 3 market_signal_cards and Layer 4 short-term memory context.

    Returns a market_view dict matching the Layer 5 schema.
    """
    from datetime import datetime, timezone, timedelta
    _IST_local = timezone(timedelta(hours=5, minutes=30))
    today      = datetime.now(_IST_local).strftime("%Y%m%d")

    # Base regime from phaseA raw data
    regime = compute_regime()
    posture = regime.get("market_posture", "selective_research")
    signals = regime.get("signals", {})
    raw     = regime.get("raw_data", {})

    # Enrich with L3 institutional flow signals
    fii_l3 = _extract_fii_from_signals(market_signals)
    if fii_l3 is not None and raw.get("fii_net_cr") is None:
        raw["fii_net_cr"] = fii_l3

    # Enrich with L4 memory: recurring short-term themes
    short_term_mem = memory_context.get("relevant_short_term_memory") or []
    recurring_themes = [r.get("summary", "") for r in short_term_mem if r.get("occurrence_count", 1) >= 3]

    # Derive Layer 5 schema fields from regime
    regime_label   = _posture_to_regime(posture)
    risk_level     = _posture_to_risk(posture)
    trend_state    = _signals_to_trend(signals)
    val_state      = _pe_to_valuation(signals.get("nifty_pe", "unknown"))
    flow_state     = _fii_to_flow(signals.get("fii", "unknown"), signals.get("breadth", "unknown"))
    vol_state      = _vix_to_vol(signals.get("vix", "unknown"))
    recommended    = posture

    reasoning = _build_reasoning(signals, raw, recurring_themes)
    data_gaps  = _identify_gaps(raw)

    supporting_refs: list[dict] = []
    for sig in (market_signals or [])[:5]:
        for r in (sig.get("source_refs") or [])[:2]:
            supporting_refs.append(r)

    return {
        "market_view_id":           f"MKT_VIEW_{today}_INDIA",
        "research_run_id":          run_id,
        "market":                   "india",
        "regime":                   regime_label,
        "risk_level":               risk_level,
        "trend_state":              trend_state,
        "valuation_state":          val_state,
        "liquidity_flow_state":     flow_state,
        "volatility_state":         vol_state,
        "recommended_posture":      recommended,
        "not_final_recommendation": True,
        "reasoning_summary":        reasoning,
        "supporting_refs":          supporting_refs[:10],
        "data_gaps":                data_gaps,
        "confidence":               _confidence(signals),
        "raw_data":                 raw,
        "sectors":                  regime.get("sectors", {}),
        "recurring_memory_themes":  recurring_themes[:5],
    }


def _extract_fii_from_signals(signals: list[dict]) -> float | None:
    for sig in signals:
        if sig.get("metric_name") == "fii_net_flow" and sig.get("metric_value") is not None:
            try:
                return float(sig["metric_value"])
            except (TypeError, ValueError):
                pass
    return None


def _posture_to_regime(posture: str) -> str:
    return {
        "aggressive_research": "risk_on",
        "selective_research":  "neutral_to_cautious",
        "cautious_watchlist":  "risk_off",
        "defensive":           "risk_off",
        "wait":                "uncertain",
    }.get(posture, "neutral")


def _posture_to_risk(posture: str) -> str:
    return {
        "aggressive_research": "low",
        "selective_research":  "medium",
        "cautious_watchlist":  "high",
        "defensive":           "high",
        "wait":                "uncertain",
    }.get(posture, "medium")


def _signals_to_trend(signals: dict) -> str:
    breadth = signals.get("breadth", "unknown")
    if breadth == "bullish":    return "bullish"
    if breadth == "bearish":    return "bearish"
    if breadth == "neutral":    return "sideways"
    return "uncertain"


def _pe_to_valuation(pe_signal: str) -> str:
    return {"expensive": "expensive", "fair": "fair", "cheap": "cheap"}.get(pe_signal, "uncertain")


def _fii_to_flow(fii_sig: str, breadth_sig: str) -> str:
    if fii_sig in ("buying",):             return "positive"
    if fii_sig in ("heavy_selling",):      return "negative"
    if fii_sig in ("selling",):
        return "mixed" if breadth_sig == "bullish" else "negative"
    return "mixed"


def _vix_to_vol(vix_sig: str) -> str:
    return {"fear": "high", "elevated": "elevated", "moderate": "moderate", "calm": "low"}.get(
        vix_sig, "uncertain"
    )


def _build_reasoning(signals: dict, raw: dict, recurring_themes: list[str]) -> list[str]:
    r: list[str] = []
    fii  = signals.get("fii", "unknown")
    vix  = signals.get("vix", "unknown")
    br   = signals.get("breadth", "unknown")
    pe   = signals.get("nifty_pe", "unknown")
    inr  = signals.get("usd_inr", "unknown")

    if fii == "buying":
        r.append("FII flows are positive — supportive for market liquidity.")
    elif fii in ("selling", "heavy_selling"):
        fii_val = raw.get("fii_net_cr")
        r.append(f"FII net selling ({fii_val} ₹cr) — liquidity headwind.")
    if vix == "fear":
        r.append("India VIX elevated — heightened market fear; caution warranted.")
    elif vix == "calm":
        r.append("India VIX low — market complacency; volatility could pick up.")
    if br == "bullish":
        r.append("Market breadth is strong — broad participation in the rally.")
    elif br == "bearish":
        r.append("Weak breadth — rally is narrow or broad selling underway.")
    if pe in ("expensive",):
        r.append("Nifty valuations appear stretched; selective stock picking preferred.")
    if inr in ("weak", "very_weak"):
        r.append("Rupee weakness adds to imported inflation and FII exit pressure.")
    for t in recurring_themes[:2]:
        r.append(f"Memory: recurring short-term signal — {t}")
    if not r:
        r.append("Mixed signals; selective research posture recommended.")
    return r


def _identify_gaps(raw: dict) -> list[str]:
    gaps: list[str] = []
    if raw.get("ad_ratio") is None:
        gaps.append("Market breadth (A/D ratio) not available")
    if raw.get("nifty_pe") is None:
        gaps.append("Nifty valuation (PE/PB) not available")
    if raw.get("fii_net_cr") is None:
        gaps.append("FII net flow not available")
    if raw.get("vix_india") is None:
        gaps.append("India VIX not available")
    return gaps


def _confidence(signals: dict) -> float:
    known = sum(1 for v in signals.values() if v != "unknown")
    total = len(signals) or 1
    return round(0.4 + 0.5 * (known / total), 2)
    print(f"\n  Saved → {saved}")
