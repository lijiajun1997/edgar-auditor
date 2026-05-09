# Financial Concepts Reference

Available financial concepts for the `concept` command. Each concept maps to specific
sections in SEC filings using title and XBRL role matching.

| Key | Label | Description | Form Types |
|-----|-------|-------------|------------|
| `revenue_recognition` | Revenue Recognition / 收入确认 | Revenue recognition policies, breakdown, and disclosures | 20-F, 10-K, 10-Q |
| `audit_fees` | Audit Fees / 审计费用 | Fees paid to auditors for audit and other services | 20-F, 10-K |
| `cam` | Critical Audit Matters / 关键审计事项 | Critical audit matters identified by auditors | 20-F, 10-K |
| `going_concern` | Going Concern / 持续经营 | Going concern evaluation and substantial doubt disclosures | 20-F, 10-K, 10-Q |
| `vie` | VIE Structure / VIE结构 | Variable Interest Entity structure and consolidation | 20-F, 10-K |
| `related_party` | Related Party Transactions / 关联交易 | Transactions with related parties | 20-F, 10-K, 10-Q |
| `icfr` | Internal Controls / 内部控制 | Internal control over financial reporting | 20-F, 10-K |
| `risk_factors` | Risk Factors / 风险因素 | Risk factor disclosures | 20-F, 10-K |
| `accounting_policy` | Accounting Policies / 会计政策 | Significant accounting policies and estimates | 20-F, 10-K, 10-Q |
| `goodwill_impairment` | Goodwill Impairment / 商誉减值 | Goodwill and impairment disclosures | 20-F, 10-K, 10-Q |
| `cybersecurity` | Cybersecurity / 网络安全 | Cybersecurity risk management and governance | 20-F, 10-K |
| `segment` | Business Segments / 业务分部 | Operating and reportable segments | 20-F, 10-K, 10-Q |

## Usage Examples

```bash
# List all concepts
python scripts/edgar.py concept

# Search revenue recognition across all BABA filings
python scripts/edgar.py concept revenue_recognition --ticker BABA

# Search audit fees in 20-F only
python scripts/edgar.py concept audit_fees --ticker BABA --form 20-F

# Search going concern across all companies
python scripts/edgar.py concept going_concern
```
