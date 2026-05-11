"""
法条库加载器。

从 articles_annotated.jsonl 读取数据，扁平化为 RuleUnit 列表并构建索引。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from pydantic import ValidationError

from config import resolve_kb_path
from schemas.kb import RuleUnit

logger = logging.getLogger("jiubufa.kb.loader")


class KnowledgeBase:
    """已加载到内存的法条库。"""

    def __init__(self, rule_units: List[RuleUnit]) -> None:
        self.rule_units: List[RuleUnit] = rule_units
        self._by_id: Dict[str, RuleUnit] = {ru.rule_unit_id: ru for ru in rule_units}

        # 倒排索引（用于快速过滤 + 召回）
        self._idx_workflow_step: Dict[str, Set[str]] = defaultdict(set)
        self._idx_norm_type: Dict[str, Set[str]] = defaultdict(set)
        self._idx_claim_type: Dict[str, Set[str]] = defaultdict(set)
        self._idx_defense_type: Dict[str, Set[str]] = defaultdict(set)
        self._idx_legal_domain: Dict[str, Set[str]] = defaultdict(set)
        self._idx_case_cause: Dict[str, Set[str]] = defaultdict(set)
        self._idx_effective: Dict[str, Set[str]] = defaultdict(set)

        for ru in rule_units:
            for v in ru.L2_workflow_norm.workflow_steps:
                self._idx_workflow_step[v].add(ru.rule_unit_id)
            for v in ru.L2_workflow_norm.norm_type:
                self._idx_norm_type[v].add(ru.rule_unit_id)
            for v in ru.L3_claim_defense.claim_type:
                self._idx_claim_type[v].add(ru.rule_unit_id)
            for v in ru.L3_claim_defense.defense_type:
                self._idx_defense_type[v].add(ru.rule_unit_id)
            for v in ru.L1_source_case.legal_domain:
                self._idx_legal_domain[v].add(ru.rule_unit_id)
            for cause_field in (
                ru.L1_source_case.case_cause_l1,
                ru.L1_source_case.case_cause_l2,
                ru.L1_source_case.case_cause_l3,
                ru.L1_source_case.case_cause_l4,
            ):
                for v in cause_field:
                    self._idx_case_cause[v].add(ru.rule_unit_id)
            if ru.L1_source_case.effective_status:
                self._idx_effective[ru.L1_source_case.effective_status].add(
                    ru.rule_unit_id
                )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, rule_unit_id: str) -> Optional[RuleUnit]:
        return self._by_id.get(rule_unit_id)

    def by_workflow_step(self, step: str) -> Set[str]:
        return self._idx_workflow_step.get(step, set())

    def by_norm_type(self, norm_type: str) -> Set[str]:
        return self._idx_norm_type.get(norm_type, set())

    def by_claim_type(self, claim_type: str) -> Set[str]:
        return self._idx_claim_type.get(claim_type, set())

    def by_defense_type(self, defense_type: str) -> Set[str]:
        return self._idx_defense_type.get(defense_type, set())

    def by_legal_domain(self, domain: str) -> Set[str]:
        return self._idx_legal_domain.get(domain, set())

    def by_case_cause(self, cause: str) -> Set[str]:
        return self._idx_case_cause.get(cause, set())

    def effective_ids(self) -> Set[str]:
        """所有现行有效的 rule_unit_id 集合。"""
        return self._idx_effective.get("现行有效", set())

    def __len__(self) -> int:
        return len(self.rule_units)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("跳过 %s 第 %d 行：JSON 解析失败：%s", path, line_no, exc)
                continue


def load_knowledge_base(path: Optional[Path] = None) -> KnowledgeBase:
    """加载并构建法条库。"""

    kb_path = path or resolve_kb_path()
    kb_path = Path(kb_path)
    if not kb_path.exists():
        logger.warning(
            "法条库文件不存在：%s。返回空 KB。请将 articles_annotated.jsonl 放到该路径。",
            kb_path,
        )
        return KnowledgeBase([])

    rule_units: List[RuleUnit] = []
    skipped_articles = 0
    bad_units = 0

    for article in _iter_jsonl(kb_path):
        annotation = article.get("annotation") or {}
        units = annotation.get("rule_units") or []
        if not isinstance(units, list):
            skipped_articles += 1
            continue
        for unit in units:
            # 父法条信息冗余进入 rule_unit
            if "law_name" not in unit:
                unit["law_name"] = article.get("law_name")
            if "article_no" not in unit:
                unit["article_no"] = article.get("article_no")
            try:
                ru = RuleUnit.model_validate(unit)
                rule_units.append(ru)
            except ValidationError as exc:
                bad_units += 1
                logger.debug(
                    "rule_unit 校验失败：%s | err=%s",
                    unit.get("rule_unit_id"),
                    exc.errors()[:1],
                )
                continue

    logger.info(
        "法条库加载完成：%d 条 rule_unit（来源：%s；跳过文章 %d，无效单元 %d）",
        len(rule_units),
        kb_path,
        skipped_articles,
        bad_units,
    )
    return KnowledgeBase(rule_units)


# 模块级单例
_default_kb: Optional[KnowledgeBase] = None


def get_default_kb() -> KnowledgeBase:
    global _default_kb
    if _default_kb is None:
        _default_kb = load_knowledge_base()
    return _default_kb


def reset_default_kb() -> None:
    """测试时手动重置。"""
    global _default_kb
    _default_kb = None
