#!/usr/bin/env python3
"""
EDGAR Auditor - SEC Filing Query Tool for Auditors.

Usage: python edgar.py <command> [options]

Commands:
  init                              Download ticker data
  lookup <ticker_or_name>           Find company
  filings <ticker> [options]        List filings with filtering
  download <ticker> <accession>     Download filing (HTM + MD + index)
  toc <ticker> <form> <accession>   Get table of contents
  section <t> <f> <acc> <sec_id>    Read section content
  search <ticker> <keyword>         Keyword search
  concept [key] [options]           Concept search / list
  fpages <ticker> <form> <accession> Extract financial statements (f-pages)
"""

import argparse
import io
import json
import os
import sys
import warnings

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

# ── Path setup: add scripts/ to sys.path so edgar_lib is importable ────────

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# ── Imports (all from bundled edgar_lib) ────────────────────────────────────

from edgar_lib.db import (
    load_tickers, save_tickers, load_filings_index, save_filings_index,
    get_filing_dir,
)
from edgar_lib.sec_client import (
    fetch_all_tickers, fetch_company_filings, fetch_filing_directory, download_file,
)
from edgar_lib.html_to_md import convert_html_to_md
from edgar_lib.ticker_sync import lookup_cik
from edgar_lib.concept_map import CONCEPTS, get_all_concepts


# ── Output helpers ──────────────────────────────────────────────────────────

def _out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))

def _err(msg):
    _out({"error": str(msg)})


# ── Ticker management ───────────────────────────────────────────────────────

_BUNDLED_TICKERS = os.path.join(_SCRIPT_DIR, "..", "data", "tickers.json")


def _ensure_tickers():
    """Download ticker data if cache is missing or too small.

    If project has no tickers.json, seed from bundled copy first.
    """
    tickers = load_tickers()
    if len(tickers) < 100:
        if os.path.isfile(_BUNDLED_TICKERS):
            with open(_BUNDLED_TICKERS, encoding="utf-8") as f:
                bundled = json.load(f)
            if len(bundled) >= 100:
                save_tickers(bundled)
                tickers = bundled
                print(f"Seeded {len(tickers)} tickers from bundled cache.", file=sys.stderr)
                return tickers
        print("Downloading SEC ticker data...", file=sys.stderr)
        tickers = fetch_all_tickers()
        save_tickers(tickers)
        print(f"Cached {len(tickers)} tickers.", file=sys.stderr)
    return tickers


def _resolve_cik(ticker):
    """Resolve ticker to (CIK, name). Refreshes on miss."""
    ticker = ticker.upper().strip()
    tickers = load_tickers()
    cik, name = lookup_cik(ticker, tickers)
    if cik:
        return cik, name
    tickers = fetch_all_tickers()
    save_tickers(tickers)
    return lookup_cik(ticker, tickers)


# ── SEC metadata lookup ────────────────────────────────────────────────────

def _find_filing_meta(ticker, accession):
    """Look up a specific filing's metadata from the SEC submissions API."""
    cik, name = _resolve_cik(ticker)
    if not cik:
        return None
    data = fetch_company_filings(cik)
    filings = data.get("filings", {})
    for i, acc in enumerate(filings.get("accessionNumber", [])):
        if acc == accession:
            return {
                "cik": cik,
                "name": data.get("company_name", name or ""),
                "form": filings["form"][i],
                "primary_doc": filings["primaryDocument"][i],
                "filed_date": filings["filingDate"][i],
            }
    return None


# ── Section index builder ───────────────────────────────────────────────────

def _build_index(ticker, form, accession, primary_doc):
    """Build section index for a single filing. Returns TOC summary or None."""
    from edgar_lib.section_indexer import (
        index_xbrl_filing, index_html_filing,
        _get_sections_file, SECTIONS_INDEX_DIR,
    )

    fdir = get_filing_dir(ticker, form, accession)
    sections_file = _get_sections_file(ticker, form, accession)

    if not os.path.exists(sections_file):
        sections = index_xbrl_filing(fdir)
        is_xbrl = sections is not None

        if not is_xbrl:
            sections = index_html_filing(fdir, primary_doc or "")

        if sections is not None:
            if is_xbrl and primary_doc:
                html_sections = index_html_filing(fdir, primary_doc)
                if html_sections:
                    for s in html_sections:
                        s["id"] = f"htm_{s['id']}"
                        s["source"] = "html_main"
                    sections.extend(html_sections)

            os.makedirs(SECTIONS_INDEX_DIR, exist_ok=True)
            result = {
                "key": f"{ticker}_{form}_{accession.replace('-', '')}",
                "ticker": ticker, "form": form,
                "accession": accession,
                "filed_date": "",
                "sections": sections,
                "section_count": len(sections),
            }
            with open(sections_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

    from edgar_lib.section_search import get_toc
    toc = get_toc(ticker, form, accession)
    if toc:
        return {
            "total_sections": toc["total_sections"],
            "sections": [
                {"id": s["section_id"], "title": s["title"], "category": s["category"]}
                for s in toc["toc"][:50]
            ],
        }
    return None


# ── File downloader ─────────────────────────────────────────────────────────

_SKIP = ("index-headers", "-index.", "filings.xml", "rss.xml")


def _download_filing_files(cik, ticker, form, accession):
    """Download all filing files (HTM, MD, XML). Returns (downloaded_list, filing_dir)."""
    fdir = get_filing_dir(ticker, form, accession)
    acc_nd = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nd}"

    dir_files = []
    try:
        listing = fetch_filing_directory(cik, accession)
        dir_files = listing.get("directory", {}).get("item", [])
    except Exception:
        pass

    downloaded = []

    for fi in dir_files:
        fname = fi["name"]
        if any(p in fname.lower() for p in _SKIP):
            continue

        if fname.endswith((".htm", ".html")):
            html_path = os.path.join(fdir, fname)
            md_path = os.path.join(fdir, fname.rsplit(".", 1)[0] + ".md")

            if not os.path.exists(html_path):
                try:
                    download_file(f"{base}/{fname}", html_path)
                    downloaded.append({"file": fname, "type": "html"})
                except Exception as e:
                    downloaded.append({"file": fname, "type": "html", "error": str(e)[:100]})
                    continue

            if os.path.exists(html_path) and not os.path.exists(md_path):
                with open(html_path, encoding="utf-8", errors="replace") as fh:
                    html = fh.read()
                with open(md_path, "w", encoding="utf-8") as fh:
                    fh.write(convert_html_to_md(html))
                downloaded.append({"file": fname.rsplit(".", 1)[0] + ".md", "type": "md"})

        elif fname.endswith(".xml"):
            xml_path = os.path.join(fdir, fname)
            if not os.path.exists(xml_path):
                try:
                    download_file(f"{base}/{fname}", xml_path)
                    downloaded.append({"file": fname, "type": "xml"})
                except Exception:
                    pass

    return downloaded, fdir


# ── Shared: ensure filing downloaded + find primary_doc ─────────────────────

def _ensure_downloaded(ticker, form, accession):
    """Ensure a filing is downloaded. Returns (cik, name, primary_doc) or None."""
    cik, name = _resolve_cik(ticker)
    if not cik:
        _err(f"Ticker '{ticker}' not found")
        return None

    fdir = get_filing_dir(ticker, form, accession)
    if not os.path.isdir(fdir) or not os.listdir(fdir):
        _download_filing_files(cik, ticker, form, accession)

    idx = load_filings_index()
    key = f"{ticker}_{form}_{accession.replace('-', '')}"
    primary_doc = idx.get(key, {}).get("primary_doc", "")

    if not primary_doc:
        meta = _find_filing_meta(ticker, accession)
        if meta:
            primary_doc = meta["primary_doc"]

    return cik, name, primary_doc


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args):
    tickers = _ensure_tickers()
    _out({"status": "ok", "tickers_available": len(tickers)})


def cmd_lookup(args):
    _ensure_tickers()
    query = args.query.strip()
    query_upper = query.upper()
    tickers = load_tickers()

    if query_upper in tickers:
        info = tickers[query_upper]
        _out({"found": True, "ticker": query_upper, "cik": info["cik"], "name": info["name"]})
        return

    query_lower = query.lower()
    matches = []
    for tk, info in tickers.items():
        if query_lower in info.get("name", "").lower():
            matches.append({"ticker": tk, "cik": info["cik"], "name": info["name"]})

    if matches:
        matches.sort(key=lambda x: len(x["name"]))
        _out({"found": True, "query": query, "match_type": "name", "matches": matches[:20]})
    else:
        tickers = fetch_all_tickers()
        save_tickers(tickers)
        if query_upper in tickers:
            info = tickers[query_upper]
            _out({"found": True, "ticker": query_upper, "cik": info["cik"], "name": info["name"]})
        else:
            _out({"found": False, "query": query, "hint": "Company not found in SEC database"})


_AUDITOR_FORMS = {
    "20-F", "10-K", "10-Q", "8-K",
    "F-1", "F-1/A", "F-3", "F-3/A", "F-4", "F-4/A",
    "S-1", "S-1/A", "S-3", "S-3/A", "S-4", "S-4/A",
    "6-K",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
}


def cmd_filings(args):
    ticker = args.ticker.upper().strip()
    cik, name = _resolve_cik(ticker)
    if not cik:
        _err(f"Ticker '{ticker}' not found")
        return

    data = fetch_company_filings(cik)
    filings = data.get("filings", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    docs = filings.get("primaryDocument", [])

    results = []
    for i in range(len(forms)):
        if args.form and forms[i] != args.form:
            continue
        if not args.all and forms[i] not in _AUDITOR_FORMS:
            continue
        if args.from_date and dates[i] < args.from_date:
            continue
        if args.to_date and dates[i] > args.to_date:
            continue
        results.append({
            "form": forms[i],
            "filed_date": dates[i],
            "accession": accessions[i],
            "primary_document": docs[i] if i < len(docs) else "",
        })

    limit = args.limit or len(results)
    _out({
        "ticker": ticker,
        "company_name": data.get("company_name", name or ""),
        "cik": cik,
        "total_in_recent": len(forms),
        "filtered_count": len(results),
        "filings": results[:limit],
    })


def cmd_download(args):
    ticker = args.ticker.upper().strip()
    accession = args.accession.strip()

    meta = _find_filing_meta(ticker, accession)
    if not meta:
        _err(f"Accession '{accession}' not found for {ticker}")
        return

    form = meta["form"]
    primary_doc = meta["primary_doc"]

    downloaded, fdir = _download_filing_files(meta["cik"], ticker, form, accession)

    idx = load_filings_index()
    key = f"{ticker}_{form}_{accession.replace('-', '')}"
    idx[key] = {
        "ticker": ticker, "form": form, "accession": accession,
        "filed_date": meta["filed_date"], "primary_doc": primary_doc,
        "status": "downloaded",
    }
    save_filings_index(idx)

    toc_summary = _build_index(ticker, form, accession, primary_doc)

    _out({
        "ticker": ticker,
        "company_name": meta["name"],
        "form": form,
        "accession": accession,
        "filed_date": meta["filed_date"],
        "filing_dir": fdir,
        "downloaded_files": downloaded,
        "total_downloaded": len(downloaded),
        "toc_available": toc_summary is not None,
        "toc_summary": toc_summary,
        "hint": (
            "Use 'toc' to explore sections, 'section' to read content, "
            "'fpages' to extract financial statements, 'fpage' for cover page."
        ),
    })


def cmd_toc(args):
    ticker = args.ticker.upper().strip()
    form = args.form
    accession = args.accession.strip()

    from edgar_lib.section_search import get_toc as _get_toc

    toc = _get_toc(ticker, form, accession)
    if not toc:
        meta = _find_filing_meta(ticker, accession)
        if meta:
            _build_index(ticker, form, accession, meta["primary_doc"])
        toc = _get_toc(ticker, form, accession)

    if not toc:
        _err("No TOC available. Run 'download' first.")
        return

    _out(toc)


def cmd_section(args):
    ticker = args.ticker.upper().strip()
    form = args.form
    accession = args.accession.strip()
    section_id = args.section_id.strip()

    from edgar_lib.section_search import read_section as _read_section

    result = _read_section(ticker, form, accession, section_id)
    if not result:
        _err(f"Section '{section_id}' not found. Use 'toc' to list available sections.")
        return

    _out(result)


def cmd_search(args):
    ticker = args.ticker.upper().strip()
    keyword = args.keyword.strip()

    from edgar_lib.section_search import keyword_search as _kw_search

    result = _kw_search(ticker, keyword, form_type=args.form)
    if result["total_matches"] == 0:
        result["hint"] = "No matches found. Try 'download' first to build the section index."
    _out(result)


def cmd_concept(args):
    if not args.concept_key:
        concepts = get_all_concepts()
        items = [{"key": k, "label": v["label"], "description": v["description"]}
                 for k, v in concepts.items()]
        _out({"total": len(items), "concepts": items})
        return

    key = args.concept_key.strip()
    if key not in CONCEPTS:
        _err(f"Unknown concept: '{key}'. Run 'concept' without args to list all.")
        return

    from edgar_lib.section_search import search_by_concept as _concept_search

    result = _concept_search(key, ticker=args.ticker, form_type=args.form)
    _out(result)


def cmd_fpages(args):
    ticker, form, accession = args.ticker.upper().strip(), args.form, args.accession.strip()
    result = _ensure_downloaded(ticker, form, accession)
    if not result:
        return
    _, _, primary_doc = result

    from edgar_lib.fpage_extractor import extract_financial_pages_md
    md, fy = extract_financial_pages_md(ticker, form, accession, primary_doc)
    if md:
        _out({"ticker": ticker, "form": form, "accession": accession,
              "fiscal_year": fy, "content_length": len(md), "content": md})
    else:
        _err(
            "Financial pages extraction failed. "
            "The filing may not contain a standard audit report section "
            "(required to locate F-pages boundary)."
        )


# ── CLI setup ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="edgar",
        description="EDGAR Auditor - SEC Filing Query Tool",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    p = sub.add_parser("init", help="Download SEC ticker data")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("lookup", help="Look up company by ticker or name")
    p.add_argument("query", help="Ticker symbol or company name")
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("filings", help="List filings with filtering")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("--form", help="Filter by form type (e.g., 20-F, 10-K)")
    p.add_argument("--from", dest="from_date", help="Start date (YYYY-MM-DD)")
    p.add_argument("--to", dest="to_date", help="End date (YYYY-MM-DD)")
    p.add_argument("--limit", type=int, help="Max results")
    p.add_argument("--all", action="store_true", help="Show all filing types (default: auditor-relevant only)")
    p.set_defaults(func=cmd_filings)

    p = sub.add_parser("download", help="Download filing (HTM + MD + index)")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("accession", help="Accession number (from 'filings' command)")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("toc", help="Get table of contents")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("form", help="Form type (e.g., 10-K, 20-F)")
    p.add_argument("accession", help="Accession number")
    p.set_defaults(func=cmd_toc)

    p = sub.add_parser("section", help="Read a specific section")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("form", help="Form type")
    p.add_argument("accession", help="Accession number")
    p.add_argument("section_id", help="Section ID (from 'toc' command)")
    p.set_defaults(func=cmd_section)

    p = sub.add_parser("search", help="Keyword search across filings")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("keyword", help="Search keyword")
    p.add_argument("--form", help="Filter by form type")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("concept", help="List or search by financial concept")
    p.add_argument("concept_key", nargs="?", help="Concept key (omit to list all)")
    p.add_argument("--ticker", help="Filter by ticker")
    p.add_argument("--form", help="Filter by form type")
    p.set_defaults(func=cmd_concept)

    p = sub.add_parser("fpages", help="Extract financial statements (F-pages)")
    p.add_argument("ticker", help="Stock ticker symbol")
    p.add_argument("form", help="Form type")
    p.add_argument("accession", help="Accession number")
    p.set_defaults(func=cmd_fpages)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        _err("Interrupted")
    except Exception as e:
        _err(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
