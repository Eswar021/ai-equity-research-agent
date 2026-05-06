# Context Extraction Layer

Collects raw context from multiple sources and saves structured JSON files.
Every module is independently runnable via `python <file>.py`.

The goal of this layer is simple: **extract raw data from sources and save it**.
No aggregation, no calculations, no analysis — that happens in later layers.

All timestamps are **IST (Asia/Kolkata, UTC+5:30)**.

---

## Three-Phase Architecture

| Phase | Folder | Purpose |
|---|---|---|
| **A — Broad Market Discovery** | `phaseA_BMD/` | Market-wide data — no ticker needed. Runs daily to get the full market picture. |
| **B — Candidate Selection** | `phaseB_CS/` | Reads Phase A output, extracts signals via LLM, scores tickers, produces a ranked candidate list. |
| **C — Company Deep Dive** | `phaseC_CDD/` | Per-ticker deep dive — fundamentals, filings, price data for each candidate. |

---

## Top-Level Orchestrator Scripts

| Script | Purpose |
|---|---|
| `run_phase_a.py` | Runs all Phase A collectors in sequence |
| `run_phase_b.py` | Runs B1 → B2 → B3 in sequence. Flags: `--skip-signals` (reuse last signals file), `--provider=openai\|lmstudio` |
| `run_phase_c.py` | Runs Phase C deep dive on all candidates. Flags: `--skip-screener` (skip screener.in scrape), `--ticker BHEL.NS` (single ticker test) |
| `inspect_phase_a.py` | Diagnostic health check — shows file counts, item counts, content quality for all Phase A outputs and key market data values. No side effects. |

---

## Data Freshness — What Can Be Re-fetched vs What Requires Daily Runs

| Module | History available? | Notes |
|---|---|---|
| screener_in | ✅ Always | Full 10-year financials always in page |
| peer_comparison | ✅ Always | Ratios fetched live from yfinance |
| analyst_estimates | ✅ Always | Yahoo Finance aggregates brokerage data |
| price_history | ✅ Always | yfinance has years of OHLCV |
| corporate_actions | ✅ Always | Full NSE action history in API |
| exchange_filings | ✅ Always | All NSE announcements always fetchable |
| filing_docs (transcripts) | ✅ Always | All past transcript PDFs stay on NSE servers |
| sec_filings | ✅ Always | SEC EDGAR keeps everything |
| india_macro | ✅ Always | World Bank has decades; NSE PE/PB is live |
| us_macro (FRED) | ✅ Always | FRED has decades of history; requires `FRED_API_KEY` |
| **fii_dii** | ❌ Today only | NSE API returns most recent trading day only |
| **bulk_deals** | ❌ Today only | NSE CSV archive only has today's data |
| **fno_data** | ❌ Live only | Option chain is a real-time snapshot |

> For `fii_dii`, `bulk_deals`, and `fno_data` — if you miss a day, that day's data is unrecoverable from NSE's public API. Run these daily.

---

## Folder Structure

All outputs land in `output/{YYYY-MM-DD}/` — each daily run gets its own dated folder. Phase A, B, and C all write to the same date folder when run on the same day.

```
context_ext_layer/
├── phaseA_BMD/              Phase A — Broad Market Discovery
│   ├── rss.py               RSS feed headlines + summaries (11 feeds)
│   ├── moneycontrol.py      Moneycontrol news by category
│   ├── economic_times.py    Economic Times news by category
│   ├── newsdata_io.py       NewsData.io API — broad market queries
│   ├── mediastack.py        Mediastack API — broad market queries
│   ├── gmail.py             Newsletters via Gmail IMAP
│   ├── india_macro.py       NSE index PE/PB, commodities, FX, rates
│   ├── us_macro.py          US macro data from FRED
│   ├── fii_dii.py           FII/DII daily institutional flows
│   ├── bulk_deals.py        Bulk & block deals (today's NSE CSV)
│   ├── fno_data.py          F&O option chain — NIFTY, BANKNIFTY (index-level)
│   ├── yt_transcript.py     YouTube channel search + transcript download
│   ├── browser_scraper.py   JS-rendered websites (Playwright)
│   └── generic.py           Any open website (article text via trafilatura)
│
├── phaseB_CS/               Phase B — Candidate Selection
│   ├── market_regime.py     B1: rule-based macro regime (no LLM)
│   ├── news_signal_extractor.py  B2: LLM extracts events from all Phase A text
│   └── candidate_scorer.py  B3: ranks tickers by signal strength + regime fit
│
├── utils/                   Shared utilities (used across phases)
│   ├── ticker_extractor.py  NSE ticker resolution (alias dict + fuzzy match)
│   ├── nse_symbols.py       NSE symbol list manager (2360 stocks, 7-day cache)
│   └── nse_equity_cache.json  cached NSE symbol list (auto-refreshed)
│
└── phaseC_CDD/              Phase C — Company Deep Dive (per-ticker)
    ├── screener_in.py        Company financials + filings (Indian stocks)
    ├── market_data.py        Current price snapshot
    ├── price_history.py      Historical OHLCV data
    ├── peer_comparison.py    Industry peer comparison
    ├── analyst_estimates.py  Analyst price targets, EPS/revenue estimates
    ├── exchange_filings.py   NSE corporate announcements
    ├── filing_docs.py        Concall transcripts + investor presentations
    ├── corporate_actions.py  Dividends, splits, bonuses, buybacks
    └── sec_filings.py        US company SEC EDGAR filings

llm/
└── llm_client.py            make_llm() factory — OpenAI, LMStudio providers

output/
└── {YYYY-MM-DD}/            One dated folder per daily run
    ├── phaseA/              Phase A raw outputs
    │   ├── rss/
    │   ├── moneycontrol/
    │   ├── economic_times/
    │   ├── newsdata_io/
    │   ├── mediastack/
    │   ├── gmail/
    │   ├── youtube/
    │   ├── fii_dii/
    │   ├── bulk_deals/
    │   ├── macro_data/
    │   └── fno_data/
    ├── phaseB/              Phase B outputs
    │   ├── market_regime/   market_regime_{date}.json
    │   ├── signals/         signals_{date}.json  (all LLM-extracted signals)
    │   ├── candidates/      candidates_{date}.json + candidates_{date}_final.json
    │   └── signal_logs/     signals_{date}.jsonl  (one LLM call record per item)
    └── phaseC/              Phase C outputs (per-ticker, module-based dirs)
        ├── market_data/     {TICKER}_{date}.json + {TICKER}_history_1y_{date}.json
        ├── screener_in/     {company_slug}_{hash}.json
        ├── peer_comparison/ {TICKER}_peers_{date}.json
        ├── analyst_estimates/ {TICKER}_analyst_estimates_{date}.json
        ├── exchange_filings/  {TICKER}_announcements_{date}.json
        │                      {TICKER}_filing_docs_{date}.json
        └── corporate_actions/ {TICKER}_corporate_actions_{date}.json
```

---

---

# LLM Layer

---

## llm/llm_client.py

Central factory for creating LangChain LLM instances used across all phases.

**Key function**
- `make_llm(provider, model, temperature, base_url)` → LangChain chat model

**Supported providers:**

| Provider | Env var | Default model | Notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY_S_M_R` | `gpt-5-nano` (or `OPENAI_MODEL` env var) | Default provider |
| `lmstudio` | `LMSTUDIO_API_KEY` | `qwen/qwen2.5-coder-14b` | Local model via LM Studio |

**Usage**
```python
from llm.llm_client import make_llm
llm = make_llm(provider="openai", temperature=0.05)
```

---

---

# Phase A — Broad Market Discovery

---

## india_macro.py

**Why it matters for long-term analysis:**
No stock exists in isolation. Market-wide valuation context (Nifty PE) tells you whether the market itself is expensive or cheap — entering at a Nifty PE of 12 vs 28 dramatically affects long-term returns. Interest rates (RBI repo rate) affect cost of capital for companies and PE multiples for valuations. Inflation and GDP growth drive earnings expectations. Gold and crude oil prices affect input costs for many sectors. USD/INR affects export-oriented companies and multinationals.

**What it does:** Fetches a macro snapshot combining four sources:
1. **NSE allIndices API** → PE, PB, dividend yield and price for 9 major indices
2. **yfinance (market rates)** → USD/INR, US 10-Year yield, India VIX, Nifty, Sensex
3. **yfinance (commodities)** → Gold, Silver, Crude WTI & Brent, Natural Gas, Copper, Aluminium, Iron Ore, Coal
4. **World Bank API** → India CPI inflation and GDP growth (last 3 annual data points)
5. **RBI KeyRates page** → current repo rate (best-effort scrape)

**Key functions**
- `fetch_macro_snapshot()` → combined dict
- `fetch_commodity_prices()` → commodities dict only
- `save_macro_snapshot()` → saves `india_macro_{date}.json`, returns file path

**Commodity tickers and their sector relevance:**

| Key | Ticker | Unit | Sectors it affects |
|---|---|---|---|
| `gold_usd` | `GC=F` | USD/oz | Jewellery cos, inflation hedge |
| `silver_usd` | `SI=F` | USD/oz | EV sector, industrial metals |
| `crude_wti_usd` | `CL=F` | USD/barrel | Oil & Gas, paints, tyres |
| `crude_brent_usd` | `BZ=F` | USD/barrel | India's actual import benchmark |
| `natural_gas_usd` | `NG=F` | USD/MMBtu | GAIL, Petronet LNG, IGL, Gujarat Gas |
| `copper_usd` | `HG=F` | USD/lb | Hindalco, Vedanta, cable/wire cos |
| `aluminium_usd` | `ALI=F` | USD/MT | Hindalco, NALCO, Vedanta |
| `iron_ore_usd` | `TIO=F` | USD/MT | Tata Steel, JSW Steel, SAIL |
| `coal_usd` | `MTF=F` | USD/MT | Coal India, NTPC, Adani Power |

**Output**
```json
{
  "fetched_at": "2026-05-02T15:30:00+05:30",
  "nse_indices": [
    {
      "name": "NIFTY 50", "last": 23997.55,
      "pe": 20.94, "pb": 3.29, "dividend_yield": 1.3,
      "year_high": 26277.35, "year_low": 21964.6
    }
  ],
  "market_rates": {
    "usd_inr":      { "symbol": "INR=X",     "value": 94.88, "unit": "INR per USD" },
    "us_10y_yield": { "symbol": "^TNX",      "value": 4.38,  "unit": "%" },
    "vix_india":    { "symbol": "^INDIAVIX", "value": 18.46, "unit": "index" },
    "nifty_50":     { "symbol": "^NSEI",     "value": 23997, "unit": "index" },
    "sensex":       { "symbol": "^BSESN",    "value": 76913, "unit": "index" }
  },
  "commodity_prices": {
    "gold_usd":        { "symbol": "GC=F", "value": 3280.0, "unit": "USD/oz" },
    "crude_brent_usd": { "symbol": "BZ=F", "value": 65.2,   "unit": "USD/barrel" }
  },
  "india_macro": {
    "india_cpi_inflation_pct": [{ "year": "2024", "value": 4.95 }],
    "india_gdp_growth_pct":    [{ "year": "2024", "value": 6.49 }]
  },
  "rbi_repo_rate": "6.50%"
}
```

---

## us_macro.py

**Why it matters for long-term analysis:**
Indian markets do not trade in isolation from global macro. When the US Fed raises rates, foreign capital flows out of emerging markets (including India) — FII selling typically follows. US inflation (CPI) drives Fed decisions which drive US Treasury yields which drive USD strength which drives USD/INR. The yield curve (10Y–2Y spread) is the most reliable US recession predictor — inverted curve = US recession risk = risk-off globally.

**What it does:** Fetches key US macro series from FRED (Federal Reserve Economic Data). Free API, no cost.

**Requires:** `FRED_API_KEY` environment variable.

**Series fetched:**

| Series | FRED ID | Why it matters |
|---|---|---|
| Fed Funds Rate | `DFF` | The most important rate in the world |
| 10-Year Treasury | `DGS10` | Global risk-free benchmark |
| 2-Year Treasury | `DGS2` | More reactive to near-term Fed policy |
| Yield Curve (10Y–2Y) | `T10Y2Y` | Negative = inverted = recession signal |
| US CPI | `CPIAUCSL` | Monthly inflation measure |
| USD/INR | `DEXINUS` | Direct FX impact (note: FRED stopped updating after 2019 — use india_macro.py for live rate) |

**Key functions**
- `fetch_fred_series(series_id, count)` → list of `{date, value}` dicts or None
- `save_us_macro(count)` → saves `us_macro_{date}.json`, returns path

---

## fii_dii.py

**What it does:** Fetches the most recent trading day's FII/DII buy/sell/net values in crores from NSE.

- **FII/FPI**: Foreign funds — hedge funds, sovereign wealth funds, pension funds from outside India. Sustained FII selling = market under pressure.
- **DII**: Indian institutional investors — mutual funds, LIC, insurance companies. Often act as counterbalance, buying when FIIs sell.
- Values are in **crores (₹)** — 1 crore = 10 million rupees.

**Key functions**
- `fetch_fii_dii()` → dict
- `save_fii_dii()` → saves `fii_dii_{date}.json`, returns file path

**Output**
```json
{
  "date": "30-Apr-2026",
  "fii": { "buy": 15049.55, "sell": 23097.41, "net": -8047.86 },
  "dii": { "buy": 18252.89, "sell": 14765.79, "net": 3487.10 }
}
```

> `net` negative = net sellers (bearish). In this example, FIIs sold ₹8,047 crore net while DIIs absorbed ₹3,487 crore net.

---

## bulk_deals.py

**What it does:** Fetches today's bulk and block deals from NSE's public CSV archives.

- **Bulk deal**: Any transaction where a single client buys or sells **≥0.5% of the company's total shares** in a single day.
- **Block deal**: A large pre-negotiated trade (minimum ₹10 crore) executed during a special 35-minute window before market open.

**Key functions**
- `fetch_bulk_deals()` → list
- `fetch_block_deals()` → list
- `fetch_all_deals()` → `{bulk_deals: [...], block_deals: [...]}`
- `fetch_deals_for_symbol(ticker)` → filtered to one stock
- `save_bulk_deals()` → saves `bulk_block_deals_{date}.json`, returns file path

**Output**
```json
{
  "bulk_deals": [
    {
      "date": "30-APR-2026", "symbol": "RELIANCE",
      "scrip_name": "Reliance Industries Ltd",
      "client": "NORTH STAR OPPORTUNITIES FUND VCC",
      "buy_sell": "BUY", "quantity": "101868",
      "trade_price": "1436.50", "remarks": "-"
    }
  ],
  "block_deals": []
}
```

---

## fno_data.py

**What it does:** Fetches the full F&O option chain for a stock or index from NSE, and derives sentiment metrics: PCR, max pain, top OI strikes, and ATM implied volatility.

- **PCR (Put-Call Ratio)**: Total PE OI ÷ Total CE OI. Above 1.2 = bearish bias. Below 0.8 = bullish bias.
- **Max Pain**: Strike where the maximum number of options expire worthless. Stocks gravitate here near expiry.
- **ATM IV**: How much volatility the market expects. Spikes before earnings.

**Phase A use:** NIFTY and BANKNIFTY (index-level sentiment)
**Phase C use:** Per-ticker F&O for F&O-eligible stocks (~200 stocks)

**Supported symbols:** NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, and ~200 F&O-eligible stocks.

> **Live only** — empty outside market hours (Mon–Fri 9:15 AM – 3:30 PM IST) and on holidays.

**Key functions**
- `fetch_fno_snapshot(ticker)` → chain + derived metrics
- `save_fno_snapshot(ticker)` → saves `{TICKER}_fno_{date}.json`, returns file path

**Output**
```json
{
  "ticker": "NIFTY",
  "underlying_value": 24500.0,
  "timestamp": "05-May-2026 10:30:00",
  "pcr": 0.85,
  "max_pain": 24000,
  "atm_iv": { "strike": 24500, "expiry": "08-May-2026", "ce_iv": 12.5, "pe_iv": 13.2 },
  "top_oi_strikes": {
    "top_ce_oi": [{ "strike": 25000, "oi": 1234567, "expiry": "08-May-2026" }],
    "top_pe_oi": [{ "strike": 24000, "oi": 1100000, "expiry": "08-May-2026" }]
  },
  "option_chain": [...]
}
```

---

## moneycontrol.py

**What it does:** Scrapes articles from Moneycontrol news categories.

**Key functions**
- `save_category(category_name, today_only, max_pages)` → saves JSON, returns file path

**Available categories:** `markets`, `stocks`, `earnings`, `economy`, `companies`, `india`, `mutual_funds`, `commodities`, `ipo`

| Parameter | Default | Behaviour |
|---|---|---|
| `today_only` | `True` | If True, only today's articles (date-verified). If False, no date filter |
| `max_pages` | `5` | Max listing pages to scan |

**Output**
```json
{
  "category": "stocks",
  "total": 14,
  "articles": [
    {
      "url": "https://...", "title": "Article headline",
      "author": "Reporter Name",
      "published": "2026-05-02T08:30:00+05:30",
      "body": "Full article body text..."
    }
  ]
}
```

---

## economic_times.py

Same pattern as Moneycontrol — scrapes articles from ET news categories.

**Available categories:** `stocks_news`, `expert_view`, `stocks_recos`, `commodities`

**Key functions:** `save_category(category_name, today_only, max_pages)` → saves JSON, returns file path

Output structure identical to Moneycontrol.

---

## rss.py

**What it does:** Fetches RSS feeds — headlines and summaries. Feed list in `config/rss_feeds.py` (11 feeds: Livemint, Hindu BusinessLine, NDTV Profit, ET Markets, Moneycontrol, Yahoo Finance, Investing.com).

**Key functions**
- `fetch_feed(url)` → list of articles
- `save_feed(feed_name, url)` → saves one feed, returns file path
- `save_all_feeds()` → saves all feeds in config, returns list of paths

> Full article bodies are not in RSS output. Use `generic.py` or `browser_scraper.py` on individual article URLs for full text.

---

## newsdata_io.py

**What it does:** Fetches news via the NewsData.io API. Returns title, description, and keywords.

**Limit:** 200 credits/day on free tier.

**Key functions**
- `fetch_news(query, country, language, limit)` → list
- `save_news(query)` → saves JSON, returns file path

---

## mediastack.py

**What it does:** Fetches news via the Mediastack API.

**Limit:** 500 requests/month — use sparingly.

Same input/output structure as `newsdata_io.py`.

---

## gmail.py

**What it does:** Connects to Gmail via IMAP and fetches recent emails from a specific sender domain or subject keyword. Strips HTML, returns plain text body.

**Requires:** `GMAIL_EMAIL` and `GMAIL_APP_PASSWORD` environment variables.

**Key functions**
- `fetch_newsletters(from_domain, subject_keyword, limit)` → list
- `save_newsletters(from_domain, subject_keyword, limit)` → saves JSON, returns file path

**Output**
```json
{
  "newsletters": [
    {
      "subject": "Market Wrap | May 2, 2026",
      "sender": "Hindu BusinessLine <news@busline.hindugroup.org>",
      "date": "Fri, 02 May 2026 07:00:00 +0530",
      "body": "Full email body as plain text..."
    }
  ]
}
```

---

## yt_transcript.py

**What it does:** Two capabilities in one module:
1. **Channel search** — uses the YouTube Data API to find recent videos from configured channels (excludes Shorts via `videoDuration=medium/long`)
2. **Transcript download** — fetches and saves the transcript for any known video URL

**Requires:** `YOUTUBE_API_KEY` environment variable. Channel list in `config/youtube_channels.py`.

**Optional proxy:** Set `YOUTUBE_PROXY` in `.env` (e.g. `http://user:pass@host:port`) to route transcript requests through a proxy — useful when your IP is temporarily rate-limited by YouTube.

**Key functions**
- `save_transcript(video_url)` → download transcript for a single URL, returns file path
- `save_channel(channel, days=2)` → search + save all new videos from one channel
- `save_all_channels(days=2)` → search + save across all enabled channels

**Duration buckets:** `medium` (4–20 min, news clips/analysis) and `long` (20+ min, full shows). Shorts (< 4 min) are excluded automatically by the YouTube API.

**Output (one file per video)**
```json
{
  "video_url":    "https://www.youtube.com/watch?v=xxx",
  "video_id":     "xxx",
  "extracted_at": "2026-05-02T15:30:00+05:30",
  "transcript":   "Full transcript text as a single string..."
}
```

---

## generic.py

**What it does:** Extracts article text from any publicly accessible website using `trafilatura`. Works for blogs, Finshots, Wikipedia, open news sites. Does not work on JS-heavy or paywalled sites.

**Key functions**
- `extract_article(url)` → dict
- `save_article(url)` → saves JSON, returns file path

---

## browser_scraper.py

**What it does:** Uses Playwright (headless Chromium) to render JavaScript-heavy pages before extracting text. Use for sites that require JS to load content (e.g. Tickertape, Trendlyne). Slower than `generic.py`.

**Key functions:** `extract_page(url)`, `save_page(url)`

---

---

# Phase B — Candidate Selection

Runs in three sequential steps (B1 → B2 → B3), orchestrated by `run_phase_b.py`.

---

## B1 — market_regime.py

**What it does:** Reads the latest Phase A macro outputs and computes a structured market regime using rule-based thresholds — no LLM involved.

**Inputs (latest file from each dir):**
- `output/phaseA/macro_data/india_macro_*.json`
- `output/phaseA/macro_data/us_macro_*.json`
- `output/phaseA/fii_dii/fii_dii_*.json`
- `output/phaseA/fno_data/NIFTY_fno_*.json` (optional — empty outside market hours)

**Signal thresholds:**

| Signal | Metric | Thresholds |
|---|---|---|
| breadth | NIFTY 500 A/D ratio | < 0.6 bearish, 0.6–1.4 neutral, > 1.4 bullish |
| vix | India VIX | > 25 fear, 18–25 elevated, 13–18 moderate, < 13 calm |
| fii | FII net ₹cr | < -5000 heavy_selling, -5000 to -1000 selling, -1000 to 500 flat, > 500 buying |
| crude | Brent USD/bbl | > 100 expensive, 75–100 moderate, < 75 cheap |
| usd_inr | USD/INR | > 87 weak_rupee, 83–87 moderate, < 83 strong_rupee |

**Market posture:** `bullish` / `neutral` / `bearish` — derived by majority-voting across signals.

**Sector recommendations** are derived from posture + crude + FII signals (e.g. cheap crude → tailwind for Aviation, Paints; heavy FII selling → avoid mid/smallcap).

**Key functions**
- `compute_regime()` → regime dict
- `save_regime()` → saves `market_regime_{date}.json`, returns file path

**Output**
```json
{
  "generated_at": "2026-05-05T09:00:00+05:30",
  "market_posture": "neutral",
  "signals": {
    "breadth": "neutral", "vix": "moderate",
    "fii": "selling", "crude": "cheap", "usd_inr": "moderate"
  },
  "raw_data": {
    "ad_ratio": 1.1, "vix_india": 15.2, "fii_net_cr": -2400,
    "crude_brent_usd": 64.5, "usd_inr": 84.1
  },
  "sectors": {
    "favored": ["Aviation", "Paints", "Tyres", "OMCs"],
    "avoid":   ["PSU Banks", "Mid Cap", "Small Cap"]
  }
}
```

---

## B2 — news_signal_extractor.py

**What it does:** Walks all Phase A text outputs, calls the LLM once per article to extract structured company-specific events, then resolves company names to NSE tickers.

**LLM approach:** Uses LangChain structured output — `pipeline = prompt | llm.with_structured_output(NewsSignals)` — built once before the loop, not per item. Pydantic enforces the output schema; no manual JSON parsing.

**Content filtering:** Items with body/summary < 40 chars are skipped (title-only articles add noise, no signal). Items with total text < 80 chars are also skipped.

**Source weights** (how credible each source's signals are during scoring):

| Source | Weight |
|---|---|
| moneycontrol | 3.0 |
| economic_times | 3.0 |
| gmail | 2.0 |
| rss | 2.0 |
| newsdata_io | 1.5 |
| mediastack | 1.5 |
| youtube | 1.0 |

**LLM output schema (per signal):**

| Field | Type | Source |
|---|---|---|
| `ticker_hint` | str | LLM |
| `event_type` | enum | LLM |
| `sentiment` | positive/negative/neutral | LLM |
| `severity` | high/medium/low | LLM |
| `key_claim` | str | LLM |
| `ticker` | NSE symbol or null | resolved post-LLM |
| `company` | full name | resolved post-LLM |

**Event types:** `earnings_beat`, `earnings_miss`, `earnings_inline`, `guidance_raise`, `guidance_cut`, `dividend`, `buyback`, `management_change`, `regulatory_action`, `merger_acquisition`, `analyst_upgrade`, `analyst_downgrade`, `block_deal`, `macro_impact`, `other`

**LLM call logging:** Every call (prompt input + signal output + any error) is appended to `output/logs/llm_calls/signals_{date}.jsonl` as one JSON record per line.

**Key functions**
- `collect_all_items()` → list of all filtered text items from Phase A
- `extract_signals_for_item(item, pipeline)` → list of resolved signal dicts
- `extract_all_signals(llm, verbose)` → full result dict
- `save_signals(result)` → saves `signals_{date}.json`, returns file path

**Output structure**
```json
{
  "generated_at": "...", "llm_model": "gpt-5-nano",
  "stats": {
    "total_items_scanned": 864, "items_with_signals": 210,
    "total_signals": 487, "items_failed_llm": 2
  },
  "items": [
    {
      "source": "moneycontrol", "title": "Infosys beats Q4 estimates...",
      "signal_count": 2,
      "signals": [
        {
          "source": "moneycontrol", "source_weight": 3.0,
          "ticker_hint": "Infosys", "ticker": "INFY.NS", "company": "Infosys Limited",
          "event_type": "earnings_beat", "sentiment": "positive", "severity": "high",
          "key_claim": "Q4 net profit up 22% YoY, beats Street estimate by 8%"
        }
      ]
    }
  ]
}
```

---

## B3 — candidate_scorer.py

**What it does:** Combines signals from B2 + regime from B1 + bulk/block deals to produce a ranked candidate list for Phase C. All scoring is deterministic — no LLM.

**Scoring formula per signal:**
```
signal_score = source_weight × severity_weight × sentiment_modifier
```

| Component | Values |
|---|---|
| severity_weight | high=3.0, medium=2.0, low=1.0 |
| sentiment_modifier | positive=+1.0, negative=-1.0, neutral=+0.4 |
| bulk buy | +5.0 flat bonus |
| bulk sell | -5.0 flat penalty |
| sector in regime favored | +4.0 bonus |
| sector in regime avoid | -3.0 penalty |

**Filtering:** Candidates with `|final_score| < 3.0` are dropped. Maximum 15 candidates returned.

**Key functions**
- `score_candidates(signals_data, regime, bulk_signals)` → list of candidate dicts
- `save_candidates(candidates, regime, signals_file, bulk_file)` → saves `candidates_{date}.json`

**Output (per candidate)**
```json
{
  "rank": 1, "ticker": "INFY.NS", "company": "Infosys Limited",
  "final_score": 18.5, "signal_count": 4, "source_count": 2,
  "event_types": ["earnings_beat", "analyst_upgrade"],
  "sector": "Technology",
  "regime_alignment": "neutral",
  "key_signals": [
    { "key_claim": "Q4 net profit up 22% YoY, beats estimate by 8%",
      "sentiment": "positive", "severity": "high", "source": "moneycontrol" }
  ]
}
```

---

## utils/ticker_extractor.py

**Why it matters:**
Phase B's LLM returns company names as written in articles ("Infosys", "IndiGo", "HDFC Bank"). This module maps those names to NSE tickers. Located in `utils/` because it is a shared utility used internally by `news_signal_extractor.py`, not a pipeline step.

**Two-pass resolution:**
1. **Aliases dict** — short/colloquial names (SBI → SBIN.NS, TCS → TCS.NS, IndiGo → INDIGO.NS ...)
2. **Fuzzy lookup** — against the full NSE list, threshold=82 to avoid false positives (e.g. "indigo" → "Indo-National" at lower thresholds)

**Key functions**
- `extract_tickers(text)` → list of `{company, ticker}` dicts
- `lookup_ticker(company_name, threshold)` → fuzzy search, returns best match or None

**Dependency:** `utils/nse_symbols.py` — downloads NSE equity list on first use, caches locally at `utils/nse_equity_cache.json`, auto-refreshes every 7 days.

**Output — extract_tickers**
```json
[
  { "company": "Reliance Industries Limited", "ticker": "RELIANCE.NS" },
  { "company": "Tata Consultancy Services Limited", "ticker": "TCS.NS" }
]
```

**Output — lookup_ticker**
```json
{ "ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Industries Limited", "score": 100.0 }
```

---

---

# Phase C — Company Deep Dive

`run_phase_c.py` orchestrates the full Phase C run. For each of the 25 candidates from Phase B, it calls 8 modules in sequence:

1. **market_data** — always first (provides sector for re-scoring)
2. **price_history** — 1-year OHLCV
3. **screener_in** — 10-year fundamentals (skip with `--skip-screener`)
4. **peer_comparison** — sector peers
5. **analyst_estimates** — consensus and price targets
6. **exchange_filings** — material NSE announcements
7. **filing_docs** — earnings transcripts + presentations
8. **corporate_actions** — dividends, splits, buybacks

After all tickers are processed, `run_phase_c.py` applies the regime sector bonus (+4 favoured / −3 avoided) using the sector fetched in step 1, re-ranks candidates, and saves `candidates_{date}_final.json` alongside the original Phase B candidates file.

---

## screener_in.py

**Why it matters for long-term analysis:**
This is the core module for fundamental analysis of Indian stocks. It gives you 10 years of P&L, balance sheet, cash flow, and ratios in one place — the same data a professional equity analyst looks at to assess business quality, growth trajectory, debt levels, and capital efficiency. Shareholding tables show who owns the stock and how that's changed.

**What it does:** Scrapes company financials from screener.in — key ratios, pros/cons, quarterly results, annual P&L, balance sheet, cash flow, financial ratios, CAGR growth metrics, and quarterly/yearly shareholding patterns. Optionally downloads and extracts text from quarterly filing PDFs.

**Key functions**
- `extract_company(url)` → dict
- `save_company(url)` → saves JSON, returns file path

| Parameter | Default | Behaviour |
|---|---|---|
| `fetch_pdfs` | `False` | If True, downloads and extracts text from quarterly filing PDFs |
| `pdf_quarters` | `None` | How many most-recent quarters to fetch PDFs for. `None` = all available |

**Input**
```
url: str   screener.in company URL
           https://www.screener.in/company/RELIANCE/consolidated/
```

**Output (abbreviated)**
```json
{
  "company_name": "Reliance Industries Ltd",
  "key_ratios": { "Market Cap": "19,43,263 Cr", "P/E": "22.5", "ROE": "8.69%" },
  "pros": ["Strong cash flow generation"],
  "cons": ["High debt levels"],
  "quarterly_results": [...],
  "profit_loss": [...],
  "balance_sheet": [...],
  "cash_flow": [...],
  "ratios": [...],
  "growth_metrics": { "Sales Growth": { "TTM": "8%", "10Yrs": "12%" } },
  "shareholding_quarterly": [{ "metric": "Promoters", "Mar 2024": "50.30%", "Jun 2024": "50.30%" }],
  "shareholding_yearly": [{ "metric": "FIIs", "Mar 2023": "23.50%", "Mar 2024": "24.10%" }]
}
```

> **Shareholding trend:** The quarterly/yearly tables contain the full multi-quarter history. Key signals: promoter stake increasing = confidence; promoter pledging = red flag; consistent FII/DII accumulation = institutional validation.

---

## peer_comparison.py

**Why it matters:** A stock's valuation only makes sense relative to sector peers. If Reliance trades at PE 24x but the rest of oil & gas trades at PE 8–13x, that premium needs justification.

**What it does:** Builds a side-by-side comparison vs all constituents of the stock's NSE sectoral index. Uses yfinance.

**Key functions**
- `fetch_peer_comparison(ticker, max_peers)` → dict
- `save_peer_comparison(ticker, max_peers)` → saves JSON, returns file path

**Input:** `ticker: str` — "RELIANCE" or "RELIANCE.NS"

---

## analyst_estimates.py

**Why it matters:** Forward PE (current price ÷ next-year EPS estimate) tells you what you're paying for growth. EPS revision trend is one of the most reliable signals — when analysts consistently cut estimates, earnings disappointments usually follow.

**What it does:** Fetches analyst consensus data from Yahoo Finance — price targets, EPS/revenue estimates, earnings history, recommendations, and EPS trend/revisions.

**Key functions**
- `fetch_analyst_estimates(ticker)` → dict
- `save_analyst_estimates(ticker)` → saves JSON, returns file path

**Input:** `ticker: str` — "RELIANCE" or "RELIANCE.NS"

---

## exchange_filings.py

**Why it matters:** NSE filings are the official record of everything a company tells the exchange — results, acquisitions, management changes, credit ratings. These are the events that change the investment thesis.

**Key functions**
- `fetch_announcements(ticker, limit, material_only)` → list of dicts
- `save_announcements(ticker, limit, material_only)` → saves JSON, returns file path

| Parameter | Default | Behaviour |
|---|---|---|
| `limit` | `50` | Max most-recent announcements |
| `material_only` | `False` | If True, filters to investment-relevant types only |

---

## filing_docs.py

**Why it matters:** Earnings call transcripts are where management explains results, discusses strategy, and gives forward guidance. Reading 4 quarters of transcripts (1 year) tells you how management thinks about competition, margins, capex, and risk.

**Indian reporting schedule:** Q1 Apr–Jun (published ~Jul), Q2 Jul–Sep (~Oct), Q3 Oct–Dec (~Jan), Q4 Jan–Mar (~Apr/May). `last_n=4` = last 1 year of earnings calls.

**Key functions**
- `fetch_filing_docs(ticker, transcripts, presentations)` → combined dict
- `save_filing_docs(ticker, transcripts, presentations)` → saves JSON, returns file path

| Parameter | Default | Behaviour |
|---|---|---|
| `transcripts` | `4` | Most-recent earnings call transcripts (4 = 1 year) |
| `presentations` | `2` | Most-recent investor presentations |

---

## corporate_actions.py

**Why it matters:** Dividend history reveals capital allocation philosophy. Bonus issues and splits are positive signals. Buybacks indicate management believes the stock is undervalued.

**What it does:** Collects corporate events from NSE API (last ~20 events) and yfinance (longer history — 30+ years of dividends and splits).

**Key functions**
- `fetch_corporate_actions(ticker)` → combined dict
- `save_corporate_actions(ticker)` → saves JSON, returns file path

---

## market_data.py

**What it does:** Current price snapshot — price, daily change, 52-week range, 1M/3M/1Y returns, volume, market cap, sector.

**Key functions**
- `fetch_stock(ticker)` → dict
- `save_stock(ticker)` → saves JSON, returns file path

**Output**
```json
{
  "ticker": "RELIANCE.NS",
  "name": "Reliance Industries Limited",
  "price": 1436.0,
  "day_change_pct": 0.74,
  "52w_high": 1611.8,
  "52w_low": 1290.0,
  "return_1m": 6.47,
  "return_3m": 3.64,
  "return_1y": 0.36,
  "volume": 8234100,
  "market_cap": 19432629862400,
  "sector": "Energy"
}
```

---

## price_history.py

**What it does:** Historical OHLCV price data. Supports standard periods or custom date range.

**Key functions**
- `fetch_history(ticker, period, start, end)` → dict
- `save_history(ticker, period, start, end)` → saves JSON, returns file path

| Parameter | Default | Behaviour |
|---|---|---|
| `period` | `"1y"` | `"1mo"` / `"3mo"` / `"6mo"` / `"1y"` / `"2y"` / `"5y"` / `"max"` |
| `start` | `None` | `"YYYY-MM-DD"` — overrides period when both start and end given |
| `end` | `None` | `"YYYY-MM-DD"` |

---

## sec_filings.py

**Why it matters:** For US-listed companies, SEC filings are the gold standard. 10-K (annual) and 10-Q (quarterly) contain XBRL-structured financial data going back 5+ years. 8-K contains material event disclosures. No API key required.

**Key functions**
- `get_cik(ticker)` → `(cik, company_name)`
- `fetch_key_financials(cik)` → dict of metrics with annual and quarterly series
- `fetch_recent_filings(cik)` → dict grouped by form type
- `save_sec_data(ticker)` → saves JSON, returns file path

| Parameter | Default | Behaviour |
|---|---|---|
| `fetch_financials` | `True` | Pull XBRL key metrics |
| `fetch_filings` | `True` | Pull recent 10-K / 10-Q / 8-K metadata |
| `fetch_texts` | `False` | Download and extract text from most recent filing |
| `text_form_types` | `["8-K"]` | Which form types to download text for |

**Input:** `ticker: str` — US ticker ("AAPL", "MSFT", "GOOGL")
