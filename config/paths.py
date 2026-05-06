from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).parent.parent

DB_DIR = PROJECT_ROOT / "db"

# ── Output Directories ────────────────────────────────────────────────────────
_TODAY     = date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = PROJECT_ROOT / "output" / _TODAY

# ── Phase A: Broad Market Discovery ───────────────────────────────────────────
PHASE_A_DIR = OUTPUT_DIR / "phaseA"

RSS_OUTPUT_DIR         = PHASE_A_DIR / "rss"
MONEYCONTROL_OUTPUT_DIR = PHASE_A_DIR / "moneycontrol"
ET_OUTPUT_DIR          = PHASE_A_DIR / "economic_times"
NEWSDATA_OUTPUT_DIR    = PHASE_A_DIR / "newsdata_io"
MEDIASTACK_OUTPUT_DIR  = PHASE_A_DIR / "mediastack"
GMAIL_OUTPUT_DIR       = PHASE_A_DIR / "gmail"
YOUTUBE_OUTPUT_DIR     = PHASE_A_DIR / "youtube"
FII_DII_OUTPUT_DIR     = PHASE_A_DIR / "fii_dii"
BULK_DEALS_OUTPUT_DIR  = PHASE_A_DIR / "bulk_deals"
MACRO_OUTPUT_DIR       = PHASE_A_DIR / "macro_data"
FNO_OUTPUT_DIR         = PHASE_A_DIR / "fno_data"   # index-level (NIFTY, BANKNIFTY)
BROWSER_SCRAPER_OUTPUT_DIR = PHASE_A_DIR / "browser_scraped"
GENERIC_WEB_OUTPUT_DIR     = PHASE_A_DIR / "generic_web"

# ── Phase B: Candidate Selection ──────────────────────────────────────────────
PHASE_B_DIR              = OUTPUT_DIR / "phaseB"
MARKET_REGIME_OUTPUT_DIR = PHASE_B_DIR / "market_regime"
SIGNALS_OUTPUT_DIR       = PHASE_B_DIR / "signals"
CANDIDATES_OUTPUT_DIR    = PHASE_B_DIR / "candidates"

# ── LLM call logs (B2 signal extraction prompts + responses) ─────────────────
LLM_LOGS_DIR = PHASE_B_DIR / "llm_signal_logs"

# ── Phase C: Company Deep Dive ────────────────────────────────────────────────
PHASE_C_DIR                  = OUTPUT_DIR / "phaseC"
MARKET_DATA_OUTPUT_DIR       = PHASE_C_DIR / "market_data"
SCREENER_IN_OUTPUT_DIR       = PHASE_C_DIR / "screener_in"
PEER_COMPARISON_OUTPUT_DIR   = PHASE_C_DIR / "peer_comparison"
ANALYST_ESTIMATES_OUTPUT_DIR = PHASE_C_DIR / "analyst_estimates"
EXCHANGE_FILINGS_OUTPUT_DIR  = PHASE_C_DIR / "exchange_filings"
CORPORATE_ACTIONS_OUTPUT_DIR = PHASE_C_DIR / "corporate_actions"
SEC_OUTPUT_DIR               = PHASE_C_DIR / "sec_filings"
FNO_TICKER_OUTPUT_DIR        = PHASE_C_DIR / "fno_data"   # per-ticker F&O
