import logging

from edgar_lib.db import load_tickers
from edgar_lib.sec_client import fetch_all_tickers

logger = logging.getLogger(__name__)


def lookup_cik(ticker: str, tickers_db: dict | None = None) -> tuple[str | None, str | None]:
    if tickers_db is None:
        tickers_db = load_tickers()
    t: str = ticker.upper().strip()
    info: dict | None = tickers_db.get(t)
    if info:
        return info["cik"], info["name"]
    return None, None
