"""
intelligence_layer/market_opportunity_intelligence/market_regime_agent.py  —  Layer 5, Market Regime Agent

Reads the most recent Layer 1 macro outputs and computes a structured
market regime — all rule-based thresholds, no LLM.

Inputs (latest file from each dir):
  output/{date}/phaseA/macro_data/india_macro_*.json
  output/{date}/phaseA/macro_data/us_macro_*.json
  output/{date}/phaseA/fii_dii/fii_dii_*.json
  output/{date}/phaseA/fno_data/NIFTY_fno_*.json   (optional — empty outside market hours)

Output:
  output/{date}/phaseB/market_regime/market_regime_{date}.json

Standalone test:
  python intelligence_layer/market_opportunity_intelligence/market_regime_agent.py
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
    print(f"\n  Saved → {saved}")
