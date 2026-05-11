"""
案件输入材料的标准对象定义。

对应 Jiubufa_Workflow_Design_V3_GPT.md 第 3 节的输入材料规范。
所有字段尽量使用 Optional + 默认值，以便容忍部分材料缺失。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 案件基本信息
# ---------------------------------------------------------------------------


class CaseBasicInfo(BaseModel):
    case_id: Optional[str] = None
    case_name: Optional[str] = None
    case_cause_text: Optional[str] = None
    court: Optional[str] = None
    procedure_stage: Optional[str] = None  # 一审 / 二审 / 再审 / 执行异议 / 程序性审查
    filing_date: Optional[str] = None
    material_sources: List[str] = Field(default_factory=list)
    case_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# 当事人
# ---------------------------------------------------------------------------


class PartyInfo(BaseModel):
    party_id: str
    party_name: Optional[str] = None
    party_role: Optional[str] = None  # 原告 / 被告 / 第三人 / 申请人 / 被申请人
    legal_status: Optional[str] = None  # 自然人 / 法人 / 非法人组织
    relationship_to_case: Optional[str] = None
    identity_evidence: List[str] = Field(default_factory=list)
    standing_issue: bool = False


# ---------------------------------------------------------------------------
# 诉讼请求
# ---------------------------------------------------------------------------


class ClaimObject(BaseModel):
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
    priority_type: Optional[str] = None  # primary / alternative / parallel / selective


# ---------------------------------------------------------------------------
# 事实主张
# ---------------------------------------------------------------------------


class ClaimFactObject(BaseModel):
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
    clarity_status: Optional[str] = None  # 明确 / 模糊 / 矛盾 / 遗漏
    opponent_response: Optional[str] = None  # 承认 / 否认 / 不明确 / 抗辩


# ---------------------------------------------------------------------------
# 答辩 / 抗辩
# ---------------------------------------------------------------------------


class DefenseObject(BaseModel):
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


# ---------------------------------------------------------------------------
# 反诉
# ---------------------------------------------------------------------------


class CounterclaimObject(BaseModel):
    counterclaim_id: str
    counterclaim_text: str
    counterclaim_type_candidate: List[str] = Field(default_factory=list)
    linked_evidence_ids: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 证据
# ---------------------------------------------------------------------------


class EvidenceObject(BaseModel):
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
    probative_force: Optional[str] = None  # 强 / 中 / 弱 / 不采信
    adopted_status: Optional[str] = None  # 采信 / 不采信 / 部分采信 / 待补充


# ---------------------------------------------------------------------------
# 质证意见
# ---------------------------------------------------------------------------


class CrossExaminationObject(BaseModel):
    cross_id: str
    evidence_id: str
    opponent: Optional[str] = None
    legality_opinion: Optional[str] = None
    relevance_opinion: Optional[str] = None
    authenticity_opinion: Optional[str] = None
    probative_force_opinion: Optional[str] = None
    reason: Optional[str] = None
    need_supplementary_proof: bool = False


# ---------------------------------------------------------------------------
# 法律意见
# ---------------------------------------------------------------------------


class LegalArgumentObject(BaseModel):
    argument_id: str
    submitted_by: Optional[str] = None
    target_claim_or_defense: Optional[str] = None
    cited_law_name: Optional[str] = None
    cited_article_no: Optional[str] = None
    argument_text: Optional[str] = None
    norm_type_candidate: List[str] = Field(default_factory=list)
    dispute_status: Optional[str] = None
    court_view_needed: bool = False


# ---------------------------------------------------------------------------
# 程序事项
# ---------------------------------------------------------------------------


class ProceduralInfo(BaseModel):
    jurisdiction: Optional[str] = None
    limitation_period_status: Optional[str] = None
    proof_period_status: Optional[str] = None
    other_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 顶层案件输入
# ---------------------------------------------------------------------------


class CaseInput(BaseModel):
    """工作流的顶层输入对象。"""

    case_basic_info: CaseBasicInfo = Field(default_factory=CaseBasicInfo)
    party_info: List[PartyInfo] = Field(default_factory=list)
    claims: List[ClaimObject] = Field(default_factory=list)
    claim_facts: List[ClaimFactObject] = Field(default_factory=list)
    defense_opinions: List[DefenseObject] = Field(default_factory=list)
    counterclaims: List[CounterclaimObject] = Field(default_factory=list)
    evidence_list: List[EvidenceObject] = Field(default_factory=list)
    cross_examinations: List[CrossExaminationObject] = Field(default_factory=list)
    court_records: List[str] = Field(default_factory=list)  # 庭审笔录原文段落
    legal_arguments: List[LegalArgumentObject] = Field(default_factory=list)
    procedural_info: Optional[ProceduralInfo] = None
    existing_judgment_or_mediation: Optional[str] = None

    # 工作流执行选项
    fallback_user_choice: Optional[str] = None
    """保底裁判机制下用户的选择：
       supplement / continue_weak_judgment / partial_output_only。
       未设置时若触发保底门，编排器会终止并返回 fallback_gate。"""
