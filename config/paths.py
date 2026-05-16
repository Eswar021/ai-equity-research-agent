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

# ── Phase D: Research Target Planner (proxy mapping themes → listed) ─────────
PHASE_D_DIR                  = OUTPUT_DIR / "phaseD"
PROXY_MAPPINGS_DIR           = PHASE_D_DIR / "proxy_mappings"
PROXY_LLM_LOGS_DIR           = PHASE_D_DIR / "llm_proxy_logs"

# ── Phase E: Evidence Builder ────────────────────────────────────────────────
PHASE_E_DIR                  = OUTPUT_DIR / "phaseE"
EVIDENCE_CARDS_DIR           = PHASE_E_DIR / "evidence_cards"

# ── Phase F: Analysis Agents ─────────────────────────────────────────────────
PHASE_F_DIR                  = OUTPUT_DIR / "phaseF"
ANALYST_OUTPUT_DIR           = PHASE_F_DIR / "analyst_views"
ANALYST_LLM_LOGS_DIR         = PHASE_F_DIR / "llm_analyst_logs"

# ── Phase G: Final Report ────────────────────────────────────────────────────
PHASE_G_DIR                  = OUTPUT_DIR / "phaseG"

# ── Layer 1 contract output (produced by layer1_bundler after Phase A) ───────
LAYER1_DIR = OUTPUT_DIR / "layer1"

# ── Layer 2 contract output (produced by layer2_runner) ──────────────────────
LAYER2_DIR = OUTPUT_DIR / "layer2"

# ── Layer 3 contract output (produced by layer3_runner) ──────────────────────
LAYER3_DIR              = OUTPUT_DIR / "layer3"
LAYER3_LLM_LOGS_DIR     = LAYER3_DIR / "llm_extraction_logs"
LAYER3_PROMPT_LOGS_DIR  = LAYER3_DIR / "prompt_logs"

# ── Layer 4 contract output (produced by layer4_runner) ──────────────────────
LAYER4_DIR                   = OUTPUT_DIR / "layer4"

# ── Layer 5 contract output (produced by layer5_runner) ──────────────────────
LAYER5_DIR                   = OUTPUT_DIR / "layer5"

# ── Layer 6 contract output (produced by layer6_runner) ──────────────────────
LAYER6_DIR                   = OUTPUT_DIR / "layer6"

# ── Layer 7 contract output (produced by layer7_bundler after Phase C) ───────
LAYER7_DIR = OUTPUT_DIR / "layer7"

# ── Layer 8 contract output (produced by layer8_runner) ──────────────────────
LAYER8_DIR = OUTPUT_DIR / "layer8"

# ── Layer 9 contract output (produced by layer9_runner) ──────────────────────
LAYER9_DIR = OUTPUT_DIR / "layer9"

# ── Layer 10 contract output (produced by layer10_runner) ────────────────────
LAYER10_DIR = OUTPUT_DIR / "layer10"

# ── Persistent memory store (cross-run, in db/) ───────────────────────────────
DB_MEMORY_DIR                    = DB_DIR / "memory"
DB_WORKING_MEMORY_DIR            = DB_MEMORY_DIR / "working_memory"
DB_SHORT_TERM_MEMORY_FILE        = DB_MEMORY_DIR / "short_term_market_memory.jsonl"
DB_WATCH_MEMORY_FILE             = DB_MEMORY_DIR / "watch_memory.jsonl"
DB_LONG_TERM_MEMORY_FILE         = DB_MEMORY_DIR / "long_term_investment_memory.jsonl"
DB_THESIS_MEMORY_FILE            = DB_MEMORY_DIR / "thesis_memory.jsonl"
DB_PORTFOLIO_MEMORY_FILE         = DB_MEMORY_DIR / "portfolio_memory.jsonl"
DB_ENTITY_MEMORY_INDEX_FILE      = DB_MEMORY_DIR / "entity_memory_index.json"
DB_THEME_MEMORY_INDEX_FILE       = DB_MEMORY_DIR / "theme_memory_index.json"
DB_MEMORY_AUDIT_INDEX_FILE       = DB_MEMORY_DIR / "memory_audit_index.jsonl"
# ── User portfolio (optional) ────────────────────────────────────────────────
PORTFOLIO_FILE               = PROJECT_ROOT / "config" / "portfolio.json"
