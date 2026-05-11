"""
五层标签检索器。

核心：根据当前九步法节点 + 案由 + 请求/抗辩类型 + 法律领域，
对法条库做加权打分召回，返回 top-k 个 RuleUnit。

打分维度（可调）：
- L2.workflow_steps 命中：硬性过滤 + 1 分
- L2.norm_type 命中：每命中一个 +3
- L3.claim_type 命中：每命中一个 +5
- L3.defense_type 命中：每命中一个 +5
- L1.case_cause_l3 / l2 / l1 命中：3 / 2 / 1 分
- L1.legal_domain 命中：+2
- effective_status == "现行有效"：必要条件
- L1.special_priority == "特别规则"：+1（特别法优先）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from schemas.kb import RuleUnit

from .loader import KnowledgeBase, get_default_kb

logger = logging.getLogger("jiubufa.kb.retriever")


# ---------------------------------------------------------------------------
# 查询参数
# ---------------------------------------------------------------------------


@dataclass
class RetrievalQuery:
    workflow_step: str
    norm_types: List[str] | None = None  # 期望的规范功能
    claim_types: List[str] | None = None
    defense_types: List[str] | None = None
    case_causes: List[str] | None = None  # 任意级别都行
    legal_domains: List[str] | None = None
    require_effective: bool = True
    must_norm_type: List[str] | None = None  # 必须命中其中之一（硬过滤）
    keyword_hints: List[str] | None = None  # 文本兜底匹配


@dataclass
class ScoredRuleUnit:
    rule_unit: RuleUnit
    score: float
    matched_dimensions: Dict[str, List[str]]


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------


class Retriever:
    def __init__(self, kb: Optional[KnowledgeBase] = None) -> None:
        self.kb = kb or get_default_kb()

    def search(self, query: RetrievalQuery, top_k: int = 10) -> List[ScoredRuleUnit]:
        if len(self.kb) == 0:
            logger.warning("法条库为空，检索返回空结果。")
            return []

        # 1) 候选集合：用 workflow_step 做第一道硬过滤
        candidate_ids: Set[str] = self.kb.by_workflow_step(query.workflow_step)
        if not candidate_ids:
            # 法条库里如果没有该 step 标注，退化为遍历全库（小库可承受）
            candidate_ids = {ru.rule_unit_id for ru in self.kb.rule_units}

        # 2) 现行有效过滤
        if query.require_effective:
            effective = self.kb.effective_ids()
            if effective:
                candidate_ids = candidate_ids & effective

        # 3) must_norm_type 硬过滤（如必须是 request_basis）
        if query.must_norm_type:
            must_set: Set[str] = set()
            for nt in query.must_norm_type:
                must_set |= self.kb.by_norm_type(nt)
            if must_set:
                candidate_ids = candidate_ids & must_set

        # 4) 打分
        scored: List[ScoredRuleUnit] = []
        for rid in candidate_ids:
            ru = self.kb.get(rid)
            if ru is None:
                continue
            score, matches = self._score(ru, query)
            if score <= 0:
                continue
            scored.append(ScoredRuleUnit(rule_unit=ru, score=score, matched_dimensions=matches))

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # 打分
    # ------------------------------------------------------------------

    def _score(
        self, ru: RuleUnit, q: RetrievalQuery
    ) -> tuple[float, Dict[str, List[str]]]:
        score = 0.0
        matches: Dict[str, List[str]] = {}

        # workflow_step 命中（已过滤一次，这里给基础分）
        if q.workflow_step in ru.L2_workflow_norm.workflow_steps:
            score += 1.0
            matches.setdefault("workflow_step", []).append(q.workflow_step)

        # norm_type
        if q.norm_types:
            hits = [nt for nt in q.norm_types if nt in ru.L2_workflow_norm.norm_type]
            if hits:
                score += 3.0 * len(hits)
                matches["norm_type"] = hits

        # claim_type
        if q.claim_types:
            hits = [ct for ct in q.claim_types if ct in ru.L3_claim_defense.claim_type]
            if hits:
                score += 5.0 * len(hits)
                matches["claim_type"] = hits

        # defense_type
        if q.defense_types:
            hits = [
                dt for dt in q.defense_types if dt in ru.L3_claim_defense.defense_type
            ]
            if hits:
                score += 5.0 * len(hits)
                matches["defense_type"] = hits

        # case_cause（按 l3 > l2 > l1 加权）
        if q.case_causes:
            cc_l1 = ru.L1_source_case.case_cause_l1
            cc_l2 = ru.L1_source_case.case_cause_l2
            cc_l3 = ru.L1_source_case.case_cause_l3
            cc_l4 = ru.L1_source_case.case_cause_l4
            l1_hits = [c for c in q.case_causes if c in cc_l1]
            l2_hits = [c for c in q.case_causes if c in cc_l2]
            l3_hits = [c for c in q.case_causes if c in cc_l3]
            l4_hits = [c for c in q.case_causes if c in cc_l4]
            if l1_hits:
                score += 1.0 * len(l1_hits)
            if l2_hits:
                score += 2.0 * len(l2_hits)
            if l3_hits:
                score += 3.0 * len(l3_hits)
            if l4_hits:
                score += 4.0 * len(l4_hits)
            all_hits = l1_hits + l2_hits + l3_hits + l4_hits
            if all_hits:
                matches["case_cause"] = all_hits

        # legal_domain
        if q.legal_domains:
            hits = [d for d in q.legal_domains if d in ru.L1_source_case.legal_domain]
            if hits:
                score += 2.0 * len(hits)
                matches["legal_domain"] = hits

        # 特别法优先
        if ru.L1_source_case.special_priority == "特别规则":
            score += 1.0

        # 关键词兜底（法条文本包含）
        if q.keyword_hints:
            text = ru.rule_unit_text or ""
            kw_hits = [kw for kw in q.keyword_hints if kw and kw in text]
            if kw_hits:
                score += 0.5 * len(kw_hits)
                matches["keyword_hints"] = kw_hits

        return score, matches


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def search_request_basis(
    *,
    case_causes: List[str] | None = None,
    legal_domains: List[str] | None = None,
    claim_types: List[str] | None = None,
    keyword_hints: List[str] | None = None,
    top_k: int = 12,
) -> List[ScoredRuleUnit]:
    """检索请求权基础规则单元（第二步常用）。"""
    return Retriever().search(
        RetrievalQuery(
            workflow_step="step2_request_basis",
            norm_types=["request_basis", "formation_right_basis", "liability_rule"],
            must_norm_type=["request_basis", "formation_right_basis", "liability_rule"],
            claim_types=claim_types,
            case_causes=case_causes,
            legal_domains=legal_domains,
            keyword_hints=keyword_hints,
        ),
        top_k=top_k,
    )


def search_defense_basis(
    *,
    case_causes: List[str] | None = None,
    legal_domains: List[str] | None = None,
    defense_types: List[str] | None = None,
    keyword_hints: List[str] | None = None,
    top_k: int = 10,
) -> List[ScoredRuleUnit]:
    """检索抗辩权基础规则单元（第三步常用）。"""
    return Retriever().search(
        RetrievalQuery(
            workflow_step="step3_defense_basis",
            norm_types=[
                "defense_basis",
                "exemption_rule",
                "exception_rule",
                "procedure_rule",
            ],
            must_norm_type=[
                "defense_basis",
                "exemption_rule",
                "exception_rule",
                "procedure_rule",
            ],
            defense_types=defense_types,
            case_causes=case_causes,
            legal_domains=legal_domains,
            keyword_hints=keyword_hints,
        ),
        top_k=top_k,
    )
