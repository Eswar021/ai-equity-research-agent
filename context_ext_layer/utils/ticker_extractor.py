import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rapidfuzz import process, fuzz

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from context_ext_layer.utils.nse_symbols import load_symbols, _simplify

_IST = timezone(timedelta(hours=5, minutes=30))

# Colloquial aliases that are too short or ambiguous to match via simplified name.
# E.g. "SBI" is unambiguous in speech but "state bank" simplified is just "state"
# which would false-positive on many things.
ALIASES: dict[str, str] = {
    # ── Indices ──────────────────────────────────────────────────────────────
    "nifty":              "^NSEI",
    "sensex":             "^BSESN",
    "bank nifty":         "^NSEBANK",
    "nifty bank":         "^NSEBANK",

    # ── Large caps — short names / acronyms ──────────────────────────────────
    "sbi":                "SBIN.NS",
    "tcs":                "TCS.NS",
    "hul":                "HINDUNILVR.NS",
    "hindustan unilever": "HINDUNILVR.NS",
    "m&m":                "M&M.NS",
    "mahindra":           "M&M.NS",
    "l&t":                "LT.NS",
    "larsen":             "LT.NS",
    "lic":                "LICI.NS",
    "ioc":                "IOC.NS",
    "indian oil":         "IOC.NS",
    "bpcl":               "BPCL.NS",
    "ongc":               "ONGC.NS",
    "ntpc":               "NTPC.NS",
    "gail":               "GAIL.NS",
    "sail":               "SAIL.NS",
    "nmdc":               "NMDC.NS",
    "hpcl":               "HINDPETRO.NS",
    "bhel":               "BHEL.NS",
    "itc":                "ITC.NS",
    "acc":                "ACC.NS",
    "dlf":                "DLF.NS",
    "hdfcbank":           "HDFCBANK.NS",
    "hdfc bank":          "HDFCBANK.NS",
    "icici bank":         "ICICIBANK.NS",
    "kotak bank":         "KOTAKBANK.NS",
    "kotak mahindra":     "KOTAKBANK.NS",
    "axis bank":          "AXISBANK.NS",
    "yes bank":           "YESBANK.NS",
    "pnb":                "PNB.NS",
    "punjab national":    "PNB.NS",
    "bob":                "BANKBARODA.NS",
    "bank of baroda":     "BANKBARODA.NS",
    "reliance":           "RELIANCE.NS",
    "infosys":            "INFY.NS",
    "infy":               "INFY.NS",
    "wipro":              "WIPRO.NS",
    "hcltech":            "HCLTECH.NS",
    "hcl tech":           "HCLTECH.NS",
    "hcl technologies":   "HCLTECH.NS",
    "tech mahindra":      "TECHM.NS",
    "techm":              "TECHM.NS",
    "bajaj finance":      "BAJAJFIN.NS",
    "bajaj finserv":      "BAJAJFINSV.NS",
    "bajaj auto":         "BAJAJ-AUTO.NS",
    "maruti":             "MARUTI.NS",
    "maruti suzuki":      "MARUTI.NS",
    "tata motors":        "TATAMOTORS.NS",
    "tata steel":         "TATASTEEL.NS",
    "tata power":         "TATAPOWER.NS",
    "tata consultancy":   "TCS.NS",
    "adani ports":        "ADANIPORTS.NS",
    "adani green":        "ADANIGREEN.NS",
    "adani enterprises":  "ADANIENT.NS",
    "sun pharma":         "SUNPHARMA.NS",
    "sun pharmaceutical": "SUNPHARMA.NS",
    "dr reddy":           "DRREDDY.NS",
    "dr. reddy":          "DRREDDY.NS",
    "cipla":              "CIPLA.NS",
    "divi's":             "DIVISLAB.NS",
    "divis":              "DIVISLAB.NS",
    "asian paints":       "ASIANPAINT.NS",
    "titan":              "TITAN.NS",
    "ultracemco":         "ULTRACEMCO.NS",
    "ultratech":          "ULTRACEMCO.NS",
    "jswsteel":           "JSWSTEEL.NS",
    "jsw steel":          "JSWSTEEL.NS",
    "power grid":         "POWERGRID.NS",
    "powergrid":          "POWERGRID.NS",
    "coal india":         "COALINDIA.NS",

    # ── New-age / fintech ─────────────────────────────────────────────────────
    "paytm":              "PAYTM.NS",
    "zomato":             "ZOMATO.NS",
    "swiggy":             "SWIGGY.NS",
    "nykaa":              "FSN.NS",
    "policybazaar":       "POLICYBZR.NS",
    "delhivery":          "DELHIVERY.NS",

    # ── Aviation (IndiGo not in NSE simplified list; SpiceJet suspended) ─────
    "indigo":             "INDIGO.NS",   # InterGlobe Aviation
    "interglobe":         "INDIGO.NS",

    # ── Others commonly mentioned in news ─────────────────────────────────────
    "irctc":              "IRCTC.NS",
    "irfc":               "IRFC.NS",
    "rvnl":               "RVNL.NS",
    "hal":                "HAL.NS",
    "bel":                "BEL.NS",
    "mrf":                "MRF.NS",
    "pidilite":           "PIDILITIND.NS",
    "page industries":    "PAGEIND.NS",
    "havells":            "HAVELLS.NS",
    "voltas":             "VOLTAS.NS",
    "crompton":           "CROMPTON.NS",
    "godrej consumer":    "GODREJCP.NS",
    "godrej properties":  "GODREJPROP.NS",
    "oberoi realty":      "OBEROIRLTY.NS",
    "indusind":           "INDUSINDBK.NS",
    "indusind bank":      "INDUSINDBK.NS",
    "shriram finance":    "SHRIRAMFIN.NS",
    "cholamandalam":      "CHOLAFIN.NS",
    "muthoot":            "MUTHOOTFIN.NS",
    "manappuram":         "MANAPPURAM.NS",
    "srf":                "SRF.NS",
    "deepak nitrite":     "DEEPAKNI.NS",
    "navin fluorine":     "NAVINFLUOR.NS",
}


def _build_simplified_index(symbols: dict) -> dict[str, str | None]:
    """
    Map simplified_name → ticker.
    If two companies share the same simplified name, value is None (ambiguous — skip in text extraction).
    """
    index: dict[str, str | None] = {}
    for ticker, data in symbols.items():
        s = data["simplified"]
        if not s or len(s) < 4:   # skip very short simplified names (noise risk)
            continue
        if s in index:
            index[s] = None        # mark ambiguous
        else:
            index[s] = ticker
    return index


def extract_tickers(text: str) -> list[dict]:
    """
    Extract NSE ticker symbols mentioned in article text.
    Two-pass:
      1. Aliases dict (short/colloquial names: SBI, TCS, nifty …)
      2. Simplified name exact-match against the full 2360-stock NSE list
    Returns [{"company": ..., "ticker": ...}], deduplicated.
    """
    symbols     = load_symbols()
    index       = _build_simplified_index(symbols)
    text_lower  = text.lower()
    seen        = set()
    results     = []

    def _add(ticker: str, label: str):
        if ticker not in seen:
            seen.add(ticker)
            name = symbols.get(ticker, {}).get("name", label) if ticker in symbols else label
            results.append({"company": name, "ticker": ticker})

    # Pass 1 — aliases (sorted longest first to avoid substring shadowing)
    for alias, ticker in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, text_lower):
            _add(ticker, alias.upper())

    # Pass 2 — simplified NSE names (longest first to catch "hdfc bank" before "hdfc")
    for simplified, ticker in sorted(index.items(), key=lambda x: -len(x[0])):
        if ticker is None or ticker in seen:
            continue
        pattern = r"\b" + re.escape(simplified) + r"\b"
        if re.search(pattern, text_lower):
            _add(ticker, simplified.title())

    return results


def lookup_ticker(company_name: str, threshold: int = 75) -> dict | None:
    """
    Fuzzy-search for a company by name in the full NSE list.
    Useful when you know roughly what to look for.
    Returns {"ticker", "name", "score"} or None.
    """
    symbols = load_symbols()
    # rapidfuzz matches against dict VALUES; keys are returned as the identifier
    choices = {ticker: data["simplified"] for ticker, data in symbols.items() if data["simplified"]}

    query = _simplify(company_name)
    match = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
    if match and match[1] >= threshold:
        simplified, score, ticker = match
        return {
            "ticker": ticker,
            "name":   symbols[ticker]["name"],
            "score":  score,
        }
    return None


if __name__ == "__main__":
    sample = """
    Reliance Industries and TCS led the Nifty gains today as HDFC Bank fell after earnings.
    Infosys guidance disappointed while Bajaj Finance hit a new 52-week high.
    Maruti Suzuki reported strong numbers and ONGC crude output rose month-on-month.
    The Sensex closed flat while Bank Nifty outperformed. Zomato and Paytm saw heavy selling.
    """

    print("── extract_tickers ─────────────────────────")
    tickers = extract_tickers(sample)
    print(f"Found {len(tickers)} tickers:")
    for t in tickers:
        print(f"  {t['company']:45s} → {t['ticker']}")

    print("\n── lookup_ticker (fuzzy) ───────────────────")
    for query in ["Bajaj Finserv", "Sun Pharma", "Larsen and Toubro", "Hindustan Lever"]:
        result = lookup_ticker(query)
        if result:
            print(f"  '{query}' → {result['ticker']}  ({result['name']}, score={result['score']})")
        else:
            print(f"  '{query}' → no match")
