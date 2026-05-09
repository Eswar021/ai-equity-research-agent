# Logic — How the Algorithms Work

Deep dive into the reasoning and mechanics behind each step of the pipeline. No file paths or run commands — see CONTEXT_LAYER.md for those.

---

## 1. Content Filtering (Phase A → B2)

Not everything collected in Phase A is useful. Two filters prevent low-quality content from reaching the LLM.

**Filter 1 — Total text length ≥ 80 characters.**
Removes empty API responses, broken scrapes, and pure metadata records with no readable text.

**Filter 2 — Body/summary field alone ≥ 40 characters.**
This is the critical filter. RSS feeds from sources like Investing.com and Yahoo Finance sometimes return items where the title is 70 characters (so the total passes Filter 1) but the summary field is empty, null, or just "Click to read more." Without this filter, the LLM receives a headline with no content. It either returns no signals (wasted API call) or hallucinates signals from the headline alone (false positives).

Each source sends different content fields to the LLM:

| Source | Content sent to LLM |
|---|---|
| Moneycontrol / Economic Times | Title + full article body (richest content) |
| RSS | Title + summary (1–3 sentences typically) |
| NewsData.io / Mediastack | Title + description |
| YouTube | First 3,500 chars of transcript (~10 minutes of speech) |
| Gmail | Subject line + full email body |

Effect: roughly 1,200 raw collected items reduce to ~864 after filtering on a typical day.

---

## 2. LLM Signal Extraction (Phase B2)

### Why Pydantic structured output instead of JSON string parsing

Early versions of the extractor asked the LLM to "return a valid JSON array of signals." Models frequently returned malformed JSON: missing closing brackets, trailing commas, markdown code fences wrapping the JSON, explanatory text before or after the array. This required 30+ lines of repair logic (strip fences, fix commas, fallback parsers) that was brittle and broke on edge cases regularly.

Switching to `llm.with_structured_output(NewsSignals)` — where `NewsSignals` is a Pydantic model — eliminates the problem entirely. The model is constrained by the schema at the API level. The response is always a valid Python object matching the schema. No repair, no fallback, no parsing.

### Pipeline built once, not per item

```python
# Built once before the loop
pipeline = _prompt | llm.with_structured_output(NewsSignals)

for item in items:
    result  = pipeline.invoke({"text": item["text"]})
    signals = result.signals
```

Building the pipeline inside the loop (once per item) adds overhead — `.with_structured_output()` construction is not a no-op. With 864 items, building it 864 times adds measurable latency. Built once outside the loop, it's constructed once and reused.

### What the LLM provides vs what's resolved post-LLM

The LLM is not asked to know NSE ticker symbols. It extracts the company name as written in the article. Ticker resolution is done programmatically after the LLM call.

| Field | Source | Notes |
|---|---|---|
| `ticker_hint` | LLM | Company name as in article: "Infosys", "IndiGo", "HDFC Bank" |
| `event_type` | LLM | One of 14 types: earnings_beat, merger_acquisition, etc. |
| `sentiment` | LLM | positive / negative / neutral |
| `severity` | LLM | high / medium / low |
| `key_claim` | LLM | One sentence: what specifically happened |
| `ticker` | Post-LLM | NSE symbol: INFY.NS, INDIGO.NS, HDFCBANK.NS |
| `company` | Post-LLM | Full legal name from NSE list |

### Prompt design

The system prompt establishes Indian equity market context explicitly. Without it, models apply generic assumptions — treating "NIFTY" as a brand name, misclassifying Indian corporate structures, or using US earnings calendar timing. Key rules in the prompt:

- Extract only events for specific listed companies. Skip index commentary ("Nifty gained 200 points today" → no signal).
- Severity is defined with hard thresholds: >15% YoY swing = high, <15% = medium, routine disclosures = low.
- Non-English text (Hindi, Telugu, Marathi): extract if company names are identifiable.
- Return an empty signals list if no company-specific actionable event is found — do not force signals from macro commentary.

---

## 3. Ticker Resolution (Phase B2 post-LLM)

Two-pass approach to map `ticker_hint` (company name string from LLM) → NSE ticker symbol.

### Pass 1 — Alias dictionary (exact match, case-insensitive)

A hardcoded dictionary of ~80 short or colloquial names that are too ambiguous for fuzzy matching to handle reliably:

```
"sbi"     → SBIN.NS     ("state bank" simplified is just "state" — too generic)
"tcs"     → TCS.NS
"indigo"  → INDIGO.NS   (needed after false positive at lower fuzzy threshold)
"paytm"   → PAYTM.NS
"zomato"  → ZOMATO.NS
```

This pass runs first and handles the highest-frequency cases reliably without touching the fuzzy engine.

### Pass 2 — Fuzzy match against NSE symbol list (2,360 stocks)

Uses rapidfuzz on simplified company names (stripped of "Ltd", "Limited", "India", "Industries" suffixes) with a threshold of **82 out of 100**.

**Why threshold 82:**
This threshold was calibrated against specific real-world failures:
- At threshold 70: "IndiGo" matched "Indo-National" (ticker: NIPPOBATRY.NS) — completely wrong company
- At threshold 70: "SpiceJet" matched "Spacenet Enterprises" (ticker: SPCENET.NS) — completely wrong
- At threshold 82: both false positives disappear
- At threshold 82: true matches still work — "Sun Pharma" → SUNPHARMA.NS, "Larsen Toubro" → LT.NS, "Bajaj Finserv" → BAJAJFINSV.NS

The alias dictionary is the safety net for cases where the correct match genuinely has a low fuzzy score.

### Unresolved tickers

If both passes fail, the signal is **kept, not discarded**, with `ticker = null` and `company = ticker_hint.title()`. The signal's event type, sentiment, severity, and key_claim are all valid — only the ticker is unknown. This is preserved for potential name-based lookup in Phase C or D, rather than silently losing the signal.

The NSE symbol list is downloaded on first use and auto-refreshed every 7 days (cached locally). This means the first run after 7 days has a one-time network call to NSE.

---

## 4. Market Regime (Phase B1)

### Five independent signals

Each signal maps one raw number to a categorical label:

| Signal | Input metric | Labels |
|---|---|---|
| breadth | NIFTY 500 advance/decline ratio | bearish (<0.6), neutral (0.6–1.4), bullish (>1.4) |
| vix | India VIX index | fear (>25), elevated (18–25), moderate (13–18), calm (<13) |
| fii | FII net flows ₹ crore | heavy_selling (<-5000), selling (-5000 to -1000), flat (-1000 to 500), buying (>500) |
| crude | Brent crude USD/barrel | expensive (>100), moderate (75–100), cheap (<75) |
| usd_inr | USD/INR exchange rate | very_weak (>87), weak (85–87), moderate (83–85), strong (<83) |

### Market posture

The five categorical signals are voted on. Bullish-flavored signals (bullish breadth, calm VIX, FII buying, cheap crude, strong rupee) get a +1. Bearish-flavored signals get a -1. The majority determines the posture:

- 3+ bullish → BULLISH (or RISK_ON when combined with buying FII + strong breadth)
- 3+ bearish → BEARISH
- Otherwise → NEUTRAL

### Sector recommendations

Derived from the signal combination, not just posture:

- **Cheap crude (<$75):** tailwind for Aviation, Paints, Tyres, OMCs (lower input costs)
- **Expensive crude (>$100):** tailwind for Oil & Gas upstream; Aviation, Paints get penalised
- **FII heavy selling:** avoid mid-cap and small-cap (less institutional support = higher volatility)
- **BULLISH posture:** favour cyclicals — Auto, Metal, Realty, Infra, Banking
- **BEARISH posture:** favour defensives — FMCG, Pharma, IT (dollar earner, counter-cyclical)

Everything is deterministic — no LLM. Numerical thresholds applied directly. This makes the regime fast (sub-second), reproducible, and immune to hallucination.

---

## 5. Candidate Scoring (Phase B3)

### Formula

For each LLM-extracted signal:

```
contribution = source_weight × severity_weight × sentiment_modifier
```

**Weights:**

| Dimension | Value | Rationale |
|---|---|---|
| moneycontrol / economic_times | 3.0 | Full article bodies, editorial standards, India market focus |
| rss / gmail | 2.0 | Reputable sources but summary-only or curated newsletters |
| newsdata_io / mediastack | 1.5 | API-aggregated, lower editorial bar |
| youtube | 1.0 | Transcript quality varies; often opinion not fact |
| severity: high | 3.0 | >15% YoY swing, M&A, CEO exit, major regulatory action |
| severity: medium | 2.0 | <15% swing, analyst rating change, guidance update |
| severity: low | 1.0 | Dividends, bonus shares, routine disclosures |
| sentiment: positive | +1.0 | Good news |
| sentiment: negative | -1.0 | Bad news (negative score = sell/avoidance signal) |
| sentiment: neutral | +0.4 | Being talked about without clear direction — still worth noting |

**Maximum per signal** = 3.0 × 3.0 × +1.0 = **+9.0** (Moneycontrol, high severity, positive).

### Bulk deal bonus

Bulk and block deals are institutional money in motion — a large fund or institution bought/sold ≥0.5% of the company in a single day. This is a strong independent signal regardless of news coverage, so it gets a flat bonus: **+5.0 per buy deal**, **−5.0 per sell deal**.

### Worked example — BHEL at +75.0

14 signals across 4 sources (moneycontrol, economic_times, rss, newsdata_io):

- 5 high-severity positive signals from MC/ET: 5 × (3.0 × 3.0 × 1.0) = **+45.0**
- 5 medium-severity positive signals from MC/ET: 5 × (3.0 × 2.0 × 1.0) = **+30.0**
- 4 lower-weight signals from RSS/newsdata at medium severity: ~**+4.5 to +12.0**

Total ≈ **+75.0**

### Sorted by |final_score|, not final_score

The list is sorted by the absolute value of the score. A stock with a score of −60 (like ACC with earnings miss signals) is ranked #2 — it is as actionable as BHEL at +75, just in the opposite direction (short candidate, or a stock to actively avoid). Sorting by absolute value ensures both sides surface.

### Filtering funnel

- 864 articles processed → 630 signals extracted → 120 unique tickers with at least one resolved signal
- `|score| < 3.0` → dropped (noise, single weak signal)
- 104 tickers pass threshold → top 25 by |score| selected

---

## 6. Sector Re-scoring (Phase C)

### Why it's done in Phase C, not Phase B

The market regime (B1) identifies favoured and avoided sectors. Logically, sector alignment should be part of B3 scoring. But yfinance sector labels — the authoritative, per-ticker sector classification — are only fetched in Phase C via `market_data.py`. Running a separate yfinance call for 120 tickers just for sector labels during B3 would add significant time to Phase B and duplicate work that Phase C does anyway.

The compromise: B3 scores purely on signal strength. Phase C fetches market data (which includes sector) for the top 25 candidates, then applies the sector adjustment and re-ranks.

### Sector label mapping

yfinance returns GICS-style sector strings ("Technology", "Consumer Cyclical", "Industrials"). These are mapped to the regime's short keys:

| yfinance label | Regime key |
|---|---|
| Technology, Information Technology | it |
| Financial Services, Banking | banking |
| Healthcare, Pharmaceutical | pharma |
| Consumer Defensive, Consumer Staples | fmcg |
| Consumer Cyclical, Automobile | auto |
| Basic Materials, Metal, Steel | metal |
| Real Estate | realty |
| Industrials, Infrastructure, Capital Goods | infra |
| Energy, Oil & Gas | oil_gas |

### Effect on ranking

The adjustment is intentionally small relative to signal scores: **+4.0** for favoured sectors, **−3.0** for avoided sectors. BHEL at +75 gets +4 (Industrials → infra, regime-favoured) → +79. SUNPHARMA at +24 gets −3 (Healthcare → pharma, regime-avoided) → +21. The purpose is tie-breaking and nudging regime-aligned stocks up — not overriding strong signal scores.

### Sector mapping log

After Phase C completes, `sector_map_{date}.json` records for every ticker: the raw yfinance sector string, the mapped regime key, whether it fell in favored/avoid, and the adj applied. Tickers where `mapped_key` is null despite having a non-null raw sector are flagged with a note suggesting the alias be added to `_SECTOR_ALIASES`. This surfaces silent misses where a sector's signals were not getting their regime bonus.

---

## 7. Entity-centric Signal Extraction (Phase B2 — revised schema)

The original schema assumed every signal maps to a listed company. The revised schema separates entity types:

| `entity_type` | What it represents | Ticker resolution |
|---|---|---|
| `listed` | NSE/BSE-listed company | Three-pass: direct symbol → alias dict → fuzzy @82 |
| `private` | Unlisted/foreign entity (Zepto, OpenAI JV) | Skipped — name preserved as thematic target |
| `sector` | Broad theme ("quick-commerce ecosystem") | Skipped — preserved as thematic target |
| `macro` | Macroeconomic event (RBI rate, crude move) | Skipped — preserved as thematic target |
| `policy` | Government/regulatory action (PLI, SEBI rule) | Skipped — preserved as thematic target |

The `sector_theme` field on every signal captures the broader investment theme for listed/private entities (e.g. "green energy capex" on an NTPC signal). This flows into the evidence card and helps the analyst identify cross-stock thematic clusters.

**Three-pass ticker resolution for listed entities:**
1. Pass 0: Direct NSE symbol match (`KOTAKBANK` → `KOTAKBANK.NS`)
2. Pass 1: Alias dict (`"kotak bank"`, `"sbi"`, `"tcs"` ...)
3. Pass 2: Fuzzy match at threshold 82

If all three passes fail, the signal is preserved with `ticker=null` and `entity_type=listed` — it surfaces as an unresolved listed signal in the output stats.

---

## 8. Proxy Mapping (Phase D)

### Problem

After Phase B, roughly 40–60 thematic targets exist: private companies, sector trends, macro events. These have high signal value but no NSE ticker, so Phase C cannot process them.

### Solution

For each thematic target, one LLM call asks: *"which 3–5 NSE-listed Indian companies are most directly impacted by this theme/entity?"* The LLM returns company names with relationship type (beneficiary, competitor, supplier, customer, proxy), impact direction (positive/negative/neutral), and confidence level.

### Resolution

Each returned company name goes through `lookup_ticker(name, threshold=82)` — the same fuzzy engine as Phase B. Unresolved names are dropped (better to miss than to hallucinate a ticker).

### Merge logic

- **Ticker already in listed_targets**: append a `proxy_links` entry with theme source, relationship, impact, confidence, reason
- **New ticker**: create a new listed_target entry with `score = theme_relevance × 0.6 × impact_sign`, `selected_for_phase_c=True` (forced — themes are high-signal even at low score)

After merging, all listed_targets are re-ranked by `|final_score|`.

### Why score damping = 0.6

A proxy ticker's signal is second-order: the theme mentions the underlying entity, not the listed company directly. 0.6 damping reflects that the listed company's exposure to the theme is inferred, not directly evidenced. The result: proxy tickers enter the candidate pool but rank below directly-mentioned stocks with similar scores.

---

## 9. Evidence Card Aggregation (Phase E)

Phase C produces 8 separate JSON files per ticker. Phase E assembles them into one analyst-ready card.

**Key computed fields (not in raw Phase C output):**

| Field | Computation |
|---|---|
| `price_vs_52w_high_pct` | `(price / 52w_high - 1) × 100` — how far from peak |
| `max_drawdown_1y_pct` | `min(daily_return_pct)` over 1-year OHLCV history |
| `sentiment_score` | `Σ (severity_weight × sentiment_sign)` over key_signals |
| `signal_density` | `signal_count / source_count` — signals per source (high density = concentrated attention) |

**Screener.in file lookup** uses a one-time index built from all screener files: slugified company name → filepath. Fallback: first-6-characters prefix match on the slug. This is needed because screener saves files as `{company_slug}_{hash}.json` — the hash is not predictable from the ticker.

**Data gaps** are recorded explicitly: if a Phase C module returned no file for a ticker, its name goes into `evidence_card.data_gaps`. The analyst prompt instructs the LLM to lower conviction by one notch when data_gaps is non-empty.

---

## 10. Stock Analyst Decision Rules (Phase F)

The analyst LLM is given strict decision rules in the system prompt — not left to its own judgment:

**Recommendation thresholds:**

| Recommendation | Conditions |
|---|---|
| `invest` | positive `sentiment_score` AND (`revenue_cagr_5y > 8%` OR `profit_cagr_5y > 10%`) AND ≥2 distinct sources |
| `avoid` | sharply negative `sentiment_score` OR fundamental red flags (negative profit growth, high P/E with declining ROE, regulatory action) |
| `watch` | real signal but conviction insufficient — low source count, mixed sentiment, or data gaps |

**Conviction thresholds:**

| Conviction | Conditions |
|---|---|
| `high` | ≥3 distinct sources AND regime favored sector AND no material data_gaps |
| `medium` | some triangulation but missing one of: source diversity / regime alignment / fundamentals |
| `low` | single source, conflicting signals, or major data_gaps |

Non-empty `data_gaps` automatically lowers conviction by one notch (high→medium, medium→low).

**Price action** is portfolio-flag-aware: if `portfolio_flag="held"`, only `hold` or `exit` are allowed. For `none/watchlisted/avoided`: `buy_now`, `wait_for_dip`, or `n/a`.

**Sources cited**: analyst must include 1–3 actual URLs from `evidence_card.signals.key_claims[*].url`. Invented URLs are not allowed per prompt rule.

---

## 11. CIO Synthesis (Phase G1)

### The gap Phase F leaves

Phase F analysts each see exactly one evidence card. They cannot see that 7 of 12 invest calls are in Industrials, or that NTPC and CESC are both high-conviction buys for the same power-demand theme (redundant portfolio exposure), or that the regime is cautious but 70% of calls are bullish (tension to flag).

### Single LLM call over all views

The CIO prompt receives a compressed table of all analyst views (one line per ticker: ticker | sector | recommendation | conviction | price_action | thesis[:80]) plus the regime snapshot and portfolio holdings.

Token budget: ~30 views × ~100 tokens = ~3K tokens input, ~500 output. One call.

### What the CIO is explicitly forbidden from doing

The prompt rule: *"Do NOT re-analyze stocks — the analysts already did that."* The CIO's job is synthesis over the full set, not re-judging individual stocks. This keeps the output honest (it can only reference what the analysts already established) and keeps the call cheap.

### Top picks selection criteria (in priority order)

1. Regime alignment — favored-sector stocks rank higher, all else equal
2. Theme de-duplication — if two stocks serve the same thesis, pick the stronger proxy
3. Sector concentration — avoid picking >40% from one sector
4. Portfolio overlap — skip if user already holds a stock with the same investment thesis
5. Catalyst immediacy — a high-conviction watch with an imminent catalyst can outrank a generic invest

### Fallback behaviour

If the CIO LLM call fails or hasn't run, `report_synthesizer.py` generates the report without the "Today's Action Plan" section. The rest of the report is unchanged. No code modification needed — the section builder returns an empty string if `cio_synthesis_{date}.json` does not exist.
