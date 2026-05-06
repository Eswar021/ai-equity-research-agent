# Eswar_Work

stock_researcher.mdFileCONTEXT_LAYER.mdFileOkay, I have built the context collection layer. You can check the high level overview of that in contextlayer.md file. And you can check the logics and example outputs in stockresearch.md file where you will see all my code structure and logic in that file. So check and tell me whether it is good or not, and if it is good, how to proceed further, like in next layer, what are the things we need to do? And also, if we are properly extracting or not, check. Since the outputs are very long, I have like only provided the samples of it. Okay, check like since it is like a stock research analysis like a agent we are designing. I think, for example, if there is an like a stock investor, wait, in his perspective, what are all the things he will consider, what are all the uh data he will look into, right? And also, since we are like in this layer, we are like extracting the raw data, right? We need to somehow like uh convert this raw data into like something useful, right? We can't just pass this entire raw data, right? So how in processing layer, how exactly we are we are going to convert this data? And we don't need to convert everything, right? Some we need to pass them as it is, right? So the things that we need to convert, right, what are all the things, what are all the data that we need to convert, right? What are all the operations we have to do? And for which outputs we need to pass them as it is in the downstream LLMs or agents. And also, we have to keep in mind about the agents also, like what are all the agents we have to do, we have to build, right? And which agent has to take what type of outputs. So that all depends on this processing or whatever this layer we call it as. So here we'll do like context building, like extracting proper data one by one, these kind of things. So properly tell me, research and tell me exactly what we will do, whether the context layer we built is enough or not, and what else we can do, and what are our next steps, keeping our future entire project, keeping in mind and we have to build this, right? So tell me exactly, do some research, think deeply, and tell me.
Yes — your **context collection layer is good and clearly going in the right direction**. I checked both uploaded files. Your current layer already covers the main evidence sources an investment research system needs: Indian fundamentals, US fundamentals, market data, macro, institutional flows, F&O, news, RSS, newsletters, YouTube transcripts, ticker extraction, filings, analyst estimates, and persistent history. Your own `CONTEXT_LAYER.md` also correctly states that this layer’s goal is only to **extract raw data and save structured JSON**, with “no aggregation, no calculations, no analysis” in this layer. That separation is correct.


Your project structure also shows that you already have sample outputs for most important modules: Reliance analyst estimates, corporate actions, exchange filings, filing docs, peer comparison, market snapshots, macro data, FII/DII, F&O, RSS feeds, news APIs, web scrapers, SEC filings, ticker extraction, and YouTube transcript outputs. That means the context layer is no longer theoretical; it is producing actual artifacts.


Now the next layer should be the **Processing + Context Building Layer**.


---


# 1. My verdict on your current context layer


## Overall: good enough to proceed


Your context layer is strong because it covers the three big pillars of investment research:


```
1. Business quality
   - screener.in financials
   - SEC filings
   - peer comparison
   - analyst estimates
   - corporate actions
   - exchange filings
   - concall transcripts

2. Market behavior
   - current price
   - price history
   - volume
   - 52-week range
   - index/macro data
   - F&O data
   - FII/DII flows

3. Narrative / event context
   - news APIs
   - Moneycontrol
   - Economic Times
   - RSS
   - newsletters
   - YouTube transcripts
   - generic web scraper
```


That is exactly the right collection scope for a stock research agent.


Your module grouping is also good. You separated Indian company fundamentals, US fundamentals, market data, institutional activity, news/information, utilities, and persistent history.


---


# 2. Are you properly extracting data?


Mostly yes, but with one important point: you are **properly extracting raw/source-level data**, not yet **analysis-ready data**.


That is fine because your context layer is not supposed to analyze.


For example, your market snapshot output for Reliance is clean and useful. It includes ticker, name, exchange, currency, price, daily change, 52-week high/low, 1M/3M/1Y returns, volume, market cap, sector, industry, and fetched timestamp. That is a good extraction output.


Your ticker extraction output also looks directionally correct because it maps company names to NSE tickers, such as Reliance Industries Limited to `RELIANCE.NS` and Tata Consultancy Services Limited to `TCS.NS`.


Your news extraction is also reasonable. Moneycontrol and Economic Times collectors fetch today’s articles, verify publish date, and return title, author, published time, URL, and full body text. Your RSS collector correctly handles headline/summary-level data, and your documentation clearly says RSS does not contain full article bodies, so full text should be fetched through `generic.py` or `browser_scraper.py`.


Your filing layer is also good. You are collecting NSE announcements, concall transcripts, and investor presentations. This is very important because transcripts contain management commentary, strategy, Q&A, margin discussion, capex discussion, and guidance signals. Your design correctly notes that `last_n=4` transcripts means one year of earnings calls.


So the extraction layer is **good**.


But now you need to stop thinking in terms of “raw data” and start thinking in terms of **investment evidence objects**.


---


# 3. What is missing in the context layer?


You do not need many new collectors immediately. Your bigger missing part is **standardization and processing**.


Still, I would add or improve these items before going too far:


## A. Add a common metadata wrapper for every output


Right now, every module has a slightly different JSON shape. That is okay for extraction, but difficult for agents.


Every output should eventually become this common structure:


```
{
  "source_id": "",
  "source_type": "",
  "source_name": "",
  "market": "India / US / Global",
  "ticker": "",
  "company_name": "",
  "url": "",
  "published_at": "",
  "fetched_at": "",
  "raw_payload_path": "",
  "clean_text": "",
  "structured_data": {},
  "source_reliability": "high / medium / low",
  "freshness_status": "fresh / stale / historical",
  "extraction_status": "success / partial / failed",
  "data_quality_score": 0.0
}
```


This should not replace your raw files. Keep raw files as they are. But create a **normalized version** for downstream agents.


---


## B. Add source reliability scoring


Not all data should be treated equally.


Use something like:


```
High reliability:
- SEC filings
- NSE filings
- company investor presentation
- earnings call transcript
- exchange announcements
- official macro data

Medium reliability:
- Moneycontrol
- Economic Times
- analyst estimates
- established news APIs
- RSS from known publishers

Low reliability:
- YouTube transcript
- newsletters
- blogs
- generic scraped websites
- social media, if added later
```


The LLM should know this. A YouTube claim should not override an NSE filing.


This is important because investment decisions depend on source quality. CFA Institute’s financial statement analysis guidance also emphasizes understanding the company’s business model, financial performance, financial position, economic environment, and industry context — not just isolated commentary. [CFA Institute](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/introduction-financial-statement-analysis?utm_source=chatgpt.com)


---


## C. Add deduplication


Your system may collect the same story from:


```
- RSS
- Moneycontrol
- Economic Times
- NewsData.io
- Mediastack
- generic scraper
```


The processing layer should identify duplicate or near-duplicate articles.


Create a `content_hash` and maybe `canonical_event_id`.


Example:


```
{
  "event_id": "RELIANCE_2026-05-02_Q4_RESULTS",
  "duplicate_sources": [
    "moneycontrol",
    "economic_times",
    "rss"
  ],
  "canonical_summary": "Reliance reported Q4 results and announced dividend."
}
```


This prevents the model from thinking the same event is multiple separate signals.


---


## D. Add freshness checks


Your docs correctly identify that some modules have full history and some are today-only/live-only, especially FII/DII, bulk deals, and F&O data.


Now the processing layer should label every data point:


```
fresh
stale
historical
market-hours-only
missing
partial
```


For example:


```
{
  "module": "fno_data",
  "freshness_status": "market-hours-only",
  "usable_for": "short-term sentiment only",
  "do_not_use_for": "long-term investment thesis"
}
```


---


# 4. What should the next layer do?


The next layer should be called:


```
processing_layer/
```


or better:


```
intelligence_prep_layer/
```


Its job:


```
Raw collected data
   ↓
Clean + normalize
   ↓
Extract entities/events/metrics
   ↓
Calculate derived indicators
   ↓
Create compact evidence cards
   ↓
Build agent-specific context packets
```


Your current context layer answers:


```
“What data did we collect?”
```


The processing layer should answer:


```
“What does this data mean in structured form?”
```


Not final recommendation yet. Just structured meaning.


---


# 5. What data should be converted vs passed as-is?


This is the most important part.


## A. Data that should be converted


### 1. Price history


Do not pass full OHLCV history to the LLM.


Your sample output shows that some history files are very large — for example, `INFY_NS_history_max` has 7,613 records and is over 1 MB.


Convert price history into features:


```
{
  "ticker": "RELIANCE.NS",
  "price_features": {
    "current_price": 1436,
    "return_1d": 0.74,
    "return_1m": 6.47,
    "return_3m": 3.64,
    "return_1y": 0.36,
    "distance_from_52w_high_pct": -10.91,
    "distance_from_52w_low_pct": 11.32,
    "volatility_30d": "",
    "max_drawdown_1y": "",
    "trend_status": "sideways / bullish / bearish",
    "volume_spike": true
  }
}
```


Pass the summary features, not full daily rows.


---


### 2. Screener financial tables


Do not pass full P&L, balance sheet, cash flow tables directly.


Convert them into:


```
{
  "fundamental_features": {
    "sales_growth_3y_cagr": "",
    "sales_growth_5y_cagr": "",
    "profit_growth_3y_cagr": "",
    "operating_margin_trend": "improving / stable / declining",
    "roe_trend": "improving / stable / declining",
    "debt_to_equity_trend": "increasing / stable / decreasing",
    "free_cash_flow_quality": "strong / weak / inconsistent",
    "cash_conversion": "good / poor",
    "promoter_holding_trend": "increasing / stable / decreasing",
    "pledge_risk": "yes / no / unknown",
    "fii_dii_holding_trend": "accumulation / distribution / stable"
  }
}
```


Your docs already mention that Screener data includes 10-year P&L, balance sheet, cash flow, ratios, growth metrics, and shareholding patterns. It also correctly states that shareholding trends should be computed in the processing layer.


---


### 3. Analyst estimates


Do not pass the full analyst estimate object as raw JSON.


Convert it into:


```
{
  "analyst_signal": {
    "mean_target_upside_pct": 18.8,
    "coverage_count": 32,
    "recommendation_bias": "bullish",
    "eps_revision_90d": "negative",
    "earnings_surprise_trend": "deteriorating",
    "estimate_quality": "high_coverage",
    "risk_note": "analysts remain bullish but EPS trend is weakening"
  }
}
```


The processing layer should especially focus on:


```
- EPS revisions
- target upside
- number of analysts
- earnings surprise history
- recommendation distribution
```


A stock with many buy ratings but falling EPS estimates should not be blindly marked as a strong buy.


---


### 4. Exchange filings and announcements


Convert announcements into event cards.


Raw:


```
{
  "type": "Outcome of Board Meeting",
  "subject": "..."
}
```


Processed:


```
{
  "event_type": "financial_results / dividend / acquisition / management_change",
  "event_date": "",
  "ticker": "RELIANCE",
  "event_summary": "",
  "impact_direction": "positive / negative / neutral / mixed",
  "severity": "low / medium / high",
  "time_horizon": "short / medium / long",
  "is_material": true,
  "source_reliability": "high"
}
```


Your exchange filing layer already supports `material_only=True`, which is good because it filters to investment-relevant items such as results, dividends, acquisitions, management changes, credit ratings, and buybacks.


---


### 5. Concall transcripts and investor presentations


Do not pass the full transcript unless the final agent needs a specific quote.


Convert them into management commentary cards:


```
{
  "management_commentary": {
    "quarter": "Q4 FY26",
    "tone": "positive / cautious / negative / mixed",
    "key_claims": [],
    "guidance": {
      "revenue": "",
      "margin": "",
      "capex": "",
      "demand": ""
    },
    "analyst_questions": [
      {
        "topic": "margin pressure",
        "management_answer_summary": "",
        "risk_level": "medium"
      }
    ],
    "red_flags": [],
    "positive_signals": [],
    "source_url": ""
  }
}
```


Pass the extracted commentary plus source link. Keep the full transcript in storage for retrieval.


---


### 6. News, newsletters, YouTube, RSS


Convert narrative content into **event + claim objects**.


Example:


```
{
  "claim_id": "",
  "source_type": "youtube",
  "source_reliability": "medium",
  "ticker": "HDFCBANK.NS",
  "claim": "The speaker says HDFC Bank's margin pressure is temporary.",
  "claim_type": "opinion",
  "event_type": "margin_pressure",
  "sentiment": "mixed",
  "evidence_strength": "low",
  "requires_verification": true
}
```


For news:


```
{
  "event_id": "",
  "ticker": "TCS.NS",
  "event_type": "earnings_miss",
  "event_summary": "",
  "impact_direction": "negative",
  "severity": "medium",
  "temporary_or_structural": "unknown",
  "source_count": 4,
  "highest_reliability_source": "exchange_filing"
}
```


This is where your system stops being a summarizer.


---


### 7. Macro data


Convert macro into market regime:


```
{
  "market_regime": {
    "india_market_valuation": "fair / expensive / cheap",
    "nifty_pe_signal": "neutral",
    "vix_signal": "elevated",
    "fii_dii_signal": "fii_selling_dii_support",
    "rate_environment": "tight / easing / neutral",
    "global_risk": "medium",
    "recommended_posture": "selective buying / wait / defensive"
  }
}
```


Do not pass full macro payload every time.


---


### 8. F&O data


F&O should be converted into short-term sentiment only.


```
{
  "derivatives_signal": {
    "ticker": "NIFTY",
    "pcr": 0.85,
    "max_pain": 24000,
    "support_zones": [],
    "resistance_zones": [],
    "atm_iv": "",
    "sentiment": "mild bullish / bearish / neutral",
    "use_for": "short_term_only"
  }
}
```


Do not let F&O influence long-term buy decisions heavily.


---


## B. Data that can be passed as-is


Some data can be passed as-is or almost as-is because it is already compact:


```
- current market snapshot
- latest analyst price target summary
- latest corporate action list
- top 5 material announcements
- latest FII/DII daily flow
- top derived F&O metrics: PCR, max pain, top OI
- ticker extraction result
- SEC recent filing metadata
```


But even for these, add metadata:


```
source reliability
freshness
market
ticker
retrieved_at
```


---


## C. Data that should stay in storage and only be retrieved when needed


Keep these in raw storage/vector DB:


```
- full YouTube transcripts
- full earnings call transcripts
- full investor presentation text
- full scraped articles
- full SEC filing text
- full price history
- full option chain
- full Screener tables
```


The LLM should not receive all of this by default.


Instead, use retrieval:


```
Question: “Why did Reliance margins fall?”
Retrieve:
- latest concall margin discussion chunks
- latest quarterly results
- related news/event cards
- analyst EPS revision card
```


---


# 6. The processing layer you should build now


I would build the next layer like this:


```
processing_layer/
├── registry/
│   └── source_registry.py
├── normalizers/
│   ├── normalize_market_data.py
│   ├── normalize_screener.py
│   ├── normalize_filings.py
│   ├── normalize_news.py
│   ├── normalize_transcripts.py
│   ├── normalize_macro.py
│   └── normalize_analyst_estimates.py
├── validators/
│   ├── schema_validator.py
│   ├── freshness_validator.py
│   └── quality_validator.py
├── entity_resolution/
│   ├── ticker_resolver.py
│   └── company_alias_resolver.py
├── event_extraction/
│   ├── news_event_extractor.py
│   ├── filing_event_extractor.py
│   └── transcript_event_extractor.py
├── feature_engineering/
│   ├── price_features.py
│   ├── fundamental_features.py
│   ├── valuation_features.py
│   ├── analyst_features.py
│   ├── macro_features.py
│   └── derivatives_features.py
├── summarizers/
│   ├── document_summarizer.py
│   ├── transcript_summarizer.py
│   └── evidence_card_builder.py
├── context_builder/
│   ├── company_context_builder.py
│   ├── market_context_builder.py
│   ├── event_context_builder.py
│   └── agent_context_router.py
└── outputs/
    ├── normalized/
    ├── features/
    ├── evidence_cards/
    └── agent_context/
```


This layer should produce four final output types:


```
1. normalized_documents
2. extracted_events
3. computed_features
4. agent_context_packets
```


---


# 7. Investor perspective: what should your system analyze?


A real investor does not look only at “news.” They usually think in this order:


## 1. Business quality


```
- Is revenue growing?
- Are profits growing?
- Are margins improving or falling?
- Is ROE/ROCE strong?
- Is free cash flow strong?
- Is debt manageable?
- Is the company gaining or losing market share?
- Is management credible?
```


## 2. Valuation


```
- Is the stock expensive or cheap versus its own history?
- Is it expensive or cheap versus peers?
- Is forward PE reasonable based on expected growth?
- Is price-to-book justified?
- Is dividend yield meaningful?
```


## 3. Growth outlook


```
- Are analysts raising or cutting EPS?
- Is management giving positive guidance?
- Is sector demand improving?
- Are there new catalysts?
```


## 4. Risk


```
- Debt risk
- margin pressure
- regulatory risk
- promoter pledge risk
- governance risk
- cyclicality
- commodity exposure
- FX/rate sensitivity
- accounting or cash-flow weakness
```


## 5. Market timing


```
- Is the market expensive?
- Is volatility high?
- Are FIIs buying or selling?
- Is the stock near 52-week high/low?
- Is the stock falling because of temporary news or structural weakness?
```


## 6. Portfolio fit


```
- Is this suitable for long term or short term?
- Is it too risky?
- Does it duplicate existing exposure?
- Should the entry be lump sum or staggered?
```


SEC Investor.gov also emphasizes that investor decisions depend on time horizon and risk tolerance, and SEBI investor education highlights diversification as a way to reduce risk across companies and asset classes. [Investor](https://www.investor.gov/introduction-investing/getting-started/asset-allocation?utm_source=chatgpt.com) [SEBI Investor](https://investor.sebi.gov.in/securities-risks_trade_derivatives.html?utm_source=chatgpt.com)


So your agent must eventually produce **research support**, not personalized guaranteed advice.


---


# 8. The exact processing operations you need


Here is the practical list.


## Operation 1: Normalize


Convert every raw file into a standard shape.


```
{
  "doc_id": "",
  "source_type": "",
  "ticker": "",
  "company": "",
  "published_at": "",
  "fetched_at": "",
  "text": "",
  "structured_data": {},
  "source_reliability": "",
  "freshness_status": ""
}
```


## Operation 2: Validate


Check:


```
- Is ticker present?
- Is date present?
- Is price present?
- Is text too short?
- Is source stale?
- Is currency known?
- Is market known?
- Is extraction partial?
```


Output:


```
{
  "data_quality_score": 0.86,
  "missing_fields": [],
  "warnings": ["RSS summary only, no full body"]
}
```


## Operation 3: Deduplicate


Group same articles/events.


```
same title
same URL
same event
same date
high text similarity
```


## Operation 4: Chunk long text


For:


```
- YouTube transcripts
- earnings call transcripts
- investor presentations
- SEC filing text
- long articles
```


Chunk by:


```
- section
- timestamp
- speaker
- topic
- 800–1200 tokens
```


Store chunks in vector DB.


## Operation 5: Extract entities


```
- companies
- tickers
- sectors
- people
- products
- macro terms
- financial metrics
- event names
```


## Operation 6: Extract claims


From narrative sources:


```
{
  "claim": "",
  "ticker": "",
  "claim_type": "fact / opinion / forecast / rumor",
  "evidence_strength": "high / medium / low",
  "requires_verification": true
}
```


## Operation 7: Extract events


From filings/news/transcripts:


```
{
  "event_type": "",
  "event_date": "",
  "ticker": "",
  "impact": "positive / negative / neutral / mixed",
  "severity": "low / medium / high",
  "temporary_or_structural": "temporary / structural / unknown"
}
```


## Operation 8: Compute derived metrics


Examples:


```
price:
- 1D/1W/1M/3M/1Y return
- distance from 52W high/low
- volatility
- drawdown
- trend status
- volume spike

fundamentals:
- revenue CAGR
- profit CAGR
- margin trend
- ROE/ROCE trend
- debt trend
- CFO/PAT
- free cash flow trend

valuation:
- PE vs peers
- PB vs peers
- EV/EBITDA if available
- target upside
- PEG if possible

analyst:
- EPS revisions
- recommendation bias
- surprise trend

macro:
- Nifty valuation regime
- FII/DII trend
- VIX risk
- rates and currency pressure

news:
- event frequency
- sentiment trend
- source reliability
```


## Operation 9: Build evidence cards


This is the most important output of the processing layer.


Example:


```
{
  "evidence_card_id": "RELIANCE_EARNINGS_Q4_2026",
  "ticker": "RELIANCE.NS",
  "theme": "earnings_result",
  "summary": "Reliance reported Q4 results with stable revenue but margin pressure in core segments.",
  "positive_evidence": [],
  "negative_evidence": [],
  "neutral_evidence": [],
  "source_links": [],
  "source_reliability": "high",
  "investment_relevance": "high",
  "temporary_or_structural": "unknown",
  "requires_agent_review": true
}
```


## Operation 10: Build agent context packets


Different agents should receive different context.


Do not send the same huge context to all agents.


---


# 9. Agents you should build next


You do not need all agents immediately. Build them in this order.


## Phase 1 agents


### 1. Data Quality Agent


Input:


```
normalized outputs
```


Output:


```
Can we trust this data?
What is missing?
Which sources failed?
Which fields are stale?
```


### 2. Entity + Ticker Resolution Agent


Input:


```
news/transcripts/newsletters/articles
```


Output:


```
verified company/ticker mappings
```


This is important because wrong ticker mapping will destroy the analysis.


### 3. Event Extraction Agent


Input:


```
news + filings + transcripts
```


Output:


```
event cards
```


This agent identifies:


```
earnings miss
guidance cut
management change
large order
credit rating downgrade
regulatory issue
temporary sentiment issue
structural problem
```


### 4. Fundamental Feature Agent


Input:


```
screener data / SEC data / analyst estimates / peer comparison
```


Output:


```
business quality score
valuation score
growth score
risk score
```


### 5. Market Regime Agent


Input:


```
macro data + FII/DII + index data + VIX + price trend
```


Output:


```
market condition: risk-on / risk-off / neutral
recommended posture: aggressive / selective / cautious / wait
```


### 6. Context Builder Agent


Input:


```
all processed features and evidence cards
```


Output:


```
compact final context packet for investment decision agent
```


---


# 10. What each future agent should receive


## Market Regime Agent receives


```
{
  "nifty_index_features": {},
  "nifty_pe_pb_history": {},
  "fii_dii_trend": {},
  "vix": {},
  "rates": {},
  "commodities": {},
  "global_macro": {}
}
```


It should not receive full YouTube transcripts or company filings.


---


## Company Fundamental Agent receives


```
{
  "ticker": "",
  "screener_features": {},
  "sec_features": {},
  "analyst_features": {},
  "peer_comparison_features": {},
  "corporate_action_features": {},
  "management_commentary_summary": {}
}
```


It should not receive full news dump.


---


## Event Impact Agent receives


```
{
  "ticker": "",
  "event_cards": [],
  "recent_news_cards": [],
  "filing_events": [],
  "price_reaction": {},
  "volume_reaction": {}
}
```


Its job is to answer:


```
Is this event positive, negative, temporary, structural, or noise?
```


---


## Risk Agent receives


```
{
  "debt_trend": {},
  "cash_flow_quality": {},
  "margin_trend": {},
  "pledge_risk": {},
  "regulatory_events": [],
  "management_change_events": [],
  "negative_news_events": [],
  "valuation_risk": {}
}
```


---


## Final Research Agent receives only compact data


```
{
  "market_regime_summary": {},
  "company_quality_summary": {},
  "valuation_summary": {},
  "event_impact_summary": {},
  "risk_summary": {},
  "evidence_cards": [],
  "data_gaps": []
}
```


This is what makes it useful.


---


# 11. Your next concrete implementation steps


Start with this order.


## Step 1: Build `processing_layer/source_registry.py`


This should scan `output/context_ext_layer_outputs/` and create an index:


```
{
  "module": "market_data",
  "file_path": "",
  "ticker": "RELIANCE.NS",
  "source_type": "market_snapshot",
  "fetched_at": "",
  "status": "available"
}
```


## Step 2: Build normalizers


Create one normalized JSON per source.


Example output folder:


```
output/processing_layer_outputs/normalized/
```


## Step 3: Build feature extractors


Start with these four only:


```
price_features.py
fundamental_features.py
analyst_features.py
news_event_features.py
```


## Step 4: Build evidence cards


Create:


```
output/processing_layer_outputs/evidence_cards/RELIANCE_2026-05-02.json
```


## Step 5: Build company context packet


Create:


```
output/processing_layer_outputs/agent_context/RELIANCE_context_packet_2026-05-02.json
```


This should be the final input to your first LLM research agent.


---


# 12. The exact context packet format I recommend


Use this as your main downstream format:


```
{
  "ticker": "RELIANCE.NS",
  "company": "Reliance Industries Limited",
  "as_of": "2026-05-02",
  "market": "India",
  "data_quality": {
    "overall_score": 0.86,
    "missing_data": [],
    "stale_data": [],
    "source_count": 18,
    "high_reliability_source_count": 6
  },
  "market_context": {
    "market_regime": "neutral",
    "nifty_valuation": "fair",
    "fii_dii_signal": "mixed",
    "volatility_signal": "medium"
  },
  "price_context": {
    "current_price": 1436,
    "return_1m": 6.47,
    "return_3m": 3.64,
    "return_1y": 0.36,
    "distance_from_52w_high_pct": -10.91,
    "distance_from_52w_low_pct": 11.32,
    "trend": "sideways"
  },
  "fundamental_context": {
    "business_quality": "medium",
    "growth_trend": "stable",
    "margin_trend": "watch",
    "debt_risk": "medium",
    "cash_flow_quality": "unknown"
  },
  "valuation_context": {
    "peer_relative_valuation": "premium",
    "analyst_target_upside_pct": 18.8,
    "valuation_risk": "medium"
  },
  "event_context": [
    {
      "event_type": "earnings_result",
      "summary": "",
      "impact": "mixed",
      "severity": "medium",
      "temporary_or_structural": "unknown",
      "source_reliability": "high"
    }
  ],
  "management_context": {
    "tone": "mixed",
    "positive_points": [],
    "concerns": [],
    "guidance": []
  },
  "risk_context": {
    "red_flags": [],
    "watch_items": [],
    "structural_risks": []
  },
  "evidence_cards": [],
  "raw_retrieval_refs": []
}
```


This is the format your downstream agents need.


---


# 13. Final answer: is your context layer enough?


Yes, your context extraction layer is enough to move forward.


But it is not yet enough to send directly to an investment decision LLM.


Right now you have:


```
Raw source extraction layer — good
```


Next you need:


```
Processing / context-building layer — mandatory
```


Then:


```
Analysis agents — after processing layer
```


The correct roadmap is:


```
Layer 1: Context Extraction
Status: Mostly done

Layer 2: Processing + Context Building
Status: Build next

Layer 3: Specialist Analysis Agents
Status: Build after processed context exists

Layer 4: Final Investment Research Agent
Status: Build after specialist agents work

Layer 5: Guardrail / Compliance / Risk Explanation Layer
Status: Add before final user-facing output
```


Your next priority should be this:


```
Do not build the final stock recommendation agent yet.

First build:
1. normalizer
2. validator
3. feature extractor
4. event extractor
5. evidence card builder
6. company context packet builder
```


Once this is built, your final LLM will receive clean investment evidence instead of raw dumped data. That is the difference between a basic summarizer and a real stock research agent.

I got a doubt. Here, we are taking data, raw data in different formats, right? One is like based on some particular company where extracting the data, and some other are based on the particular time, like of the market, and some other on the news globally. So, are we like getting, fetching data based on some company? Like initially, do we need to identify a company and based on that company, do we need to collect all the data? Or is it not like that? Is it like a market-based, like a taking all the data, like not just a data revolving around the particular company, but entire all the data, right? And also, in this processing layer, are we going to use any LLMs? Because you said, in some places, we need to mention like whether that is positive, negative, or whether it is going to affect positive or negatively in future, right? So those things, you mentioned like for transcripts, you mentioned we have to have an impact, like positive, negative, neutral, or mixed. So, how are we going to exactly find these positive, negative, neutral, or mixed tags? Because these are like a text-based, right? Are we going to use LLMs to produce these or are we not going to have these tags for these transcripts or any... Context-based, like a text-based or a string-based one, not numerical ones. If you have like a categorical ones, how exactly we are going to create these tags, like how, what data are we going to create these events, like these contexts? How exactly we are going to normalize these contexts? And also, I want to understand, here we have like a context layer, we have like 25 modules, and from each module, we are like generating different kinds of outputs. Now I want to understand at like module level, how the output from that module will be converted, right? So explain that also. It will be easy for me to like visualize and code. So at module level, at each module level, present we have data, like a history of data, right? In one of the module, we are fetching all the like history of prices of a particular stock, right? So how are we going to convert that data? And also, for example, some of them are taking like a tickers, right? For example, for a particularly for a company, for HDFC. So how we are going to know which company data we will be going to extract? Right. So do we need to have a layer in between, like in, even before our extraction layer, context extraction layer, do we need to have some LLM to analyze or something, or in between some of those modules? Because we need to pass different parameters to different modules, right? For some are like taking like general ones. So, for example, news, they will always like follow the same URL to take the news. But for some of the modules, they are taking like a particular companies, right? So day by day, if, for example, if you are running daily, you won't just focus on some company, right? We will be focusing on based on the news, we will see which one are best, right? Based on the, like based on the news or something, other things, we will analyze which company we need to analyze, which company we need to invest or do we need to invest in mutual funds. Like based on the market, if market is low, then we have to consider investing because anyway in future it will increase, right? So how are we going to exactly decide and where exactly we are going to decide what are the parameters we are going to pass to these modules in the extraction layer, right? Because... For processing layer, the data we build from context layer is important. But how exactly, on what basis we are going to build, like extract data at the context layer? Are we, are we, or do we have to divide this context layer into like two or three parts, where first based on the news or based on the YouTube transcript or based on the some context, we need to first identify what are the companies data we need to fetch and then there, and then later, once we identify what are the companies or what are the data we need to extract, then we will use the other modules that are based on the company, we will extract those particular data. Should we do it like this or how exactly we are going to do? How exactly we are going to trigger these or how exactly we are going to extract the data, where exactly and what are the parameters and what basis we are going to pass those parameters? Think deeply, analyze our system because we need to know what is the head, what is the tail, and then only we can properly like trigger, right? Otherwise, even though we have like a proper modules to extract the data, those will be useful. And at the module level also explain how we are going to convert the data from that, like output from that module to which form, right? And why we are converting that, why it will be useful, why we are transferring it, converting into different... different format in processing layer at each module level.
You’re asking the right architecture question: before processing, we need a “what should I collect?” decision layer. I’ll map the full head-to-tail flow and then show module-by-module how each raw output becomes useful processed context.

One key correction: your extraction layer should not be one single daily job that fetches every company. It should run in two speeds: broad market discovery first, then ticker-specific deep dive only for selected candidates.

Your doubt is correct. The system should **not always start with a company** and it should **not always collect all market data for every company**.


The correct design is:


```
1. Broad discovery first
   Find what the market/news/videos/newsletters are talking about.

2. Candidate selection second
   Identify which companies, sectors, indexes, or themes are worth deeper analysis.

3. Ticker-specific deep dive third
   For selected companies only, fetch fundamentals, filings, price history, peers, analyst estimates, etc.

4. Processing/context-building fourth
   Convert raw outputs into features, events, evidence cards, and agent-ready context packets.

5. Analysis agents last
   Use processed context to decide watchlist / avoid / buy candidate / wait.
```


Your current extraction layer is good, but now you need one layer **before extraction orchestration** and one layer **after extraction processing**.


---


# 1. Company-first or market-first?


It should support **both**.


There are 4 modes.


## Mode 1: User asks for a specific company


Example:


```
“Analyze Reliance”
“Should I invest in HDFC Bank?”
“Check AAPL after earnings”
```


Then the system already knows the ticker/company.


Flow:


```
User query
   ↓
Ticker resolver
   ↓
Run company-specific collectors
   ↓
Run market-wide context collectors
   ↓
Processing layer
   ↓
Research agents
```


For this mode, you directly call modules like:


```
market_data
price_history
screener_in
peer_comparison
analyst_estimates
exchange_filings
filing_docs
corporate_actions
fno_data if eligible
sec_filings if US stock
news APIs with ticker/company query
```


---


## Mode 2: User gives YouTube/newsletter/article


Example:


```
User gives a YouTube video about market crash.
User gives a newsletter about AI stocks.
User gives an article about Indian banking stocks.
```


Here you do **not know the company upfront**.


Flow:


```
YouTube/article/newsletter
   ↓
Extract transcript/body text
   ↓
Ticker/entity extraction
   ↓
Candidate ticker list
   ↓
Run company-specific collectors for those tickers
   ↓
Processing layer
   ↓
Research agents
```


This is where your `ticker_extractor` module becomes very important. Your context layer already has ticker extraction as a utility for mapping company names from text into NSE tickers.


---


## Mode 3: Daily market scan


This is the main autonomous system.


Every day, you do not start with a company. You start with **market-wide discovery**.


Flow:


```
Daily scheduler
   ↓
Run broad collectors
   - RSS
   - Moneycontrol
   - Economic Times
   - News APIs
   - macro data
   - FII/DII
   - bulk deals
   - index F&O
   - newsletters
   ↓
Extract tickers, sectors, themes, events
   ↓
Rank candidate stocks/sectors
   ↓
Run company-specific deep-dive only for top candidates
```


This is the best design for “find me good opportunities from market/news.”


---


## Mode 4: Watchlist / portfolio mode


Example:


```
User has 20 favorite stocks.
System monitors them daily.
```


Flow:


```
Watchlist tickers
   ↓
Daily light refresh
   - price
   - latest news
   - filings
   - analyst estimate changes
   - FII/DII/macro context
   ↓
Deep refresh only if alert condition happens
```


Example alert conditions:


```
- price drops more than 5%
- volume spikes
- new material filing
- earnings result published
- analyst EPS cut
- corporate action
- negative news event
```


---


# 2. So do we need a layer before context extraction?


Yes.


You need a **Collection Planner / Research Orchestrator** before the extraction layer.


Your current context layer has many useful modules, and your documentation correctly says each module extracts raw data and saves structured JSON, while aggregation/calculation/analysis happens later.


But someone has to decide:


```
Which module should run?
With what parameters?
For which ticker?
For which date?
For which source?
With what depth?
```


That is not the job of the extraction module. That is the job of the orchestrator.


---


# 3. Correct full architecture


Think of the project like this:


```
Layer 0: Research Orchestrator / Collection Planner
Decides what to collect and which modules to trigger.

Layer 1: Context Extraction Layer
Your existing modules. They fetch raw data and save JSON.

Layer 2: Processing / Context Building Layer
Normalizes, calculates, extracts events, creates evidence cards.

Layer 3: Specialist Agents
Market agent, fundamental agent, event agent, risk agent, valuation agent.

Layer 4: Final Research Agent
Combines all specialist outputs into investment research.

Layer 5: Guardrail / Compliance Layer
Checks language, confidence, risk, evidence, no guaranteed advice.
```


Your current layer is **Layer 1**.


Now you need **Layer 0 and Layer 2**.


---


# 4. What does the Research Orchestrator do?


It receives one of these inputs:


```
{
  "mode": "daily_market_scan | ticker_analysis | source_analysis | watchlist_monitoring",
  "user_query": "",
  "source_urls": [],
  "seed_tickers": [],
  "market": "india | us | global",
  "depth": "light | standard | deep",
  "max_candidates": 10
}
```


Then it creates a collection plan:


```
{
  "collection_plan_id": "daily_scan_2026_05_03",
  "mode": "daily_market_scan",
  "steps": [
    {
      "stage": "market_discovery",
      "modules": ["rss", "moneycontrol", "economic_times", "newsdata_io", "macro_data", "fii_dii", "bulk_deals"]
    },
    {
      "stage": "candidate_discovery",
      "modules": ["ticker_extractor"]
    },
    {
      "stage": "company_deep_dive",
      "tickers": ["RELIANCE.NS", "HDFCBANK.NS"],
      "modules": ["market_data", "price_history", "screener_in", "analyst_estimates", "peer_comparison", "exchange_filings"]
    }
  ]
}
```


---


# 5. How exactly do we decide which company data to fetch?


You need a **candidate generation step**.


For daily market scan, do this:


```
Step 1: Collect broad market/news data.
Step 2: Extract companies/tickers/sectors from text.
Step 3: Score each candidate.
Step 4: Pick top candidates.
Step 5: Run company-specific deep-dive modules.
```


Candidate score can be rule-based at first.


Example:


```
candidate_score =
  mention_score
+ event_materiality_score
+ price_move_score
+ volume_spike_score
+ source_reliability_score
+ novelty_score
```


Example candidate ranking:


```
{
  "ticker": "HDFCBANK.NS",
  "company": "HDFC Bank",
  "candidate_score": 82,
  "why_selected": [
    "Mentioned in 5 news articles",
    "Price down more than 3%",
    "Banking sector under pressure",
    "High-reliability source detected"
  ],
  "next_modules_to_run": [
    "market_data",
    "price_history",
    "screener_in",
    "analyst_estimates",
    "peer_comparison",
    "exchange_filings",
    "filing_docs"
  ]
}
```


This candidate scoring is **not the final investment decision**. It only decides where to spend deeper analysis effort.


---


# 6. Do we use LLMs in the processing layer?


Yes, but carefully.


Use **normal code/math** for numeric data.


Use **LLM only for text understanding**.


## Do not use LLM for these


```
- price returns
- moving averages
- volatility
- max drawdown
- PE comparison
- revenue growth
- profit CAGR
- margin trend calculation
- debt trend calculation
- volume spike
- FII/DII net flow
- PCR / max pain / top OI
```


These should be deterministic Python/pandas calculations.


## Use LLM for these


```
- extracting claims from transcripts
- summarizing management commentary
- identifying event type from article/transcript
- classifying tone: positive/negative/mixed
- deciding whether text suggests temporary or structural issue
- extracting risks from long filings
- grouping duplicate news into same event
```


So yes, in processing layer, you will have some small LLM-based processors, but they should output strict JSON.


---


# 7. Important distinction: sentiment vs impact


This is very important.


Do not use only one label called `positive` or `negative`.


You need 4 different labels.


## 1. Text sentiment


How the article/video sounds.


```
{
  "text_sentiment": "negative"
}
```


Example: “The speaker is worried.”


## 2. Event impact


What the event means for business.


```
{
  "event_impact": "negative"
}
```


Example: “Company cut guidance.”


## 3. Price reaction


How the market reacted.


```
{
  "price_reaction": "stock_down_5_percent"
}
```


## 4. Thesis impact


Whether this affects long-term investment thesis.


```
{
  "thesis_impact": "temporary | structural | unknown"
}
```


Example:


```
Negative article sentiment does not always mean negative investment opportunity.

A stock may fall after temporary bad news.
That can become a watchlist/buy candidate only if fundamentals remain strong.
```


So processing layer should not simply tag:


```
positive / negative
```


It should tag:


```
{
  "text_sentiment": "negative",
  "event_impact": "negative",
  "price_reaction": "sharp_drop",
  "thesis_impact": "temporary_possible",
  "confidence": "medium"
}
```


---


# 8. How will LLM create these tags?


Use a dedicated **Text Event Extractor LLM**.


Input:


```
{
  "source_type": "youtube_transcript",
  "source_reliability": "medium",
  "ticker": "HDFCBANK.NS",
  "chunk_text": "The bank is facing short-term margin pressure after the merger, but deposit growth is improving..."
}
```


Prompt:


```
You are an investment event extraction model.

Extract only investment-relevant events and claims from the provided text.

Return JSON only.

Do not make final buy/sell recommendations.

Classify:
- event_type
- text_sentiment
- business_impact
- time_horizon
- temporary_or_structural
- evidence_strength
- confidence
- exact_supporting_text

Rules:
- If the text is only opinion, mark claim_type as opinion.
- If the text gives factual result/guidance, mark claim_type as fact.
- If there is not enough evidence, use "unknown".
- Do not infer beyond the text.
```


Output:


```
{
  "events": [
    {
      "ticker": "HDFCBANK.NS",
      "event_type": "margin_pressure",
      "claim_type": "opinion",
      "text_sentiment": "mixed",
      "business_impact": "negative",
      "temporary_or_structural": "temporary_possible",
      "time_horizon": "medium_term",
      "evidence_strength": "medium",
      "confidence": 0.72,
      "supporting_text": "short-term margin pressure after the merger, but deposit growth is improving"
    }
  ]
}
```


That is how you convert text into categorical tags.


---


# 9. Module-level conversion map


Below is the most important design table for your coding.


---


## 1. `rss_feed.py`


Your RSS layer collects headlines and summaries, and your docs correctly mention that RSS does not contain full article bodies; full text should be fetched separately using generic or browser scraping.


### Scope


```
Market-wide / discovery
```


### Trigger


```
Daily scheduled job
```


### Raw output


```
feed_name, title, URL, published date, summary
```


### Processing conversion


```
{
  "document_type": "rss_item",
  "headline": "",
  "summary": "",
  "url": "",
  "published_at": "",
  "mentioned_tickers": [],
  "mentioned_sectors": [],
  "event_hint": "",
  "needs_full_article_fetch": true,
  "discovery_score": 0
}
```


### Why convert?


RSS is mainly a **discovery source**. It tells you what to fetch deeper.


### Downstream


```
Candidate Generator
News Event Extractor
Full Article Fetcher
```


---


## 2. `moneycontrol.py`


### Scope


```
Market-wide and stock news
```


### Trigger


```
Daily scheduled job
or ticker-specific query if needed
```


### Raw output


```
title, author, published, body, URL
```


### Processing conversion


```
{
  "document_type": "news_article",
  "source": "moneycontrol",
  "title": "",
  "published_at": "",
  "body_clean": "",
  "mentioned_tickers": [],
  "event_cards": [
    {
      "event_type": "",
      "ticker": "",
      "event_summary": "",
      "business_impact": "",
      "text_sentiment": "",
      "time_horizon": "",
      "confidence": 0.0
    }
  ]
}
```


### Why convert?


The full article body is too long and noisy. You need event cards.


### Downstream


```
Event Impact Agent
Candidate Generator
Company Context Builder
```


---


## 3. `economic_times.py`


Same as Moneycontrol.


### Processing output


```
{
  "document_type": "news_article",
  "source": "economic_times",
  "event_cards": [],
  "mentioned_tickers": [],
  "source_reliability": "medium"
}
```


### Downstream


```
Candidate Generator
Event Impact Agent
```


---


## 4. `generic.py`


### Scope


```
User-provided article / open website
```


### Trigger


```
When user gives URL
or RSS item needs full article
```


### Raw output


```
url, title, author, date, text
```


### Processing conversion


```
{
  "document_type": "generic_article",
  "source_url": "",
  "clean_text": "",
  "chunks": [],
  "mentioned_tickers": [],
  "claims": [],
  "event_cards": [],
  "source_reliability": "low_or_medium"
}
```


### Why convert?


Generic articles may be blogs/opinion. Need claim extraction and reliability score.


---


## 5. `browser_scraper.py`


### Scope


```
JS-heavy sites like Tickertape/Trendlyne
```


### Trigger


```
When static scraper fails
```


### Raw output


```
rendered page text
```


### Processing conversion


```
{
  "document_type": "rendered_web_page",
  "clean_sections": [],
  "tables_detected": [],
  "metrics_detected": {},
  "claims": [],
  "data_quality": {
    "may_contain_navigation_noise": true
  }
}
```


### Why convert?


Browser text can contain menus, ads, navigation, and repeated UI labels.


---


## 6. `youtube/transcript.py`


Your YouTube module extracts transcript text and stores video id, URL, language, and full transcript.


### Scope


```
Source-driven discovery / opinion extraction
```


### Trigger


```
User provides YouTube URL
or system monitors selected channels later
```


### Raw output


```
video_id, URL, language, transcript
```


### Processing conversion


```
{
  "document_type": "youtube_transcript",
  "chunks": [
    {
      "chunk_id": "",
      "timestamp_start": "",
      "text": "",
      "mentioned_tickers": [],
      "claims": [],
      "event_cards": []
    }
  ],
  "speaker_tone": "",
  "main_themes": [],
  "source_reliability": "medium_or_low"
}
```


### Why convert?


A transcript is long and opinion-heavy. You should extract:


```
- companies mentioned
- claims
- risks
- catalyst statements
- speaker opinions
- timestamps
```


Do not pass full transcript to final agent by default.


---


## 7. `gmail/newsletter.py`


### Scope


```
Narrative/opinion/discovery
```


### Trigger


```
Daily or when user asks
```


### Raw output


```
subject, sender, date, body
```


### Processing conversion


```
{
  "document_type": "newsletter",
  "sender": "",
  "subject": "",
  "clean_body": "",
  "mentioned_tickers": [],
  "claims": [],
  "idea_candidates": [],
  "requires_verification": true
}
```


### Why convert?


Newsletters are useful for idea discovery but should not be trusted as final evidence.


---


## 8. `newsdata_io.py` / `mediastack.py`


### Scope


```
Market-wide or ticker-specific news
```


### Trigger


```
Daily broad query
or ticker-specific query after candidate selection
```


### Parameters


```
{
  "query": "nifty sensex stock market india",
  "country": "in",
  "language": "en",
  "limit": 20
}
```


For company-specific:


```
{
  "query": "HDFC Bank earnings margin pressure",
  "country": "in",
  "language": "en"
}
```


### Processing conversion


```
{
  "document_type": "news_api_item",
  "title": "",
  "description": "",
  "keywords": [],
  "mentioned_tickers": [],
  "event_hint": "",
  "needs_full_article_fetch": true
}
```


### Why convert?


News API often gives metadata/description, not enough for full research.


---


## 9. `ticker_extractor.py`


### Scope


```
Utility
```


### Trigger


```
After collecting any text source
```


### Raw output


```
[
  {
    "company": "",
    "ticker": ""
  }
]
```


### Processing conversion


```
{
  "ticker_candidates": [
    {
      "company_name": "",
      "ticker": "",
      "confidence": 0.0,
      "source_document_id": "",
      "needs_verification": false
    }
  ]
}
```


### Why convert?


Ticker mistakes are dangerous. You need confidence and verification.


---


## 10. `market_data.py`


Your market snapshot module already gives current price, day change, 52-week range, returns, volume, market cap, sector, and industry.


### Scope


```
Company-specific
```


### Trigger


```
Whenever a ticker enters candidate list
or user asks for a ticker
or watchlist daily refresh
```


### Raw output


```
price, day_change_pct, 52w high/low, return_1m, return_3m, return_1y, volume, market cap
```


### Processing conversion


```
{
  "price_snapshot_features": {
    "current_price": "",
    "day_change_pct": "",
    "return_1m": "",
    "return_3m": "",
    "return_1y": "",
    "distance_from_52w_high_pct": "",
    "distance_from_52w_low_pct": "",
    "short_term_momentum": "positive | negative | neutral",
    "price_location": "near_high | middle_range | near_low"
  }
}
```


### Why convert?


The final agent needs interpretation, not just numbers.


---


## 11. `price_history.py`


Your docs say this module fetches OHLCV history and is useful for CAGR, max drawdown, volatility, and comparing stock price performance against business performance.


### Scope


```
Company-specific
```


### Trigger


```
Only for selected candidate tickers
```


### Raw output


```
daily OHLCV rows
```


### Processing conversion


```
{
  "price_history_features": {
    "return_1w": "",
    "return_1m": "",
    "return_3m": "",
    "return_6m": "",
    "return_1y": "",
    "cagr_3y": "",
    "cagr_5y": "",
    "max_drawdown_1y": "",
    "volatility_30d": "",
    "volatility_90d": "",
    "moving_average_50d": "",
    "moving_average_200d": "",
    "trend_status": "uptrend | downtrend | sideways",
    "volume_spike": true
  }
}
```


### Why convert?


Do not pass thousands of OHLCV rows to LLM. Convert them into compact technical/price features.


---


## 12. `screener_in.py`


Your docs describe this as the core Indian fundamental module with 10-year P&L, balance sheet, cash flow, ratios, CAGR metrics, and shareholding patterns. It also says the processing layer should compute shareholding trends from the tables.


### Scope


```
Company-specific, Indian stocks
```


### Trigger


```
Deep dive only
```


### Raw output


```
key ratios, pros, cons, quarterly results, P&L, balance sheet, cash flow, ratios, shareholding
```


### Processing conversion


```
{
  "fundamental_features": {
    "sales_growth_3y": "",
    "sales_growth_5y": "",
    "profit_growth_3y": "",
    "profit_growth_5y": "",
    "margin_trend": "improving | stable | declining",
    "roe_trend": "improving | stable | declining",
    "debt_trend": "increasing | stable | decreasing",
    "cash_flow_quality": "strong | weak | inconsistent",
    "promoter_holding_trend": "",
    "fii_holding_trend": "",
    "dii_holding_trend": "",
    "pledge_risk": "yes | no | unknown",
    "fundamental_quality_score": 0
  }
}
```


### Why convert?


Raw financial tables are too detailed. The agent needs business quality signals.


---


## 13. `peer_comparison.py`


Your peer comparison module maps a stock to an NSE sectoral index, fetches constituents, pulls ratios, and returns target plus peers sorted by market cap.


### Scope


```
Company-specific
```


### Trigger


```
Deep dive
```


### Raw output


```
target ratios + peer ratios
```


### Processing conversion


```
{
  "peer_relative_features": {
    "sector_index": "",
    "pe_percentile_vs_peers": "",
    "pb_percentile_vs_peers": "",
    "roe_rank_vs_peers": "",
    "margin_rank_vs_peers": "",
    "debt_rank_vs_peers": "",
    "growth_rank_vs_peers": "",
    "relative_valuation": "cheap | fair | expensive",
    "relative_quality": "leader | average | laggard"
  }
}
```


### Why convert?


A PE number alone means nothing. It must be compared to peers.


---


## 14. `analyst_estimates.py`


Your analyst estimate module collects price targets, EPS estimates, revenue estimates, earnings history, recommendations, EPS trend, and EPS revisions.


### Scope


```
Company-specific
```


### Trigger


```
Deep dive if analyst data exists
```


### Raw output


```
target price, EPS estimates, revenue estimates, recommendations, revisions
```


### Processing conversion


```
{
  "analyst_features": {
    "target_upside_pct": "",
    "coverage_count": "",
    "recommendation_bias": "bullish | neutral | bearish",
    "eps_revision_30d": "up | down | mixed | unavailable",
    "eps_revision_90d": "up | down | mixed | unavailable",
    "earnings_surprise_trend": "beating | missing | mixed",
    "analyst_confidence": "high | medium | low"
  }
}
```


### Why convert?


Analyst data is useful only after converting it into direction and revision signals.


---


## 15. `exchange_filings.py`


Your exchange filing module fetches official NSE announcements and supports a `material_only` filter for investment-relevant items.


### Scope


```
Company-specific official events
```


### Trigger


```
Deep dive
or daily watchlist scan
```


### Raw output


```
date, type, subject, attachment_url, has_xbrl
```


### Processing conversion


```
{
  "official_event_cards": [
    {
      "event_type": "earnings | dividend | acquisition | management_change | credit_rating | order_win | buyback",
      "event_date": "",
      "summary": "",
      "source_reliability": "high",
      "materiality": "high | medium | low",
      "business_impact": "positive | negative | neutral | mixed | unknown",
      "requires_document_fetch": true
    }
  ]
}
```


### Why convert?


Official filings are high-reliability event signals.


---


## 16. `filing_docs.py`


Your docs say this module downloads and extracts text from NSE filing PDFs such as concall transcripts and investor presentations, and that transcripts contain management strategy, margin, capex, risk, and analyst Q&A context.


### Scope


```
Company-specific qualitative management context
```


### Trigger


```
Deep dive
especially after earnings event
```


### Raw output


```
transcript text, presentation text
```


### Processing conversion


```
{
  "management_commentary_features": {
    "management_tone": "positive | cautious | negative | mixed",
    "demand_commentary": "",
    "margin_commentary": "",
    "capex_commentary": "",
    "debt_commentary": "",
    "guidance": [],
    "analyst_qna_concerns": [],
    "red_flags": [],
    "positive_signals": [],
    "source_reliability": "high"
  }
}
```


### Why convert?


Concall transcripts are long. The final agent needs management signals and quotes, not the whole transcript.


---


## 17. `corporate_actions.py`


### Scope


```
Company-specific capital allocation
```


### Trigger


```
Deep dive
```


### Raw output


```
dividends, splits, bonuses, rights, buybacks
```


### Processing conversion


```
{
  "corporate_action_features": {
    "dividend_consistency": "consistent | inconsistent | none",
    "dividend_growth": "",
    "recent_split_or_bonus": true,
    "buyback_signal": "yes | no",
    "dilution_risk": "rights_issue | none | unknown",
    "capital_allocation_quality": "shareholder_friendly | neutral | weak"
  }
}
```


### Why convert?


Corporate actions tell how management treats shareholders.


---


## 18. `sec_filings.py`


Your SEC module collects key financial metrics from XBRL and recent filings grouped by form type, with optional filing text extraction.


### Scope


```
Company-specific, US stocks
```


### Trigger


```
Only if ticker is US-listed
```


### Raw output


```
revenue, net income, EPS, assets, liabilities, equity, cash, debt, operating cash flow, 10-K, 10-Q, 8-K
```


### Processing conversion


```
{
  "us_fundamental_features": {
    "revenue_growth": "",
    "net_income_growth": "",
    "eps_growth": "",
    "operating_income_trend": "",
    "cash_trend": "",
    "debt_trend": "",
    "operating_cash_flow_trend": "",
    "latest_8k_events": [],
    "filing_risk_flags": []
  }
}
```


### Why convert?


SEC filings are high-reliability fundamentals, but raw XBRL series must be converted into growth/risk features.


---


## 19. `india_macro.py`


Your macro module collects NSE index PE/PB/DY, market rates, USD/INR, US 10Y, India VIX, Nifty/Sensex, commodities, World Bank India CPI/GDP, and RBI repo rate.


### Scope


```
Market-wide
```


### Trigger


```
Daily scheduled job
```


### Raw output


```
indices, PE/PB, rates, commodities, inflation, GDP, repo rate
```


### Processing conversion


```
{
  "india_market_regime_features": {
    "nifty_valuation_zone": "cheap | fair | expensive",
    "vix_risk": "low | medium | high",
    "rate_environment": "easing | neutral | tight",
    "currency_pressure": "low | medium | high",
    "commodity_pressure_by_sector": {
      "oil_gas": "",
      "metals": "",
      "autos": "",
      "paints": ""
    },
    "market_posture": "aggressive | selective | cautious | wait"
  }
}
```


### Why convert?


Macro is not company-specific, but it affects whether to invest broadly or selectively.


---


## 20. `us_macro.py`


### Scope


```
Global macro / India market external pressure
```


### Trigger


```
Daily or weekly
```


### Raw output


```
Fed funds, 10Y, 2Y, CPI, yield curve, USD/INR
```


### Processing conversion


```
{
  "global_macro_features": {
    "fed_rate_pressure": "high | medium | low",
    "us_10y_pressure": "high | medium | low",
    "yield_curve_signal": "recession_risk | normalizing | neutral",
    "global_risk_appetite": "risk_on | risk_off | neutral"
  }
}
```


### Why convert?


Global rates impact Indian market valuation and FII flows.


---


## 21. `fii_dii.py`


Your docs state FII/DII returns most recent trading day only and should be synced daily to build history.


### Scope


```
Market-wide institutional flow
```


### Trigger


```
Daily after market close
```


### Raw output


```
FII buy/sell/net, DII buy/sell/net
```


### Processing conversion


```
{
  "institutional_flow_features": {
    "fii_net": "",
    "dii_net": "",
    "combined_net": "",
    "flow_signal": "fii_buying | fii_selling | mixed | neutral",
    "trend_5d": "",
    "trend_20d": "",
    "market_pressure": "positive | negative | mixed"
  }
}
```


### Why convert?


One day’s flow is noisy. The useful signal is multi-day trend.


---


## 22. `bulk_deals.py`


Your code supports fetching all bulk/block deals and also filtering for a specific symbol using `fetch_deals_for_symbol(ticker)`.


### Scope


```
Market-wide first, company-specific after filtering
```


### Trigger


```
Daily scheduled job
```


### Raw output


```
bulk deals, block deals, client, buy/sell, quantity, price
```


### Processing conversion


```
{
  "bulk_deal_features": {
    "ticker": "",
    "large_buy_detected": true,
    "large_sell_detected": false,
    "institutional_activity_signal": "accumulation | distribution | neutral",
    "notable_clients": [],
    "deal_count": 0
  }
}
```


### Why convert?


Bulk deals can create candidate tickers for deep dive.


---


## 23. `fno_data.py`


Your F&O module collects option chain data and derives PCR, max pain, top OI strikes, and ATM IV. Your docs also correctly label it as short-term/trading-oriented.


### Scope


```
Index-level or stock-level short-term sentiment
```


### Trigger


```
Market hours
for NIFTY/BANKNIFTY daily
for selected F&O candidate stocks only
```


### Raw output


```
option_chain, PCR, max pain, top CE/PE OI, ATM IV
```


### Processing conversion


```
{
  "derivatives_features": {
    "pcr": "",
    "max_pain": "",
    "support_zones": [],
    "resistance_zones": [],
    "atm_iv": "",
    "short_term_sentiment": "bullish | bearish | neutral",
    "use_for": "short_term_only"
  }
}
```


### Why convert?


Do not pass full option chain to LLM. Use derived metrics only.


---


# 10. How parameters are passed to extraction modules


You need a **Module Registry**.


Example:


```
MODULE_REGISTRY = {
    "rss": {
        "scope": "market_discovery",
        "requires": [],
        "trigger": "daily",
        "params": ["feed_name", "feed_url"]
    },
    "moneycontrol": {
        "scope": "market_discovery",
        "requires": [],
        "trigger": "daily",
        "params": ["category_name"]
    },
    "youtube": {
        "scope": "source_analysis",
        "requires": ["video_url"],
        "trigger": "user_input",
        "params": ["video_url"]
    },
    "market_data": {
        "scope": "company_deep_dive",
        "requires": ["ticker"],
        "trigger": "candidate_selected",
        "params": ["ticker"]
    },
    "screener_in": {
        "scope": "company_deep_dive",
        "requires": ["ticker_or_url"],
        "trigger": "candidate_selected",
        "params": ["screener_url"]
    },
    "sec_filings": {
        "scope": "company_deep_dive",
        "requires": ["us_ticker"],
        "trigger": "candidate_selected",
        "params": ["ticker"]
    }
}
```


Then orchestrator logic:


```
def build_collection_plan(request):
    if request.mode == "ticker_analysis":
        tickers = resolve_tickers(request.seed_tickers or request.user_query)
        return deep_dive_plan(tickers)

    if request.mode == "source_analysis":
        source_docs = collect_seed_sources(request.source_urls)
        tickers = extract_candidate_tickers(source_docs)
        return deep_dive_plan(tickers)

    if request.mode == "daily_market_scan":
        return market_discovery_plan()

    if request.mode == "watchlist_monitoring":
        return watchlist_plan(request.seed_tickers)
```


---


# 11. Daily job should run in two phases


## Phase A: Broad market discovery


Run these without ticker:


```
rss_feed
moneycontrol categories
economic_times categories
newsdata_io broad queries
mediastack broad queries
gmail newsletters
india_macro
us_macro
fii_dii
bulk_deals
fno_data for NIFTY/BANKNIFTY
```


This creates:


```
market_snapshot
news_pool
ticker_mentions
sector_mentions
macro_regime
institutional_flow
bulk_deal_candidates
```


## Phase B: Company deep dive


Only after Phase A identifies candidates, run ticker-based modules:


```
market_data
price_history
screener_in
peer_comparison
analyst_estimates
exchange_filings
filing_docs
corporate_actions
sec_filings for US
fno_data if F&O eligible
ticker-specific news API query
```


This saves compute and avoids collecting everything for all companies.


---


# 12. What the processing layer finally produces


It should not produce one giant JSON.


It should produce these 5 outputs:


```
1. normalized_documents
2. ticker_candidates
3. feature_sets
4. event_cards
5. agent_context_packets
```


## Example final processed company context


```
{
  "ticker": "HDFCBANK.NS",
  "company": "HDFC Bank",
  "selection_reason": [
    "Mentioned in 7 articles",
    "Price down 4.2%",
    "Banking sector under pressure",
    "High-volume move detected"
  ],
  "price_features": {},
  "fundamental_features": {},
  "valuation_features": {},
  "analyst_features": {},
  "event_cards": [],
  "risk_flags": [],
  "source_quality": {
    "high_reliability_sources": 3,
    "medium_reliability_sources": 8,
    "low_reliability_sources": 2
  }
}
```


---


# 13. So what is head and what is tail?


This is the final mental model.


```
HEAD:
Research Orchestrator

It decides:
- are we doing market scan?
- are we analyzing a ticker?
- are we analyzing a YouTube/article/newsletter?
- which modules should run?
- what parameters should be passed?

BODY:
Context Extraction Layer

It fetches:
- raw market data
- raw company data
- raw news
- raw transcripts
- raw filings
- raw macro data

MIDDLE:
Processing Layer

It converts:
- raw rows → features
- raw text → claims/events
- raw filings → event cards
- raw financials → business quality features
- raw market data → regime features

TAIL:
Agent Layer

It reasons:
- market good or bad?
- company good or bad?
- event temporary or structural?
- valuation attractive or expensive?
- risk acceptable or not?
- final rating: buy candidate / watchlist / avoid
```


---


# 14. What you should build next


Build in this exact order:


```
1. collection_planner/
   - decides which extraction modules to run
   - creates collection_plan.json

2. processing_layer/normalizers/
   - converts every module output into standard document/context format

3. processing_layer/feature_engineering/
   - numeric calculations from price, fundamentals, analyst data, macro, F&O

4. processing_layer/text_processors/
   - LLM-based claim/event extraction from news, transcripts, newsletters

5. processing_layer/evidence_cards/
   - combines facts + claims + events into compact research evidence

6. agent_context_builder/
   - builds final context packet for each specialist agent
```


Do not jump directly to the final investment agent.


Your next coding target should be:


```
Collection Planner + Candidate Generator
```


Because without that, your extraction modules are powerful but not properly triggered.


The most important design decision is this:


```
Market-wide modules run daily.
Text/news modules discover candidate tickers.
Ticker-specific modules run only for selected candidates.
Processing layer converts raw outputs into features, events, and evidence cards.
LLMs are used only for text interpretation, not for numeric calculations.
```


That gives your system a clear head, body, and tail.
Okay, great. Your analysis is really good. It is really helpful. But now, we have like four modes that we discussed, right? How our entire architecture should run. Present, I want to focus on completely autonomous where it will, I mean, if I just trigger it or maybe daily I have scheduled it at a time. So what should happen is, it should automatically fetch the, all the details that are required. Initially, we thought, right, at the phase A, like a broad market discovery. And there we have to get like RSS feed, money control categories, economic time categories, news data I worked for is, right, or you mentioned now, all these in phase A. So we will get like a market snapshot, news polls, all the information about our market and today's trends, etc. And once we get that, then, probably we need to use an LLM to use an LLM or some other technique to extract tickers or like company deep dive, whatever we need for company deep dive, we need to extract from phase A for company deep dive. Once we got that, then we will again extract the company deep dive information based on that automatically. And here, from phase A and phase B, we will have like a market, like a information and that company related information. All these will be raw. This will be like extraction layer, which involves in like three or four phases, and also there will be an LLM layer, probably, or maybe we can use some other technique to process, right? Then, and also, at module level, let me know where are the, at what module I need to use the LLM to convert that into a categorical, like a proper structure in processing layer, because converting some, that raw input text files or filling documents or whatever, probably we need to put them in a vector database, right? If there's a topic, like for filling documents like annual reports, probably we need to put them in a vector database. So we can get only context whatever we needed, so based on the company. So here, the main thing is, present the logic I have for some of the modules in context layer, they're mainly like based on a single thing. For example, if you take YouTube model, if I give a YouTube URL link, a video link, then it will extract. But now, since it is like complete autonomous, probably we will configure some of the YouTube channels, and from some of those YouTube channels, it should fetch the transcript from the latest videos, probably based on the like we need to keep track of what are the videos we have extracted from those channels. Maybe probably if we have like YouTube ID, sorry, video ID, probably some ID, you know, that we can extract. If we are not getting that from a library, probably what we have to do is we need to like extract the YouTube URL links properly. I'm not exactly sure, but yeah, we need to like write a code to fetch the first, first we need to fetch the like latest YouTube video URLs of the channel. Then we need to use our existing logic to extract the transcripts, right? And we have to like config what are the YouTube channels we have to get the transcripts from. Then the same way, we also have to like configure the websites or whatever all the things, right? We need, like from face, whatever the data we have to get from face, we have to like config them. So based on that config, it will fetch data automatically at face, like a market news and everything. Hey, yeah. So now based on this, explain our flow in detail.
Yes — for the **fully autonomous daily mode**, your system should not wait for a user to provide a company or YouTube URL. It should run like a market-research pipeline:


```
Daily trigger
   ↓
Broad market discovery
   ↓
Ticker / sector / event discovery
   ↓
Candidate ranking
   ↓
Company-specific deep dive
   ↓
Processing + vector indexing
   ↓
Specialist agents
   ↓
Final daily research report
```


Your current context layer is already suitable as the extraction foundation because it is explicitly designed to collect raw context and save structured JSON, while aggregation/calculation/analysis are deferred to later layers. It also already has the correct groups: fundamentals, US filings, market/price data, institutional activity, news/information, ticker extraction, and persistent history.


---


# 1. Main autonomous design


For autonomous mode, divide the whole system into **five running stages**:


```
Stage 0: Config + Scheduler
Stage 1: Broad Market Discovery Extraction
Stage 2: Discovery Processing + Candidate Selection
Stage 3: Company Deep-Dive Extraction
Stage 4: Processing + Context Building
Stage 5: Agent Analysis + Final Report
```


This is the correct “head-to-tail” flow.


---


# 2. Stage 0 — Config + scheduler


You need a config-driven setup. The system should not hardcode RSS feeds, YouTube channels, categories, tickers, or URLs inside the logic.


Create something like:


```
config/
├── autonomous_run_config.yaml
├── rss_feeds.py
├── youtube_channels.yaml
├── news_queries.yaml
├── website_sources.yaml
├── market_config.yaml
└── deep_dive_rules.yaml
```


Example:


```
run_mode: autonomous_daily

market:
  primary_market: india
  include_us_macro: true
  include_us_stocks: false

schedule:
  discovery_time: "08:00"
  post_market_time: "16:30"
  timezone: "Asia/Kolkata"

limits:
  max_news_articles_per_source: 50
  max_youtube_videos_per_channel: 3
  max_candidates_for_deep_dive: 10
  max_llm_text_docs_per_run: 80

candidate_selection:
  min_mention_score: 2
  min_candidate_score: 50
  always_include_bulk_deal_stocks: true
  always_include_material_filing_stocks: true
```


For YouTube channels:


```
youtube_channels:
  - name: "CNBC-TV18"
    channel_id: "UC..."
    enabled: true
    max_latest_videos: 3
    keywords:
      - market
      - nifty
      - earnings
      - stocks
      - results

  - name: "ET Now"
    channel_id: "UC..."
    enabled: true
    max_latest_videos: 3
```


For broad news:


```
news_queries:
  india_market:
    - "nifty sensex stock market india"
    - "indian stocks earnings results"
    - "nse stocks corporate announcements"
    - "rbi interest rate inflation india"
    - "fii dii flows indian market"
```


This config is the brain of your autonomous trigger.


---


# 3. Stage 1 — Broad market discovery extraction


This is **Phase A**.


At this stage, do not deep dive into companies yet. First collect broad market signals.


## Modules to run in Phase A


```
Market-wide modules:
- rss_feed.py
- moneycontrol.py
- economic_times.py
- newsdata_io.py
- mediastack.py
- gmail/newsletter.py
- youtube channel latest video collector + transcript.py
- india_macro.py
- us_macro.py
- fii_dii.py
- bulk_deals.py
- fno_data.py for NIFTY / BANKNIFTY
```


Your docs already mention that some modules are market-wide and some are company-specific, and that FII/DII, bulk deals, and F&O require regular collection because their public data is today-only/live-only.


---


## Phase A output


After this stage, you should have a raw discovery pool:


```
output/context_ext_layer_outputs/
├── rss/
├── web_scrapers/moneycontrol/
├── web_scrapers/economic_times/
├── news_apis/
├── gmail/
├── youtube/
├── macro_data/
├── fii_dii/
├── bulk_deals/
└── fno_data/
```


This raw data tells you:


```
What happened in the market today?
Which sectors are active?
Which companies are mentioned?
Which stocks had bulk/block deals?
Is market sentiment risk-on or risk-off?
Are FIIs selling or buying?
Are there important macro changes?
Are YouTube/newsletter sources discussing any specific stocks?
```


---


# 4. YouTube autonomous collection flow


Your current YouTube module works when you give a URL. For autonomous mode, add a **YouTube channel discovery module before it**.


New module:


```
context_ext_layer/youtube/channel_videos.py
```


Its job:


```
Configured channel ID
   ↓
Fetch latest videos
   ↓
Filter by date / keywords / already-processed video IDs
   ↓
Return video URLs
   ↓
Pass each URL to existing transcript.py
```


## Track processed videos


Create a small table/file:


```
db/history/youtube_processed_videos.jsonl
```


Record:


```
{
  "channel_id": "UC...",
  "video_id": "Z4CEuHwW0Oo",
  "title": "Market outlook today...",
  "published_at": "2026-05-03T06:00:00Z",
  "processed_at": "2026-05-03T08:10:00Z",
  "transcript_status": "success"
}
```


Before extracting transcript, check:


```
Have we already processed this video_id?
   yes → skip
   no  → extract transcript
```


## YouTube autonomous flow


```
youtube_channels.yaml
   ↓
Fetch latest video metadata from each channel
   ↓
Filter:
   - published today / last 24h
   - title contains market/stock/earnings keywords
   - not already processed
   ↓
Build video URL
   ↓
Use existing transcript.py
   ↓
Save transcript JSON
   ↓
Register video_id as processed
```


## YouTube output after processing


Raw transcript is not directly sent to final agents. It becomes:


```
{
  "source_type": "youtube_transcript",
  "video_id": "",
  "channel_name": "",
  "title": "",
  "published_at": "",
  "mentioned_tickers": [],
  "claims": [],
  "event_cards": [],
  "summary": "",
  "source_reliability": "medium_or_low"
}
```


Use LLM here, because YouTube transcripts are text-heavy and opinion-heavy.


---


# 5. Stage 2 — Discovery processing + candidate selection


This is the most important bridge between Phase A and Phase B.


After broad extraction, you process the discovery pool and decide:


```
Which companies deserve a deep dive today?
```


This stage has two parts:


```
A. Deterministic processing
B. LLM-based text event extraction
```


---


## 5.1 Deterministic processing


Use normal Python for:


```
- clean HTML/text
- remove duplicates
- extract URLs
- extract dates
- match company names using ticker_extractor.py
- count ticker mentions
- detect bulk deal tickers
- detect FII/DII trend
- calculate market regime from macro values
- calculate F&O index sentiment
```


No LLM needed for these.


Example candidate evidence:


```
{
  "ticker": "RELIANCE.NS",
  "mention_count": 6,
  "sources": ["moneycontrol", "rss", "youtube"],
  "bulk_deal_detected": true,
  "material_news_detected": true,
  "sector": "Energy"
}
```


---


## 5.2 LLM-based discovery processing


Use LLM only for text interpretation.


Use it for:


```
- classify article/transcript topic
- identify event type
- classify text sentiment
- classify business impact
- extract claims
- identify whether a news item sounds temporary or structural
- summarize long transcript/article into investment-relevant points
```


For each text item, the LLM should return strict JSON:


```
{
  "document_id": "",
  "mentioned_companies": [
    {
      "company": "HDFC Bank",
      "ticker": "HDFCBANK.NS",
      "confidence": 0.92
    }
  ],
  "events": [
    {
      "ticker": "HDFCBANK.NS",
      "event_type": "margin_pressure",
      "text_sentiment": "negative",
      "business_impact": "negative",
      "time_horizon": "medium_term",
      "temporary_or_structural": "temporary_possible",
      "confidence": 0.74,
      "supporting_text": ""
    }
  ],
  "market_themes": [
    "banking sector pressure",
    "margin compression"
  ]
}
```


Important: this is not the final recommendation. This only creates **candidate evidence**.


---


# 6. Candidate scoring


After Phase A processing, calculate a `candidate_score`.


Example:


```
candidate_score =
  ticker_mention_score
+ source_reliability_score
+ event_materiality_score
+ price_or_volume_trigger_score
+ bulk_deal_score
+ filing_score
+ sector_theme_score
+ novelty_score
```


Example scoring rules:


```
Mentioned in 1 source       +5
Mentioned in 3+ sources     +15
Mentioned in 5+ sources     +25
Official filing event       +30
Bulk/block deal detected    +20
Earnings/guidance event     +25
Regulatory/legal issue      +25
YouTube-only mention        +5
Newsletter-only mention     +5
High reliability source     +20
Duplicate article           +0 after deduplication
```


Output:


```
{
  "run_date": "2026-05-03",
  "selected_candidates": [
    {
      "ticker": "HDFCBANK.NS",
      "company": "HDFC Bank",
      "candidate_score": 84,
      "selection_reason": [
        "Mentioned in 7 articles",
        "Banking sector theme detected",
        "Negative margin-pressure event detected",
        "High-reliability source present"
      ],
      "deep_dive_required": true
    },
    {
      "ticker": "RELIANCE.NS",
      "company": "Reliance Industries",
      "candidate_score": 76,
      "selection_reason": [
        "Bulk deal detected",
        "Energy sector mentioned",
        "Multiple news mentions"
      ],
      "deep_dive_required": true
    }
  ]
}
```


This candidate list becomes the input to Phase B.


---


# 7. Stage 3 — Company deep-dive extraction


This is **Phase B**.


Now you run company-specific modules only for selected candidates.


For each selected ticker, run:


```
Company-specific modules:
- market_data.py
- price_history.py
- screener_in.py
- peer_comparison.py
- analyst_estimates.py
- exchange_filings.py
- filing_docs.py
- corporate_actions.py
- fno_data.py if stock is F&O eligible
- sec_filings.py if US ticker
- news APIs with ticker-specific query
```


Your context layer already separates modules like `screener_in.py`, `peer_comparison.py`, `analyst_estimates.py`, `exchange_filings.py`, `filing_docs.py`, `corporate_actions.py`, `sec_filings.py`, `market_data.py`, and `price_history.py`, so this deep-dive phase can directly orchestrate those existing modules.


---


## Example Phase B plan


```
{
  "ticker": "HDFCBANK.NS",
  "market": "india",
  "modules_to_run": [
    {
      "module": "market_data",
      "params": {
        "ticker": "HDFCBANK.NS"
      }
    },
    {
      "module": "price_history",
      "params": {
        "ticker": "HDFCBANK.NS",
        "period": "1y"
      }
    },
    {
      "module": "screener_in",
      "params": {
        "url": "https://www.screener.in/company/HDFCBANK/"
      }
    },
    {
      "module": "peer_comparison",
      "params": {
        "ticker": "HDFCBANK.NS",
        "max_peers": 15
      }
    },
    {
      "module": "analyst_estimates",
      "params": {
        "ticker": "HDFCBANK.NS"
      }
    },
    {
      "module": "exchange_filings",
      "params": {
        "ticker": "HDFCBANK",
        "limit": 50,
        "material_only": true
      }
    },
    {
      "module": "filing_docs",
      "params": {
        "ticker": "HDFCBANK",
        "transcripts": 4,
        "presentations": 2
      }
    }
  ]
}
```


---


# 8. Stage 4 — Processing + context building


Now raw Phase A and Phase B outputs become useful.


This processing layer should produce:


```
1. normalized_documents
2. ticker_candidates
3. event_cards
4. numeric_features
5. vector_index_chunks
6. company_context_packets
7. market_context_packet
```


---


# 9. Where to use LLMs module-by-module


Use this rule:


```
Numeric / table data → deterministic Python
Long text / narrative / commentary → LLM + strict JSON
```


## LLM required


```
Use LLM for:
- YouTube transcripts
- newsletters
- generic articles
- Moneycontrol article body
- Economic Times article body
- investor presentation text
- concall transcript text
- SEC filing text if you extract risk factors / MD&A
- exchange filing subject classification if keyword rules are not enough
```


## LLM not required


```
Do not use LLM for:
- market_data.py
- price_history.py
- peer_comparison.py ratio calculations
- analyst_estimates.py numeric summaries
- FII/DII calculations
- bulk deal filtering/counting
- F&O derived metrics
- macro numeric features
- corporate action date/count calculations
```


---


# 10. Module-level autonomous conversion map


## A. Discovery modules


| Module | Autonomous trigger | Processing output | LLM? | Vector DB? |
| --- | --- | --- | --- | --- |
| `rss_feed.py` | Daily | headline cards, URLs, ticker hints | Optional | No, unless summary is long |
| `moneycontrol.py` | Daily by category | news event cards | Yes | Yes for full article body |
| `economic_times.py` | Daily by category | news event cards | Yes | Yes for full article body |
| `newsdata_io.py` | Daily broad queries | headline/news metadata cards | Optional | Usually no |
| `mediastack.py` | Daily or limited use | headline/news metadata cards | Optional | Usually no |
| `gmail/newsletter.py` | Daily | idea cards, claim cards | Yes | Yes |
| `youtube/channel_videos.py` | Daily per configured channel | video URL list | No | No |
| `youtube/transcript.py` | For new videos | transcript claim/event cards | Yes | Yes |
| `ticker_extractor.py` | After every text source | ticker candidates | No first, LLM fallback | No |


---


## B. Market-wide modules


| Module | Autonomous trigger | Processing output | LLM? | Vector DB? |
| --- | --- | --- | --- | --- |
| `india_macro.py` | Daily morning + post-market | India market regime features | No | No |
| `us_macro.py` | Daily/weekly | global risk features | No | No |
| `fii_dii.py` | Daily after market close | institutional flow trend | No | No |
| `bulk_deals.py` | Daily after market close | bulk-deal candidate tickers | No | No |
| `fno_data.py` for NIFTY/BANKNIFTY | Market hours/post-market | derivatives sentiment | No | No |


---


## C. Company deep-dive modules


| Module | Trigger | Processing output | LLM? | Vector DB? |
| --- | --- | --- | --- | --- |
| `market_data.py` | Candidate selected | price snapshot features | No | No |
| `price_history.py` | Candidate selected | trend, volatility, drawdown, moving average features | No | No |
| `screener_in.py` | Candidate selected | fundamental quality features | No for tables; optional LLM for pros/cons | Store PDFs/text only |
| `peer_comparison.py` | Candidate selected | relative valuation/quality features | No | No |
| `analyst_estimates.py` | Candidate selected | estimate revision and analyst signal | No | No |
| `exchange_filings.py` | Candidate selected/watchlist | official event cards | Optional LLM for subject summarization | No |
| `filing_docs.py` | Candidate selected/earnings event | management commentary features | Yes | Yes |
| `corporate_actions.py` | Candidate selected | capital allocation features | No | No |
| `sec_filings.py` | US candidate selected | US fundamental/risk features | No for XBRL; Yes for filing text | Yes for filing text |
| `fno_data.py` for stock | F&O eligible candidate | stock derivatives features | No | No |


---


# 11. Vector database strategy


Do not put everything into vector DB.


## Put these into vector DB


```
- YouTube transcript chunks
- newsletter chunks
- full article bodies
- concall transcript chunks
- investor presentation chunks
- SEC filing text chunks
- quarterly filing PDF text
```


## Do not put these into vector DB


```
- market_data current snapshot
- price history rows
- analyst estimates JSON
- peer comparison ratios
- FII/DII numbers
- bulk deal rows
- F&O option chain rows
- macro numeric data
```


Numeric data should go into structured tables or JSON feature files, not vector DB.


---


## Chunking design


For text documents:


```
{
  "chunk_id": "HDFCBANK_TRANSCRIPT_Q4FY26_0001",
  "document_id": "HDFCBANK_TRANSCRIPT_Q4FY26",
  "ticker": "HDFCBANK.NS",
  "source_type": "concall_transcript",
  "published_at": "",
  "chunk_text": "",
  "section": "management_commentary | analyst_qna | risk | guidance",
  "embedding": [],
  "metadata": {
    "source_reliability": "high",
    "market": "india",
    "fiscal_period": "Q4FY26"
  }
}
```


Then later agents can retrieve:


```
“Give me margin pressure commentary for HDFC Bank”
“Find management guidance from latest transcript”
“Find risk factors about debt”
```


---


# 12. Detailed autonomous daily flow


Here is the full daily flow.


## Step 1: Start run


```
scheduler triggers autonomous_daily_run
```


Create run record:


```
{
  "run_id": "AUTO_2026_05_03_AM",
  "run_type": "autonomous_daily",
  "started_at": "2026-05-03T08:00:00+05:30",
  "status": "running"
}
```


---


## Step 2: Load configs


```
Load:
- RSS feeds
- Moneycontrol categories
- ET categories
- news API queries
- Gmail newsletter filters
- YouTube channel IDs
- macro settings
- candidate scoring rules
- deep-dive limits
```


---


## Step 3: Broad extraction


Run:


```
rss_feed.save_all_feeds()
moneycontrol.save_category(...)
economic_times.save_category(...)
newsdata_io.save_news(...)
mediastack.save_news(...)
newsletter.save_newsletters(...)
youtube_channel_videos.fetch_latest()
transcript.save_transcript(video_url)
india_macro.save_macro_snapshot()
us_macro.save_us_macro()
fii_dii.save_fii_dii()
bulk_deals.save_bulk_deals()
fno_data.save_fno_snapshot("NIFTY")
fno_data.save_fno_snapshot("BANKNIFTY")
```


---


## Step 4: Sync today-only history


Immediately run:


```
python db/sync.py
```


This is important because FII/DII, bulk deals, and some macro snapshots need persistent history. Your docs already mention that `db/sync.py` appends daily outputs into persistent JSONL history for modules that only return today’s snapshot.


---


## Step 5: Normalize discovery documents


Every raw output becomes a normalized document:


```
{
  "document_id": "",
  "run_id": "AUTO_2026_05_03_AM",
  "source_type": "moneycontrol_article",
  "source_name": "Moneycontrol",
  "title": "",
  "url": "",
  "published_at": "",
  "fetched_at": "",
  "market": "india",
  "raw_path": "",
  "clean_text": "",
  "source_reliability": "medium",
  "processing_status": "normalized"
}
```


---


## Step 6: Deduplicate


Group duplicate news:


```
Same URL → duplicate
Same title → duplicate
Same headline with small changes → near duplicate
Same company + same event + same date → event duplicate
```


Output:


```
{
  "canonical_event_id": "HDFCBANK_MARGIN_PRESSURE_2026_05_03",
  "source_count": 5,
  "duplicate_documents": []
}
```


---


## Step 7: Extract ticker candidates


Use hybrid method:


```
1. Deterministic ticker_extractor.py
2. Alias dictionary
3. Company-name fuzzy match
4. LLM fallback only for ambiguous text
```


Output:


```
{
  "ticker_candidates": [
    {
      "ticker": "HDFCBANK.NS",
      "company": "HDFC Bank",
      "source_documents": [],
      "mention_count": 7,
      "confidence": 0.93
    }
  ]
}
```


---


## Step 8: LLM event extraction for text sources


Run LLM on:


```
- full article bodies
- YouTube transcript chunks
- newsletters
- generic website text
```


Output event cards:


```
{
  "event_id": "HDFCBANK_MARGIN_PRESSURE_2026_05_03",
  "ticker": "HDFCBANK.NS",
  "event_type": "margin_pressure",
  "event_summary": "Multiple sources discussed margin pressure in banking stocks.",
  "text_sentiment": "negative",
  "business_impact": "negative",
  "temporary_or_structural": "unknown",
  "source_reliability": "medium",
  "confidence": 0.72,
  "supporting_sources": []
}
```


---


## Step 9: Candidate scoring


Combine:


```
ticker mentions
event cards
bulk deal tickers
sector themes
source reliability
macro impact
news novelty
```


Output:


```
{
  "selected_candidates": [
    {
      "ticker": "HDFCBANK.NS",
      "score": 84,
      "reason": [
        "High news mention count",
        "Banking sector stress theme",
        "Margin pressure event detected"
      ]
    },
    {
      "ticker": "RELIANCE.NS",
      "score": 76,
      "reason": [
        "Bulk deal detected",
        "Energy sector active",
        "Multiple article mentions"
      ]
    }
  ]
}
```


---


## Step 10: Build Phase B deep-dive plan


For each selected ticker, decide modules.


Example rules:


```
Indian stock:
- market_data
- price_history
- screener_in
- peer_comparison
- analyst_estimates
- exchange_filings
- filing_docs
- corporate_actions
- fno_data if eligible

US stock:
- market_data
- price_history
- sec_filings
- analyst_estimates
- peer_comparison if supported
- news APIs
```


---


## Step 11: Run company deep-dive extraction


This creates raw company-specific files.


```
output/context_ext_layer_outputs/
├── market_data/HDFCBANK_NS_2026-05-03.json
├── market_data/HDFCBANK_NS_history_1y_2026-05-03.json
├── analyst_estimates/HDFCBANK_analyst_estimates_2026-05-03.json
├── peer_comparison/HDFCBANK_peers_2026-05-03.json
├── exchange_filings/HDFCBANK_announcements_2026-05-03.json
├── exchange_filings/HDFCBANK_filing_docs_2026-05-03.json
└── corporate_actions/HDFCBANK_corporate_actions_2026-05-03.json
```


---


## Step 12: Process company-specific outputs


Convert:


```
price history → price features
market data → price snapshot features
screener → fundamental features
peer comparison → relative valuation features
analyst estimates → analyst signal features
exchange filings → official event cards
filing docs → management commentary features
corporate actions → capital allocation features
```


Output:


```
{
  "ticker": "HDFCBANK.NS",
  "price_features": {},
  "fundamental_features": {},
  "valuation_features": {},
  "analyst_features": {},
  "official_event_cards": [],
  "management_commentary_features": {},
  "risk_features": {}
}
```


---


## Step 13: Build vector index


For selected text sources, chunk and index:


```
- full articles
- YouTube transcripts
- newsletters
- concall transcripts
- investor presentations
- SEC filing text
```


Each chunk includes metadata:


```
{
  "ticker": "HDFCBANK.NS",
  "source_type": "concall_transcript",
  "source_reliability": "high",
  "published_at": "",
  "event_id": "",
  "section": "analyst_qna"
}
```


---


## Step 14: Build final company context packet


This is what agents consume.


```
{
  "ticker": "HDFCBANK.NS",
  "company": "HDFC Bank",
  "run_id": "AUTO_2026_05_03_AM",
  "selection_reason": [],
  "market_context": {},
  "price_context": {},
  "fundamental_context": {},
  "valuation_context": {},
  "analyst_context": {},
  "event_context": [],
  "management_context": {},
  "risk_context": {},
  "source_quality": {},
  "retrieval_refs": []
}
```


---


# 13. Stage 5 — Agents


Now the actual agent layer starts.


Use these agents:


```
1. Market Regime Agent
2. Candidate Explanation Agent
3. Fundamental Quality Agent
4. Event Impact Agent
5. Valuation Agent
6. Risk Agent
7. Final Research Agent
8. Guardrail/Compliance Agent
```


## Market Regime Agent receives


```
macro features
FII/DII features
index F&O features
Nifty/Sensex valuation
global macro
```


Output:


```
{
  "market_regime": "neutral_to_cautious",
  "recommended_posture": "selective_buying",
  "reason": []
}
```


## Fundamental Agent receives


```
screener features
SEC features
analyst estimate features
peer features
corporate action features
```


Output:


```
{
  "business_quality": "medium",
  "growth_quality": "stable",
  "financial_risk": "medium",
  "score": 68
}
```


## Event Impact Agent receives


```
news event cards
official filing event cards
price reaction
volume reaction
management commentary
```


Output:


```
{
  "latest_event_impact": "mixed",
  "temporary_or_structural": "unknown",
  "confidence": "medium"
}
```


## Final Research Agent receives compact outputs only


It should not receive all raw files.


Output:


```
{
  "daily_market_view": {},
  "top_buy_candidates": [],
  "watchlist": [],
  "avoid_or_high_risk": [],
  "data_gaps": [],
  "final_summary": ""
}
```


---


# 14. Recommended folder structure


Add these layers:


```
Stock_Researcher/
├── config/
│   ├── autonomous_run_config.yaml
│   ├── youtube_channels.yaml
│   ├── news_queries.yaml
│   └── deep_dive_rules.yaml
│
├── orchestration_layer/
│   ├── autonomous_runner.py
│   ├── collection_planner.py
│   ├── module_registry.py
│   ├── candidate_generator.py
│   ├── deep_dive_planner.py
│   └── run_state.py
│
├── context_ext_layer/
│   └── existing modules
│
├── processing_layer/
│   ├── normalizers/
│   ├── deduplication/
│   ├── entity_resolution/
│   ├── text_event_extraction/
│   ├── feature_engineering/
│   ├── evidence_cards/
│   ├── vector_indexing/
│   └── context_builder/
│
├── agent_layer/
│   ├── market_regime_agent.py
│   ├── fundamental_agent.py
│   ├── event_impact_agent.py
│   ├── valuation_agent.py
│   ├── risk_agent.py
│   ├── final_research_agent.py
│   └── guardrail_agent.py
│
└── output/
    ├── context_ext_layer_outputs/
    ├── processing_layer_outputs/
    └── agent_outputs/
```


---


# 15. The main flow in simple words


Your autonomous system should behave like this:


```
Every day, the system wakes up.

First, it collects broad market data:
news, RSS, newsletters, YouTube transcripts, macro, FII/DII, bulk deals, F&O.

Then it processes that broad data:
extracts tickers, detects events, identifies themes, scores companies.

Then it selects a limited number of companies:
for example, top 10 candidates.

Then it performs a deep dive:
fundamentals, price history, filings, analyst estimates, peers, management transcripts.

Then it processes the deep-dive data:
numeric data becomes features, text data becomes event/claim cards, long documents go into vector DB.

Then specialist agents analyze:
market condition, business quality, valuation, event impact, risks.

Then final agent produces:
daily market view, stock candidates, watchlist, avoid list, and data gaps.
```


---


# 16. Your next build target


The next thing to code is **not** the final LLM agent.


Build this next:


```
orchestration_layer/autonomous_runner.py
orchestration_layer/collection_planner.py
orchestration_layer/candidate_generator.py
```


Minimum first version:


```
1. Run RSS + Moneycontrol + ET + macro + FII/DII + bulk deals.
2. Normalize article/headline text.
3. Extract tickers using ticker_extractor.py.
4. Count mentions and detect bulk-deal tickers.
5. Select top 5 candidate tickers.
6. Run market_data + price_history + screener + exchange_filings for those tickers.
7. Save one company_context_packet JSON per ticker.
```


Then add YouTube autonomous channel ingestion.


Then add LLM event extraction.


That order will keep your system clean and avoid overbuilding too early.
ChatGPT can make mistakes. Check important info. See Cookie Preferences.
