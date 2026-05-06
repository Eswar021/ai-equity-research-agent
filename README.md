# Stock Researcher

An automated daily pipeline that scans Indian financial news, extracts company-specific signals using an LLM, and produces a data-rich shortlist of stocks worth investigating further.

---

## What it does

Every morning you run three commands. By the time you open your analysis tool, you have:

- A ranked list of 25 stocks that appeared prominently in the day's financial news
- The reason each stock appeared: earnings beat, management change, bulk deal, regulatory action, analyst upgrade, etc.
- A full data package for each: 10-year financials, peer comparison, analyst estimates, earnings transcripts, NSE filings, price history

The system does not make buy/sell decisions. It filters signal from noise so you spend your time analyzing, not reading.

---

## Pipeline

```
Phase A — Collect         ~15 min      run_phase_a.py
Phase B — Filter          ~2 hrs       run_phase_b.py
Phase C — Deep Dive       ~30 min      run_phase_c.py
Phase D — Analyze         coming soon
```

**Phase A — Collect**
Scrapes 7+ sources simultaneously: Moneycontrol, Economic Times, RSS feeds (Livemint, Hindu BusinessLine, NDTV Profit, ET Markets and more), NewsData.io, Mediastack, Gmail newsletters, YouTube channel transcripts. Also fetches daily market data: Nifty/VIX levels, FII/DII institutional flows, F&O option chain sentiment, India and US macro indicators, bulk and block deals.

**Phase B — Filter**
Three sequential steps:
- B1: Computes the market regime from macro data using rule-based thresholds — overall posture (bullish/neutral/bearish/risk-on), favoured and avoid sectors for the day.
- B2: Sends each article and transcript to an LLM, which extracts structured signals: which company, what event, how severe, positive or negative. Roughly 800+ articles processed per run.
- B3: Scores each company by aggregating signals across all sources, weighted by source credibility and signal severity. Bulk and block deals add a bonus. Top 25 candidates by signal strength are selected.

**Phase C — Deep Dive**
For each of the top 25 candidates, fetches: current market data (price, sector, 52-week range), 10-year fundamentals from screener.in, 1-year price history, sector peer comparison, analyst consensus and price targets, material NSE corporate announcements, earnings call transcripts, and corporate actions (dividends, splits, buybacks). After fetching, re-ranks candidates using the market regime sector alignment.

---

## Prerequisites

Python 3.11 or higher.

**Required API keys — add to `.env`:**

| Variable | Used by | Cost |
|---|---|---|
| `OPENAI_API_KEY_S_M_R` | Phase B LLM signal extraction | Paid |
| `YOUTUBE_API_KEY` | Phase A YouTube channel search | Free (10,000 units/day) |
| `FRED_API_KEY` | Phase A US macro data (FRED) | Free |
| `NEWSDATA_API_KEY` | Phase A NewsData.io | Free (200 credits/day) |
| `MEDIASTACK_API_KEY` | Phase A Mediastack | Free (500 req/month) |
| `GMAIL_EMAIL` + `GMAIL_APP_PASSWORD` | Phase A newsletter fetch | Free |

Phase C uses yfinance and NSE public APIs — no keys required.

**Optional:**

| Variable | Purpose |
|---|---|
| `YOUTUBE_PROXY` | Proxy for YouTube transcript fetch if your IP is rate-limited |
| `LMSTUDIO_BASE_URL` | Use a local LM Studio model instead of OpenAI for Phase B |

---

## How to run

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your API keys

python run_phase_a.py       # collect all sources
python run_phase_b.py       # extract signals + score candidates
python run_phase_c.py       # deep dive on top candidates
```

Each phase is independently runnable. Useful flags:

```bash
python run_phase_b.py --skip-signals       # reuse last signals file, re-run scoring only
python run_phase_b.py --provider lmstudio  # use local model
python run_phase_c.py --skip-screener      # skip screener.in scrape (faster)
python run_phase_c.py --ticker BHEL.NS     # deep dive one ticker only
```

**Diagnostic check after Phase A:**
```bash
python inspect_phase_a.py   # shows file counts, item counts, content health per source
```

---

## Output

All outputs land in `output/{YYYY-MM-DD}/` — each daily run is fully isolated.

```
output/2026-05-06/
├── phaseA/
│   ├── moneycontrol/       articles (title + full body)
│   ├── economic_times/     articles (title + full body)
│   ├── rss/                headlines + summaries per feed
│   ├── newsdata_io/        title + description
│   ├── mediastack/         title + description
│   ├── youtube/            one file per video with full transcript
│   ├── gmail/              newsletter email bodies
│   ├── macro_data/         Nifty PE/PB, VIX, commodities, FII macro
│   ├── fii_dii/            daily institutional flows
│   ├── fno_data/           NIFTY/BANKNIFTY option chain snapshot
│   └── bulk_deals/         today's bulk and block deals
├── phaseB/
│   ├── market_regime/      macro regime: posture + favoured/avoid sectors
│   ├── signals/            all LLM-extracted signals (one record per article)
│   ├── candidates/         ranked candidates — pre and post sector adjustment
│   └── signal_logs/        LLM call log: prompt + response per article (.jsonl)
└── phaseC/
    ├── market_data/        current price, sector, 52W range, returns
    ├── screener_in/        10-year P&L, balance sheet, cash flow, shareholding
    ├── peer_comparison/    sector peer valuation comparison
    ├── analyst_estimates/  consensus price targets, EPS estimates, revisions
    ├── exchange_filings/   material NSE announcements + earnings transcripts
    └── corporate_actions/  dividends, splits, buybacks history
```

---

## Documentation

| Doc | Location | What it covers |
|---|---|---|
| This file | `README.md` | What, why, and how to run |
| Logic deep-dive | `docs/context_ext_layer_docs/LOGIC.md` | How each algorithm works |
| Design decisions | `docs/context_ext_layer_docs/DECISIONS.md` | Why non-obvious choices were made |
| Operational reference | `docs/context_ext_layer_docs/CONTEXT_LAYER.md` | Every module: inputs, outputs, functions, file paths |
