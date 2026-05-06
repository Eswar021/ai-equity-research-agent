"""
Analyst estimates and consensus data for Indian (and US) listed stocks.

Source: Yahoo Finance via yfinance — aggregates research from major brokerages.
For Indian stocks: Motilal Oswal, Kotak, ICICI Securities, Jefferies, etc.
No API key required.

Data collected:
  - Price targets     : consensus high / mean / median / low vs current price
  - EPS estimates     : current Q, next Q, current year, next year
  - Revenue estimates : same periods as EPS
  - Earnings history  : last 4 quarters actual vs estimated EPS + surprise %
  - Recommendations   : monthly buy/hold/sell counts (last 3 months)
  - EPS trend         : estimate revisions — current vs 7d / 30d / 60d / 90d ago
  - EPS revisions     : up/down revision counts in last 7d / 30d
"""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import ANALYST_ESTIMATES_OUTPUT_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def _nse_ticker(ticker: str) -> str:
    """Ensure ticker has .NS suffix for NSE stocks."""
    ticker = ticker.upper().strip()
    if not re.search(r"\.(NS|BO)$", ticker):
        return ticker + ".NS"
    return ticker


def _df_to_records(df) -> list[dict] | None:
    """Convert a pandas DataFrame to a list of dicts, or None if df is None/empty."""
    if df is None or df.empty:
        return None
    df = df.reset_index()
    return df.where(df.notna(), None).to_dict(orient="records")


def fetch_analyst_estimates(ticker: str) -> dict:
    """
    Fetch all available analyst estimate data for a stock.

    Returns a dict with:
      ticker, fetched_at,
      price_targets, earnings_estimates, revenue_estimates,
      earnings_history, recommendations, eps_trend, eps_revisions
    """
    yf_ticker = _nse_ticker(ticker)
    symbol    = re.sub(r"\.(NS|BO)$", "", yf_ticker)
    t         = yf.Ticker(yf_ticker)

    # ── Price targets ─────────────────────────────────────────────────────────
    pt_raw = t.analyst_price_targets  # dict: {current, high, low, mean, median}
    if pt_raw and pt_raw.get("mean"):
        current = pt_raw.get("current")
        mean    = pt_raw.get("mean")
        upside  = round((mean - current) / current * 100, 1) if current and mean else None
        price_targets = {
            "current_price": current,
            "target_high":   pt_raw.get("high"),
            "target_mean":   mean,
            "target_median": pt_raw.get("median"),
            "target_low":    pt_raw.get("low"),
            "upside_to_mean_pct": upside,
        }
    else:
        price_targets = None

    # ── EPS & revenue estimates ───────────────────────────────────────────────
    ee = t.earnings_estimate
    re_ = t.revenue_estimate

    def _parse_estimate_df(df):
        if df is None or df.empty:
            return None
        result = {}
        for period, row in df.iterrows():
            entry = {}
            for col in df.columns:
                v = row[col]
                entry[col] = None if (v != v) else v  # NaN → None
            result[period] = entry
        return result

    # ── Earnings history (actual vs estimate, last 4 quarters) ───────────────
    eh = t.earnings_history
    earnings_history = None
    if eh is not None and not eh.empty:
        earnings_history = []
        for period, row in eh.iterrows():
            earnings_history.append({
                "quarter":          str(period),
                "eps_actual":       None if row.get("epsActual") != row.get("epsActual") else row.get("epsActual"),
                "eps_estimate":     None if row.get("epsEstimate") != row.get("epsEstimate") else row.get("epsEstimate"),
                "eps_surprise":     None if row.get("epsDifference") != row.get("epsDifference") else row.get("epsDifference"),
                "surprise_pct":     None if row.get("surprisePercent") != row.get("surprisePercent") else round(row.get("surprisePercent") * 100, 2),
            })

    # ── Analyst recommendations (buy/hold/sell counts, last 3 months) ────────
    rec = t.recommendations
    recommendations = None
    if rec is not None and not rec.empty:
        recommendations = []
        for _, row in rec.iterrows():
            recommendations.append({
                "period":       row.get("period"),
                "strong_buy":   row.get("strongBuy"),
                "buy":          row.get("buy"),
                "hold":         row.get("hold"),
                "sell":         row.get("sell"),
                "strong_sell":  row.get("strongSell"),
            })

    # ── EPS trend (revisions over time) ──────────────────────────────────────
    et = t.eps_trend
    eps_trend = _parse_estimate_df(et)

    # ── EPS revisions (up/down counts) ───────────────────────────────────────
    er = t.eps_revisions
    eps_revisions = _parse_estimate_df(er)

    return {
        "ticker":               symbol,
        "yf_ticker":            yf_ticker,
        "fetched_at":           datetime.now(_IST).isoformat(),
        "price_targets":        price_targets,
        "earnings_estimates":   _parse_estimate_df(ee),
        "revenue_estimates":    _parse_estimate_df(re_),
        "earnings_history":     earnings_history,
        "recommendations":      recommendations,
        "eps_trend":            eps_trend,
        "eps_revisions":        eps_revisions,
    }


def save_analyst_estimates(ticker: str) -> str:
    symbol = re.sub(r"\.(NS|BO)$", "", ticker.upper())
    data   = fetch_analyst_estimates(ticker)

    ANALYST_ESTIMATES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    filename = f"{symbol}_analyst_estimates_{today}.json"

    out_file = ANALYST_ESTIMATES_OUTPUT_DIR / filename
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(out_file)


if __name__ == "__main__":
    ticker = "RELIANCE"

    print(f"Fetching analyst estimates for {ticker} ...\n")
    saved = save_analyst_estimates(ticker)
    print(f"Saved to: {saved}\n")

    with open(saved) as f:
        d = json.load(f)

    # Price targets
    pt = d.get("price_targets")
    if pt:
        print(f"── Price Targets ─────────────────────────────────────────────")
        print(f"  Current:  ₹{pt['current_price']:,.0f}")
        print(f"  Mean:     ₹{pt['target_mean']:,.0f}  ({pt['upside_to_mean_pct']:+.1f}% upside)")
        print(f"  Range:    ₹{pt['target_low']:,.0f} – ₹{pt['target_high']:,.0f}")

    # Recommendations
    rec = d.get("recommendations")
    if rec:
        print(f"\n── Analyst Recommendations (last {len(rec)} months) ───────────────")
        for r in rec:
            total = (r["strong_buy"] or 0) + (r["buy"] or 0) + (r["hold"] or 0) + (r["sell"] or 0) + (r["strong_sell"] or 0)
            print(f"  {r['period']:>4}  SB={r['strong_buy']}  B={r['buy']}  H={r['hold']}  S={r['sell']}  SS={r['strong_sell']}  (total={total})")

    # EPS estimates
    ee = d.get("earnings_estimates")
    if ee:
        print(f"\n── EPS Estimates ─────────────────────────────────────────────")
        for period, v in ee.items():
            analysts = int(v.get("numberOfAnalysts") or 0)
            growth   = f"{v.get('growth')*100:+.1f}%" if v.get("growth") is not None else "—"
            print(f"  {period:>4}  avg={v.get('avg')}  low={v.get('low')}  high={v.get('high')}  analysts={analysts}  growth={growth}")

    # Earnings history
    eh = d.get("earnings_history")
    if eh:
        print(f"\n── Earnings History (actual vs estimate) ─────────────────────")
        for q in eh:
            beat = "BEAT" if (q["eps_surprise"] or 0) > 0 else "MISS"
            print(f"  {q['quarter']}  actual={q['eps_actual']}  est={q['eps_estimate']}  surprise={q['surprise_pct']}%  [{beat}]")

    # EPS trend
    et = d.get("eps_trend")
    if et:
        print(f"\n── EPS Trend (estimate revisions) ────────────────────────────")
        for period, v in et.items():
            direction = ""
            if v.get("current") and v.get("90daysAgo"):
                change = v["current"] - v["90daysAgo"]
                direction = f"  {'▲' if change > 0 else '▼'} {abs(change):.2f} vs 90d ago"
            print(f"  {period:>4}  now={v.get('current')}  7d={v.get('7daysAgo')}  30d={v.get('30daysAgo')}{direction}")
