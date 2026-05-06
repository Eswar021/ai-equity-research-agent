**You**

I am working on a project where if I give the context from different sources, like from a YouTube video, uh something related to for an investment-based, okay? And if there is like uh some investment-related news or like stock market news, if there is a video, I can give like a transcript of that video. And also from scraping some of the data from uh uh some of the uh websites or some newsletters, and based on these, uh it wanted to say the model has to return if there are if there are any significant um stocks that I can invest in, or like it should explain whether it is a good time or bad time to invest in the uh stock market, like how based on the uh previous trends, it should say how like whether the market is down or low uh or up. Uh if it is like at a lower, no, we have to like invest, right? So, like it's like a stocks suggestion like based on the news and other thing, it should suggest me like these key things, not just summarizing all the context, like key findings, whether invest or not, okay? If invest, why, what is the reason that it is saying I should invest? And what are the, if I have to invest in a stock, like if it's based on the news, it will identify, right? Present because of some news, that particular stocks, that particular stock for that particular company, there is some bad news, so there is a decrease in stock. And if it is like a temporary one, like some news that only caused a decrease in stock rate for only today, and if it's not a major thing, then we should invest in that, right? So based on those also, you should suggest. So to build this system, what are the like instructions I need to give to that agent? For example, let us assume we have all the tools that will help us to extract news, newsletters, YouTube transcripts, etc. Now, when we are passing all this context to the LLM, what is the prompt that we should give so it can, you know, understand everything and it will behave according to our rules. So let us consider we are building an agent-based system. So how should we do it?

---

**ChatGPT**

I’ll frame this as an agent design, not just a single prompt: inputs, specialist agents, decision rules, output format, and guardrails so it does not hallucinate stock recommendations.

---

**ChatGPT**

You should build this as an **investment research agent**, not as a simple summarizer. The agent should read YouTube transcripts, newsletters, news articles, scraped web content, and market data, then return **actionable research signals** with reasons, risks, confidence, and evidence.

Important: do not make the model blindly say “stock is down, so buy.” A stock can be down because of a temporary news event, or because the business is actually weakening. The agent must separate **temporary price reaction** from **structural business risk**.

Also, because this touches investment recommendations, add strong guardrails. In real financial advice, risk tolerance, time horizon, diversification, and suitability matter. SEC Investor.gov explains that asset allocation depends heavily on time horizon and risk tolerance, and diversification helps reduce portfolio risk. FINRA also notes that higher expected return usually comes with higher risk. Investor+2Investor+2

---

## Recommended agent flow

Use multiple agents instead of one big prompt:

```
Input Sources
   ↓
Source Cleaning Agent
   ↓
Entity / Ticker Extraction Agent
   ↓
News & Event Classification Agent
   ↓
Market Data / Trend Analysis Agent
   ↓
Fundamental / Risk Analysis Agent
   ↓
Investment Decision Agent
   ↓
Compliance / Guardrail Agent
   ↓
Final Output
```

The final answer should not just summarize. It should say:

```
Market condition: Risk-on / risk-off / neutral
Overall action: Buy selectively / wait / avoid / watchlist
Stock candidates: ticker, reason, catalyst, risk, confidence
Temporary dip or structural issue: explanation
Evidence: source-based reasoning
Time horizon: short-term / medium-term / long-term
```

---

## Master system prompt for the main agent

You can use this as your core instruction:

```
You are an investment research analysis agent. Your role is to analyze provided context from YouTube transcripts, financial news, newsletters, scraped websites, earnings updates, analyst commentary, and market data.

Your goal is not to summarize the content. Your goal is to extract investment-relevant signals and produce a structured research view.

You must identify:
1. Important companies, sectors, tickers, commodities, indexes, or macro themes mentioned.
2. Whether the information is positive, negative, mixed, or neutral for each company or sector.
3. Whether the news appears temporary, sentiment-driven, or structurally important.
4. Whether the stock price movement looks like a possible opportunity, a warning signal, or noise.
5. Whether the current market environment is favorable for investing, waiting, reducing risk, or building a watchlist.
6. What additional data is required before making a stronger conclusion.

You must not give blind buy/sell calls. You must provide a research-based rating:
- Strong Buy Candidate
- Buy Candidate
- Watchlist
- Hold / Neutral
- Avoid
- High Risk / Speculative

You must always explain:
- Why this stock or sector is being highlighted.
- What event or trend is causing the signal.
- Whether the price drop is likely temporary or structural.
- What risks could invalidate the thesis.
- What data is missing.
- Confidence level: High, Medium, or Low.

You must never claim guaranteed returns. You must never say a user should invest only because a stock price has fallen. A fallen price is an opportunity only if the business quality, earnings outlook, balance sheet, valuation, and future catalyst support recovery.

You must separate short-term trading signals from long-term investment signals.

Use only the provided context and available tool results. If evidence is weak, say the signal is weak. If the ticker mapping is uncertain, do not assume. Ask for confirmation or mark it as uncertain.

Output must be clear, structured, and decision-oriented.
```

---

## Agent 1: Source cleaning and reliability prompt

```
You are a financial source-cleaning agent.

Given raw text from YouTube transcripts, newsletters, scraped websites, and news articles, clean the content and extract only investment-relevant information.

For each source, identify:
- Source type: YouTube, newsletter, news article, blog, social media, earnings report, SEC filing, analyst report, company announcement.
- Publication date or estimated date.
- Main topics.
- Companies, sectors, tickers, indexes, commodities, or macro indicators mentioned.
- Whether the source is factual, opinion-based, promotional, speculative, or uncertain.
- Any claims that require verification.

Remove filler, repeated transcript text, sponsor sections, unrelated personal commentary, and generic market noise.

Return structured notes with source reliability:
- High reliability: official filings, company earnings, regulator data, exchange data.
- Medium reliability: established financial news, credible analyst commentary.
- Low reliability: social media, promotional newsletters, unsourced YouTube claims.

Do not make investment conclusions. Only clean, classify, and prepare the source data.
```

---

## Agent 2: Entity and ticker extraction prompt

```
You are a financial entity extraction agent.

From the cleaned context, extract all companies, tickers, sectors, indexes, commodities, currencies, and macroeconomic indicators.

For each entity, return:
- Company name
- Ticker symbol
- Exchange, if known
- Sector / industry
- Mentions count
- Context of mention
- Sentiment: positive, negative, mixed, neutral
- Confidence in ticker mapping

Rules:
- Do not guess ticker symbols when company names are ambiguous.
- If a company has multiple listings, mark ambiguity.
- If only a product name is mentioned, identify the parent company only when confidence is high.
- Distinguish company-specific news from sector-wide news.
```

Example:

```
{
  "entities": [
    {
      "company": "Nvidia",
      "ticker": "NVDA",
      "sector": "Semiconductors",
      "sentiment": "Positive",
      "reason": "AI chip demand mentioned as strong",
      "confidence": "High"
    }
  ]
}
```

---

## Agent 3: News and event classification prompt

This is very important for your use case.

```
You are a financial news impact classification agent.

For each company or sector mentioned, classify the event type and expected investment impact.

Classify event type:
- Earnings beat
- Earnings miss
- Revenue growth
- Margin pressure
- Guidance raise
- Guidance cut
- Product launch
- Regulatory issue
- Lawsuit
- Fraud/accounting concern
- Management change
- Analyst upgrade/downgrade
- Macro pressure
- Interest rate impact
- Sector rotation
- Temporary sentiment issue
- Structural business deterioration
- M&A / acquisition
- Supply chain issue
- Geopolitical risk

For each event, decide whether it is:
1. Temporary / one-time
2. Medium-term concern
3. Structural long-term risk
4. Positive catalyst
5. Noise / low relevance

Use this logic:
- Temporary bad news may create opportunity if fundamentals remain strong, valuation becomes attractive, and there is a recovery catalyst.
- Structural bad news is not a buy signal even if the stock price drops.
- Positive news is not automatically a buy signal if valuation is already expensive.
- Repeated negative news increases risk.
- Management credibility, debt, declining demand, regulatory investigation, fraud, or accounting issues should be treated as serious risks.

Return:
- Event summary
- Impact direction
- Time horizon
- Severity
- Investment interpretation
- Confidence
```

---

## Agent 4: Market trend analysis prompt

This agent should check whether the overall market is high, low, overheated, or weak.

```
You are a market trend analysis agent.

Analyze the current market condition using index performance, sector performance, price trends, volatility, interest rates, inflation data, earnings trends, liquidity, and macro news.

Determine:
- Market regime: risk-on, risk-off, neutral, uncertain.
- Trend: bullish, bearish, sideways, recovering, overextended.
- Whether the market appears expensive, fairly valued, undervalued, or uncertain.
- Whether broad-market investing looks attractive now.
- Whether selective stock picking is better than broad buying.
- Whether cash/waiting/watchlist is more appropriate.

Use these signals where available:
- Major indexes: S&P 500, Nasdaq, Dow, Russell 2000.
- Moving averages: 20-day, 50-day, 200-day.
- Market breadth.
- Sector rotation.
- Volatility index.
- Earnings growth.
- Interest rate expectations.
- Inflation and jobs data.
- Valuation indicators such as P/E compared with historical averages.

Do not conclude “market is low, so buy” unless valuation, trend, sentiment, and macro data support the conclusion.

Return:
- Market condition
- Risk level
- Suggested posture: aggressive, selective, cautious, defensive, wait
- Reasoning
- Data gaps
```

---

## Agent 5: Stock opportunity scoring prompt

Use this to rank stocks.

```
You are a stock opportunity scoring agent.

For each identified stock, calculate a research score from 0 to 100 using the provided context and available market/fundamental data.

Score the stock using these categories:

1. News catalyst strength: 0-20
2. Fundamental quality: 0-20
3. Valuation attractiveness: 0-15
4. Price dislocation / dip opportunity: 0-15
5. Technical trend support: 0-10
6. Risk level: 0-10
7. Source confidence: 0-10

Adjust scoring:
- Penalize heavily for fraud, accounting issues, major regulatory risk, debt/liquidity problems, repeated guidance cuts, or business model deterioration.
- Do not reward a stock only because it dropped.
- Reward temporary overreaction only when fundamentals remain strong.
- Reward high-quality companies with clear catalysts and reasonable valuation.
- Lower confidence if evidence comes mostly from opinion sources.

Return:
- Ticker
- Score
- Rating
- Reason
- Bull case
- Bear case
- Key catalyst
- Key risk
- Suggested action
```

Suggested score mapping:

```
85-100: Strong Buy Candidate
70-84: Buy Candidate
55-69: Watchlist
40-54: Neutral / Hold
Below 40: Avoid / High Risk
```

---

## Agent 6: Final investment decision prompt

```
You are the final investment decision agent.

Using outputs from all previous agents, produce a clean investment research report.

Your answer must include:

1. Executive decision
   - Should the user invest now, wait, or only build a watchlist?
   - Is the current market favorable or risky?

2. Market view
   - Overall market condition
   - Major reasons
   - Risk level

3. Top stock candidates
   For each stock:
   - Ticker
   - Company
   - Rating
   - Confidence
   - Why it is interesting
   - What news caused the signal
   - Whether the opportunity is temporary dip, long-term growth, value opportunity, or speculative
   - Risks
   - What should be verified before investing

4. Stocks or sectors to avoid
   - Explain why

5. Watchlist
   - Stocks that are interesting but need better entry price or more confirmation

6. Data gaps
   - Missing financials, valuation, price trend, earnings date, debt, guidance, etc.

7. Final note
   - This is research support, not guaranteed financial advice.
```

---

## Final output format you should force

Ask the model to always return this structure:

```
{
  "overall_market_view": {
    "condition": "Risk-on / Risk-off / Neutral / Uncertain",
    "recommended_posture": "Invest selectively / Wait / Build watchlist / Avoid high risk",
    "confidence": "High / Medium / Low",
    "reasoning": []
  },
  "top_opportunities": [
    {
      "ticker": "",
      "company": "",
      "rating": "Strong Buy Candidate / Buy Candidate / Watchlist / Neutral / Avoid",
      "confidence": "High / Medium / Low",
      "opportunity_type": "Temporary dip / Long-term growth / Value / Momentum / Speculative",
      "news_trigger": "",
      "why_it_may_be_attractive": [],
      "risks": [],
      "what_to_verify_before_investing": [],
      "time_horizon": "Short-term / Medium-term / Long-term"
    }
  ],
  "avoid_or_high_risk": [
    {
      "ticker": "",
      "reason": "",
      "risk_type": "Structural / Valuation / Regulatory / Earnings / Debt / Unknown"
    }
  ],
  "watchlist": [
    {
      "ticker": "",
      "reason_to_watch": "",
      "entry_condition": ""
    }
  ],
  "data_gaps": [],
  "final_summary": ""
}
```

---

## Temporary dip vs structural issue rules

Give this rule strongly to your agent:

```
When a stock falls, classify the fall before recommending anything.

Temporary dip examples:
- One-day negative headline with limited long-term impact
- Analyst downgrade without fundamental deterioration
- Broad market selloff affecting strong companies
- Short-term supply issue with recovery expected
- Earnings miss caused by one-time cost
- Good company sold off with sector panic

Structural risk examples:
- Fraud or accounting concerns
- Repeated revenue decline
- Major guidance cut
- Loss of key customer
- Regulatory investigation
- Balance sheet stress
- Debt refinancing risk
- Declining margins for several quarters
- Product demand weakening
- Management credibility issues

Only mark a price drop as a buying opportunity if:
1. The issue appears temporary.
2. Fundamentals are still strong.
3. Valuation is reasonable.
4. There is a recovery catalyst.
5. Risk/reward is attractive.
6. Evidence is strong enough.
```

---

## Simple example final answer style

Your agent should produce something like this:

```
Overall Market View:
The market condition appears neutral-to-cautious. Broad buying is not ideal yet, but selective buying may be reasonable in high-quality companies where temporary news has caused a price dislocation.

Top Opportunity:
1. XYZ Corp — Watchlist / Buy Candidate
The stock dropped after a short-term earnings disappointment, but the decline appears more sentiment-driven than structural based on the provided sources. Revenue growth remains positive, management did not reduce full-year guidance, and the sector outlook is still stable.

Why it may be attractive:
- Price dropped due to one-time margin pressure.
- Demand trend remains intact.
- No major balance-sheet concern found.
- If next quarter confirms recovery, this could become a stronger buy candidate.

Risks:
- If margin pressure continues, this becomes structural.
- Need to verify debt, cash flow, valuation, and next earnings guidance.

Suggested action:
Do not buy blindly today. Add to watchlist or consider phased entry only after confirming valuation and technical support.
```

---

## Best production design

For your actual system, do not pass only transcript/news text to the LLM. Give the LLM structured context like this:

```
{
  "user_profile": {
    "risk_tolerance": "medium",
    "time_horizon": "1-3 years",
    "investment_style": "growth + value",
    "region": "US market",
    "capital_allocation_preference": "phased entry"
  },
  "sources": [
    {
      "source_type": "youtube_transcript",
      "title": "",
      "published_date": "",
      "content": ""
    },
    {
      "source_type": "newsletter",
      "published_date": "",
      "content": ""
    }
  ],
  "market_data": {
    "index_trends": {},
    "stock_prices": {},
    "valuation_metrics": {},
    "earnings_data": {}
  }
}
```

Without user profile, the agent should only give **general research candidates**, not personalized investment advice. Suitability and customer-specific context are important concepts in regulated investment recommendations; FINRA’s suitability framework includes reasonable-basis, customer-specific, and quantitative suitability obligations for firms and associated persons. FINRA

---

## The main prompt you can directly start with

```
You are an investment research agent.

I will provide context from YouTube transcripts, newsletters, news articles, scraped websites, and market data.

Your task is not to summarize the content. Your task is to identify actionable investment research signals.

Analyze the context and return:
1. Overall market condition: good time to invest, bad time to invest, wait, or invest selectively.
2. Key stocks, sectors, or themes mentioned.
3. Whether each stock is a buy candidate, watchlist candidate, avoid, or high-risk.
4. Whether any stock price drop appears temporary or structural.
5. Why the stock may be attractive or risky.
6. What news or catalyst caused the signal.
7. What data must be verified before making a decision.
8. Confidence level for each conclusion.

Rules:
- Do not recommend a stock only because it has fallen.
- Do not assume bad news is temporary.
- Do not assume positive news means the stock is a buy.
- Always check fundamentals, valuation, market trend, event severity, and risk.
- If evidence is weak, mark confidence as low.
- If ticker mapping is uncertain, say so.
- If there is not enough information, say “insufficient evidence.”
- Separate short-term trading ideas from long-term investment ideas.
- Mention risks clearly.
- Never guarantee returns.

Output in this format:

Overall Market View:
- Condition:
- Suggested posture:
- Confidence:
- Reason:

Top Stock Candidates:
For each:
- Ticker:
- Company:
- Rating:
- Opportunity type:
- News trigger:
- Why it may be attractive:
- Risks:
- What to verify:
- Time horizon:
- Confidence:

Avoid / High-Risk:
- Ticker:
- Reason:

Watchlist:
- Ticker:
- Reason to watch:
- Entry condition:

Final Summary:
- Clear, practical conclusion.
```

This will make your agent behave like a **research analyst + risk analyst + market strategist**, instead of a basic summarizer.

---

**You**

Okay, now, let us concentrate on context collecting. So, what are the sources we need to collect from, and how do we need to collect them from? Like, how to connect to those sources and how to collect those contexts? For example, if we take a YouTube video, for that video, how to get the transcript, and from particular websites, how to get the information? How exactly we need to collect all the required context for our system? What are all the contexts we need to get, right?

---

**ChatGPT**

Good, context collection is the foundation. I’ll break it into source categories, what each source gives, preferred collection method, and how to normalize everything into one schema for your agent.

---

**ChatGPT**

For your first version, do not try to collect “everything.” Start with high-signal sources: transcripts/newsletters/articles + price data + SEC filings + earnings/guidance. Then add social sentiment only after the core pipeline is stable.

---

**ChatGPT**

Yes, now we should focus on the **context collection layer**. For this investment agent, the LLM should not receive random raw text only. It should receive a clean, structured **evidence package** collected from different sources.

The system should collect these 6 major context types:

```
1. Narrative context         → YouTube transcripts, newsletters, articles, blogs
2. Market data context       → stock price, volume, index trend, sector trend
3. Company context           → financials, earnings, guidance, filings
4. Event context             → news trigger, lawsuit, earnings miss, downgrade, product launch
5. Macro context             → interest rates, inflation, Fed news, oil, currency, economy
6. Sentiment context         → analyst sentiment, news sentiment, optional social sentiment
```

---

# 1. High-level collection architecture

Your context collection pipeline should look like this:

```
User gives:
- YouTube URL
- Website URL
- Newsletter text
- Stock ticker
- Topic like “AI stocks” or “market crash news”

        ↓

Source Collector
- YouTube transcript collector
- Web article collector
- Newsletter/email collector
- News API collector
- Market data collector
- SEC filing collector
- Earnings/fundamental collector

        ↓

Cleaning + Normalization
- remove ads/sponsors/filler
- extract title, date, author, source
- extract companies and tickers
- split into chunks
- assign reliability score

        ↓

Storage
- raw text in object storage
- structured metadata in database
- chunks in vector DB
- price/fundamental data in relational tables

        ↓

LLM Context Builder
- fetch only relevant chunks
- add price/fundamental/filing data
- create final evidence package

        ↓

Investment Research Agent
```

The key point: **do not directly pass raw YouTube transcript + raw website text to the LLM.** First convert everything into structured context.

---

# 2. Main sources you should collect from

## A. YouTube videos

Use YouTube mainly for:

```
- investor interviews
- market commentary
- earnings analysis
- stock-specific discussion
- macroeconomic explanation
- founder/CEO interviews
- analyst opinions
```

For YouTube, collect:

```
{
  "source_type": "youtube",
  "video_id": "",
  "url": "",
  "title": "",
  "channel_name": "",
  "published_at": "",
  "description": "",
  "transcript": [
    {
      "start_time": "00:01:10",
      "text": "The speaker discusses Nvidia earnings..."
    }
  ],
  "language": "en",
  "is_auto_generated": true,
  "source_reliability": "medium"
}
```

The official YouTube Data API has a `captions.list` method to list caption tracks for a video, but the list response does not contain the actual captions; YouTube’s `captions.download` method is used to retrieve a caption track. The captions API also identifies caption metadata like language, status, and whether the track is ASR, meaning automatic speech recognition. Google for Developers+1

For practical implementation, you have two options:

### Option 1: Official YouTube API

Use this when:

```
- you own the video
- you have authorization
- you are working with allowed YouTube API access
```

Flow:

```
YouTube URL
   ↓
Extract video_id
   ↓
YouTube Data API videos.list → title, channel, publish date, description
   ↓
captions.list → available caption tracks
   ↓
captions.download → transcript
```

### Option 2: Public transcript collector

For a prototype, many developers use Python libraries such as `youtube-transcript-api` to fetch available public transcripts. But for production, you should check platform terms and avoid relying only on unofficial behavior.

Example prototype code:

```
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url)

    if parsed.hostname in ["www.youtube.com", "youtube.com"]:
        return parse_qs(parsed.query)["v"][0]

    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")

    raise ValueError("Invalid YouTube URL")

def get_youtube_transcript(url: str):
    video_id = extract_youtube_video_id(url)

    transcript = YouTubeTranscriptApi.get_transcript(
        video_id,
        languages=["en"]
    )

    return {
        "video_id": video_id,
        "source_type": "youtube",
        "segments": transcript
    }
```

Your cleaning layer should then convert transcript segments like this:

```
{
  "start": 35.2,
  "duration": 4.8,
  "text": "Tesla dropped after the earnings report because margins came under pressure."
}
```

Into this:

```
{
  "timestamp": "00:00:35",
  "clean_text": "Tesla dropped after earnings because margins came under pressure.",
  "entities": ["Tesla"],
  "possible_tickers": ["TSLA"],
  "event_type": "earnings / margin pressure"
}
```

---

## B. Financial news websites

Use these for:

```
- stock-specific news
- earnings reactions
- analyst upgrades/downgrades
- regulatory events
- management changes
- M&A
- lawsuits
- product launches
```

Preferred collection order:

```
1. Official API, if available
2. RSS feed
3. Licensed news/data provider
4. Web scraping only when allowed
```

Do not make scraping your first choice. Many financial websites have paywalls, terms of service, bot protection, and copyright restrictions.

For websites, collect:

```
{
  "source_type": "web_article",
  "url": "",
  "publisher": "",
  "title": "",
  "author": "",
  "published_at": "",
  "retrieved_at": "",
  "article_text": "",
  "tickers_mentioned": [],
  "source_reliability": "high/medium/low"
}
```

For RSS feeds, the RSS 2.0 structure uses a top-level `<rss>` element and a `<channel>` containing channel metadata and items such as title, link, and description, which makes it useful for collecting new article metadata in a clean way. rssboard.org

Example RSS collector:

```
import feedparser
from datetime import datetime, timezone

def collect_rss_feed(feed_url: str):
    feed = feedparser.parse(feed_url)

    articles = []

    for entry in feed.entries:
        articles.append({
            "source_type": "rss_article",
            "feed_url": feed_url,
            "title": entry.get("title"),
            "url": entry.get("link"),
            "published_at": entry.get("published"),
            "summary": entry.get("summary"),
            "retrieved_at": datetime.now(timezone.utc).isoformat()
        })

    return articles
```

For normal websites:

```
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

def collect_static_article(url: str):
    headers = {
        "User-Agent": "InvestmentResearchBot/1.0 contact@example.com"
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else None

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.find_all("p")
    ]

    article_text = "\n".join(paragraphs)

    return {
        "source_type": "web_article",
        "url": url,
        "title": title,
        "article_text": article_text,
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    }
```

For JavaScript-heavy sites, use Playwright:

```
from playwright.sync_api import sync_playwright

def collect_js_article(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        text = page.locator("body").inner_text()
        title = page.title()
        browser.close()

    return {
        "source_type": "web_article_js",
        "url": url,
        "title": title,
        "article_text": text
    }
```

But again: use this only where scraping is allowed.

---

## C. News API providers

For production, this is better than scraping.

Examples:

```
- Alpha Vantage News & Sentiment
- Finnhub company news
- Polygon.io news
- Benzinga
- Financial Modeling Prep
- Nasdaq Data Link
- NewsAPI
- GDELT
```

Alpha Vantage has a `NEWS_SENTIMENT` function that returns live and historical market news and sentiment across stocks, crypto, forex, and topics such as earnings, IPOs, M&A, financial markets, monetary policy, fiscal policy, and macro economy. Alpha Vantage

Example Alpha Vantage request:

```
import requests

def collect_alpha_vantage_news(ticker: str, api_key: str):
    url = "https://www.alphavantage.co/query"

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "apikey": api_key
    }

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()

    return response.json()
```

This kind of data is very useful because it already gives you:

```
- article title
- URL
- publication time
- ticker relevance
- sentiment score
- topics
```

---

## D. Market price data

This is mandatory. Without price data, the agent cannot say whether something is down, up, oversold, overextended, or reacting to news.

Collect:

```
- current price
- previous close
- 1-day return
- 5-day return
- 1-month return
- 3-month return
- YTD return
- 52-week high/low
- volume
- average volume
- volatility
- moving averages: 20-day, 50-day, 200-day
- sector/index comparison
```

Possible providers:

```
- Alpha Vantage
- Finnhub
- Polygon.io
- IEX Cloud
- Nasdaq Data Link
- Tiingo
- Twelve Data
- Yahoo Finance / yfinance for prototype only
```

Nasdaq Data Link provides APIs, Python SDKs, Excel tools, and other access methods for financial and market data, including real-time or delayed data and table APIs. Nasdaq Data Link Documentation

Example prototype using `yfinance`:

```
import yfinance as yf

def get_market_snapshot(ticker: str):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1y")

    latest_price = hist["Close"].iloc[-1]
    high_52w = hist["High"].max()
    low_52w = hist["Low"].min()

    return {
        "ticker": ticker,
        "latest_price": float(latest_price),
        "52_week_high": float(high_52w),
        "52_week_low": float(low_52w),
        "return_5d": float(hist["Close"].pct_change(5).iloc[-1]),
        "return_1m": float(hist["Close"].pct_change(21).iloc[-1]),
        "return_3m": float(hist["Close"].pct_change(63).iloc[-1]),
        "volume_latest": int(hist["Volume"].iloc[-1]),
        "volume_avg_30d": int(hist["Volume"].tail(30).mean())
    }
```

For production, use a licensed API instead of depending only on `yfinance`.

---

## E. SEC filings

This is one of the most important sources for U.S.-listed companies.

Use SEC filings for:

```
- 10-K annual reports
- 10-Q quarterly reports
- 8-K material events
- S-1 IPO filings
- 13F institutional holdings
- insider transaction forms
- company facts from XBRL
```

SEC provides `data.sec.gov` REST APIs for submissions and XBRL company facts. These APIs deliver JSON data and do not require authentication or API keys. SEC says the JSON structures are updated throughout the day in real time as submissions are disseminated. SEC

Important SEC endpoints:

```
Company submissions:
https://data.sec.gov/submissions/CIK##########.json

Company facts:
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
```

SEC also asks automated clients to declare a proper User-Agent, and SEC’s fair-access guidance states a current maximum request rate of 10 requests per second. SEC

Example SEC collector:

```
import requests

SEC_HEADERS = {
    "User-Agent": "YourCompanyName your-email@example.com",
    "Accept-Encoding": "gzip, deflate"
}

def get_sec_submissions(cik: str):
    cik_padded = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

    response = requests.get(url, headers=SEC_HEADERS, timeout=20)
    response.raise_for_status()

    return response.json()

def get_sec_company_facts(cik: str):
    cik_padded = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"

    response = requests.get(url, headers=SEC_HEADERS, timeout=20)
    response.raise_for_status()

    return response.json()
```

From SEC filings, extract:

```
- latest revenue
- net income
- operating margin
- debt
- cash
- free cash flow
- risk factors
- management discussion
- guidance-related language
- new 8-K events
```

This helps your agent avoid bad conclusions like:

```
“Stock dropped today, so buy.”
```

Instead, it can say:

```
“Stock dropped after an earnings miss. However, filings show revenue growth is slowing, margin pressure is recurring, and debt is increasing. This looks structural, not a temporary dip.”
```

---

## F. Earnings calls and investor relations pages

Use these for:

```
- management guidance
- future outlook
- revenue drivers
- margin pressure
- demand commentary
- segment-level performance
```

Collect from:

```
- company investor relations website
- earnings call transcript provider
- SEC 8-K earnings release
- quarterly shareholder letter
- company press releases
```

Context to store:

```
{
  "source_type": "earnings_call",
  "company": "",
  "ticker": "",
  "quarter": "Q1 2026",
  "speaker": "CEO/CFO/Analyst",
  "text": "",
  "guidance_tone": "positive/negative/mixed",
  "important_claims": []
}
```

This is very useful because news articles often summarize earnings, but the actual call gives the real management tone.

---

## G. Newsletters

Newsletters can be useful, but they are often opinion-heavy.

Collect using:

```
- Gmail API
- IMAP
- manual upload
- webhook from email forwarding
- newsletter provider API, if available
```

For newsletters, store:

```
{
  "source_type": "newsletter",
  "sender": "",
  "subject": "",
  "received_at": "",
  "body_text": "",
  "links": [],
  "mentioned_tickers": [],
  "source_reliability": "medium/low"
}
```

Clean out:

```
- unsubscribe text
- promotions
- referral links
- repeated disclaimers
- ads
- sponsor sections
```

Newsletter content should be treated as **idea generation**, not final evidence. If a newsletter says “XYZ is a great buy,” your system should verify that using price, filings, financials, and other news sources.

---

# 3. What context exactly should your system collect?

For each company/ticker, your context package should contain this:

```
{
  "ticker": "NVDA",
  "company": "Nvidia",
  "as_of": "2026-05-02T00:00:00Z",
  "narrative_context": {
    "youtube_mentions": [],
    "news_articles": [],
    "newsletters": [],
    "blogs": []
  },
  "event_context": {
    "latest_events": [
      {
        "event_type": "earnings beat",
        "event_date": "",
        "summary": "",
        "impact": "positive",
        "severity": "high",
        "source_urls": []
      }
    ]
  },
  "market_context": {
    "current_price": "",
    "one_day_change": "",
    "five_day_change": "",
    "one_month_change": "",
    "three_month_change": "",
    "volume_vs_average": "",
    "distance_from_52_week_high": "",
    "distance_from_52_week_low": "",
    "sector_performance": "",
    "index_performance": ""
  },
  "fundamental_context": {
    "revenue_growth": "",
    "eps_growth": "",
    "gross_margin": "",
    "operating_margin": "",
    "free_cash_flow": "",
    "cash": "",
    "debt": "",
    "valuation": {
      "pe_ratio": "",
      "ps_ratio": "",
      "ev_ebitda": ""
    }
  },
  "filing_context": {
    "latest_10k": "",
    "latest_10q": "",
    "latest_8k": "",
    "risk_factors": [],
    "management_discussion": []
  },
  "sentiment_context": {
    "news_sentiment": "",
    "analyst_tone": "",
    "social_sentiment": ""
  },
  "data_quality": {
    "source_count": "",
    "high_reliability_source_count": "",
    "conflicting_sources": [],
    "missing_data": []
  }
}
```

This is the ideal context that your LLM should receive.

---

# 4. Recommended source priority

For investment decisions, use this reliability order:

```
Tier 1 — Highest reliability
- SEC filings
- company earnings releases
- investor relations materials
- official exchange/market data
- official macroeconomic data

Tier 2 — Good reliability
- established financial news
- trusted market data APIs
- analyst reports
- earnings call transcripts

Tier 3 — Useful but opinion-heavy
- YouTube videos
- newsletters
- blogs
- podcasts

Tier 4 — Noisy / optional
- Reddit
- Twitter/X
- Stocktwits
- social sentiment
```

Your agent should never make a strong investment conclusion based only on Tier 3 or Tier 4 sources.

---

# 5. Context collection workflow for your system

Use this exact sequence:

```
Step 1: User provides source or topic
Example:
- YouTube URL
- “latest AI stock news”
- “analyze Tesla after earnings”
- newsletter text

Step 2: Collect raw documents
- transcript
- article text
- newsletter body
- market news
- SEC filings
- price data

Step 3: Normalize every source into one format
- source_type
- title
- URL
- published date
- retrieved date
- raw text
- clean text
- source reliability

Step 4: Extract entities
- company names
- tickers
- sectors
- indexes
- macro terms

Step 5: Enrich with structured financial data
- price movement
- volume
- valuation
- financials
- SEC filings
- earnings data

Step 6: Build final LLM context packet
- only relevant chunks
- latest data
- event classification
- conflicting evidence
- source links

Step 7: Send to investment research agent
```

---

# 6. Normalized document schema

Every source should become this format:

```
{
  "document_id": "hash_url_or_uuid",
  "source_type": "youtube_transcript | web_article | newsletter | sec_filing | market_api | earnings_call",
  "source_name": "CNBC / YouTube / SEC / Alpha Vantage",
  "url": "",
  "title": "",
  "author": "",
  "published_at": "",
  "retrieved_at": "",
  "language": "en",
  "raw_text": "",
  "clean_text": "",
  "chunks": [
    {
      "chunk_id": "",
      "text": "",
      "start_time": "",
      "end_time": "",
      "entities": [],
      "tickers": [],
      "event_types": []
    }
  ],
  "source_reliability": "high | medium | low",
  "rights_or_access_note": "",
  "checksum": ""
}
```

This makes the rest of your pipeline clean.

---

# 7. Storage design

For your project, use 3 storage layers:

```
Raw Zone
- Store original transcript/article/newsletter/filing
- S3, GCS, Azure Blob, or local object storage

Structured Zone
- Store metadata, tickers, events, prices, fundamentals
- PostgreSQL, Snowflake, BigQuery, Redshift

Vector Zone
- Store chunks for semantic retrieval
- Pinecone, Weaviate, Milvus, Chroma, pgvector
```

Simple database tables:

```
CREATE TABLE source_documents (
    document_id TEXT PRIMARY KEY,
    source_type TEXT,
    source_name TEXT,
    url TEXT,
    title TEXT,
    published_at TIMESTAMP,
    retrieved_at TIMESTAMP,
    clean_text TEXT,
    source_reliability TEXT
);

CREATE TABLE document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT,
    chunk_text TEXT,
    chunk_index INT,
    start_time TEXT,
    end_time TEXT
);

CREATE TABLE extracted_entities (
    entity_id TEXT PRIMARY KEY,
    document_id TEXT,
    chunk_id TEXT,
    entity_name TEXT,
    ticker TEXT,
    entity_type TEXT,
    confidence FLOAT
);

CREATE TABLE market_snapshots (
    ticker TEXT,
    snapshot_time TIMESTAMP,
    price NUMERIC,
    change_1d NUMERIC,
    change_5d NUMERIC,
    change_1m NUMERIC,
    volume NUMERIC,
    avg_volume_30d NUMERIC,
    high_52w NUMERIC,
    low_52w NUMERIC
);

CREATE TABLE investment_events (
    event_id TEXT PRIMARY KEY,
    ticker TEXT,
    event_type TEXT,
    event_date TIMESTAMP,
    impact TEXT,
    severity TEXT,
    summary TEXT,
    source_document_id TEXT
);
```

---

# 8. Context builder before sending to LLM

This part is very important.

The LLM should receive a compact package like this, not 50 pages of raw data:

```
{
  "task": "Identify investment opportunities from collected context",
  "user_profile": {
    "risk_tolerance": "medium",
    "time_horizon": "1-3 years",
    "market": "US equities"
  },
  "market_overview": {
    "sp500_trend": "",
    "nasdaq_trend": "",
    "vix_level": "",
    "sector_strength": ""
  },
  "candidate_stocks": [
    {
      "ticker": "TSLA",
      "company": "Tesla",
      "latest_price_context": {
        "change_1d": "-4.2%",
        "change_5d": "-8.1%",
        "volume_vs_average": "2.3x"
      },
      "news_context": [
        {
          "source": "news_article",
          "published_at": "",
          "summary": "Stock dropped after margin concerns.",
          "reliability": "high"
        }
      ],
      "youtube_context": [
        {
          "source": "youtube",
          "timestamp": "00:04:20",
          "summary": "Speaker says demand concerns may be temporary.",
          "reliability": "medium"
        }
      ],
      "filing_context": {
        "latest_10q_summary": "",
        "risk_factors": []
      },
      "fundamental_context": {
        "revenue_growth": "",
        "margin_trend": "",
        "debt_level": ""
      },
      "data_gaps": []
    }
  ]
}
```

Then the research agent decides:

```
- temporary dip or structural issue?
- buy candidate or avoid?
- high confidence or low confidence?
```

---

# 9. Minimum viable version

For your first working version, collect only these:

```
1. YouTube transcript
2. 3-5 latest news articles for extracted tickers
3. latest stock price and 1M/3M trend
4. latest SEC 10-Q / 10-K summary
5. basic fundamentals
```

Do not start with 20 sources. Start with this:

```
Input:
YouTube URL or article URL

Collector:
- Get transcript/article text
- Extract tickers
- Pull market data
- Pull recent news
- Pull SEC/company facts

LLM:
- classify event
- decide temporary vs structural
- produce investment research output
```

---

# 10. Best practical source list

Use this source setup:

```
YouTube:
- YouTube Data API for metadata/captions where authorized
- transcript collector for available public transcripts
- speech-to-text fallback only for content you are allowed to process

Websites:
- RSS feeds first
- official APIs second
- scraping only if allowed

News:
- Alpha Vantage News Sentiment
- Finnhub company news
- Polygon/Benzinga/FMP if budget allows

Market data:
- Alpha Vantage / Polygon / Finnhub / Nasdaq Data Link
- yfinance only for prototype

Filings:
- SEC data.sec.gov
- company 10-K, 10-Q, 8-K
- company facts XBRL

Earnings:
- company investor relations pages
- earnings releases
- earnings call transcripts

Macro:
- FRED
- Treasury rates
- CPI/unemployment/Fed data
- oil/DXY/interest-rate context

Optional:
- Reddit/X/Stocktwits only for sentiment, never final decision
```

---

# 11. The collector agent prompt

Use this prompt for your **context collection planner agent**:

```
You are a financial context collection planner.

Given a user query, URL, ticker, YouTube video, article, or newsletter, decide what context must be collected before an investment analysis can be performed.

Your job is not to make investment recommendations. Your job is to produce a collection plan.

For each request, identify:
1. Primary source type: YouTube, article, newsletter, ticker, market topic, or mixed.
2. Companies/tickers that must be extracted or verified.
3. Required source collectors:
   - transcript collector
   - web article collector
   - RSS/news collector
   - market data collector
   - SEC filing collector
   - earnings/fundamentals collector
   - macro data collector
4. Required fields from each source.
5. Source reliability level.
6. Collection priority: mandatory, useful, optional.
7. Data gaps that must be resolved before investment analysis.

Rules:
- Always collect market price context for any identified ticker.
- Always collect recent news for any identified ticker.
- Always collect SEC/company financial context for U.S.-listed stocks when possible.
- Do not rely only on YouTube or newsletters.
- Do not use social sentiment as final evidence.
- If ticker mapping is uncertain, mark it for verification.
- If a source is opinion-based, mark reliability as medium or low.
```

---

# 12. Best final architecture for your project

```
Collectors
├── YouTubeTranscriptCollector
├── WebArticleCollector
├── RSSCollector
├── NewsletterCollector
├── NewsAPICollector
├── MarketDataCollector
├── SECFilingCollector
├── EarningsCollector
└── MacroDataCollector

Processing
├── Cleaner
├── Deduplicator
├── Chunker
├── EntityExtractor
├── TickerResolver
├── EventClassifier
├── ReliabilityScorer
└── ContextBuilder

Storage
├── Raw object store
├── PostgreSQL/Snowflake/BigQuery
└── Vector DB

Agents
├── Collection Planner Agent
├── Source Cleaning Agent
├── Entity Extraction Agent
├── Market Data Agent
├── Fundamental Analysis Agent
├── Event Classification Agent
└── Investment Research Agent
```

For your project, this is the correct mindset:

```
YouTube/newsletters/articles create investment ideas.
Market data confirms price action.
SEC filings and financials verify business quality.
News APIs verify whether the event is real and recent.
The LLM combines all evidence and gives a research signal.
```

That is how you avoid building a basic summarizer and instead build a real **investment research context engine**.