---
name: edgar-auditor
description: >
  SEC EDGAR filing query tool for US stock auditors and financial analysts.
  Look up any US-listed company's SEC filings, download and convert to Markdown,
  search by keyword or financial concept (revenue recognition, audit fees, VIE,
  related party, CAM, going concern, etc.), extract cover pages and financial
  statements (f-pages). Supports 10-K, 10-Q, 20-F, 6-K, 8-K, F-1, S-1 and more.
  Use this skill whenever the user asks about SEC filings, EDGAR data, 10-K,
  10-Q, 20-F, annual reports, quarterly reports, financial statements, audit
  reports, MD&A, f-pages, or any US publicly traded company filing information,
  even if they just mention a ticker symbol and want financial data.
---

# EDGAR Auditor

Query any US-listed company's SEC filings via a single CLI tool. All output is JSON.

## Environment

All dependencies (requests, beautifulsoup4, lxml, markdownify) are pre-installed.
The bundled `data/tickers.json` (10,380 SEC tickers) seeds the cache automatically on first run.
Do NOT attempt to install dependencies unless a command fails with `ModuleNotFoundError`.

## Data Flow

The tool has 3 layers. Each command's output feeds into the next:

```
LAYER 1: DISCOVER          LAYER 2: ACCESS              LAYER 3: EXTRACT
─────────────────          ──────────────               ───────────────
lookup → {ticker, cik}     download → {toc, filing_dir} toc → {section_id}
filings → {accession,      toc → {sections[]}           section → {content}
          form, date}                                   search → {matches[]}
                                                       concept → {matches[]}
                                                       fpage → {cover page MD}
                                                       fpages → {financial stmts MD}
```

**Key rule**: `download` is the gateway to Layer 3. You must download a filing
before you can search, read sections, or extract f-pages from it.

## Commands Quick Reference

| Command | What it does | When to use |
|---------|-------------|-------------|
| `init` | Download ticker data | Auto-runs on first use; rarely needed manually |
| `lookup QUERY` | Find company by ticker or name | Starting point — resolve any company name to ticker/CIK |
| `filings TICKER [opts]` | List SEC filings with filters | Browse what's available for a company |
| `download TICKER ACCESSION` | Fetch filing files + build index | **Always** before search/section/fpages |
| `toc TICKER FORM ACCESSION` | Show section structure | See what's inside a filing |
| `section TICKER FORM ACC ID` | Read one section's full content | Extract specific data (revenue note, audit report, etc.) |
| `search TICKER KEYWORD` | Keyword search across sections | Find where a topic is discussed |
| `concept [KEY]` | Search by financial concept | Find audit-relevant sections by category |
| `fpage TICKER FORM ACC` | Extract cover page as MD | Get company info, FY, auditor from face page |
| `fpages TICKER FORM ACC` | Extract financial statements as MD | Get full F-pages (audit report → end of filing) |

## Composing Commands

### Pattern 1: "What filings does X have?"

```
lookup "Alibaba" → filings BABA --form 20-F
```

### Pattern 2: "Read a specific section of a filing"

```
filings BABA --form 20-F
  → download BABA <accession>
  → toc BABA 20-F <accession>        # discover section IDs
  → section BABA 20-F <accession> R15 # read Revenue note
```

### Pattern 3: "Find where X is discussed"

```
download BABA <accession>
  → search BABA "variable interest" --form 20-F   # returns matching sections
  → section BABA 20-F <acc> <section_id>           # read the hit
```

### Pattern 4: "Get all financial statements"

```
filings BABA --form 20-F
  → download BABA <accession>
  → fpages BABA 20-F <accession>   # full F-pages (audit report + statements)
```

### Pattern 5: "Audit-specific concept search"

```
download BABA <accession>
  → concept audit_fees --ticker BABA           # find audit fee disclosures
  → concept related_party --ticker BABA         # find related party sections
  → concept cam --ticker BABA                   # critical audit matters
  → section BABA 20-F <acc> <section_id>        # read the hit
```

## Command Details

### lookup

```bash
python skills/edgar-auditor/scripts/edgar.py lookup AAPL
python skills/edgar-auditor/scripts/edgar.py lookup "Apple Inc"
```

Exact ticker match first, then fuzzy name search. Auto-refreshes from SEC on miss.

Output: `{found, ticker, cik, name}` or `{found, matches[{ticker, cik, name}]}`

### filings

```bash
python skills/edgar-auditor/scripts/edgar.py filings AAPL --form 10-K --from 2024-01-01 --limit 5
```

Options: `--form TYPE` `--from YYYY-MM-DD` `--to YYYY-MM-DD` `--limit N`

Output: `{ticker, company_name, filings[{form, filed_date, accession, primary_document}]}`

### download

```bash
python skills/edgar-auditor/scripts/edgar.py download AAPL 0000320193-24-000123
```

Downloads all HTM/HTML files, converts to MD, fetches XML exhibits, builds section
index (XBRL R-sections + HTML TOC items). Already-downloaded files are skipped.

Output: `{form, filing_dir, downloaded_files[], toc_summary{sections[]}, hint}`

### toc / section / search / concept

```bash
python skills/edgar-auditor/scripts/edgar.py toc AAPL 10-K 0000320193-24-000123
python skills/edgar-auditor/scripts/edgar.py section AAPL 10-K 0000320193-24-000123 R15
python skills/edgar-auditor/scripts/edgar.py search AAPL "revenue recognition"
python skills/edgar-auditor/scripts/edgar.py concept                              # list all 12 concepts
python skills/edgar-auditor/scripts/edgar.py concept revenue_recognition --ticker AAPL
```

### fpage / fpages

```bash
python skills/edgar-auditor/scripts/edgar.py fpage BABA 20-F 0001577552-25-000001    # cover page
python skills/edgar-auditor/scripts/edgar.py fpages BABA 20-F 0001577552-25-000001   # financial statements
```

- `fpage`: Cover page (before TABLE OF CONTENTS) — company name, FY, auditor, etc.
- `fpages`: Complete financial statements (from audit report to end). For 20-F: F-1, F-2, etc.

Both auto-download the filing if not cached.

## What to Know

- **Caching**: Downloads are idempotent. Re-running `download` skips existing files.
- **Ticker refresh**: If `lookup` can't find a ticker, it refreshes from SEC automatically.
- **XBRL vs HTML**: Modern filings use XBRL (R1.htm, R2.htm...). The `download` command
  indexes both XBRL R-sections (financial data with full content) and HTML TOC items
  (narrative sections like audit fees, controls). For narrative content not captured
  in sections, the primary document MD file (e.g., `baba-20240331.md`) in the filing
  directory contains the complete filing text.
- **Concept list**: `revenue_recognition`, `audit_fees`, `cam`, `going_concern`, `vie`,
  `related_party`, `icfr`, `risk_factors`, `accounting_policy`, `goodwill_impairment`,
  `cybersecurity`, `segment`. Run `concept` without args to see all.
