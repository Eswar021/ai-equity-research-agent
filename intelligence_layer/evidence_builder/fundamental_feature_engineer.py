"""
intelligence_layer/evidence_builder/fundamental_feature_engineer.py — Layer 8

Computes fundamental features from screener_in.json.

screener_in data format:
  key_ratios: dict of str → str  (e.g. "₹ 8,65,447 Cr.", "16.6", "65.2 %")
  quarterly_results: list of {metric: str, date_col: str_val, ...} — pivot format
  growth_metrics: {
      "Compounded Sales Growth": {"5 Years:": "10%", ...},
      "Compounded Profit Growth": {...},
      "Return on Equity": {"Last Year:": "65%", ...}
  }
  profit_loss: list — same pivot format
  balance_sheet: list — same pivot format
"""

from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))


def compute(scope: dict) -> dict:
    tid = scope["target_id"]
    sc  = scope["files"].get("screener_in") or {}

    feats: dict[str, float | str | None] = {}
    warnings: list[str] = []

    key_ratios    = sc.get("key_ratios", {})
    growth        = sc.get("growth_metrics", {})
    qr_pivot      = sc.get("quarterly_results", [])  # list of metric rows

    # ── Key ratios ─────────────────────────────────────────────────────────────
    feats["pe_ratio"]          = _pct(key_ratios.get("Stock P/E"))
    feats["book_value"]        = _rupees(key_ratios.get("Book Value"))
    feats["dividend_yield_pct"]= _pct(key_ratios.get("Dividend Yield"))
    feats["roce_pct"]          = _pct(key_ratios.get("ROCE"))
    feats["roe_pct"]           = _pct(key_ratios.get("ROE"))
    feats["debt_to_equity"]    = _pct(key_ratios.get("Debt to equity"))

    # ── Growth metrics ─────────────────────────────────────────────────────────
    csg  = growth.get("Compounded Sales Growth", {})
    cpg  = growth.get("Compounded Profit Growth", {})
    roe_hist = growth.get("Return on Equity", {})

    feats["sales_cagr_5y_pct"]  = _pct(_find(csg, "5 Year"))
    feats["sales_cagr_3y_pct"]  = _pct(_find(csg, "3 Year"))
    feats["sales_ttm_growth_pct"]= _pct(_find(csg, "TTM"))
    feats["profit_cagr_5y_pct"] = _pct(_find(cpg, "5 Year"))
    feats["profit_cagr_3y_pct"] = _pct(_find(cpg, "3 Year"))
    feats["profit_ttm_growth_pct"]= _pct(_find(cpg, "TTM"))
    feats["roe_10y_pct"]        = _pct(_find(roe_hist, "10 Year"))
    feats["roe_5y_pct"]         = _pct(_find(roe_hist, "5 Year"))
    feats["roe_3y_pct"]         = _pct(_find(roe_hist, "3 Year"))
    feats["roe_last_year_pct"]  = _pct(_find(roe_hist, "Last Year"))

    # ── Quarterly results — most recent 4 quarters ────────────────────────────
    if qr_pivot:
        date_cols = _date_columns(qr_pivot)
        recent_4  = date_cols[-4:] if len(date_cols) >= 4 else date_cols
        prev_4    = date_cols[-8:-4] if len(date_cols) >= 8 else []

        sales_row = _get_row(qr_pivot, "Sales")
        opm_row   = _get_row(qr_pivot, "OPM %")
        net_profit_row = _get_row(qr_pivot, "Net Profit")

        if sales_row and recent_4:
            feats["revenue_latest_qtr"] = _rupees(sales_row.get(recent_4[-1]))
            feats["revenue_yoy_growth_pct"] = _qtr_yoy(sales_row, recent_4, prev_4)

        if opm_row and recent_4:
            opm_vals = [_pct(opm_row.get(c)) for c in recent_4 if opm_row.get(c)]
            opm_vals = [v for v in opm_vals if v is not None]
            feats["opm_latest_pct"] = opm_vals[-1] if opm_vals else None
            feats["opm_trend"] = _trend_label(opm_vals)

        if net_profit_row and recent_4:
            feats["net_profit_latest_qtr"] = _rupees(net_profit_row.get(recent_4[-1]))
            feats["net_profit_yoy_growth_pct"] = _qtr_yoy(net_profit_row, recent_4, prev_4)

    # ── Shareholding ──────────────────────────────────────────────────────────
    shr_q = sc.get("shareholding_quarterly", [])
    if shr_q and isinstance(shr_q, list):
        promoter_row = _get_row(shr_q, "Promoters")
        if promoter_row:
            sh_cols = _date_columns(shr_q)
            if len(sh_cols) >= 4:
                old = _pct(promoter_row.get(sh_cols[-4]))
                new = _pct(promoter_row.get(sh_cols[-1]))
                if old is not None and new is not None:
                    feats["promoter_holding_latest_pct"] = new
                    feats["promoter_holding_change_4q_pct"] = round(new - old, 2)
                else:
                    feats["promoter_holding_latest_pct"] = None
                    feats["promoter_holding_change_4q_pct"] = None

    if not sc:
        warnings.append("screener_in missing — no fundamental features computed")

    completeness = sum(1 for v in feats.values() if v is not None) / max(len(feats), 1)

    source_ref = f"screener_in:{scope.get('target_dir','')}/screener_in.json"

    return {
        "feature_group_id":  f"FEAT_FUND_{tid}",
        "target_id":         tid,
        "feature_group":     "fundamental_features",
        "features":          feats,
        "source_record_refs": [source_ref],
        "data_quality": {
            "completeness_score": round(completeness, 2),
            "warnings":           warnings,
        },
        "calculated_at": datetime.now(_IST).isoformat(),
    }


# ── Parsers ───────────────────────────────────────────────────────────────────

def _pct(val: str | None) -> float | None:
    """Parse '65.2 %', '65.2', '10%' → 65.2"""
    if val is None:
        return None
    s = str(val).strip().replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _rupees(val: str | None) -> float | None:
    """Parse '₹ 8,65,447 Cr.' → 8654470000000 (raw crores × 1e7)
       or '49,780' → 49780.0 (quarterly in Cr)"""
    if val is None:
        return None
    s = str(val)
    s = re.sub(r'[₹,\s]', '', s)
    multiplier = 1.0
    if s.endswith("Cr.") or s.endswith("Cr"):
        s = re.sub(r'Cr\.?$', '', s)
        multiplier = 1.0  # keep in Cr for readability
    try:
        return round(float(s) * multiplier, 2)
    except (ValueError, TypeError):
        return None


def _find(d: dict, key_fragment: str) -> str | None:
    """Find value in dict where key contains key_fragment (case-insensitive)."""
    for k, v in d.items():
        if key_fragment.lower() in k.lower():
            return v
    return None


def _date_columns(pivot: list[dict]) -> list[str]:
    """Return all date-like columns from a pivot table row (excluding 'metric')."""
    if not pivot:
        return []
    row = pivot[0]
    return [k for k in row if k != "metric"]


def _get_row(pivot: list[dict], metric_name: str) -> dict | None:
    for row in pivot:
        if row.get("metric", "").strip().lower() == metric_name.strip().lower():
            return row
    return None


def _qtr_yoy(row: dict, recent_4: list[str], prev_4: list[str]) -> float | None:
    """YoY growth for most recent quarter vs same quarter a year ago."""
    if not recent_4 or not prev_4:
        return None
    cur  = _rupees(row.get(recent_4[-1]))
    prev = _rupees(row.get(prev_4[-1]))
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 2)


def _trend_label(vals: list[float]) -> str:
    if len(vals) < 2:
        return "insufficient_data"
    diff = vals[-1] - vals[0]
    if diff > 1.5:
        return "improving"
    if diff < -1.5:
        return "declining"
    return "stable"
