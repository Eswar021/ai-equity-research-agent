# AI Equity Research Agent — System Architecture

> An automated, multi-layer pipeline that ingests financial news and market data, applies LLM-based analysis, and produces daily investment research reports with actionable buy/watch/avoid recommendations.

---

## System Overview

```mermaid
flowchart TD
    classDef source fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef layer fill:#1a3a2a,stroke:#4caf50,color:#fff
    classDef llm fill:#3a1a3a,stroke:#9c27b0,color:#fff
    classDef output fill:#3a2a1a,stroke:#ff9800,color:#fff
    classDef store fill:#2a2a2a,stroke:#888,color:#fff

    subgraph INPUTS["DATA SOURCES"]
        N1["🗞 Financial News\nMoneycontrol · Economic Times\nRSS Feeds × 7 · NewsData.io\nMediaStack · Gmail Newsletters"]
        N2["📊 Market Data\nIndia Macro · US Macro\nFII/DII Flows · F&O Chain\nBulk Deals"]
        N3["🎬 Alternative Data\nYouTube Transcripts"]
    end

    subgraph PIPELINE["11-LAYER PIPELINE"]
        L0["L0 · Manifest\nConfig snapshot"]:::layer
        L1["L1 · Scraping\n600+ records/day · 8 parallel workers"]:::layer
        L2["L2 · Dedup + Quality\nSHA-256 dedup · Stale filter · Reliability scoring"]:::layer
        L3["L3 · Intelligence Extraction ⚡LLM\n400 parallel calls · Entity · Signal · Theme extraction"]:::llm
        L4["L4 · Memory Recall\nEntity/theme index lookup · Relevance scoring"]:::layer
        L5["L5 · Hypothesis Generation ⚡LLM\n50 parallel calls · One hypothesis per signal group"]:::llm
        L6["L6 · Target Selection\nMulti-factor scoring · Dedup · Bucket into deep_dive / watchlist"]:::layer
        L7["L7 · Deep Dive Data Collection\nyfinance · screener.in · NSE API"]:::layer
        L8["L8 · Evidence Builder\nNews matching · Gap detection · Packet assembly"]:::layer
        L9["L9 · Specialist Analysis ⚡LLM\n4 agents × 7 targets · 28 parallel calls"]:::llm
        L10["L10 · Final Report ⚡LLM\nComposite scoring · 2 agents × 7 targets · Report generation"]:::llm
    end

    subgraph OUTPUTS["OUTPUTS"]
        O1["📄 final_report.md\nMarkdown investment report"]:::output
        O2["📋 watchlist_actions.json\nEntry · Stop · Bull/Base/Bear scenarios"]:::output
        O3["🧠 Memory DB\ndb/memory/*.jsonl\nBuilds over time across runs"]:::store
    end

    N1 & N2 & N3 --> L0
    L0 --> L1 --> L2 --> L3 --> L4 --> L5 --> L6 --> L7 --> L8 --> L9 --> L10
    L10 --> O1 & O2 & O3
```

---

## Layer-by-Layer Architecture

### L0 — Manifest

Reads all config YAMLs at run start and writes a single `run_manifest.json` snapshot. Every downstream layer reads config exclusively from this file — ensures all layers run against the same config even if YAMLs change mid-day.

```
src/config/
├── l1_sources.yaml      → scraper URLs, API keys, query strings
├── l2_filters.yaml      → stale thresholds, reliability tiers
├── l3_config.yaml       → LLM provider/model, batch sizes
├── l5_config.yaml       → grouping weights, hypothesis limits
├── l6_config.yaml       → scoring weights, target caps
├── l7_config.yaml       → ticker resolution, data source limits
├── l9_config.yaml       → LLM provider/model, parallel workers
└── l10_config.yaml      → composite weights, recommendation thresholds
```

---

### L1 — Scraping Layer

Runs all scrapers in parallel via `ThreadPoolExecutor(max_workers=8)`. Each scraper is an independent module exposing a single `collect(cfg: dict) → list[dict]` interface.

```mermaid
flowchart LR
    classDef scraper fill:#1e3a5f,stroke:#4a90d9,color:#fff

    subgraph SCRAPERS["12 PARALLEL SCRAPERS"]
        direction TB
        S1["Moneycontrol\nHTML scraper · 5 categories\nmarkets · stocks · earnings\neconomy · companies"]:::scraper
        S2["Economic Times\nHTML scraper · 3 sections\nstocks_news · expert_view\nstocks_recos"]:::scraper
        S3["RSS Feeds\n7 feeds\nMint · NDTV Profit · ET\nMoneycontrol · Hindu Biz\nYahoo Finance IN\nInvesting.com IN"]:::scraper
        S4["NewsData.io API\n4 queries\nNSE/BSE market · Earnings\nRBI/inflation · FII/DII flows"]:::scraper
        S5["MediaStack API\n2 queries\nNifty/Sensex · NSE earnings"]:::scraper
        S6["Gmail API\nNewsletter scraper\nMint Briefing · Zerodha Pulse\nMorningstar · Hindu Business"]:::scraper
        S7["YouTube\nChannel transcripts\nAuto-captioning via yt-dlp"]:::scraper
        S8["India Macro\nNifty daily change\nFII/DII net flows\nMarket breadth"]:::scraper
        S9["US Macro\nS&P 500 · DXY\nVIX · 10Y Treasury yield"]:::scraper
        S10["FII/DII\nDaily institutional flows\nBSE + NSE combined"]:::scraper
        S11["Bulk Deals\nNSE bulk deal data\nQty · Price · Buy/Sell"]:::scraper
        S12["F&O Data\nNIFTY + BANKNIFTY\nOptions chain · OI · PCR"]:::scraper
    end

    SCRAPERS --> OUT["raw_records.json\n600+ records/day\n5 source_types:\nnews_article · market_snapshot\ncorporate_action · newsletter\nvideo_transcript"]
```

**Record schema:** Every scraper output follows a standard format — `source`, `source_type`, `title`, `url`, `published_at` (ISO-8601 IST), `content` (full text), `metadata`.

---

### L2 — Dedup + Quality Filter

Zero LLM calls. Deterministic filtering in a single pass.

```mermaid
flowchart LR
    IN["~600 raw records"] --> D1

    D1{"SHA-256\ncontent hash\nalready seen?"}
    D1 -- duplicate --> DROP1["❌ Drop\n~50 dupes/day"]
    D1 -- unique --> D2

    D2{"published_at\n> 48 hours ago?"}
    D2 -- stale + not market_snapshot\nor corporate_action --> DROP2["❌ Drop\n~8 stale/day"]
    D2 -- fresh or exempt --> D3

    D3["Source reliability\ntier assignment\nhigh: Moneycontrol · ET\nmedium: RSS · NewsData\nlow: MediaStack · Bulk"]

    D3 --> D4["Flag: low_content\nif len(content) < 100 chars"]
    D4 --> D5["Quality tier:\nhigh = reliable + no flags\nmedium = mixed\nlow = unreliable or flagged"]
    D5 --> OUT["filtered_records.json\n~550 records/day"]
```

---

### L3 — Intelligence Extraction *(LLM)*

The most compute-intensive layer. Every article gets read by the LLM to extract structured investment signals.

```mermaid
flowchart TD
    IN["~550 filtered records"]

    IN --> PART["Partition by content length"]
    PART --> SKIP["market_snapshot +\ncorporate_action\n→ derive entities\nfrom metadata (no LLM)"]
    PART --> SHORT["Short records\n< 800 chars\nbatch up to 5 per call"]
    PART --> LONG["Long records\n≥ 800 chars\n1 call per record"]

    SHORT & LONG --> POOL["ThreadPoolExecutor\n15 parallel workers\n~400 LLM calls/day"]

    POOL --> EXTRACT["Per-record extraction\nvia LangChain + Pydantic"]

    subgraph SCHEMA["EXTRACTED SCHEMA"]
        direction TB
        E1["entities[]\nname · type · investable\nsignal_type · context"]
        E2["facts[]\ntext · entity\ntime_reference"]
        E3["events[]\ntype · entity · impact"]
        E4["themes[]\nname · relevance"]
        E5["market_signals[]\ntype · direction\nmagnitude · entity"]
        E6["confidence\nlow / medium / high"]
    end

    EXTRACT --> SCHEMA
    SCHEMA --> OUT["enriched_records.json\n~550 enriched records\n+ llm_calls.jsonl\n(full audit log)"]
```

**LLM providers supported:** OpenAI (GPT models), Google Gemini, LM Studio (local models via OpenAI-compatible API).

---

### L4 — Memory Recall

Rule-based. Looks up past investment decisions stored in `db/memory/` to surface historical context for current signals.

```mermaid
flowchart LR
    REC["enriched_records.json\n~550 records"]
    MEM["db/memory/\nwatch_memory.jsonl\nentity_memory_index.json\ntheme_memory_index.json"]

    REC --> COLLECT["Collect all unique\nentities + themes\nacross all records"]
    MEM --> IDX["Index lookup\nentity name → memory_ids\ntheme name → memory_ids"]

    COLLECT --> IDX
    IDX --> RECALL["Recall matching\nmemory records"]
    RECALL --> SCORE["Score each candidate:\nrelevance × recency × quality"]
    SCORE --> OUT["memory_context.json\nrecords + recalled_memory[]\n(0 on first run, grows\nover time with each run)"]
```

---

### L5 — Hypothesis Generation *(LLM)*

Groups enriched records into signal clusters, detects market regime, and generates one investment hypothesis per group.

```mermaid
flowchart TD
    IN["memory_context.json\n~550 records + past context"]

    IN --> GRP["GROUP RECORDS"]

    subgraph GROUPING["GROUPING STRATEGY"]
        G1["Theme-centric groups\nAll records sharing a theme\neg. 'banking sector rally'"]
        G2["Entity-centric groups\nOrphan entities not\ncovered by any theme\neg. 'Honasa Consumer'"]
    end

    GRP --> GROUPING

    GROUPING --> WEIGHT["Weight each group:\nsignal_count × 2\n+ source_diversity × 5\n+ freshness_bonus\n→ weight_score"]

    WEIGHT --> TOP["Top 50 groups\nby weight_score"]

    IN --> REGIME["Market Regime Detection\nScan market_snapshot records\nbull / bear / sideways / uncertain\n→ market_regime.json"]

    TOP --> LLM["ThreadPoolExecutor\n50 parallel LLM calls"]

    subgraph HYP["PER-HYPOTHESIS OUTPUT"]
        H1["hypothesis (investment thesis text)"]
        H2["time_horizon\nintraday · short_term\nmedium_term · long_term"]
        H3["strength: strong / medium / weak"]
        H4["beneficiaries[] (ticker names)"]
        H5["deep_dive_questions[]"]
        H6["invalidating_conditions[]"]
    end

    LLM --> HYP
    HYP --> OUT["hypotheses.json\n50 hypotheses\n+ llm_calls.jsonl"]
```

---

### L6 — Target Selection

Rule-based multi-factor scoring. Selects the 7 best targets for expensive deep-dive research.

```mermaid
flowchart LR
    IN["hypotheses.json\n50 hypotheses"]

    IN --> SCORE["MULTI-FACTOR SCORING\n\nstrength_score: strong=30 · medium=15 · weak=5\nsignal_volume: count×2 · capped at 30\nsource_diversity: sources×5 · capped at 20\nregime_alignment: 5-20 based on market regime\nweight_bonus: L5 weight_score÷150 · capped at 10\n─────────────────────────────────────────\nmax possible score: 110"]

    SCORE --> DEDUP["Entity deduplication\nFuzzy name matching\nStrip: Ltd · Corp · Inc\nKeep higher-scoring variant"]

    DEDUP --> BUCKET["BUCKET ASSIGNMENT\n\n≥ 55 → deep_dive (max 7)\n30–54 → watchlist\n< 30 → skip"]

    BUCKET --> OUT["selected_targets.json\n7 deep_dive targets\n+ watchlist candidates"]
```

---

### L7 — Deep Dive Data Collection

No LLM. Collects real market and fundamental data for each of the 7 selected targets.

```mermaid
flowchart TD
    IN["selected_targets.json\n7 deep_dive targets"]

    IN --> RESOLVE["TARGET RESOLVER\n\nDirect company → NSE symbol fuzzy match\n(2,235 NSE symbols, auto-refresh weekly)\n\nSector keyword → sector ETF + top 5 constituents\neg. 'Banking sector' → HDFCBANK · ICICIBANK · SBIN · AXISBANK · KOTAKBANK\n\nCommodity keyword → proxy tickers\neg. 'Oil price volatility' → RELIANCE · ONGC · BPCL · GAIL · IOC\n\nUnresolved → macro theme (no tickers, skip price data)"]

    RESOLVE --> COLLECT["PER-TICKER DATA COLLECTION\n(parallel across targets)"]

    subgraph DATA_SOURCES["3 DATA SOURCES PER TICKER"]
        YF["yfinance API\n────────────────\nCurrent price · 52w high/low\nRSI(14) · 50-DMA · 200-DMA\nVolume ratio · Float shares\nAnalyst consensus:\n count · mean target\n upside % to target"]
        SCR["screener.in scraper\n────────────────\nMarket cap · P/E TTM · P/B\nROE · ROCE · Dividend yield\nRevenue + PAT growth (TTM YoY)\nQuarterly trend: last 4 quarters\n (revenue · PAT · OPM%)\nOwnership:\n promoter% · pledge%\n FII% · DII% · FII QoQ change\nTop 4 peer comparisons"]
        NSE["NSE Corporate API\n────────────────\nCorporate actions:\n dividends · splits · rights\nRecent filings (3 months):\n board meetings · results\n shareholding changes"]
    end

    COLLECT --> DATA_SOURCES

    DATA_SOURCES --> OUT["target_evidence_bundles.json\n7 bundles · one per target\n14+ tickers collected in parallel"]
```

---

### L8 — Evidence Builder

Assembles self-contained evidence packets so L9 agents never need to look backwards in the pipeline.

```mermaid
flowchart LR
    subgraph INPUTS_L8["INPUTS FROM 4 LAYERS"]
        I1["L4: enriched records\n+ recalled memories"]
        I2["L5: hypothesis text\n+ invalidating conditions"]
        I3["L6: target score\n+ score breakdown"]
        I4["L7: ticker market data\n+ fundamentals + ownership"]
    end

    INPUTS_L8 --> BUILD

    subgraph BUILD["PACKET ASSEMBLY"]
        NM["news_matcher\nMatch enriched records to target\nby entity name + ticker symbol\nTop 15 articles by relevance"]
        GD["gap_detector\nIdentify missing critical fields\neg. roe_pct · nim_pct · net_npa_pct\nFlag impact on analysis quality"]
        PC["past_context\nInject recalled L4 memories\n(historical price targets,\nprevious thesis outcomes)"]
    end

    BUILD --> OUT["evidence_packets.json\n7 self-contained packets\n\nEach packet contains:\n✓ Full thesis text\n✓ Market data (price · RSI · DMAs)\n✓ Fundamentals (ROE · PE · growth)\n✓ Ownership structure\n✓ 15 supporting news articles\n✓ Evidence gaps list\n✓ Macro context (FII/DII · regime)"]
```

---

### L9 — Specialist Analysis *(LLM × 4 agents)*

The core analytical engine. Four independent LLM agents assess each target from different angles.

```mermaid
flowchart TD
    IN["evidence_packets.json\n7 targets"]

    subgraph PHASE1["PHASE 1 — 3 agents × 7 targets = 21 parallel calls"]
        FA["Fundamental Agent\n────────────────────\nInput: ROE · ROCE · revenue growth\nPAT growth · quarterly_trend\nmoat indicators from news\n\nOutput:\nscore (0–100)\nverdict: strong · adequate · weak\nrevenue_quality\nmargin_trend\nmoat_indicators[]\nconcerns[]"]

        VA["Valuation Agent\n────────────────────\nInput: P/E · P/B · analyst targets\nupside % · peer P/E\n\nOutput:\nscore (0–100)\nverdict: undervalued · fairly_valued\n overvalued · insufficient_data\npe_analysis · pb_analysis\nupside_to_consensus_target\nmargin_of_safety"]

        RA["Risk Agent\n────────────────────\nInput: ownership (promoter% · pledge%)\nFII flows · RSI · DMA position\nevidence gaps\n\nOutput:\nscore (0–100, higher = riskier)\nverdict: low · medium · high\nred_flags[]\nkey_findings[]\n\n+ Post-processing risk floor:\nif promoter=null AND roe=null → ≥70\nif promoter=null OR roe=null → ≥60"]
    end

    IN --> PHASE1

    subgraph PHASE2["PHASE 2 — 1 agent × 7 targets = 7 parallel calls\n(runs after Phase 1 completes, receives Phase 1 results as context)"]
        TV["Thesis Validation Agent\n────────────────────\nInput: hypothesis text + Phase 1 scores\nsupporting news (15 articles)\ndeep_dive_questions + invalidating_conditions\n\nOutput:\nscore (0–100)\nverdict: strongly_supported · supported\n contradicted · insufficient_data\nconviction_level: high · medium · low\nquestion_answers[] (per deep_dive_question)\ninvalidation_check[] (per condition, with status)"]
    end

    PHASE1 --> PHASE2
    PHASE2 --> OUT["scorecards.json\n7 scorecards\n28/28 LLM calls\n+ llm_calls.jsonl (full audit)"]
```

---

### L10 — Final Report *(LLM + rule-based composite)*

Combines 4 specialist scores into a composite, generates human-readable analysis, and writes the investment report.

```mermaid
flowchart TD
    IN["scorecards.json\n7 scorecards"]

    subgraph COMPOSITE["RULE-BASED COMPOSITE SCORING (no LLM)"]
        CS["composite = 0.25 × Fundamental\n           + 0.20 × Valuation\n           + 0.20 × Thesis\n           + 0.20 × (100 − Risk)\n           + 0.15 × Market_Alignment\n\nMarket_Alignment = regime_base_score\n    + thesis_strength_adj  (strong:+10 · weak:-10)\n    + fii_adj              (|FII flow| > 500cr: ±10)\n\nregime_base: bull=75 · sideways=50 · bear=25"]

        REC["RECOMMENDATION TIERS\n\ncomposite ≥ 70  →  STRONG BUY\ncomposite 62-69 →  BUY\ncomposite 55-61 →  WATCH\ncomposite < 55  →  AVOID\n\nOverride: thesis verdict = contradicted\n          → always AVOID"]
    end

    IN --> COMPOSITE

    subgraph LLM_PHASE["LLM SYNTHESIS (2 phases, parallel)"]
        SYN["Phase 1 · Synthesis Agent × 7 targets\n────────────────────────────────\nInput: all 4 specialist assessments\n       composite score · market context\n\nOutput:\ninvestment_narrative (3-4 paragraphs)\nrecommendation\nentry_price_range (specific ₹ range)\nstop_loss_guide (specific ₹ level)\nposition_sizing_note\nexit_triggers[] (3-5 invalidation events)\ncatalysts[] (3-5 near-term catalysts)"]

        SCN["Phase 2 · Scenarios Agent × 7 targets\n(skipped for macro themes with no tickers)\n────────────────────────────────\nInput: current price data · synthesis\ntime_horizon (calibrates target range)\n\nshort_term  → ±5-8% from current\nmedium_term → 25-40% of analyst upside\nlong_term   → full analyst consensus target\n\nOutput:\nbull_case + bull_price_target + probability_bull\nbase_case + base_price_target + probability_base\nbear_case + bear_price_target + probability_bear"]
    end

    COMPOSITE --> LLM_PHASE

    LLM_PHASE --> OUT1["final_report.md\nMarkdown report with:\n• Market header (regime · FII · Nifty)\n• Summary table (rank · score · rec)\n• Per-target: thesis · entry · stop\n  narrative · scenarios · invalidation"]

    LLM_PHASE --> OUT2["watchlist_actions.json\nMachine-readable:\n• entry_price_range · stop_loss\n• bull/base/bear ₹ targets\n• probabilities · position_sizing\n• exit_triggers · catalysts"]

    LLM_PHASE --> OUT3["db/memory/watch_memory.jsonl\nWrites investment decisions\nback to memory DB for\nfuture run recall (L4)"]
```

---

## Full Data Flow

| Layer | Input | Output | LLM Calls | ~Time |
|-------|-------|--------|-----------|-------|
| L0 Manifest | 9 config YAMLs | run_manifest.json | — | 1s |
| L1 Scraping | 12 live sources | 600+ raw records | — | 4–5 min |
| L2 Dedup/Quality | 600 records | ~550 filtered | — | 2s |
| L3 Intelligence | 550 records | 550 enriched | ~400 parallel | 8–12 min |
| L4 Memory | 550 enriched | 550 + recalled context | — | 3s |
| L5 Hypothesis | 550 records | 50 hypotheses | 50 parallel | 3–5 min |
| L6 Target Select | 50 hypotheses | 7 deep-dive targets | — | 1s |
| L7 Deep Dive | 7 targets | 7 evidence bundles | — | 30s |
| L8 Evidence | 4 upstream files | 7 packets | — | <1s |
| L9 Specialist | 7 packets | 7 scorecards | 28 parallel | 5 min |
| L10 Final Report | 7 scorecards | report + watchlist | 14 parallel | 2 min |
| **Total** | | | **~492 calls** | **~35–40 min** |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| LLM Orchestration | LangChain (prompt templates, structured output, parallel chains) |
| LLM Providers | OpenAI GPT · Google Gemini · LM Studio (local, OpenAI-compatible) |
| Structured LLM Output | Pydantic v2 (schema-enforced JSON responses) |
| Parallel Execution | `concurrent.futures.ThreadPoolExecutor` |
| Web Scraping | `requests` + `BeautifulSoup4` |
| Market Data | `yfinance` (prices, technicals, analyst consensus) |
| Fundamental Data | screener.in (scraper) |
| Corporate Data | NSE corporate API |
| News APIs | NewsData.io · MediaStack · Gmail API · YouTube Data API |
| RSS Parsing | `feedparser` |
| Memory/Storage | JSONL flat files + JSON indexes (`db/memory/`) |
| Config Management | YAML → JSON manifest snapshot per run |
| Output | Markdown report + JSON machine-readable watchlist |

---

## Output Sample

**Daily Report Summary Table:**

| Rank | Target | Score | Rec | F | V | R | T | MA |
|------|--------|-------|-----|---|---|---|---|----|
| 1 | HDFC Bank | 65 | BUY | 78 | 78 | 62 | 72 | 50 |
| 2 | ICICI Bank | 64 | BUY | 72 | 82 | 72 | 82 | 50 |
| 3 | Honasa Consumer | 62 | BUY | 84 | 58 | 77 | 86 | 50 |
| 4 | Banking Sector | 61 | WATCH | 62 | 82 | 72 | 78 | 50 |
| 5 | Axis Bank | 61 | WATCH | 62 | 80 | 68 | 78 | 50 |
| 6 | Oil Price Volatility | 61 | WATCH | 74 | 72 | 72 | 74 | 50 |
| 7 | Geopolitical Risk | 47 | AVOID | 72 | 0 | 72 | 78 | 50 |

*F=Fundamental · V=Valuation · R=Risk · T=Thesis · MA=Market Alignment*

**Per-target output includes:** Investment narrative (3-4 paragraphs), specific ₹ entry range, stop-loss level with rationale, position sizing guidance, 3-5 exit triggers, 3-5 catalysts, and bull/base/bear price scenarios with probabilities.
