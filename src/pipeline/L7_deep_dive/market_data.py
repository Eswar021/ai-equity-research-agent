"""
Market data collector — fetches price, technicals, and analyst estimates via yfinance.

All tickers must be bare NSE symbols (e.g. "HDFCBANK").
The .NS suffix is added internally.

Returns a dict with: price, analyst_consensus fields.
Returns None if the ticker is invalid or data unavailable — caller logs and skips.
"""

from __future__ import annotations

import re
import pandas as pd
import yfinance as yf


def _nse(ticker: str) -> str:
    t = ticker.upper().strip()
    if not re.search(r"\.(NS|BO)$", t):
        return t + ".NS"
    return t


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    val   = 100 - (100 / (1 + rs))
    last  = val.iloc[-1]
    return round(float(last), 1) if pd.notna(last) else None


def _pct_vs_ma(current: float, ma: float | None) -> float | None:
    if ma is None or ma == 0:
        return None
    return round((current - ma) / ma * 100, 2)


def fetch(ticker: str, history_days: int = 200) -> dict | None:
    """
    Fetch price/technical data + analyst consensus for an NSE ticker.
    Returns None on failure (invalid ticker, no data).
    """
    yf_ticker = _nse(ticker)
    try:
        t    = yf.Ticker(yf_ticker)
        info = t.info

        # Basic validity check — yfinance returns a minimal dict for unknown tickers
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None

        hist = t.history(period=f"{history_days}d")
        if hist.empty or len(hist) < 5:
            return None

        closes = hist["Close"]
        current = float(closes.iloc[-1])

        def _ret(days: int) -> float | None:
            if len(closes) < days + 1:
                return None
            start = float(closes.iloc[-(days + 1)])
            if start == 0:
                return None
            return round((current - start) / start * 100, 2)

        def _ma(days: int) -> float | None:
            if len(closes) < days:
                return None
            return float(closes.iloc[-days:].mean())

        ma50  = _ma(50)
        ma200 = _ma(200)

        vol_series = hist["Volume"]
        vol_ratio  = None
        if len(vol_series) >= 21:
            avg_20   = float(vol_series.iloc[-21:-1].mean())
            curr_vol = float(vol_series.iloc[-1])
            if avg_20 > 0:
                vol_ratio = round(curr_vol / avg_20, 2)

        w52_high = info.get("fiftyTwoWeekHigh")
        w52_low  = info.get("fiftyTwoWeekLow")
        pct_from_high = None
        if w52_high and w52_high > 0:
            pct_from_high = round((current - w52_high) / w52_high * 100, 2)

        price_data = {
            "current":          round(current, 2),
            "return_30d_pct":   _ret(30),
            "return_90d_pct":   _ret(90),
            "rsi_14":           _rsi(closes),
            "pct_above_50dma":  _pct_vs_ma(current, ma50),
            "pct_above_200dma": _pct_vs_ma(current, ma200),
            "volume_ratio_20d": vol_ratio,
            "52w_high":         w52_high,
            "52w_low":          w52_low,
            "pct_from_52w_high": pct_from_high,
        }

        # Analyst consensus (best-effort — often empty for mid/small caps)
        analyst: dict = {}
        try:
            target_mean = info.get("targetMeanPrice")
            if target_mean and price:
                upside = round((target_mean - price) / price * 100, 1)
                analyst["target_price_mean"] = round(target_mean, 2)
                analyst["upside_pct"]        = upside

            analyst["recommendation_mean"] = info.get("recommendationMean")  # 1=StrongBuy…5=StrongSell
            analyst["analyst_count"]      = info.get("numberOfAnalystOpinions")

            # Forward EPS / forward P/E
            fwd_eps = info.get("forwardEps")
            fwd_pe  = info.get("forwardPE")
            if fwd_eps:
                analyst["forward_eps"] = round(fwd_eps, 2)
            if fwd_pe:
                analyst["forward_pe"]  = round(fwd_pe, 2)

            # Trailing EPS for cross-check
            trailing_eps = info.get("trailingEps")
            if trailing_eps:
                analyst["trailing_eps"] = round(trailing_eps, 2)

        except Exception:
            pass

        return {
            "price":             price_data,
            "analyst_consensus": analyst if analyst else None,
        }

    except Exception:
        return None
