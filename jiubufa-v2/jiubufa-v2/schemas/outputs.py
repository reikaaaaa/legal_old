"""
工作流最终输出结构。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .intermediates import (
    FallbackGate,
    Step1Output,
    Step2Output,
    Step3Output,
    Step4Output,
    Step5Output,
    Step6Output,
    Step7Output,
    Step8Output,
    Step9Output,
    SubsumptionResult,
    SufficiencyScore,
)


# ---------------------------------------------------------------------------
# 强裁判输出
# ---------------------------------------------------------------------------


class StrongJudgmentOutput(BaseModel):
    """强裁判结果。"""

    mode: str = "strong_judgment"
    sufficiency_score: SufficiencyScore
    risk_level: str = "low"
    subsumption_results: List[SubsumptionResult] = Field(default_factory=list)
    document_skeleton: Dict[str, Any] = Field(default_factory=dict)
    """裁判文书框架，含：
       原告诉讼请求 / 被告辩称 / 争议焦点 / 本院查明 / 本院认为 / 判决主文 等。"""
    consistency_check: Dict[str, Any] = Field(default_factory=dict)
    """文书"八个一致"校验结果。"""


# ---------------------------------------------------------------------------
# 弱裁判输出
# ---------------------------------------------------------------------------


class WeakSubsumptionResult(BaseModel):
    claim_id: str
    candidate_rule_unit_id: Optional[str] = None
    conditioned_element_result: List[Dict[str, Any]] = Field(default_factory=list)
    defense_review_status: str = "not_available"  # not_available / limited / reviewed
    tentative_judgment_result: str  # likely_supported / likely_partially_supported / likely_rejected / uncertain
    confidence: str = "low"  # low / medium
    reasoning_summary: Optional[str] = None
    risk_note: Optional[str] = None


class FallbackPathItem(BaseModel):
    return_to_step: str
    reason: str


class WeakJudgmentOutput(BaseModel):
    """弱裁判结果。"""

    mode: str = "weak_judgment"
    sufficiency_score: SufficiencyScore
    risk_level: str = "high"
    user_choice: str = "continue_weak_judgment"
    missing_inputs: List[str] = Field(default_factory=list)
    assumptions_used: List[str] = Field(default_factory=list)
    unsupported_elements: List[str] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
    law_application_risks: List[str] = Field(default_factory=list)
    fact_finding_risks: List[str] = Field(default_factory=list)
    proof_risks: List[str] = Field(default_factory=list)
    fallback_path: List[FallbackPathItem] = Field(default_factory=list)
    weak_subsumption_results: List[WeakSubsumptionResult] = Field(default_factory=list)
    upgrade_to_strong_judgment_requirements: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 部分输出（partial_output_only 模式）
# ---------------------------------------------------------------------------


class PartialOutput(BaseModel):
    mode: str = "partial_output_only"
    sufficiency_score: SufficiencyScore
    fixed_claims: List[Dict[str, Any]] = Field(default_factory=list)
    request_basis_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    defense_basis_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    element_matrix: List[Dict[str, Any]] = Field(default_factory=list)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    note: str = "在材料不足以裁判时仅输出要件、争点与证据缺口，不输出裁判倾向。"


# ---------------------------------------------------------------------------
# 工作流总输出
# ---------------------------------------------------------------------------


class WorkflowResult(BaseModel):
    """工作流的总返回。"""

    case_id: Optional[str] = None
    status: str  # ok / blocked / awaiting_user_choice
    fallback_gate: Optional[FallbackGate] = None

    # 各步骤产出（成功跑到的步骤才会填充）
    step1: Optional[Step1Output] = None
    step2: Optional[Step2Output] = None
    step3: Optional[Step3Output] = None
    step4: Optional[Step4Output] = None
    step5: Optional[Step5Output] = None
    step6: Optional[Step6Output] = None
    step7: Optional[Step7Output] = None
    step8: Optional[Step8Output] = None
    step9: Optional[Step9Output] = None

    # 终态输出，三选一
    strong_judgment: Optional[StrongJudgmentOutput] = None
    weak_judgment: Optional[WeakJudgmentOutput] = None
    partial_output: Optional[PartialOutput] = None

    # 调试信息
    timings_ms: Dict[str, int] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
