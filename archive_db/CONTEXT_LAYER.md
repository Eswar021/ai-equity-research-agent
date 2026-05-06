# Context Extraction Layer

Collects raw context from multiple sources and saves structured JSON files.
Every module is independently runnable via `python <file>.py`.

The goal of this layer is simple: **extract raw data from sources and save it**.
No aggregation, no calculations, no analysis — that happens in later layers.

---

## How Modules Are Organised Here

Modules are grouped by purpose, not just by folder:

| Group | Purpose |
|---|---|
| **Indian Company Fundamentals** | Core financials, filings, management commentary for Indian stocks |
| **US Company Fundamentals** | Core financials and filings for US-listed stocks |
| **Market & Price Data** | Prices, history, macro indicators |
| **Institutional Activity** | FII/DII flows, bulk deals, F&O — mostly short-term signals |
| **News & Information** | News articles, newsletters, transcripts, RSS |
| **Utilities** | Ticker extraction, symbol resolution |
| **Persistent History (db/)** | Accumulated daily data for modules that only return today's snapshot |

---

## Data Freshness — What Can Be Re-fetched vs What Requires Daily Runs

Some sources always have full history available. Others only return today's data — if you don't run them daily, that day's data is gone.

| Module | History available? | Notes |
|---|---|---|
| screener_in | ✅ Always | Full 10-year financials always in page |
| price_history | ✅ Always | yfinance has years of OHLCV |
| corporate_actions | ✅ Always | Full NSE action history in API |
| exchange_filings | ✅ Always | All NSE announcements always fetchable |
| filing_docs (transcripts) | ✅ Always | All past transcript PDFs stay on NSE servers |
| sec_filings | ✅ Always | SEC EDGAR keeps everything |
| macro_data | ✅ Always | World Bank has decades; NSE PE/PB is live |
| **fii_dii** | ❌ Today only | NSE API returns most recent trading day only |
| **bulk_deals** | ❌ Today only | NSE CSV archive only has today's data |
| **fno_data** | ❌ Live only | Option chain is a real-time snapshot |

> For `fii_dii`, `bulk_deals`, and `macro_data` (NSE index PE/PB), run `db/sync.py` after each daily collection to append to the persistent history files in `db/`. If you miss a day for FII/DII or bulk deals, that day is unrecoverable from NSE's public API.

---

## Folder Structure

```
context_ext_layer/
├── web_scrapers/
│   ├── screener_in.py          Company financials + filings (Indian stocks)
│   ├── moneycontrol.py         News by category
│   ├── economic_times.py       News by category
│   ├── generic.py              Any open website (article text)
│   └── browser_scraper.py      JS-rendered websites (Playwright)
├── exchange_filings/
│   ├── exchange_filings.py     NSE corporate announcements
│   └── filing_docs.py          Concall transcripts + investor presentations
├── corporate_actions/
│   └── corporate_actions.py    Dividends, splits, bonuses, rights (NSE + yfinance)
├── sec_filings/
│   └── sec_filings.py          US company SEC EDGAR filings
├── market_data/
│   ├── market_data.py          Current price snapshot
│   └── price_history.py        Historical OHLCV data
├── macro_data/
│   └── macro_data.py           NSE index PE/PB, commodities, FX, rates
├── fii_dii/
│   └── fii_dii.py              FII/DII daily institutional flows
├── bulk_deals/
│   └── bulk_deals.py           Bulk & block deals (today's NSE CSV)
├── fno_data/
│   └── fno_data.py             F&O option chain + PCR, max pain, OI
├── ticker_extractor/
│   ├── nse_symbols.py          NSE symbol list manager (2360 stocks)
│   └── ticker_extractor.py     Extract tickers from text
├── youtube/
│   └── transcript.py           YouTube video transcripts
├── rss/
│   └── rss_feed.py             RSS feed headlines + summaries
├── news_apis/
│   ├── newsdata_io.py          NewsData.io API
│   └── mediastack.py           Mediastack API
└── gmail/
    └── newsletter.py           Newsletters via Gmail IMAP
```

---

---

# Indian Company Fundamentals

---

## web_scrapers / screener_in.py

**Why it matters for long-term analysis:**
This is the core module for fundamental analysis of Indian stocks. It gives you 10 years of P&L, balance sheet, cash flow, and ratios in one place — the same data a professional equity analyst looks at to assess business quality, growth trajectory, debt levels, and capital efficiency. The shareholding tables show who owns the stock and how that's changed — consistently rising promoter stake is a quality signal; pledged promoter shares are a red flag.

**What it does:** Scrapes company financials from screener.in — key ratios, pros/cons, quarterly results, annual P&L, balance sheet, cash flow, financial ratios, CAGR growth metrics, and quarterly/yearly shareholding patterns. The Raw PDF row in quarterly results contains screener source URLs; passing `fetch_pdfs=True` follows the redirect to BSE/NSE, downloads the actual filing PDF, and extracts its full text.

> The quarterly result PDFs are the 3–5 page financial statements filed by the company each quarter — not the full annual report. For the full qualitative annual report content (MD&A, strategy, risks), use `filing_docs.py` for concall transcripts and investor presentations.

**Key functions**
- `extract_company(url)` → dict
- `save_company(url)` → saves JSON, returns file path

**Parameters**
| Parameter | Default | Behaviour |
|---|---|---|
| `fetch_pdfs` | `False` | If True, downloads and extracts text from quarterly filing PDFs |
| `pdf_quarters` | `None` | How many most-recent quarters to fetch PDFs for. `None` = all available |

**Input**
```
url: str   screener.in company URL
           https://www.screener.in/company/RELIANCE/consolidated/
           https://www.screener.in/company/HDFCBANK/
```

**Output**
```json
{
  "company_name": "Reliance Industries Ltd",
  "description": "...",
  "key_ratios": { "Market Cap": "19,43,263 Cr", "P/E": "22.5", "ROE": "8.69%" },
  "pros": ["Strong cash flow generation"],
  "cons": ["High debt levels"],
  "quarterly_results": [
    { "metric": "Sales", "Mar 2024": "2,36,228", "Jun 2024": "..." },
    { "metric": "Raw PDF", "Mar 2024": "https://www.screener.in/company/source/quarter/..." }
  ],
  "quarterly_pdfs": [
    {
      "quarter": "Mar 2026",
      "source_url": "https://www.screener.in/company/source/quarter/...",
      "pdf_url": "https://www.bseindia.com/xml-data/corpfiling/...",
      "text": "Full extracted text from the BSE filing PDF..."
    }
  ],
  "profit_loss": [ { "metric": "Sales", "Mar 2023": "..." } ],
  "balance_sheet": [ { "metric": "Equity Capital", "Mar 2023": "..." } ],
  "cash_flow": [ { "metric": "Cash from Operations", "Mar 2023": "..." } ],
  "ratios": [ { "metric": "ROE %", "Mar 2023": "..." } ],
  "growth_metrics": { "Sales Growth": { "TTM": "8%", "10Yrs": "12%" } },
  "shareholding_quarterly": [
    { "metric": "Promoters", "Mar 2024": "50.30%", "Jun 2024": "50.30%" }
  ],
  "shareholding_yearly": [
    { "metric": "FIIs", "Mar 2023": "23.50%", "Mar 2024": "24.10%" }
  ]
}
```

> `quarterly_pdfs` is `[]` when `fetch_pdfs=False`. The Raw PDF row in `quarterly_results` always has screener source URLs regardless.
>
> **Shareholding trend**: The `shareholding_quarterly` and `shareholding_yearly` tables already contain the full multi-quarter history. No separate module is needed to track shareholding changes — the processing layer reads this table and computes trends. Key things to look for: promoter stake increasing = confidence; promoter pledging shares = red flag; consistent FII/DII accumulation = institutional validation.

---

## exchange_filings / exchange_filings.py

**Why it matters for long-term analysis:**
NSE filings are the official record of everything a company tells the stock exchange. While screener.in gives you structured financials, this gives you the event feed — when results were declared, what acquisitions were made, when management changed, credit rating upgrades/downgrades. These are the events that change the investment thesis. A sudden CEO change, a large acquisition, or a credit rating downgrade are thesis-altering events that an analyst must track.

**What it does:** Fetches the full list of NSE corporate announcements for a stock. Supports filtering to material events only (skips routine notices like trading window closures). Each announcement includes the type, subject text, and a PDF attachment URL.

**Key functions**
- `fetch_announcements(ticker, limit, material_only)` → list of dicts
- `save_announcements(ticker, limit, material_only)` → saves JSON, returns file path

**Parameters**
| Parameter | Default | Behaviour |
|---|---|---|
| `limit` | `50` | Max number of most-recent announcements to return |
| `material_only` | `False` | If True, filters to investment-relevant types only (results, dividends, acquisitions, management changes, credit ratings, buybacks, etc.) |

**Input**
```
ticker: str   "RELIANCE" or "RELIANCE.NS"
```

**Output**
```json
{
  "ticker": "RELIANCE",
  "fetched_at": "2026-05-02T10:00:00+00:00",
  "total_returned": 50,
  "material_only": true,
  "announcements": [
    {
      "date": "24-Apr-2026 19:26:28",
      "type": "Outcome of Board Meeting",
      "subject": "In continuation of our letter dated April 17, 2026...",
      "attachment_url": "https://nsearchives.nseindia.com/corporate/...",
      "has_xbrl": false
    }
  ]
}
```

> `has_xbrl`: XBRL is a structured machine-readable format for financial data. Some result filings include an XBRL data file alongside the PDF. Not relevant for text-based analysis — can be ignored.
>
> One NSE event generates multiple filings in sequence: advance "Board Meeting" notice → "Outcome of Board Meeting" → "Dividend" formal disclosure → "Press Release". These are not duplicates — they are sequential stages of the same event. Each adds a layer of detail.

---

## exchange_filings / filing_docs.py

**Why it matters for long-term analysis:**
Earnings call transcripts are where management explains results, discusses strategy, answers hard analyst questions, and gives forward guidance. This is the qualitative layer that the numbers alone don't show. Reading 4 quarters of transcripts (one year) tells you how management thinks about competition, margins, capex, and risk. Investor presentations are the slide decks companies prepare at results time — they contain segment breakdowns, market share data, and growth roadmaps not always in the financials.

**What it does:** Downloads and extracts text from NSE filing attachment PDFs — specifically earnings call transcripts and investor presentations. These are publicly filed by companies with NSE after each quarterly result.

**How Indian reporting works:** Indian companies report **quarterly** (4 times per year):
- Q1: Apr–Jun results (published ~Jul)
- Q2: Jul–Sep results (published ~Oct)
- Q3: Oct–Dec results (published ~Jan)
- Q4: Jan–Mar results (published ~Apr/May)

So `last_n=4` transcripts = last 4 quarters = **last 1 year** of earnings calls. `last_n=8` = 2 years, `last_n=12` = 3 years.

**Key functions**
- `fetch_concall_transcripts(ticker, last_n)` → list of dicts (date, subject, pdf_url, text)
- `fetch_investor_presentations(ticker, last_n)` → list of dicts
- `fetch_filing_docs(ticker, transcripts, presentations)` → combined dict
- `save_filing_docs(ticker, transcripts, presentations)` → saves JSON, returns file path

**Parameters**
| Parameter | Default | Behaviour |
|---|---|---|
| `transcripts` | `4` | Number of most-recent earnings call transcripts — 4 = 1 year, 8 = 2 years |
| `presentations` | `2` | Number of most-recent investor presentations |

> Only filings whose subject explicitly says "transcript" are included — audio recordings and meeting notices (same `Analysts/Institutional Investor Meet` category) are skipped automatically.

**Input**
```
ticker: str   "RELIANCE" or "RELIANCE.NS"
```

**Output**
```json
{
  "ticker": "RELIANCE",
  "fetched_at": "2026-05-02T10:00:00+00:00",
  "transcripts": [
    {
      "date": "26-Apr-2026 23:28:02",
      "subject": "Transcript of the discussion on the Audited Financial Results...",
      "pdf_url": "https://nsearchives.nseindia.com/corporate/...",
      "text": "Full transcript text, up to 80,000 chars. Contains management commentary and analyst Q&A..."
    }
  ],
  "presentations": [
    {
      "date": "24-Apr-2026 19:44:40",
      "subject": "Reliance Industries Limited has informed the Exchange about Investor Presentation...",
      "pdf_url": "https://nsearchives.nseindia.com/corporate/...",
      "text": "Extracted slide content text..."
    }
  ]
}
```

---

## corporate_actions / corporate_actions.py

**Why it matters for long-term analysis:**
Dividend history reveals capital allocation philosophy. A company that has paid and grown dividends for 10+ years is demonstrating consistent profitability and shareholder-friendly management. Bonus issues (free shares to existing holders) and splits are positive signals. Rights issues at discount can dilute value. Buybacks indicate management believes the stock is undervalued. Together, these tell you how the company treats its shareholders over a long period.

**What it does:** Collects corporate events for a stock from two sources:
- **NSE API** (`nse_actions`): the last ~20 events of all types — dividends, bonus issues, splits, rights issues, demergers, buybacks. This is the authoritative source for Indian-specific events.
- **yfinance** (`yf_dividends`, `yf_splits`): longer historical record (30+ years of dividends, full split history). Useful because NSE API only returns ~20 most recent events total.

> NSE returns ~20 most recent events regardless of type. So if a company declared many dividends, older ones get pushed off. yfinance fills in the longer dividend and split history.

**Key functions**
- `fetch_nse_corporate_actions(ticker)` → list of events
- `fetch_yf_corporate_actions(ticker)` → `{dividends: [...], splits: [...]}`
- `fetch_corporate_actions(ticker)` → combined dict
- `save_corporate_actions(ticker)` → saves JSON, returns file path

**Input**
```
ticker: str   "RELIANCE.NS" (NSE) or "AAPL" (US, yfinance only)
```

**Output**
```json
{
  "ticker": "RELIANCE",
  "nse_actions": [
    {
      "symbol": "RELIANCE",
      "series": "EQ",
      "purpose": "Dividend - Rs 5.5 Per Share",
      "ex_date": "14-Aug-2025",
      "record_date": "14-Aug-2025",
      "bc_start": "-",
      "bc_end": "-",
      "face_value": "10",
      "company": "Reliance Industries Limited"
    }
  ],
  "yf_dividends": [
    { "date": "2025-08-14", "amount": 5.5 },
    { "date": "2024-08-19", "amount": 5.0 }
  ],
  "yf_splits": [
    { "date": "2024-10-28", "ratio": 2.0 }
  ]
}
```

> **When dividends happen:** Indian companies on an Apr–Mar fiscal year typically declare dividends at their AGM (Annual General Meeting), which clusters in **June–August** each year after Q4 results. So most dividend ex-dates fall in that window annually. Splits and bonuses are one-time decisions with no fixed timing.

---

---

# US Company Fundamentals

---

## sec_filings / sec_filings.py

**Why it matters for long-term analysis:**
For US-listed companies, SEC filings are the gold standard for fundamental data. The 10-K (annual) and 10-Q (quarterly) filings contain XBRL-structured financial data — machine-readable revenue, earnings, assets, debt, cash flow going back 5+ years. The 8-K contains material event disclosures (earnings announcements, acquisitions, management changes). No API key required — SEC EDGAR is fully public.

**What it does:** Collects SEC EDGAR data — key financial metrics from XBRL structured data, and recent filing metadata with direct document URLs. Optionally downloads and extracts text from filings. CIK lookup is cached locally and auto-refreshes every 7 days.

**Key functions**
- `get_cik(ticker)` → `(cik, company_name)`
- `fetch_key_financials(cik)` → dict of metrics with annual and quarterly series
- `fetch_recent_filings(cik)` → dict grouped by form type
- `fetch_filing_text(doc_url)` → extracted plain text, capped at 50K chars
- `save_sec_data(ticker)` → saves JSON, returns file path

**Parameters for save_sec_data**
| Parameter | Default | Behaviour |
|---|---|---|
| `fetch_financials` | `True` | Pull XBRL key metrics (revenue, EPS, assets, debt, cash flow) |
| `fetch_filings` | `True` | Pull recent 10-K / 10-Q / 8-K metadata |
| `fetch_texts` | `False` | Download and extract text from most recent filing per type |
| `text_form_types` | `["8-K"]` | Which form types to download text for |
| `limit_per_type` | `5` | How many filings to return per form type |

**Input**
```
ticker: str   US ticker — "AAPL", "MSFT", "GOOGL"
```

**Output**
```json
{
  "ticker": "AAPL",
  "cik": "0000320193",
  "company_name": "Apple Inc.",
  "key_financials": {
    "revenue":           { "annual": [...5 years], "quarterly": [...8 quarters] },
    "net_income":        { "annual": [...], "quarterly": [...] },
    "eps_basic":         { "annual": [...], "quarterly": [...] },
    "eps_diluted":       { "annual": [...], "quarterly": [...] },
    "operating_income":  { "annual": [...], "quarterly": [...] },
    "total_assets":      { "annual": [...], "quarterly": [...] },
    "total_liabilities": { "annual": [...], "quarterly": [...] },
    "stockholders_equity": { "annual": [...], "quarterly": [...] },
    "cash":              { "annual": [...], "quarterly": [...] },
    "long_term_debt":    { "annual": [...], "quarterly": [...] },
    "operating_cash_flow": { "annual": [...], "quarterly": [...] }
  },
  "recent_filings": {
    "10-K": [ { "accession_no": "...", "filing_date": "2025-10-31", "doc_url": "https://..." } ],
    "10-Q": [ { "..." } ],
    "8-K":  [ { "...", "items": "2.02" } ]
  }
}
```

> `items` in 8-K entries are SEC item codes — "2.02" = Results of Operations (earnings announcement), "8.01" = Other Events, "5.02" = Director/Officer changes.

---

---

# Market & Price Data

---

## market_data / market_data.py

**Why it matters:**
The current price snapshot establishes where the stock is today — entry price context, 52-week range position, and short-term momentum (1M/3M/1Y returns). For long-term analysis, the absolute price matters less than the valuation (P/E etc. from screener), but you need the current price to calculate things like discount to intrinsic value.

**What it does:** Fetches the current market snapshot for a ticker — price, daily change, 52-week range, 1M/3M/1Y returns, volume, market cap, sector. Works for NSE (`TICKER.NS`) and US tickers.

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
  "sector": "Energy",
  "industry": "Oil & Gas Integrated"
}
```

---

## market_data / price_history.py

**Why it matters:**
Long-term OHLCV history is how you calculate CAGR, max drawdown, volatility, and compare the stock's price performance against its business performance. A company growing earnings at 15% per year but whose stock has gone nowhere for 3 years may be accumulating value. Using `period="max"` gives you the full listing history back to IPO.

**What it does:** Fetches daily OHLCV (Open, High, Low, Close, Volume) price history. Supports standard periods or a custom date range.

**Key functions**
- `fetch_history(ticker, period, start, end)` → dict
- `save_history(ticker, period, start, end)` → saves JSON, returns file path

**Parameters**
| Parameter | Default | Behaviour |
|---|---|---|
| `period` | `"1y"` | `"1mo"` / `"3mo"` / `"6mo"` / `"1y"` / `"2y"` / `"5y"` / `"max"` |
| `start` | `None` | `"YYYY-MM-DD"` — overrides period when both start and end are given |
| `end` | `None` | `"YYYY-MM-DD"` |

**Output**
```json
{
  "ticker": "HDFCBANK.NS",
  "period": "1y",
  "total_records": 248,
  "history": [
    { "date": "2025-05-02", "open": 985.0, "high": 994.55, "low": 983.3, "close": 992.65, "volume": 16607180 }
  ]
}
```

> `period="max"` populates `first_day` with the IPO/listing day's OHLCV — the closest proxy for the original listing price.

---

## macro_data / macro_data.py

**Why it matters for long-term analysis:**
No stock exists in isolation. Market-wide valuation context (Nifty PE) tells you whether the market itself is expensive or cheap — entering at a Nifty PE of 12 vs 28 dramatically affects long-term returns. Interest rates (RBI repo rate) affect cost of capital for companies and PE multiples for valuations. Inflation and GDP growth drive earnings expectations. Gold and crude oil prices affect input costs for many sectors. USD/INR affects export-oriented companies and multinationals.

**What it does:** Fetches a macro snapshot combining four sources:
1. **NSE allIndices API** → PE, PB, dividend yield and price for 9 major indices
2. **yfinance** → USD/INR, Gold, Crude Oil WTI, US 10-Year yield, India VIX, Nifty, Sensex
3. **World Bank API** → India CPI inflation and GDP growth (last 3 annual data points)
4. **RBI KeyRates page** → current repo rate (best-effort scrape)

**Key functions**
- `fetch_macro_snapshot()` → combined dict
- `save_macro_snapshot()` → saves `macro_{date}.json`, returns file path

**Output**
```json
{
  "fetched_at": "2026-05-02T10:00:00+00:00",
  "nse_indices": [
    {
      "name": "NIFTY 50",
      "last": 24500.0,
      "change_pct": -0.5,
      "change_pct_1y": 8.2,
      "pe": 22.1,
      "pb": 3.4,
      "dividend_yield": 1.2,
      "year_high": 26277.35,
      "year_low": 21964.6
    }
  ],
  "market_rates": {
    "usd_inr":       { "symbol": "INR=X",  "value": 84.2,  "unit": "INR per USD" },
    "gold_usd":      { "symbol": "GC=F",   "value": 3280.0,"unit": "USD/oz" },
    "crude_wti_usd": { "symbol": "CL=F",   "value": 62.5,  "unit": "USD/barrel" },
    "us_10y_yield":  { "symbol": "^TNX",   "value": 4.3,   "unit": "%" },
    "vix_india":     { "symbol": "^INDIAVIX","value": 14.2, "unit": "index" }
  },
  "india_macro": {
    "india_cpi_inflation_pct": [
      { "year": "2024", "value": 4.85 },
      { "year": "2023", "value": 5.65 }
    ],
    "india_gdp_growth_pct": [
      { "year": "2024", "value": 6.4 }
    ]
  },
  "rbi_repo_rate": "6.50%"
}
```

> **Why track Nifty PE over time:** Running `save_macro_snapshot()` daily and syncing with `db/sync.py` builds a Nifty PE/PB time series. When Nifty PE is above 25, the market is historically expensive. Below 16 is historically cheap. This is one of the most useful long-term market entry/exit signals.

---

---

# Institutional Activity

> **Note on relevance for long-term analysis:** The modules in this group are primarily short-term or trading-oriented signals. For a long-term buy-and-hold investor, these provide context but should not drive decisions. The quarterly % shareholding from screener (FII/DII/promoter holdings) is more relevant for long-term analysis than daily flow data.

---

## fii_dii / fii_dii.py

**What it does:** Fetches the most recent trading day's FII (Foreign Institutional Investors / FPI) and DII (Domestic Institutional Investors) buy/sell/net values in crores from NSE. This is a market-wide number — not per stock.

**What FII and DII mean:**
- **FII/FPI**: Foreign funds investing in India — hedge funds, sovereign wealth funds, pension funds from outside India. FII activity is the strongest single-day driver of Indian market direction. Sustained FII selling = market under pressure.
- **DII**: Indian institutional investors — mutual funds, LIC, insurance companies. They often act as a counterbalance, buying when FIIs sell.
- Values are in **crores (₹)** — 1 crore = 10 million rupees.

**Limitation:** NSE API returns only the most recent trading day. Historical data cannot be re-fetched. Run daily and sync with `db/sync.py` to build history.

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

> `net` negative = net sellers (bearish signal). `net` positive = net buyers. In this example, FIIs sold ₹8,047 crore net while DIIs absorbed some of it by buying ₹3,487 crore net.

---

## bulk_deals / bulk_deals.py

**What it does:** Fetches today's bulk and block deals from NSE's public CSV archives.

**What bulk vs block deals mean:**
- **Bulk deal**: Any transaction where a single client buys or sells **≥0.5% of the company's total shares** in a single day. Publicly disclosed because it signals a significant position change by an institution or HNI (High Net Worth Individual).
- **Block deal**: A large pre-negotiated trade (minimum ₹10 crore) executed during a special 35-minute window before market open. Two institutional parties have already agreed on price off-market. Block deals are less frequent than bulk deals.

**Limitation:** NSE CSV only has today's data. Historical bulk deals are not publicly available from NSE's free endpoints.

> `remarks` field is usually "-" — it's an optional field NSE only fills for special circumstances. Most normal bulk deals have no remarks.

**Key functions**
- `fetch_bulk_deals()` → list (today's bulk deals)
- `fetch_block_deals()` → list (today's block deals)
- `fetch_all_deals()` → `{bulk_deals: [...], block_deals: [...]}`
- `fetch_deals_for_symbol(ticker)` → filtered to one stock
- `save_bulk_deals()` → saves `bulk_block_deals_{date}.json`, returns file path

**Output**
```json
{
  "bulk_deals": [
    {
      "date": "30-APR-2026",
      "symbol": "RELIANCE",
      "scrip_name": "Reliance Industries Ltd",
      "client": "NORTH STAR OPPORTUNITIES FUND VCC",
      "buy_sell": "BUY",
      "quantity": "101868",
      "trade_price": "1436.50",
      "remarks": "-"
    }
  ],
  "block_deals": []
}
```

---

## fno_data / fno_data.py

**What it does:** Fetches the full F&O (Futures & Options) option chain for a stock or index from NSE, and derives sentiment metrics: PCR, max pain, top OI strikes, and ATM implied volatility.

**What F&O means:**
F&O is the derivatives market. These contracts give traders the right (options) or obligation (futures) to buy/sell a stock at a fixed price on a future date. Traders use them to hedge positions or speculate without holding the actual stock.

- **Call option (CE)**: Right to buy at a price. Profitable when stock goes **up**
- **Put option (PE)**: Right to sell at a price. Profitable when stock goes **down**
- **OI (Open Interest)**: Number of outstanding contracts at each strike — high OI = significant market interest at that level. Acts as support (high PE OI) or resistance (high CE OI)
- **PCR (Put-Call Ratio)**: Total PE OI ÷ Total CE OI. Above 1.2 = more puts = bearish bias. Below 0.8 = bullish bias
- **Max Pain**: Strike price where the maximum number of options expire worthless — where option buyers collectively lose the most. Stocks tend to gravitate toward max pain near expiry
- **ATM IV (Implied Volatility)**: How much volatility the market expects. Spikes before earnings results

**Supported symbols:**
- **Indices**: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY
- **F&O stocks**: ~200 NSE-approved stocks (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, WIPRO, AXISBANK, KOTAKBANK, LT, BAJFINANCE, MARUTI, TATAMOTORS, etc.)

**Limitation:** Returns a live real-time snapshot. Empty outside market hours (Mon–Fri 9:15 AM – 3:30 PM IST) and on holidays. Historical option chain data is not available via NSE's public API.

**Key functions**
- `fetch_option_chain(ticker)` → raw chain dict
- `fetch_fno_snapshot(ticker)` → chain + derived metrics
- `save_fno_snapshot(ticker)` → saves `{TICKER}_fno_{date}.json`, returns file path

**Output**
```json
{
  "ticker": "NIFTY",
  "underlying_value": 24500.0,
  "timestamp": "05-May-2026 10:30:00",
  "expiry_dates": ["08-May-2026", "15-May-2026", "29-May-2026"],
  "pcr": 0.85,
  "max_pain": 24000,
  "atm_iv": {
    "strike": 24500, "expiry": "08-May-2026",
    "ce_iv": 12.5, "pe_iv": 13.2
  },
  "top_oi_strikes": {
    "top_ce_oi": [
      { "strike": 25000, "oi": 1234567, "expiry": "08-May-2026" }
    ],
    "top_pe_oi": [
      { "strike": 24000, "oi": 1100000, "expiry": "08-May-2026" }
    ]
  },
  "option_chain": [
    {
      "strike_price": 24000,
      "expiry_date": "08-May-2026",
      "ce": { "oi": 500000, "change_oi": 12000, "volume": 45000, "iv": 15.5, "ltp": 234.5, "change": 12.3, "pchange": 5.5 },
      "pe": { "oi": 750000, "change_oi": -8000, "volume": 38000, "iv": 16.2, "ltp": 89.5, "change": -5.2, "pchange": -5.5 }
    }
  ]
}
```

> `option_chain` will have 200–300+ rows for NIFTY (many strikes across multiple expiries). The derived metrics (pcr, max_pain, atm_iv, top_oi_strikes) are the investment-relevant summary — the full chain is there for deeper analysis.

---

---

# News & Information

---

## youtube / transcript.py

**Why it matters:**
Analyst interviews, management presentations at investor conferences, CNBC discussions with fund managers — YouTube carries a lot of financial content that isn't available in text form elsewhere. Transcripts let you extract structured information from video content.

**What it does:** Fetches the transcript of a YouTube video. Falls back to any available language if English is not found.

**Key functions**
- `extract_transcript(video_url)` → raw transcript text
- `save_transcript(video_url)` → saves JSON, returns file path

**Output**
```json
{
  "video_id": "dQw4w9WgXcQ",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "language": "en",
  "transcript": "Full transcript text as a single string..."
}
```

---

## web_scrapers / moneycontrol.py

**What it does:** Scrapes today's articles from Moneycontrol news categories. Each article is individually fetched to verify publish date; pagination stops when an older article is found.

**Key functions**
- `scrape_listing(base_url, target_date, max_pages)` → list
- `scrape_article(url)` → dict
- `save_category(category_name)` → saves JSON, returns file path

**Available categories**
```
markets, stocks, earnings, economy, companies,
india, mutual_funds, commodities, ipo
```

**Parameters**
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
      "url": "https://...",
      "title": "Article headline",
      "author": "Reporter Name",
      "published": "2026-05-02T08:30:00+05:30",
      "body": "Full article body text..."
    }
  ]
}
```

---

## web_scrapers / economic_times.py

Same pattern as Moneycontrol — scrapes today's articles from ET news categories.

**Available categories:** `stocks_news`, `expert_view`, `stocks_recos`, `commodities`

**Output structure** — identical to Moneycontrol output.

---

## web_scrapers / generic.py

**What it does:** Extracts article text from any publicly accessible website using `trafilatura`. Works for blogs, Finshots, Wikipedia, open news sites. Does not work on JS-heavy or paywalled sites.

**Key functions**
- `extract_article(url)` → dict
- `save_article(url)` → saves JSON, returns file path

**Output**
```json
{
  "url": "https://finshots.in/archive/...",
  "title": "Article title",
  "author": "Author name",
  "date": "2026-05-01",
  "text": "Full extracted article text..."
}
```

---

## web_scrapers / browser_scraper.py

**What it does:** Uses Playwright (headless Chromium) to render JavaScript-heavy pages before extracting text. Use this for sites that require JS to load content (e.g. Tickertape, Trendlyne). Slower than `generic.py`.

**Key functions** — same as `generic.py`: `extract_page(url)`, `save_page(url)`

---

## rss / rss_feed.py

**What it does:** Fetches RSS feeds — headlines and summaries only (not full article body). Feed list is defined in `config/rss_feeds.py`.

**Key functions**
- `fetch_feed(url)` → list
- `save_feed(feed_name, url)` → saves one feed
- `save_all_feeds()` → saves all feeds in config, returns list of paths

> Full article bodies are not in RSS output. Use `generic.py` or `browser_scraper.py` on individual URLs for full text.

---

## news_apis / newsdata_io.py

**What it does:** Fetches news via the NewsData.io API. Returns title, description, and keywords. **Limit:** 200 credits/day on free tier.

**Key functions**
- `fetch_news(query, country, language, limit)` → list
- `save_news(query)` → saves JSON, returns file path

---

## news_apis / mediastack.py

**What it does:** Fetches news via the Mediastack API. **Limit:** 500 requests/month — use sparingly.

Same input/output structure as `newsdata_io.py`.

---

## gmail / newsletter.py

**What it does:** Connects to Gmail via IMAP and fetches emails from a specific sender domain or by subject keyword. Strips HTML and returns plain text body.

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

---

# Utilities

---

## ticker_extractor / ticker_extractor.py

**Why it matters:**
When you collect news articles, transcripts, or newsletters, they mention companies by name — not by ticker. This module scans text and maps company names to NSE tickers so the downstream analysis layer can cross-reference news with stock data.

**What it does:** Scans free-form text and identifies NSE-listed companies, returning their ticker symbols. Uses the full 2360-stock NSE list plus a small alias dict for short/colloquial names (SBI → SBIN.NS, TCS → TCS.NS, etc.).

**Key functions**
- `extract_tickers(text)` → list of `{company, ticker}` dicts
- `lookup_ticker(company_name)` → fuzzy search, returns best match or None
- `save_tickers(text, label)` → saves JSON, returns file path

**Dependency:** `nse_symbols.py` — downloads the NSE equity list on first use and caches it locally. Auto-refreshes every 7 days.

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

# Persistent History (db/)

---

## db / sync.py

**Why it exists:**
Three modules can only return today's data from NSE — `fii_dii`, `bulk_deals`, and `macro_data` (specifically the NSE index PE/PB). If you want a historical trend, you have to accumulate daily snapshots. `sync.py` is the only code that writes to `db/` — individual modules write to `output/` only. This keeps a clean separation between session outputs and persistent history.

**How it works:**
Each history file is **JSONL** format (JSON Lines — one JSON record per line, append-only). Sync reads from the latest output file, checks if that date is already in history, and appends only if it's new. This makes sync **idempotent** — you can run it multiple times safely.

**If you miss a day:** The output files in `output/` are the natural backup. If the db history file is ever lost or corrupted, run `python db/sync.py --all` to rebuild it from all existing output files.

**Usage**
```bash
python db/sync.py          # sync latest output file for each module
python db/sync.py --all    # scan all output files and sync any missing dates
```

**History files created**

| File | Content | When to sync |
|---|---|---|
| `db/fii_dii/history.jsonl` | Daily FII/DII buy/sell/net | After each `fii_dii.py` run |
| `db/bulk_deals/history.jsonl` | Daily bulk/block deals with symbols | After each `bulk_deals.py` run |
| `db/macro_data/history.jsonl` | NSE index PE/PB + market rates | After each `macro_data.py` run |

**Sample history record (fii_dii)**
```jsonl
{"date": "2026-04-30", "fii": {"buy": 15049.55, "sell": 23097.41, "net": -8047.86}, "dii": {"buy": 18252.89, "sell": 14765.79, "net": 3487.1}}
{"date": "2026-05-01", "fii": {"buy": 18200.0, "sell": 14100.0, "net": 4100.0}, "dii": {"buy": 12500.0, "sell": 15200.0, "net": -2700.0}}
```

> **Why Nifty PE history is particularly valuable:** Tracking Nifty PE over months and years gives you one of the best market valuation signals available. Historically, Nifty PE above 25 has been expensive, below 16 cheap. Building this time series by running `macro_data.py` + `sync.py` daily turns a single-point metric into a trend you can reason about.
