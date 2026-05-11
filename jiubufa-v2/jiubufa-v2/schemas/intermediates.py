"""
九步法每一步产生的中间产物对象。

这些对象会逐步累积到 WorkflowState 中，作为后续步骤的输入。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .kb import RuleUnitRef


# ---------------------------------------------------------------------------
# 第一步：固定权利请求
# ---------------------------------------------------------------------------


class FixedClaim(BaseModel):
    claim_id: str
    claim_text_normalized: str
    claim_type: List[str] = Field(default_factory=list)
    object_type: Optional[str] = None
    amount: Optional[float] = None
    claimant: Optional[str] = None
    respondent: Optional[str] = None
    is_clear: bool = True
    is_executable: bool = True
    issues: List[str] = Field(default_factory=list)
    clarification_questions: List[str] = Field(default_factory=list)
    priority_type: Optional[str] = None
    competition_note: Optional[str] = None  # 请求权竞合 / 聚合 / 备位说明


class Step1Output(BaseModel):
    case_cause_inferred: List[str] = Field(default_factory=list)
    legal_domain_inferred: List[str] = Field(default_factory=list)
    fixed_claims: List[FixedClaim] = Field(default_factory=list)
    overall_clarification: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第二步：请求权基础规范
# ---------------------------------------------------------------------------


class RequestBasisCandidate(BaseModel):
    claim_id: str
    rule_unit_ref: RuleUnitRef
    norm_type: List[str] = Field(default_factory=list)
    claim_type: List[str] = Field(default_factory=list)
    legal_effect_tags: List[str] = Field(default_factory=list)
    selection_reason: str
    priority: str = "primary"  # primary / alternative / supplementary
    risk_note: Optional[str] = None


class Step2Output(BaseModel):
    request_basis_candidates: List[RequestBasisCandidate] = Field(default_factory=list)
    competition_analysis: Optional[Any] = None  # 请求权竞合分析（str 或 dict）


# ---------------------------------------------------------------------------
# 第三步：抗辩权基础规范
# ---------------------------------------------------------------------------


class DefenseBasisCandidate(BaseModel):
    defense_id: str
    target_claim_id: Optional[str] = None
    response_type: str  # 承认 / 否认 / 抗辩 / 抗辩权 / 程序性异议
    defense_type: List[str] = Field(default_factory=list)
    rule_unit_ref: Optional[RuleUnitRef] = None
    legal_effect_tags: List[str] = Field(default_factory=list)
    selection_reason: Optional[str] = None
    clarification_needed: bool = False
    risk_note: Optional[str] = None


class Step3Output(BaseModel):
    defense_basis_candidates: List[DefenseBasisCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第四步：构成要件分析
# ---------------------------------------------------------------------------


class ElementMatrixRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    element_id: str
    rule_unit_id: str
    element_name: str
    element_type: Optional[str] = None
    element_logic: str = "AND"
    is_hidden_element: bool = False
    negative_element: bool = False
    exception_element: bool = False
    fact_slot: Optional[str] = None
    burden_party: Optional[str] = None
    proof_standard: Optional[str] = None
    suggested_evidence_types: List[str] = Field(default_factory=list)
    used_for: str  # request_basis / defense_basis
    target_id: str  # claim_id 或 defense_id
    note: Optional[str] = None


class Step4Output(BaseModel):
    element_matrix: List[ElementMatrixRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第五步：诉讼主张检索
# ---------------------------------------------------------------------------


class ClaimFactMappingRow(BaseModel):
    element_id: str
    fact_slot: Optional[str] = None
    required_fact: Optional[str] = None
    asserted_fact_ids: List[str] = Field(default_factory=list)
    assertion_status: str  # asserted / missing / vague / conflicting
    burden_party: Optional[str] = None
    clarification_question: Optional[str] = None
    risk_note: Optional[str] = None


class Step5Output(BaseModel):
    claim_fact_mapping: List[ClaimFactMappingRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第六步：争点整理
# ---------------------------------------------------------------------------


class Issue(BaseModel):
    issue_id: str
    issue_type: str  # fact_issue / legal_issue
    issue_text: str
    linked_element_ids: List[str] = Field(default_factory=list)
    linked_claim_id: Optional[str] = None
    linked_defense_id: Optional[str] = None
    burden_party: Optional[str] = None
    linked_evidence_ids: List[str] = Field(default_factory=list)
    priority: str = "medium"  # high / medium / low


class Step6Output(BaseModel):
    issues: List[Issue] = Field(default_factory=list)
    review_order: List[str] = Field(default_factory=list)  # issue_id 顺序


# ---------------------------------------------------------------------------
# 第七步：要件事实证明
# ---------------------------------------------------------------------------


class ProofPlanRow(BaseModel):
    issue_id: Optional[str] = None
    element_id: str
    fact_to_prove: str
    burden_party: Optional[str] = None
    proof_standard: Optional[str] = None
    existing_evidence_ids: List[str] = Field(default_factory=list)
    suggested_evidence_types: List[str] = Field(default_factory=list)
    proof_gap: Optional[str] = None
    effect_if_unknown: Optional[str] = None


class Step7Output(BaseModel):
    proof_plan: List[ProofPlanRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第八步：事实认定
# ---------------------------------------------------------------------------


class FactFinding(BaseModel):
    fact_finding_id: str
    element_id: str
    fact_slot: Optional[str] = None
    finding_status: str  # proved / not_proved / unknown
    adopted_evidence_ids: List[str] = Field(default_factory=list)
    rejected_evidence_ids: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None
    burden_party: Optional[str] = None
    effect_if_unknown: Optional[str] = None


class Step8Output(BaseModel):
    fact_findings: List[FactFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 第九步：要件归入并裁判
# ---------------------------------------------------------------------------


class ElementResult(BaseModel):
    element_id: str
    element_name: Optional[str] = None
    finding_status: str  # proved / not_proved / unknown
    note: Optional[str] = None


class DefenseReviewResult(BaseModel):
    defense_id: str
    defense_type: List[str] = Field(default_factory=list)
    elements_status: List[ElementResult] = Field(default_factory=list)
    accepted: bool = False
    effect: Optional[str] = None  # 阻却 / 消灭 / 限制 / 延缓 / 减责


class SubsumptionResult(BaseModel):
    claim_id: str
    request_basis_rule_unit_id: Optional[str] = None
    request_elements_result: List[ElementResult] = Field(default_factory=list)
    defense_results: List[DefenseReviewResult] = Field(default_factory=list)
    legal_effect_tags: List[str] = Field(default_factory=list)
    disposition_type: Optional[str] = None
    judgment_result: str  # supported / partially_supported / rejected / procedural_dismissal
    reasoning_summary: Optional[str] = None
    cited_rules: List[str] = Field(default_factory=list)  # rule_unit_id 列表


class Step9Output(BaseModel):
    subsumption_results: List[SubsumptionResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 输入完整度评分（保底机制使用）
# ---------------------------------------------------------------------------


class SufficiencyScore(BaseModel):
    """对输入材料完整度的评分。第九步前评估。"""

    claim_clarity: int = 0  # 0-20
    legal_relation_stability: int = 0  # 0-15
    request_basis_stability: int = 0  # 0-15
    defense_path_completeness: int = 0  # 0-10
    element_fact_coverage: int = 0  # 0-15
    evidence_coverage: int = 0  # 0-15
    fact_finding_reliability: int = 0  # 0-10

    @property
    def total(self) -> int:
        return (
            self.claim_clarity
            + self.legal_relation_stability
            + self.request_basis_stability
            + self.defense_path_completeness
            + self.element_fact_coverage
            + self.evidence_coverage
            + self.fact_finding_reliability
        )

    def level(self) -> str:
        from config import (  # 延迟导入避免循环
            SUFFICIENCY_THRESHOLD_MEDIUM,
            SUFFICIENCY_THRESHOLD_STRONG,
            SUFFICIENCY_THRESHOLD_WEAK,
        )

        t = self.total
        if t >= SUFFICIENCY_THRESHOLD_STRONG:
            return "strong"
        if t >= SUFFICIENCY_THRESHOLD_MEDIUM:
            return "medium"
        if t >= SUFFICIENCY_THRESHOLD_WEAK:
            return "weak_optional"
        return "block"


class FallbackGate(BaseModel):
    risk_triggered: bool
    risk_level: str  # low / medium / high / critical
    reason: List[str] = Field(default_factory=list)
    recommended_action: str = "supplement_and_retry"
    available_choices: List[Dict[str, Any]] = Field(default_factory=list)
    default_choice: str = "supplement"
    hard_block: bool = False
