import os
from pathlib import Path

# --- Paths ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", ".."))

# Data dir: use skill's data/ by default, or env override
DATA_DIR: Path = Path(os.getenv("EDGAR_DATA_DIR", os.path.join(_SKILL_DIR, "data")))
FILINGS_DIR: Path = DATA_DIR / "filings"

DB_TICKERS: Path = DATA_DIR / "tickers.json"
DB_TARGETS: Path = DATA_DIR / "targets.json"
DB_FILINGS_INDEX: Path = DATA_DIR / "filings_index.json"

FPAGES_DIR: Path = DATA_DIR / "fpages"

# --- SEC API ---
SEC_USER_AGENT: str = os.getenv("EDGAR_USER_AGENT", "edgar-auditor contact@example.com")
SEC_BASE_URL: str = "https://www.sec.gov"
SEC_DATA_URL: str = "https://data.sec.gov"
TICKER_JSON_URL: str = f"{SEC_BASE_URL}/files/company_tickers.json"

# --- Network ---
RATE_LIMIT_DELAY: float = float(os.getenv("EDGAR_RATE_LIMIT", "0.11"))
MAX_RETRIES: int = int(os.getenv("EDGAR_MAX_RETRIES", "3"))
REQUEST_TIMEOUT: int = int(os.getenv("EDGAR_REQUEST_TIMEOUT", "30"))

# --- Content thresholds ---
MIN_SECTION_LENGTH: int = 20
MAX_SECTION_LENGTH: int = 100_000
MAX_SECTION_ELEMENTS: int = 5_000
MAX_COVER_LINES: int = 200
MIN_COVER_LENGTH: int = 50
MIN_TOC_HTML_OFFSET: int = 5_000

# --- Search ---
KEYWORD_CONTEXT_CHARS: int = 300
MAX_CONTEXT_SNIPPETS: int = 3
MAX_SEARCH_RESULTS: int = 20
