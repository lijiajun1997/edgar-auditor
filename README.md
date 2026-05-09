# EDGAR Auditor

<p align="center">
  <strong>SEC Filing Query Tool for Auditors & Financial Analysts</strong><br>
  Query any US-listed company's SEC filings via a single CLI tool. All output is JSON.
</p>

---

## Features

- **Company Lookup** — Resolve any ticker or company name to CIK instantly
- **Filing Discovery** — List and filter SEC filings by form type, date range
- **Filing Download** — Fetch HTML filings, auto-convert to Markdown, build section index
- **Section Navigation** — Browse TOC, read individual sections by ID
- **Keyword Search** — Full-text search across filing sections
- **Concept Search** — 12 built-in financial concepts (audit fees, VIE, CAM, revenue recognition...)
- **Cover Page Extraction** — Extract face page as clean Markdown
- **Financial Statements** — Extract complete F-pages (audit report through end of filing)

Supported forms: **10-K, 10-Q, 20-F, 6-K, 8-K, F-1, S-1** and more.

## Quick Start

### Prerequisites

- Python 3.10+
- [edgar-crawler-src](https://github.com/) project (core parsing engine)

### Setup as Claude Code Skill

Copy the entire `edgar-auditor` directory to your Claude Code skills folder:

```bash
cp -r edgar-auditor ~/.claude/skills/
```

That's it. Bundled `data/tickers.json` (10,380 SEC tickers) seeds the cache automatically on first run.

> **Note**: Dependencies (requests, beautifulsoup4, lxml, markdownify) should be pre-installed in your environment. Do NOT install them unless you see `ModuleNotFoundError`.

### Verify

```bash
python skills/edgar-auditor/scripts/edgar.py lookup AAPL
# {"found": true, "ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."}
```

## Usage

### Data Flow

The tool operates in 3 layers — each command's output feeds into the next:

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

**Key rule**: `download` is the gateway to Layer 3. You must download a filing before you can search, read sections, or extract f-pages.

### Command Reference

| Command | What it does |
|---------|-------------|
| `init` | Download SEC ticker database |
| `lookup <ticker\|name>` | Find company by ticker or name |
| `filings <ticker> [opts]` | List filings (`--form`, `--from`, `--to`, `--limit`) |
| `download <ticker> <accession>` | Download filing files + build index |
| `toc <ticker> <form> <accession>` | Show section structure |
| `section <t> <f> <acc> <id>` | Read one section's content |
| `search <ticker> <keyword>` | Keyword search across sections |
| `concept [key]` | Search by financial concept (12 built-in) |
| `fpage <ticker> <form> <acc>` | Extract cover page as Markdown |
| `fpages <ticker> <form> <acc>` | Extract financial statements as Markdown |

### Examples

```bash
# Find company
python skills/edgar-auditor/scripts/edgar.py lookup BABA

# List recent 20-F filings
python skills/edgar-auditor/scripts/edgar.py filings BABA --form 20-F --limit 3

# Download a specific filing
python skills/edgar-auditor/scripts/edgar.py download BABA 0000950170-24-063767

# Browse sections
python skills/edgar-auditor/scripts/edgar.py toc BABA 20-F 0000950170-24-063767

# Read a specific section (e.g., Income Statement)
python skills/edgar-auditor/scripts/edgar.py section BABA 20-F 0000950170-24-063767 R2

# Search by keyword
python skills/edgar-auditor/scripts/edgar.py search BABA "variable interest" --form 20-F

# Search by financial concept
python skills/edgar-auditor/scripts/edgar.py concept audit_fees --ticker BABA --form 20-F

# Extract cover page
python skills/edgar-auditor/scripts/edgar.py fpage BABA 20-F 0000950170-24-063767

# Extract full financial statements
python skills/edgar-auditor/scripts/edgar.py fpages BABA 20-F 0000950170-24-063767
```

## Financial Concepts

12 built-in concepts for audit-relevant section discovery:

| Key | Label | Description |
|-----|-------|-------------|
| `revenue_recognition` | Revenue Recognition | Revenue recognition policies and disclosures |
| `audit_fees` | Audit Fees | Fees paid to auditors |
| `cam` | Critical Audit Matters | Key audit matters identified by auditors |
| `going_concern` | Going Concern | Going concern evaluation disclosures |
| `vie` | VIE Structure | Variable Interest Entity consolidation |
| `related_party` | Related Party Transactions | Related party transaction disclosures |
| `icfr` | Internal Controls | Internal control over financial reporting |
| `risk_factors` | Risk Factors | Risk factor disclosures |
| `accounting_policy` | Accounting Policies | Significant accounting policies and estimates |
| `goodwill_impairment` | Goodwill Impairment | Goodwill and impairment disclosures |
| `cybersecurity` | Cybersecurity | Cybersecurity risk management and governance |
| `segment` | Business Segments | Operating and reportable segments |

## Architecture

```
edgar-auditor/
├── SKILL.md              # Claude Code skill definition
├── scripts/
│   └── edgar.py          # Main CLI tool (571 lines)
└── references/
    └── concepts.md       # Financial concepts reference
```

The CLI tool imports from [edgar-crawler-src](https://github.com/) which provides:
- `sec_client` — SEC EDGAR HTTP client with rate limiting
- `section_indexer` — XBRL + HTML section indexing
- `section_search` — TOC, keyword search, concept search
- `fpage_extractor` — Cover page and financial statements extraction
- `html_to_md` — SEC HTML to Markdown conversion

## Requirements

- Python >= 3.10
- Pre-installed: `requests`, `beautifulsoup4`, `lxml`, `markdownify`
- [edgar-crawler-src](https://github.com/) project (core engine)

## License

MIT
