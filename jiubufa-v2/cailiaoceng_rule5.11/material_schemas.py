"""
材料规范层 v3.0 — Pydantic Schema 定义

输出结构对齐 jiubufa-v2 的 CaseInput，可直接送入 /api/workflow/run。

阶段一：MaterialReviewResult（审核结果）
阶段二：NormalizedCaseInput（规范化后，≈ CaseInput + 审核元数据）
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 阶段一：材料审核
# ============================================================================


class MaterialItem(BaseModel):
    name: str
    source_element: str = Field(description="对应示范文本要素或九步法检查点")
    legal_basis: str = Field(description="法律依据（法条号）")
    is_core: bool
    status: Literal["已提供", "部分提供", "缺失"]
    dimension: Literal["案由专项", "九步法"]
    description: str
    suggestion: str = ""


class CaseTypeMaterialCheck(BaseModel):
    case_module: str
    checklist: List[MaterialItem]
    core_provided_rate: float = Field(ge=0.0, le=1.0)
    special_rules_note: str = ""


class StepRequirementCheck(BaseModel):
    step_index: int = Field(ge=1, le=9)
    step_name: str
    status: Literal["充足", "部分不足", "严重缺失"]
    has_required: List[str] = Field(default_factory=list)
    missing_items: List[str] = Field(default_factory=list)
    suggestion: str = ""
    special_note: str = ""


class MaterialReviewResult(BaseModel):
    """阶段一输出：双维度审核结果。can_proceed=true 后方可进入阶段二。"""

    case_module: Literal[
        "合同纠纷", "婚姻家庭", "侵权纠纷", "劳动争议",
        "民间借贷", "其他民事案件", "无法确定",
    ]
    case_type_check: CaseTypeMaterialCheck
    step_checks: List[StepRequirementCheck]
    overall_status: Literal["材料充足", "材料基本完整", "材料不完整", "仅有案件摘要"]
    can_proceed: bool
    missing_core_materials: List[str] = Field(default_factory=list)
    missing_optional_materials: List[str] = Field(default_factory=list)
    upload_instructions: str
    confidence: Literal["高", "中", "低"]


# ============================================================================
# 阶段二：材料规范化 → CaseInput 对齐
# ============================================================================

# --- 案件基本信息 ---


class CaseBasicInfo(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py CaseBasicInfo"""

    case_id: Optional[str] = None
    case_name: Optional[str] = None
    case_cause_text: Optional[str] = None
    court: Optional[str] = None
    procedure_stage: Optional[str] = None
    filing_date: Optional[str] = None
    material_sources: List[str] = Field(default_factory=list)
    case_summary: Optional[str] = None


# --- 当事人 ---


class PartyInfo(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py PartyInfo"""

    party_id: str
    party_name: Optional[str] = None
    party_role: Optional[str] = None
    legal_status: Optional[str] = None
    relationship_to_case: Optional[str] = None
    identity_evidence: List[str] = Field(default_factory=list)
    standing_issue: bool = False


# --- 诉讼请求 ---


class ClaimObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py ClaimObject"""

    claim_id: str
    claim_text_original: str
    claim_text_normalized: Optional[str] = None
    claimant: Optional[str] = None
    respondent: Optional[str] = None
    claim_type_candidate: List[str] = Field(default_factory=list)
    object_type: Optional[str] = None
    amount: Optional[float] = None
    behavior_requested: Optional[str] = None
    is_clear: Optional[bool] = None
    is_executable: Optional[bool] = None
    conflict_with_other_claims: List[str] = Field(default_factory=list)
    supplement_needed: bool = False
    priority_type: Optional[str] = None


# --- 事实主张 ---


class ClaimFactObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py ClaimFactObject"""

    fact_id: str
    fact_text_original: str
    fact_text_normalized: Optional[str] = None
    fact_time: Optional[str] = None
    fact_actor: Optional[str] = None
    fact_counterparty: Optional[str] = None
    fact_type_candidate: List[str] = Field(default_factory=list)
    linked_claim_id: Optional[str] = None
    linked_evidence_ids: List[str] = Field(default_factory=list)
    possible_fact_slot: List[str] = Field(default_factory=list)
    clarity_status: Optional[str] = None
    opponent_response: Optional[str] = None


# --- 答辩 / 抗辩 ---


class DefenseObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py DefenseObject"""

    defense_id: str
    defense_text_original: str
    defense_text_normalized: Optional[str] = None
    defense_target_claim_id: Optional[str] = None
    response_type: Optional[str] = None  # 承认 / 否认 / 抗辩 / 抗辩权 / 程序性异议
    defense_type_candidate: List[str] = Field(default_factory=list)
    new_fact_asserted: bool = False
    linked_evidence_ids: List[str] = Field(default_factory=list)
    possible_defense_basis: List[str] = Field(default_factory=list)
    clarification_needed: bool = False


# --- 反诉 ---


class CounterclaimObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py CounterclaimObject"""

    counterclaim_id: str
    counterclaim_text: str
    counterclaim_type_candidate: List[str] = Field(default_factory=list)
    linked_evidence_ids: List[str] = Field(default_factory=list)


# --- 证据 ---


class EvidenceObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py EvidenceObject"""

    evidence_id: str
    evidence_name: str
    submitted_by: Optional[str] = None
    evidence_type: Optional[str] = None
    proof_purpose_original: Optional[str] = None
    proof_purpose_normalized: Optional[str] = None
    linked_claim_id: Optional[str] = None
    linked_defense_id: Optional[str] = None
    linked_fact_ids: List[str] = Field(default_factory=list)
    linked_element_ids: List[str] = Field(default_factory=list)
    opponent_cross_examination: Optional[str] = None
    legality_status: Optional[str] = None
    relevance_status: Optional[str] = None
    authenticity_status: Optional[str] = None
    probative_force: Optional[str] = None
    adopted_status: Optional[str] = None


class EvidenceMeta(BaseModel):
    """
    v3.0 新增：证据审核元数据。
    不进入 CaseInput，随 NormalizedCaseInput 返回供前端展示。
    """

    evidence_id: str
    subtype: str = ""  # 电子数据子类/书证子类
    completeness: Literal["完整", "部分", "待核实"] = "待核实"
    authenticity_note: str = ""
    standalone_capable: bool = True  # 《民事证据规定》第90条
    standalone_limitation: str = ""


# --- 质证意见 ---


class CrossExaminationObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py CrossExaminationObject"""

    cross_id: str
    evidence_id: str
    opponent: Optional[str] = None
    legality_opinion: Optional[str] = None
    relevance_opinion: Optional[str] = None
    authenticity_opinion: Optional[str] = None
    probative_force_opinion: Optional[str] = None
    reason: Optional[str] = None
    need_supplementary_proof: bool = False


# --- 法律意见 ---


class LegalArgumentObject(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py LegalArgumentObject"""

    argument_id: str
    submitted_by: Optional[str] = None
    target_claim_or_defense: Optional[str] = None
    cited_law_name: Optional[str] = None
    cited_article_no: Optional[str] = None
    argument_text: Optional[str] = None
    norm_type_candidate: List[str] = Field(default_factory=list)
    dispute_status: Optional[str] = None
    court_view_needed: bool = False


# --- 程序事项 ---


class ProceduralInfo(BaseModel):
    """对齐 jiubufa-v2 schemas/inputs.py ProceduralInfo"""

    jurisdiction: Optional[str] = None
    limitation_period_status: Optional[str] = None
    proof_period_status: Optional[str] = None
    other_notes: Optional[str] = None


# ============================================================================
# 阶段二顶层输出
# ============================================================================


class NormalizedCaseInput(BaseModel):
    """
    阶段二输出：规范化后的案件材料，字段结构与 CaseInput 一一对应。

    可直接通过 adapter.to_case_input() 转换为 CaseInput，
    然后送入 /api/workflow/run。
    """

    case_basic_info: CaseBasicInfo = Field(default_factory=CaseBasicInfo)
    party_info: List[PartyInfo] = Field(default_factory=list)
    claims: List[ClaimObject] = Field(default_factory=list)
    claim_facts: List[ClaimFactObject] = Field(default_factory=list)
    defense_opinions: List[DefenseObject] = Field(default_factory=list)
    counterclaims: List[CounterclaimObject] = Field(default_factory=list)
    evidence_list: List[EvidenceObject] = Field(default_factory=list)

    # 审核元数据（不进入 CaseInput）
    evidence_meta: List[EvidenceMeta] = Field(default_factory=list)

    # 可选字段
    cross_examinations: List[CrossExaminationObject] = Field(default_factory=list)
    court_records: List[str] = Field(default_factory=list)
    legal_arguments: List[LegalArgumentObject] = Field(default_factory=list)
    procedural_info: Optional[ProceduralInfo] = None
    existing_judgment_or_mediation: Optional[str] = None

    # 追溯
    original_input: str = ""


# ============================================================================
# 串联接口
# ============================================================================


class MaterialFullResult(BaseModel):
    """阶段一 + 阶段二串联输出"""

    review: MaterialReviewResult
    normalized: Optional[NormalizedCaseInput] = None
    # can_proceed=true 时 normalized 非空；false 时仅返回 review
