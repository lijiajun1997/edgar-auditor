"""20-F / 10-K / F-1 Cover Page and Financial Pages Extractor."""

import logging
import os
import re
import warnings

from bs4 import XMLParsedAsHTMLWarning

from edgar_lib.config import FPAGES_DIR, MAX_COVER_LINES, MIN_COVER_LENGTH, MIN_TOC_HTML_OFFSET
from edgar_lib.db import get_filing_dir, load_filings_index
from edgar_lib.html_to_md import convert_html_to_md

logger = logging.getLogger(__name__)


def _detect_fy_from_html(html: str, form: str) -> str | None:
    m = re.search(r'name\s*=\s*"[^"]*DocumentFiscalYearFocus"[^>]*>[^<]*<(?:[^>]+)>(\d{4})<', html, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'name\s*=\s*"[^"]*DocumentFiscalYearFocus"[^>]*>\s*(\d{4})\s*<', html, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'<title>[^<]*?[_\s]\w+[\s&#160;]*\d{0,2},?[\s&#160;]*(\d{4})\s*</title>', html, re.IGNORECASE)
    if m:
        return m.group(1)
    import html as html_mod
    decoded = html_mod.unescape(html[:200000])
    m = re.search(r'fiscal\s+year\s+ended\s+\w+\s+\d{1,2},?\s+(\d{4})', decoded, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4})(\d{2})(\d{2})x20f|x10k|x10-q', html[:5000], re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'CurrentFiscalYearEndDate[^>]*>[^<]*<[^>]*>(\d{4})', html, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _find_cover_end(html: str, form: str) -> int:
    candidates: list[int] = []
    for m in re.finditer(r'TABLE\s+OF\s+CONTENTS', html, re.IGNORECASE):
        pos = m.start()
        before = html[max(0, pos - 300):pos]
        a_opens = len(re.findall(r'<a\s[^>]*href', before, re.IGNORECASE))
        a_closes = len(re.findall(r'</a>', before, re.IGNORECASE))
        if a_opens > a_closes:
            continue
        after = html[pos:m.end() + 100]
        nearby = html[max(0, pos - 200):m.end() + 100]
        is_heading = (
            bool(re.search(r'font-weight\s*:\s*bold', nearby, re.IGNORECASE)) or
            bool(re.search(r'text-align\s*:\s*center', nearby, re.IGNORECASE)) or
            bool(re.search(r'<(?:b|strong)>', nearby, re.IGNORECASE)) or
            bool(re.search(r'</(?:p|div|h\d)>', after, re.IGNORECASE))
        )
        if is_heading and pos > MIN_TOC_HTML_OFFSET:
            candidates.append(pos)
    if candidates:
        cut = candidates[0]
        tag_start = html.rfind("<", 0, cut + 1)
        return max(tag_start, 100)
    if form in ("10-K", "10-Q", "20-F"):
        for m in re.finditer(r"<(?:p|div|td|span)[^>]*>\s*<(?:b|strong|span[^>]*font-weight:\s*bold)[^>]*>\s*(?:PART|Part)\s+I\b", html[20000:], re.IGNORECASE):
            return 20000 + m.start()
        m = re.search(r"(?:PART|Part)\s+I\b", html[50000:], re.IGNORECASE)
        if m:
            return 50000 + m.start()
    if form == "20-F":
        m = re.search(r"ITEM\s+1[\.\s].*?IDENTITY", html[20000:], re.IGNORECASE)
        if m:
            search_start = max(20000, m.start() - 50000)
            toc_pos = html.rfind("TABLE", search_start, m.start())
            if toc_pos > 20000:
                return toc_pos
            return m.start()
    if form.startswith("F-") or form.startswith("S-"):
        for pattern in [r"(?:PROSPECTUS\s+)?SUMMARY", r"THE\s+OFFERING", r"RISK\s+FACTORS", r"USE\s+OF\s+PROCEEDS", r"CAPITALIZATION", r"SELECTED\s+(?:CONSOLIDATED\s+)?FINANCIAL\s+DATA", r"MANAGEMENT.{0,5}S\s+DISCUSSION", r"DESCRIPTION\s+OF\s+(?:OUR\s+)?(?:BUSINESS|CAPITAL\s+STOCK|SECURITIES)"]:
            m = re.search(r"<(?:p|div|td|h[1-6]|span)[^>]*>\s*<(?:b|strong|span[^>]*font-weight:\s*bold)[^>]*>\s*" + pattern, html[20000:], re.IGNORECASE)
            if m:
                return 20000 + m.start()
    return len(html)


def _cut_md_cover(md: str, form: str) -> str:
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if re.match(r'^TABLE\s+OF\s+CONTENTS$', line.strip(), re.IGNORECASE):
            return "\n".join(lines[:i]).strip()
    if form in ("20-F", "10-K", "10-Q"):
        for i, line in enumerate(lines):
            if re.match(r'^\*?\*?PART\s+I\*?\*?\s*$', line.strip(), re.IGNORECASE):
                return "\n".join(lines[:i]).strip()
    if form == "20-F":
        for i, line in enumerate(lines):
            if re.search(r'ITEM\s+1[\.\s]', line, re.IGNORECASE):
                return "\n".join(lines[:i]).strip()
    if form.startswith("F-") or form.startswith("S-"):
        for i, line in enumerate(lines):
            stripped = line.strip().upper()
            for pattern in ['PROSPECTUS SUMMARY', 'THE OFFERING', 'RISK FACTORS', 'SUMMARY', 'USE OF PROCEEDS']:
                if pattern in stripped and len(stripped) < 100:
                    return "\n".join(lines[:i]).strip()
    return "\n".join(lines[:150]).strip()


def extract_fpage_md(ticker: str, form: str, accession: str, primary_doc: str) -> tuple[str | None, str | None]:
    acc = accession.replace("-", "")
    fdir = get_filing_dir(ticker, form, acc)
    htm_path = os.path.join(fdir, primary_doc)
    if not os.path.isfile(htm_path):
        for candidate in ["R1.htm", "form20-f.htm", "form10-k.htm", "formf1.htm"]:
            alt = os.path.join(fdir, candidate)
            if os.path.isfile(alt):
                htm_path = alt
                break
    if not os.path.isfile(htm_path) and os.path.isdir(fdir):
        htms = sorted(f for f in os.listdir(fdir) if f.endswith((".htm", ".html")))
        if htms:
            htm_path = os.path.join(fdir, htms[0])
    if not os.path.isfile(htm_path):
        return None, None
    with open(htm_path, encoding="utf-8", errors="replace") as f:
        html = f.read()
    fy = _detect_fy_from_html(html, form)
    basename = os.path.basename(htm_path)
    is_xbrl_chunk = basename.startswith("R") and len(basename) > 1 and basename[1].isdigit()
    if is_xbrl_chunk:
        m = re.search(r"<html[^>]*>(.*?)</html>", html, re.DOTALL | re.IGNORECASE)
        if m:
            inner = m.group(1)
            inner = re.sub(r"<script[^>]*>.*?</script>", "", inner, flags=re.DOTALL)
            inner = re.sub(r"<style[^>]*>.*?</style>", "", inner, flags=re.DOTALL)
            cover_html = f"<html><body>{inner}</body></html>"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                md = convert_html_to_md(cover_html)
            md = re.sub(r"\n{3,}", "\n\n", md).strip()
            if len(md) < MIN_COVER_LENGTH:
                return None, fy
            return md, fy
    cleaned = re.sub(r"<ix:header>.*?</ix:header>", "", html, flags=re.DOTALL)
    cleaned = re.sub(r"<ix:resources>.*?</ix:resources>", "", cleaned, flags=re.DOTALL)
    cut_pos = _find_cover_end(cleaned, form)
    cover_html = f"<html><body>{cleaned[:cut_pos]}</body></html>"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        md = convert_html_to_md(cover_html)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    lines = md.split("\n")
    clean_lines: list[str] = []
    skip_patterns = [r"^xml version", r"^(true|false)$", r"^\d{4}-\d{2}-\d{2}$", r"^\d{10,}$", r"^http[s]?://", r"^(FY|Q\d)$"]
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            if any(stripped and re.match(p, stripped, re.IGNORECASE) for p in skip_patterns):
                continue
            if re.match(r"^\d{6,}$", stripped):
                continue
            if stripped:
                started = True
        clean_lines.append(line)
    md = "\n".join(clean_lines).strip()
    md = re.sub(r"\[Table of Contents\]\([^)]*\)\s*", "", md)
    md = md.strip()
    if len(md.splitlines()) > MAX_COVER_LINES:
        md = _cut_md_cover(md, form)
    if len(md) < MIN_COVER_LENGTH:
        return None, fy
    return md, fy


def extract_financial_pages_md(ticker: str, form: str, accession: str, primary_doc: str) -> tuple[str | None, str | None]:
    acc = accession.replace("-", "")
    fdir = get_filing_dir(ticker, form, acc)
    htm_path = os.path.join(fdir, primary_doc)
    if not os.path.isfile(htm_path):
        for candidate in ["R1.htm", "form20-f.htm", "form10-k.htm"]:
            alt = os.path.join(fdir, candidate)
            if os.path.isfile(alt):
                htm_path = alt
                break
    if not os.path.isfile(htm_path):
        if os.path.isdir(fdir):
            htms = sorted(f for f in os.listdir(fdir) if f.endswith((".htm", ".html")))
            if htms:
                htm_path = os.path.join(fdir, htms[0])
    if not os.path.isfile(htm_path):
        return None, None
    with open(htm_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    fy = _detect_fy_from_html(html, form)
    audit = re.search(r"REPORT\s+OF\s+INDEPENDENT\s+REGISTERED\s+PUBLIC\s+ACCOUNTING", html, re.IGNORECASE)
    if not audit:
        logger.warning("No audit report found in %s/%s/%s", ticker, form, accession)
        return None, fy
    lookback = min(5000, audit.start())
    before = html[audit.start() - lookback : audit.start()]
    toc_match = re.search(r"(?:FINANCIAL\s+STATEMENTS|INDEX\s+TO\s+(?:CONSOLIDATED\s+)?FINANCIAL)", before, re.IGNORECASE)
    if toc_match:
        start = audit.start() - lookback + toc_match.start()
    else:
        start = max(0, audit.start() - 500)
    end = len(html)
    section_html = f"<html><body>{html[start:end]}</body></html>"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        md = convert_html_to_md(section_html)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    if len(md) < 200:
        return None, fy
    return md, fy
