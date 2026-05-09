"""Financial concept -> SEC filing section mapping."""

CONCEPTS = {
    "revenue_recognition": {
        "label": "Revenue Recognition / 收入确认",
        "description": "Revenue recognition policies, breakdown, and disclosures",
        "match_title": ["revenue", "收入", "sales", "contract", "customer", "transfer of goods"],
        "match_role": ["Revenue", "RevenueRecognition", "RevenueFromContract"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
    "audit_fees": {
        "label": "Audit Fees / 审计费用",
        "description": "Fees paid to auditors for audit and other services",
        "match_title": ["principal accountant fee", "audit fee", "auditor fee", "accounting fee", "accountant", "independent registered public"],
        "match_role": ["PrincipalAccountantFees", "AuditFees"],
        "form_types": ["20-F", "10-K"],
    },
    "cam": {
        "label": "Critical Audit Matters / 关键审计事项",
        "description": "Critical audit matters identified by auditors",
        "match_title": ["critical audit matter"],
        "match_role": ["CriticalAuditMatters"],
        "form_types": ["20-F", "10-K"],
    },
    "going_concern": {
        "label": "Going Concern / 持续经营",
        "description": "Going concern evaluation and substantial doubt disclosures",
        "match_title": ["going concern", "substantial doubt"],
        "match_role": ["GoingConcern"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
    "vie": {
        "label": "VIE Structure / VIE结构",
        "description": "Variable Interest Entity structure and consolidation",
        "match_title": ["variable interest", "consolidat", "vie"],
        "match_role": [],
        "form_types": ["20-F", "10-K"],
    },
    "related_party": {
        "label": "Related Party Transactions / 关联交易",
        "description": "Transactions with related parties",
        "match_title": ["related party", "related transaction"],
        "match_role": ["RelatedParty"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
    "icfr": {
        "label": "Internal Controls / 内部控制",
        "description": "Internal control over financial reporting",
        "match_title": ["internal control", "icfr"],
        "match_role": [],
        "form_types": ["20-F", "10-K"],
    },
    "risk_factors": {
        "label": "Risk Factors / 风险因素",
        "description": "Risk factor disclosures",
        "match_title": ["risk factor"],
        "match_role": [],
        "form_types": ["20-F", "10-K"],
    },
    "accounting_policy": {
        "label": "Accounting Policies / 会计政策",
        "description": "Significant accounting policies and estimates",
        "match_title": ["accounting policy", "significant accounting", "accounting judgement", "accounting estimate"],
        "match_role": ["AccountingPolicy", "SignificantAccounting"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
    "goodwill_impairment": {
        "label": "Goodwill Impairment / 商誉减值",
        "description": "Goodwill and impairment disclosures",
        "match_title": ["goodwill", "impairment"],
        "match_role": ["Goodwill", "Impairment"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
    "cybersecurity": {
        "label": "Cybersecurity / 网络安全",
        "description": "Cybersecurity risk management and governance",
        "match_title": ["cybersecurity"],
        "match_role": ["Cybersecurity"],
        "form_types": ["20-F", "10-K"],
    },
    "segment": {
        "label": "Business Segments / 业务分部",
        "description": "Operating and reportable segments",
        "match_title": ["segment", "operating segment"],
        "match_role": ["Segment"],
        "form_types": ["20-F", "10-K", "10-Q"],
    },
}


def match_concept(section_title: str, section_role: str = "", section_category: str = "") -> list[str]:
    title_lower = section_title.lower()
    role_lower = section_role.lower() if section_role else ""
    matches: list[str] = []
    for concept_key, concept in CONCEPTS.items():
        for pattern in concept["match_title"]:
            if pattern.lower() in title_lower:
                matches.append(concept_key)
                break
        if concept_key not in matches:
            for pattern in concept.get("match_role", []):
                if pattern.lower() in role_lower:
                    matches.append(concept_key)
                    break
    return matches


def get_all_concepts() -> dict[str, dict[str, str]]:
    return {k: {"label": v["label"], "description": v["description"]}
            for k, v in CONCEPTS.items()}
