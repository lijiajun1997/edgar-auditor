"""JSON file-based database operations for filings index and ticker data."""

import json
import os

from edgar_lib.config import DB_FILINGS_INDEX, DB_TARGETS, DB_TICKERS, FILINGS_DIR


def load_json(path) -> dict:
    path = str(path)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data: dict) -> None:
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_tickers() -> dict:
    return load_json(DB_TICKERS)


def save_tickers(data: dict) -> None:
    save_json(DB_TICKERS, data)


def load_filings_index() -> dict:
    return load_json(DB_FILINGS_INDEX)


def save_filings_index(data: dict) -> None:
    save_json(DB_FILINGS_INDEX, data)


def get_filing_dir(ticker: str, form: str, accession: str) -> str:
    acc_nodash = accession.replace("-", "")
    fdir = os.path.join(str(FILINGS_DIR), ticker, form, acc_nodash)
    os.makedirs(fdir, exist_ok=True)
    return fdir
