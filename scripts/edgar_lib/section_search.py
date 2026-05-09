"""Smart Search for SEC Filings."""

import glob
import json
import logging
import os
from typing import Any

from edgar_lib.concept_map import CONCEPTS, match_concept
from edgar_lib.config import DATA_DIR, KEYWORD_CONTEXT_CHARS, MAX_CONTEXT_SNIPPETS, MAX_SEARCH_RESULTS
from edgar_lib.db import get_filing_dir as _get_filing_dir

logger = logging.getLogger(__name__)

SECTIONS_INDEX_DIR = os.path.join(str(DATA_DIR), "sections_index")
_idx_cache: dict[str, dict[str, Any]] = {}


def _load_sections_index(ticker: str, form: str, accession: str) -> dict[str, Any] | None:
    key = f"{ticker}_{form}_{accession.replace('-', '')}"
    if key in _idx_cache:
        return _idx_cache[key]
    path = os.path.join(SECTIONS_INDEX_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _idx_cache[key] = data
    return data


def _read_section_content(filing_dir: str, section: dict[str, Any]) -> str | None:
    md_file = section.get("md_file")
    if not md_file:
        return None
    path = os.path.join(filing_dir, md_file)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_context(content: str, keyword: str, context_chars: int = KEYWORD_CONTEXT_CHARS) -> list[str]:
    if not content:
        return []
    keyword_lower = keyword.lower()
    content_lower = content.lower()
    contexts: list[str] = []
    start = 0
    seen: set = set()
    while True:
        pos = content_lower.find(keyword_lower, start)
        if pos == -1:
            break
        ctx_start = max(0, pos - context_chars)
        ctx_end = min(len(content), pos + len(keyword) + context_chars)
        nl_before = content.rfind("\n", ctx_start, pos)
        if nl_before != -1:
            ctx_start = nl_before + 1
        nl_after = content.find("\n", pos + len(keyword), ctx_end)
        if nl_after != -1:
            ctx_end = nl_after
        ctx = content[ctx_start:ctx_end].strip()
        if ctx and ctx not in seen:
            seen.add(ctx)
            contexts.append(ctx)
            if len(contexts) >= MAX_CONTEXT_SNIPPETS:
                break
        start = pos + len(keyword)
    return contexts


def get_toc(ticker: str, form: str, accession: str) -> dict[str, Any] | None:
    idx = _load_sections_index(ticker, form, accession)
    if not idx:
        return None
    toc: list[dict[str, Any]] = []
    for s in idx.get("sections", []):
        toc.append({
            "section_id": s["id"],
            "title": s.get("title", ""),
            "category": s.get("category", ""),
            "content_length": s.get("content_length", 0),
        })
    return {
        "ticker": idx["ticker"],
        "form": idx["form"],
        "accession": idx["accession"],
        "filed_date": idx.get("filed_date", ""),
        "total_sections": len(toc),
        "toc": toc,
    }


def keyword_search(ticker: str, keyword: str, form_type: str | None = None, max_results: int = MAX_SEARCH_RESULTS) -> dict[str, Any]:
    ticker = ticker.upper()
    results: list[dict[str, Any]] = []
    index_files = glob.glob(os.path.join(SECTIONS_INDEX_DIR, f"{ticker}_*.json"))
    for idx_file in index_files:
        with open(idx_file, encoding="utf-8") as f:
            idx = json.load(f)
        if form_type and idx["form"] != form_type:
            continue
        filing_dir = _get_filing_dir(idx["ticker"], idx["form"], idx["accession"])
        for section in idx.get("sections", []):
            title = section.get("title", "")
            title_match = keyword.lower() in title.lower()
            content = _read_section_content(filing_dir, section)
            content_match = content and keyword.lower() in content.lower()
            if not title_match and not content_match:
                continue
            contexts: list[str] = []
            if content_match:
                contexts = _extract_context(content, keyword)
            results.append({
                "ticker": idx["ticker"], "form": idx["form"],
                "accession": idx["accession"], "filed_date": idx.get("filed_date", ""),
                "section_id": section["id"], "section_title": title,
                "category": section.get("category", ""),
                "title_match": title_match, "content_length": section.get("content_length", 0),
                "keyword_contexts": contexts,
            })
    results.sort(key=lambda x: (x["filed_date"], x["title_match"], x["content_length"]), reverse=True)
    return {"ticker": ticker, "keyword": keyword, "total_matches": len(results), "results": results[:max_results]}


def read_section(ticker: str, form: str, accession: str, section_id: str) -> dict[str, Any] | None:
    idx = _load_sections_index(ticker, form, accession)
    if not idx:
        return None
    for section in idx.get("sections", []):
        if section["id"] == section_id:
            filing_dir = _get_filing_dir(ticker, form, accession)
            content = _read_section_content(filing_dir, section)
            return {
                "ticker": ticker, "form": form, "accession": accession,
                "filed_date": idx.get("filed_date", ""),
                "section_id": section_id, "section_title": section.get("title", ""),
                "category": section.get("category", ""),
                "content_length": len(content) if content else 0, "content": content,
            }
    return None


def search_by_concept(concept_key: str, ticker: str | None = None, form_type: str | None = None, max_results: int = MAX_SEARCH_RESULTS) -> dict[str, Any]:
    if concept_key not in CONCEPTS:
        return {"error": f"Unknown concept: {concept_key}", "available": list(CONCEPTS.keys())}
    concept = CONCEPTS[concept_key]
    results: list[dict[str, Any]] = []
    index_files = glob.glob(os.path.join(SECTIONS_INDEX_DIR, "*.json"))
    for idx_file in index_files:
        with open(idx_file, encoding="utf-8") as f:
            idx = json.load(f)
        if ticker and idx["ticker"] != ticker.upper():
            continue
        if form_type and idx["form"] != form_type:
            continue
        if idx["form"] not in concept.get("form_types", []):
            continue
        for section in idx.get("sections", []):
            title = section.get("title", "")
            role = section.get("role", "")
            matches = match_concept(title, role)
            if concept_key in matches:
                results.append({
                    "ticker": idx["ticker"], "form": idx["form"],
                    "accession": idx["accession"], "filed_date": idx.get("filed_date", ""),
                    "section_id": section["id"], "section_title": title,
                    "category": section.get("category", ""),
                    "content_length": section.get("content_length", 0),
                })
    results.sort(key=lambda x: (x["filed_date"], x["content_length"]), reverse=True)
    return {"concept": concept_key, "label": concept["label"], "total_matches": len(results), "results": results[:max_results]}
