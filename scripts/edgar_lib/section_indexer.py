"""SEC Filing Section Indexer - XBRL + HTML dual strategy."""

import json
import logging
import os
import warnings
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from lxml import etree

from edgar_lib.config import DATA_DIR, MAX_SECTION_ELEMENTS, MAX_SECTION_LENGTH, MIN_SECTION_LENGTH
from edgar_lib.db import get_filing_dir as _get_filing_dir
from edgar_lib.db import load_filings_index

logger = logging.getLogger(__name__)

SECTIONS_INDEX_DIR = os.path.join(str(DATA_DIR), "sections_index")


def _get_sections_file(ticker: str, form: str, accession: str) -> str:
    os.makedirs(SECTIONS_INDEX_DIR, exist_ok=True)
    return os.path.join(SECTIONS_INDEX_DIR, f"{ticker}_{form}_{accession.replace('-', '')}.json")


def index_xbrl_filing(filing_dir: str) -> list[dict[str, Any]] | None:
    fs_path = os.path.join(filing_dir, "FilingSummary.xml")
    if not os.path.exists(fs_path):
        return None
    try:
        tree = etree.parse(fs_path)
        sections: list[dict[str, Any]] = []
        for report in tree.xpath("//MyReports/Report"):
            html_file = report.xpath("HtmlFileName/text()")
            short_name = report.xpath("ShortName/text()")
            long_name = report.xpath("LongName/text()")
            menu_cat = report.xpath("MenuCategory/text()")
            role = report.xpath("Role/text()")
            parent_role = report.xpath("ParentRole/text()")
            if not html_file or not short_name:
                continue
            section: dict[str, Any] = {
                "id": html_file[0].replace(".htm", ""),
                "title": short_name[0],
                "long_name": long_name[0] if long_name else "",
                "category": menu_cat[0] if menu_cat else "",
                "role": role[0] if role else "",
                "parent_role": parent_role[0] if parent_role else "",
                "source_file": html_file[0],
            }
            md_file = html_file[0].replace(".htm", ".md")
            md_path = os.path.join(filing_dir, md_file)
            if os.path.exists(md_path):
                section["md_file"] = md_file
                with open(md_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                section["content_length"] = len(content)
                if len(content.strip()) < MIN_SECTION_LENGTH:
                    continue
            else:
                section["md_file"] = None
                section["content_length"] = 0
            sections.append(section)
        return sections
    except (etree.XMLSyntaxError, OSError, ValueError):
        return None


def index_html_filing(filing_dir: str, primary_doc: str) -> list[dict[str, Any]] | None:
    html_path = os.path.join(filing_dir, primary_doc)
    if not os.path.exists(html_path):
        return None
    try:
        with open(html_path, encoding="utf-8", errors="replace") as f:
            html = f.read()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")
        toc: list[dict[str, str]] = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(" ", strip=True).replace("\xa0", " ")
            if href.startswith("#") and 3 < len(text) < 200:
                anchor = href[1:]
                if anchor and text:
                    toc.append({"anchor": anchor, "title": text})
        if not toc:
            return _index_by_headings(soup, filing_dir)
        all_elements: list[Any] = []
        elem_to_idx: dict[str, int] = {}
        for idx_pos, tag in enumerate(soup.find_all(True)):
            all_elements.append(tag)
            name = tag.get("name", "")
            tid = tag.get("id", "")
            if name and name not in elem_to_idx:
                elem_to_idx[name] = idx_pos
            if tid and tid not in elem_to_idx:
                elem_to_idx[tid] = idx_pos
        sections: list[dict[str, Any]] = []
        for i, toc_entry in enumerate(toc):
            anchor = toc_entry["anchor"]
            if anchor not in elem_to_idx:
                continue
            start_idx = elem_to_idx[anchor]
            end_idx = len(all_elements)
            for j in range(i + 1, len(toc)):
                next_anchor = toc[j]["anchor"]
                if next_anchor in elem_to_idx:
                    end_idx = elem_to_idx[next_anchor]
                    break
            content_parts: list[str] = []
            for elem in all_elements[start_idx:end_idx]:
                text = elem.get_text(" ", strip=True)
                if text:
                    content_parts.append(text)
                if len(content_parts) > MAX_SECTION_ELEMENTS:
                    break
            content = " ".join(content_parts)
            if len(content.strip()) < MIN_SECTION_LENGTH or len(content) > MAX_SECTION_LENGTH:
                continue
            sections.append({
                "id": anchor,
                "title": toc_entry["title"],
                "category": _classify_section(toc_entry["title"]),
                "content_length": len(content),
                "source": "html_toc",
            })
        if sections:
            _save_html_sections(filing_dir, sections, soup, all_elements, elem_to_idx, toc)
        return sections
    except (OSError, ValueError):
        return None


def _index_by_headings(soup: BeautifulSoup, filing_dir: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title = "Cover"
    current_parts: list[str] = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "div"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        is_heading = (
            tag.name.startswith("h")
            or ("bold" in str(tag.get("style", "")).lower() and len(text) < 150)
        )
        if is_heading and len(text) < 150 and current_parts:
            content = " ".join(current_parts)
            if len(content.strip()) > MIN_SECTION_LENGTH:
                sections.append({
                    "id": f"section_{len(sections)}",
                    "title": current_title,
                    "category": _classify_section(current_title),
                    "content_length": len(content),
                    "source": "heading_split",
                })
            current_title = text.replace("\xa0", " ")
            current_parts = []
        else:
            current_parts.append(text)
    if current_parts:
        content = " ".join(current_parts)
        if len(content.strip()) > MIN_SECTION_LENGTH:
            sections.append({
                "id": f"section_{len(sections)}",
                "title": current_title,
                "category": _classify_section(current_title),
                "content_length": len(content),
                "source": "heading_split",
            })
    return sections


def _save_html_sections(
    filing_dir: str,
    sections: list[dict[str, Any]],
    soup: BeautifulSoup,
    all_elements: list[Any],
    elem_to_idx: dict[str, int],
    toc: list[dict[str, str]],
) -> None:
    for i, sec in enumerate(sections):
        anchor = sec["id"]
        if anchor not in elem_to_idx:
            continue
        start_idx = elem_to_idx[anchor]
        end_idx = len(all_elements)
        for j in range(i + 1, len(toc)):
            next_a = toc[j]["anchor"]
            if next_a in elem_to_idx:
                end_idx = elem_to_idx[next_a]
                break
        parts: list[str] = []
        for elem in all_elements[start_idx:end_idx]:
            if hasattr(elem, "get_text"):
                parts.append(elem.get_text(" ", strip=True))
            if len(parts) > MAX_SECTION_ELEMENTS:
                break
        md_path = os.path.join(filing_dir, f"_section_{anchor}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {sec['title']}\n\n")
            f.write(" ".join(parts))
        sec["md_file"] = f"_section_{anchor}.md"


CATEGORY_PATTERNS: dict[str, list[str]] = {
    "financial_statement": ["balance sheet", "statement of operations", "cash flow", "income statement", "equity", "profit or loss", "comprehensive"],
    "revenue": ["revenue", "收入确认", "收入"],
    "audit": ["audit", "independent registered", "principal accountant", "audit fee", "accounting fee", "auditor"],
    "cam": ["critical audit matter", "critical audit matters"],
    "risk": ["risk factor", "market risk", "credit risk"],
    "governance": ["director", "executive", "compensation", "governance", "insider trading", "code of ethics"],
    "vie": ["variable interest", "vie", "consolidated entity"],
    "going_concern": ["going concern"],
    "related_party": ["related party", "related transaction"],
    "accounting_policy": ["accounting policy", "significant accounting"],
    "icfr": ["internal control", "icfr"],
}


def _classify_section(title: str) -> str:
    title_lower = title.lower()
    for cat, patterns in CATEGORY_PATTERNS.items():
        for p in patterns:
            if p in title_lower:
                return cat
    return "other"
