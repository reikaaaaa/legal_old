"""
法条库规则单元的结构化定义。

严格对齐《数据库标签文档.md》中的五层标签（L1~L5）。
loader 加载 articles_annotated.jsonl 后，把每个 rule_unit 反序列化为 RuleUnit。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# L1: 法源定位与案由关系层
# ---------------------------------------------------------------------------


class L1SourceCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_type: Optional[str] = None
    effective_status: Optional[str] = None
    effective_date: Optional[str] = None
    legal_domain: List[str] = Field(default_factory=list)
    case_cause_l1: List[str] = Field(default_factory=list)
    case_cause_l2: List[str] = Field(default_factory=list)
    case_cause_l3: List[str] = Field(default_factory=list)
    case_cause_l4: List[str] = Field(default_factory=list)
    special_priority: Optional[str] = None


# ---------------------------------------------------------------------------
# L2: 九步法位置与规范功能层
# ---------------------------------------------------------------------------


class L2WorkflowNorm(BaseModel):
    model_config = ConfigDict(extra="allow")

    workflow_steps: List[str] = Field(default_factory=list)
    norm_type: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# L3: 请求 / 抗辩对象层
# ---------------------------------------------------------------------------


class L3ClaimDefense(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_type: List[str] = Field(default_factory=list)
    defense_type: List[str] = Field(default_factory=list)
    right_type: Optional[str] = None
    liability_type: Optional[str] = None
    party_role: List[str] = Field(default_factory=list)
    object_type: Optional[str] = None


# ---------------------------------------------------------------------------
# L4: 构成要件与证明层
# ---------------------------------------------------------------------------


class Element(BaseModel):
    model_config = ConfigDict(extra="allow")

    element_id: str
    element_name: str
    element_description: Optional[str] = None
    element_type: Optional[str] = None
    element_logic: Optional[str] = None  # AND / OR / NOT
    is_hidden_element: bool = False
    negative_element: bool = False
    exception_element: bool = False
    fact_slot: Optional[str] = None
    burden_party: Optional[str] = None
    proof_standard: Optional[str] = None
    suggested_evidence_types: List[str] = Field(default_factory=list)
    fact_finding_note: Optional[str] = None


class L4ElementsProof(BaseModel):
    model_config = ConfigDict(extra="allow")

    elements: List[Element] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# L5: 法律效果与裁判输出层
# ---------------------------------------------------------------------------


class L5EffectJudgment(BaseModel):
    model_config = ConfigDict(extra="allow")

    legal_effect_tags: List[str] = Field(default_factory=list)
    legal_effect_text: Optional[str] = None
    disposition_type: List[str] = Field(default_factory=list)
    effect_if_satisfied: Optional[str] = None
    effect_if_not_satisfied: Optional[str] = None
    effect_if_unknown: Optional[str] = None
    calculation_formula: Optional[str] = None
    adjustment_rule: Optional[str] = None


# ---------------------------------------------------------------------------
# 规则单元（最小检索单位）
# ---------------------------------------------------------------------------


class RuleUnit(BaseModel):
    """法条库的最小检索单位。一个法条可能拆出多个 rule_unit。"""

    model_config = ConfigDict(extra="allow")

    rule_unit_id: str
    rule_unit_text: str
    # 在父法条层冗余下来，方便检索结果直接展示：
    law_name: Optional[str] = None
    article_no: Optional[str] = None

    L1_source_case: L1SourceCase = Field(default_factory=L1SourceCase)
    L2_workflow_norm: L2WorkflowNorm = Field(default_factory=L2WorkflowNorm)
    L3_claim_defense: L3ClaimDefense = Field(default_factory=L3ClaimDefense)
    L4_elements_proof: L4ElementsProof = Field(default_factory=L4ElementsProof)
    L5_effect_judgment: L5EffectJudgment = Field(default_factory=L5EffectJudgment)

    def to_brief(self) -> Dict[str, Any]:
        """生成一个紧凑表示，用于喂给 LLM 减少 token 消耗。"""
        return {
            "rule_unit_id": self.rule_unit_id,
            "law_name": self.law_name,
            "article_no": self.article_no,
            "rule_unit_text": self.rule_unit_text,
            "norm_type": self.L2_workflow_norm.norm_type,
            "workflow_steps": self.L2_workflow_norm.workflow_steps,
            "claim_type": self.L3_claim_defense.claim_type,
            "defense_type": self.L3_claim_defense.defense_type,
            "right_type": self.L3_claim_defense.right_type,
            "liability_type": self.L3_claim_defense.liability_type,
            "elements": [
                {
                    "element_id": e.element_id,
                    "element_name": e.element_name,
                    "element_type": e.element_type,
                    "is_hidden_element": e.is_hidden_element,
                    "negative_element": e.negative_element,
                    "exception_element": e.exception_element,
                    "burden_party": e.burden_party,
                    "suggested_evidence_types": e.suggested_evidence_types,
                }
                for e in self.L4_elements_proof.elements
            ],
            "legal_effect_tags": self.L5_effect_judgment.legal_effect_tags,
            "disposition_type": self.L5_effect_judgment.disposition_type,
            "effect_if_satisfied": self.L5_effect_judgment.effect_if_satisfied,
            "effect_if_not_satisfied": self.L5_effect_judgment.effect_if_not_satisfied,
            "effect_if_unknown": self.L5_effect_judgment.effect_if_unknown,
        }


# ---------------------------------------------------------------------------
# 规则单元引用（在中间产物中替代完整对象，节省 token）
# ---------------------------------------------------------------------------


class RuleUnitRef(BaseModel):
    rule_unit_id: str
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    rule_unit_text: Optional[str] = None
    norm_type: List[str] = Field(default_factory=list)
    claim_type: List[str] = Field(default_factory=list)
    defense_type: List[str] = Field(default_factory=list)
    legal_effect_tags: List[str] = Field(default_factory=list)
