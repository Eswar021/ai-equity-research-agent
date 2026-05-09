# Stock Researcher

An automated daily pipeline that reads Indian financial news, extracts company-specific signals using an LLM, deep-dives the top candidates, and produces a structured research report with **invest / watch / avoid** recommendations — including a CIO-level synthesis that ranks the top 3–5 actionable picks.

---

## What it does

Every morning you run one command. By evening you have:

- A research report (`report_{date}.md`) with ranked buy/watch/avoid calls, each with thesis, key drivers, risks, and cited source URLs
- A **CIO synthesis** at the top: which 3–5 of the day's candidates actually matter, de-duped by theme and sector-concentration-checked
- A full data package per candidate: 10-year financials, peer comparison, analyst estimates, earnings transcripts, NSE filings, price history
- **Portfolio-aware recommendations**: if you provide `config/portfolio.json`, held stocks get hold/exit decisions, watchlist tickers get signal updates

---

## Architecture — 7 Phases

```
Phase A  →  Phase B  →  Phase D  →  Phase C  →  Phase E  →  Phase F  →  Phase G
Collect      Filter      Proxy map    Deep dive    Evidence    Analyst     Report
                         themes       tickers      cards       views       + CIO
```

| Phase | Script | What it does | LLM | ~Time |
|-------|--------|-------------|-----|-------|
| **A** — Broad Market Discovery | `run_phase_a.py` | Scrapes 7+ news sources; fetches FII/DII flows, VIX, macro, bulk deals | None | ~15 min |
| **B** — Market Intelligence | `run_phase_b.py` | B1: market regime (rule-based). B2: LLM extracts signals from ~864 articles. B3: scores + ranks listed tickers and thematic targets | Yes (B2) | ~2 min* |
| **D** — Proxy Mapper | _(via run_pipeline.py)_ | Maps thematic targets (private cos, macro events, sector themes) to 3–5 NSE-listed proxy tickers; merges into candidate list | Yes | ~5 sec* |
| **C** — Company Deep Dive | `run_phase_c.py` | Fetches market data, screener.in fundamentals, peer comparison, analyst estimates, NSE filings, transcripts for each candidate | None | ~3–8 min |
| **E** — Evidence Card Builder | _(via run_pipeline.py)_ | Pure Python: aggregates all Phase C files per ticker into one structured evidence card | None | <30 sec |
| **F** — Stock Analyst | _(via run_pipeline.py)_ | LLM call per ticker: invest/watch/avoid + thesis, drivers, risks, conviction, source URLs | Yes | ~5 sec* |
| **G** — CIO + Report | _(via run_pipeline.py)_ | G1: single LLM call over all analyst views → top picks, sector warnings, macro coherence. G2: pure Python report formatter | Yes (G1) | ~10 sec* |

\* With parallel workers (`--workers N`). Sequential times are ~5–10× longer.

---

## Prerequisites

Python 3.11 or higher.

**Required API keys — add to `.env`:**

| Variable | Used by | Cost |
|---|---|---|
| `OPENAI_API_KEY_S_M_R` | Phases B, D, F, G (LLM calls) | Paid (gpt-5-nano ~$0.15/full run) |
| `YOUTUBE_API_KEY` | Phase A YouTube channel search | Free (10,000 units/day) |
| `FRED_API_KEY` | Phase A US macro data | Free |
| `NEWSDATA_API_KEY` | Phase A NewsData.io | Free (200 credits/day) |
| `MEDIASTACK_API_KEY` | Phase A Mediastack | Free (500 req/month) |
| `GMAIL_EMAIL` + `GMAIL_APP_PASSWORD` | Phase A newsletter fetch | Free |

Phases C, E are no-LLM (yfinance + NSE public APIs — no extra keys).

**Optional:**

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Use Gemini Flash for LLM phases instead of OpenAI |
| `YOUTUBE_PROXY` | Proxy for YouTube transcript fetch if IP is rate-limited |
| `LMSTUDIO_BASE_URL` | Local LM Studio model for LLM phases |

---

## How to run

### Full pipeline (recommended)

```bash
pip install -r requirements.txt
cp .env.example .env         # fill in API keys
cp config/portfolio.example.json config/portfolio.json   # optional — add your holdings

python run_pipeline.py       # full E2E run
```

### Partial / skip-to runs

```bash
# Resume from Phase C onwards (e.g. you completed A+B+D yesterday)
python run_pipeline.py --skip-to C

# Re-run only the analyst + report (fast, reuses today's evidence cards)
python run_pipeline.py --skip-to F

# Skip Phase A collection entirely (reuse today's existing Phase A data)
python run_pipeline.py --skip-phase-a

# Single-ticker debug run (skips Phase A, runs D→C→E→F→G on one ticker)
python run_pipeline.py --ticker BHEL.NS

# Provider and concurrency
python run_pipeline.py --provider gemini --workers 15

# Skip screener.in scrape (faster Phase C, loses fundamental data)
python run_pipeline.py --skip-screener
```

### Run individual phases

```bash
python run_phase_a.py
python run_phase_b.py --skip-signals     # reuse last signals file, re-run scoring only
python run_phase_b.py --provider gemini  # use Gemini for signal extraction
python run_phase_b.py --workers 25       # concurrent LLM workers (default 25)
python run_phase_c.py --skip-screener    # skip screener.in scrape
python run_phase_c.py --ticker BHEL.NS   # single ticker test
python run_phase_c.py --workers 3        # concurrent ticker workers (default 3)
```

### Diagnostic

```bash
python inspect_phase_a.py   # file counts, item counts, content health per source
```

---

## Portfolio context (optional)

Create `config/portfolio.json` (gitignored — your private data):

```json
{
  "holdings":  [
    {"ticker": "HDFCBANK.NS", "qty": 100, "avg_price": 1450},
    {"ticker": "INFY.NS",     "qty":  50, "avg_price":  980}
  ],
  "watchlist":  ["BHEL.NS", "TATAPOWER.NS"],
  "avoid_list": ["YESBANK.NS"]
}
```

When present: held stocks get hold/exit recommendations (not buy/sell), watchlist tickers get signal updates in the report, and the CIO synthesis flags portfolio overlap.

See `config/portfolio.example.json` for the full schema.

---

## Output

All outputs land in `output/{YYYY-MM-DD}/` — each daily run is fully isolated.

```
output/2026-05-09/
├── phaseA/
│   ├── moneycontrol/          articles (title + full body)
│   ├── economic_times/        articles (title + full body)
│   ├── rss/                   headlines + summaries per feed
│   ├── newsdata_io/           title + description
│   ├── mediastack/            title + description
│   ├── youtube/               one file per video with full transcript
│   ├── gmail/                 newsletter email bodies
│   ├── macro_data/            Nifty PE/PB, VIX, commodities, FII macro
│   ├── fii_dii/               daily institutional flows
│   ├── fno_data/              NIFTY/BANKNIFTY option chain snapshot
│   └── bulk_deals/            today's bulk and block deals
├── phaseB/
│   ├── market_regime/         market_regime_{date}.json
│   ├── signals/               signals_{date}.json  (all LLM-extracted signals)
│   ├── candidates/            candidates_{date}.json  (listed + thematic targets)
│   └── signal_logs/           signals_{date}.jsonl  (LLM call log per article)
├── phaseD/
│   ├── proxy_mappings/        proxy_mappings_{date}.json  (theme → proxy tickers)
│   └── llm_proxy_logs/        proxy_{date}.jsonl
├── phaseC/
│   ├── market_data/           {TICKER}_{date}.json  (price, sector, returns)
│   ├── screener_in/           {company_slug}_{hash}.json  (10-year financials)
│   ├── peer_comparison/       {TICKER}_peers_{date}.json
│   ├── analyst_estimates/     {TICKER}_analyst_estimates_{date}.json
│   ├── exchange_filings/      {TICKER}_announcements_{date}.json
│   ├── filing_docs/           {TICKER}_filing_docs_{date}.json
│   └── corporate_actions/     {TICKER}_corporate_actions_{date}.json
├── phaseE/
│   └── evidence_cards/        {TICKER}.json  (aggregated card per ticker)
├── phaseF/
│   ├── analyst_views/         {TICKER}.json  (invest/watch/avoid + thesis)
│   └── llm_analyst_logs/      analyst_{date}.jsonl
└── phaseG/
    ├── report_{date}.md        human-readable research report
    ├── report_{date}.json      machine-readable version
    ├── cio_synthesis_{date}.json  CIO top picks + sector warnings + narrative
    └── cio_log_{date}.jsonl       CIO LLM call log
```

---

## Documentation

| Doc | Location | What it covers |
|---|---|---|
| This file | `README.md` | What, why, and how to run |
| Logic deep-dive | `docs/context_ext_layer_docs/LOGIC.md` | How each algorithm works |
| Design decisions | `docs/context_ext_layer_docs/DECISIONS.md` | Why non-obvious choices were made |
| Operational reference | `docs/context_ext_layer_docs/CONTEXT_LAYER.md` | Every module: inputs, outputs, functions, file paths |
