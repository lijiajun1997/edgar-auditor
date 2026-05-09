"""SEC EDGAR HTTP client with rate limiting and retry logic."""

import logging
import time

import requests

from edgar_lib.config import MAX_RETRIES, RATE_LIMIT_DELAY, REQUEST_TIMEOUT, SEC_DATA_URL, SEC_USER_AGENT

logger = logging.getLogger(__name__)

_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/json",
        })
    return _session


def _request(url: str, params: dict | None = None) -> requests.Response:
    s = get_session()
    for attempt in range(MAX_RETRIES):
        try:
            r = s.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            time.sleep(RATE_LIMIT_DELAY)
            return r
        except requests.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Retry %d/%d: %s, waiting %ds", attempt + 1, MAX_RETRIES, e, wait)
            time.sleep(wait)


def fetch_all_tickers() -> dict[str, dict[str, str]]:
    r = _request("https://www.sec.gov/files/company_tickers.json")
    raw = r.json()
    mapping: dict[str, dict[str, str]] = {}
    for v in raw.values():
        cik = str(v["cik_str"]).zfill(10)
        ticker = v["ticker"].upper()
        mapping[ticker] = {
            "cik": cik,
            "name": v.get("title", ""),
        }
    return mapping


def fetch_company_filings(cik: str) -> dict:
    url = f"{SEC_DATA_URL}/submissions/CIK{cik}.json"
    r = _request(url)
    data = r.json()
    recent = data.get("filings", {}).get("recent", {})
    return {
        "company_name": data.get("name", ""),
        "sic": data.get("sic", ""),
        "filings": recent,
    }


def fetch_filing_directory(cik: str, accession: str) -> dict:
    acc_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/index.json"
    r = _request(url)
    return r.json()


def download_file(url: str, save_path: str) -> int:
    s = get_session()
    s.headers["Accept"] = "*/*"
    for attempt in range(MAX_RETRIES):
        try:
            r = s.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(r.content)
            time.sleep(RATE_LIMIT_DELAY)
            return len(r.content)
        except (requests.RequestException, OSError):
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
