---
name: edgar-auditor
description: >
  SEC EDGAR filing query tool for US stock auditors and financial analysts.
  Look up any US-listed company's SEC filings, download and convert to Markdown,
  search by keyword or financial concept (revenue recognition, audit fees, VIE,
  related party, CAM, going concern, etc.), extract financial statements (f-pages).
  Supports 10-K, 10-Q, 20-F, 6-K, 8-K, F-1, S-1 and more.
  Use this skill whenever the user asks about SEC filings, EDGAR data, 10-K,
  10-Q, 20-F, annual reports, quarterly reports, financial statements, audit
  reports, MD&A, f-pages, f-page, or any US publicly traded company filing information,
  even if they just mention a ticker symbol and want financial data.
---

# EDGAR Auditor

Query any US-listed company's SEC filings via a single CLI tool. All output is JSON.

## Environment

Fully self-contained. All code is bundled in `scripts/edgar_lib/` — no external project dependency.
The bundled `data/tickers.json` (10,380 SEC tickers) seeds the cache automatically on first run.
Do NOT attempt to install dependencies unless a command fails with `ModuleNotFoundError`.

## Data Flow

```
LAYER 1: DISCOVER          LAYER 2: ACCESS              LAYER 3: EXTRACT
─────────────────          ──────────────               ───────────────
lookup → {ticker, cik}     download → {filing_dir,      search → {matches[]}
filings → {accession,                primary_md_path}   concept → {matches[]}
          form, date}                                    section → {content}
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
| `download TICKER ACCESSION` | Fetch filing files + build index | **Always** before search/section/fpages. Returns `primary_md_path` |
| `search TICKER KEYWORD` | Keyword search across sections | **PREFERRED first step** after download to locate content |
| `section TICKER FORM ACC ID` | Read one section's full content | After search identifies the right section_id |
| `concept [KEY]` | Search by financial concept | Find audit-relevant sections by category |
| `fpages TICKER FORM ACC` | Extract financial statements as MD | Get full F-pages (audit report → end of filing) |
| `toc TICKER FORM ACC` | Show section structure | **RARELY needed** — only when search fails to find target |

## Composing Commands

### Pattern 1: "What filings does X have?"

```
lookup "Alibaba" → filings BABA --form 20-F
```

### Pattern 2: "Find information about X in a filing" (SEARCH-FIRST ★)

```
filings BABA --form 20-F
  → download BABA <accession>                  # returns primary_md_path
  → search BABA "variable interest" --form 20-F  # find matching sections
  → section BABA 20-F <acc> <section_id>        # read the matched section
```

**If search returns nothing**, read the primary MD directly:
```
  → read_file(primary_md_path, offset=0, limit=2000)    # direct read
  → read_file(primary_md_path, offset=2000, limit=2000)  # continue
```

### Pattern 3: "Read the full filing text" (DIRECT MD READ)

```
download BABA <accession>   # returns primary_md_path
  → read_file(primary_md_path, offset=0, limit=2000)     # chunk read
  → read_file(primary_md_path, offset=2000, limit=2000)   # continue
  ... until EOF ...
```

Use this when the user wants to browse the whole filing or when search misses.

### Pattern 4: "Get all financial statements (f-pages)"

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
  → section BABA 20-F <acc> <section_id>        # read the hit
```

### ❌ ANTI-PATTERN: Manual structure navigation

```
# ❌ WASTEFUL — costs 2 extra rounds with no benefit
download → toc → browse section IDs → section

# ✅ EFFICIENT — search locates content directly
download → search "keyword" → section (if needed)
```

**`toc` is rarely needed.** Search covers all sections. Only use `toc` when:
- Search returns nothing AND you don't know what keywords to use
- You need to understand the filing's overall structure for a specific reason

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

Output: `{form, filing_dir, primary_md_path, downloaded_files[], toc_summary{sections[]}, hint}`

**`primary_md_path`**: Full path to the primary document's MD file. Agent can `read_file`
directly for broad reading. This is the most efficient way to consume filing content.

### search

```bash
python skills/edgar-auditor/scripts/edgar.py search AAPL "revenue recognition"
python skills/edgar-auditor/scripts/edgar.py search AAPL "variable interest" --form 20-F
```

Keyword search across all downloaded filing sections. Returns matching sections with
context snippets. **This is the preferred way to locate content** — always use before `toc`.

Output: `{ticker, keyword, total_matches, results[{section_id, section_title, keyword_contexts[]}]}`

### section

```bash
python skills/edgar-auditor/scripts/edgar.py section AAPL 10-K 0000320193-24-000123 R15
```

Read one section's full content. Use after `search` identifies the right section_id.

Output: `{section_id, section_title, content_length, content}`

### concept

```bash
python skills/edgar-auditor/scripts/edgar.py concept                              # list all 12 concepts
python skills/edgar-auditor/scripts/edgar.py concept revenue_recognition --ticker AAPL
```

### fpages

```bash
python skills/edgar-auditor/scripts/edgar.py fpages BABA 20-F 0001577552-25-000001
```

Extracts complete financial statements (from audit report to end of filing). For 20-F: F-1, F-2, etc.
Auto-downloads the filing if not cached.

Output: `{ticker, form, accession, fiscal_year, content_length, content}`

## Round Budget

| Pattern | Rounds | Notes |
|---------|--------|-------|
| Find info (search-first) | 4-5 | lookup + filings + download + search + section |
| Find info (toc→section) | 5-6 | lookup + filings + download + toc + find + section — **avoid** |
| Direct MD read | 3-5 | download + read_file chunks |
| F-pages extraction | 4 | lookup + filings + download + fpages |
| Concept search | 3-4 | download + concept + section |

**Key**: Every round counts. Search replaces toc+browse (2 rounds → 1 round).

## What to Know

- **Caching**: Downloads are idempotent. Re-running `download` skips existing files.
- **Ticker refresh**: If `lookup` can't find a ticker, it refreshes from SEC automatically.
- **XBRL vs HTML**: Modern filings use XBRL (R1.htm, R2.htm...). The `download` command
  indexes both XBRL R-sections and HTML TOC items. For content not in any indexed section,
  the primary document MD (at `primary_md_path`) contains the complete filing text.
- **Concept list**: `revenue_recognition`, `audit_fees`, `cam`, `going_concern`, `vie`,
  `related_party`, `icfr`, `risk_factors`, `accounting_policy`, `goodwill_impairment`,
  `cybersecurity`, `segment`. Run `concept` without args to see all.
- **f-pages**: User mentions "f-page", "fpages", or "f-pages" all mean the `fpages` command.

## Continuous Iteration

每次使用 edgar-auditor 完成任务后，agent 必须执行复盘：

### 1. 效率复盘

```
回顾本轮用了多少 tool rounds → 是否有浪费 → 更新 SKILL.md 工作流
```

- **多余步骤**: 做了 toc 浏览但 search 就能定位 → 加深 search-first 强调
- **搜索词不准**: search 返回空结果但内容存在 → 记录有效搜索词，更新 concept_map
- **重复下载**: 同一 filing 被下载多次 → 检查缓存逻辑

### 2. 搜索质量迭代

```
search 结果 → 分析命中率 → 更新 concept_map.py 或搜索策略
```

需迭代的场景：
- concept 搜索漏掉相关 section → 更新 CONCEPTS 中的关键词
- 用户频繁查找的 topic 没有 concept → 新增 concept
- XBRL section 标题变化导致 concept 匹配失败 → 更新匹配规则

### 3. 提取质量迭代

```
section/fpages 内容 → 与原文对比 → 修复 section_indexer 或 html_to_md
```

- 20-F section 切分不准 → 调整 indexer 参数
- HTML→MD 转换丢失表格/格式 → 更新 html_to_md
- F-pages 边界识别错误 → 修复 fpage_extractor

### 迭代记录

每次迭代在下方追加一条记录：

```
- [日期] 问题 → 修复 → 影响文件
- [2026-05-09] agent 浪费 rounds 做 toc→section 导航 → 改为 search-first 模式 → SKILL.md, edgar.py
```
