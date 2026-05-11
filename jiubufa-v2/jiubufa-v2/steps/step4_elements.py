"""第四步：拆解构成要件。

为节省 token，先把第二步、第三步选定的 rule_unit 的 L4 elements 直接抽出来，
再让 LLM 做"补隐含要件 + 标注 used_for/target_id + 整理"的工作。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from kb import get_default_kb
from llm import LLMClient
from prompts import STEP4_SYSTEM
from schemas import Step4Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step4")

STEP_KEY = "step4_element_analysis"


def _extract_elements_for_rule_unit(rule_unit_id: str) -> List[Dict[str, Any]]:
    kb = get_default_kb()
    ru = kb.get(rule_unit_id)
    if ru is None:
        return []
    return [e.model_dump(exclude_none=False) for e in ru.L4_elements_proof.elements]


def _build_user_prompt(state: WorkflowState) -> str:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    all_elements_empty = True

    # 请求权基础
    if state.step2 is not None:
        for c in state.step2.request_basis_candidates:
            rid = c.rule_unit_ref.rule_unit_id
            key = f"req::{c.claim_id}::{rid}"
            if key in seen:
                continue
            seen.add(key)
            kb_elements = _extract_elements_for_rule_unit(rid)
            if kb_elements:
                all_elements_empty = False
            items.append(
                {
                    "used_for": "request_basis",
                    "target_id": c.claim_id,
                    "rule_unit_id": rid,
                    "law_name": c.rule_unit_ref.law_name,
                    "article_no": c.rule_unit_ref.article_no,
                    "rule_unit_text": c.rule_unit_ref.rule_unit_text,
                    "elements_from_kb": kb_elements,
                }
            )

    # 抗辩权基础
    if state.step3 is not None:
        for d in state.step3.defense_basis_candidates:
            if d.rule_unit_ref is None:
                continue
            rid = d.rule_unit_ref.rule_unit_id
            key = f"def::{d.defense_id}::{rid}"
            if key in seen:
                continue
            seen.add(key)
            kb_elements = _extract_elements_for_rule_unit(rid)
            if kb_elements:
                all_elements_empty = False
            items.append(
                {
                    "used_for": "defense_basis",
                    "target_id": d.defense_id,
                    "rule_unit_id": rid,
                    "law_name": d.rule_unit_ref.law_name,
                    "article_no": d.rule_unit_ref.article_no,
                    "rule_unit_text": d.rule_unit_ref.rule_unit_text,
                    "elements_from_kb": kb_elements,
                }
            )

    # 构建上下文：当 items 为空或全部 elements_from_kb 为空时，用诉请+法条文本兜底
    fallback_context = ""
    if not items or all_elements_empty:
        fixed_claims = (
            [c.model_dump(exclude_none=False) for c in state.step1.fixed_claims]
            if state.step1 and state.step1.fixed_claims
            else []
        )
        req_basis_texts = []
        if state.step2:
            for c in state.step2.request_basis_candidates:
                req_basis_texts.append(
                    f"{c.rule_unit_ref.law_name} {c.rule_unit_ref.article_no}: {c.rule_unit_ref.rule_unit_text}"
                )
        def_basis_texts = []
        if state.step3:
            for d in state.step3.defense_basis_candidates:
                if d.rule_unit_ref:
                    def_basis_texts.append(
                        f"{d.rule_unit_ref.law_name} {d.rule_unit_ref.article_no}: {d.rule_unit_ref.rule_unit_text}"
                    )
        fallback_context = (
            "\n【补充上下文】\n"
            "标签库中这些规则单元的 L4 构成要件标注不完整。"
            "请基于你的法律知识，为以下诉请和法条拆解构成要件：\n\n"
            f"## 固定诉请\n{json.dumps(fixed_claims, ensure_ascii=False, indent=2)}\n\n"
            f"## 请求权基础法条\n{json.dumps(req_basis_texts, ensure_ascii=False, indent=2) if req_basis_texts else '（无）'}\n\n"
            f"## 抗辩基础法条\n{json.dumps(def_basis_texts, ensure_ascii=False, indent=2) if def_basis_texts else '（无）'}\n\n"
            "请为每项诉请/抗辩创建对应的 ElementMatrixRow，"
            "从法条文本中抽取要件名称(elements_name)，标注 element_type、burden_party、proof_standard、suggested_evidence_types。"
        )

    payload = {"items": items}
    
    # 构建完整上下文
    full_context = build_full_context(
        state,
        current_step=STEP_KEY,
        include_original_case=True,
        include_previous_steps=True,
    )
    
    # 拼接 prompt
    prompt_parts = []
    
    if full_context:
        prompt_parts.append(full_context)
        prompt_parts.append("\n" + "="*80 + "\n")
    
    prompt_parts.append(
        "下面每个 item 包含一条规则单元（请求权基础或抗辩权基础）以及其 L4 标签库中的 elements。"
        "请把这些 elements 展开到 element_matrix；"
        "对 elements_from_kb 为空或缺失关键要件的项，请补充必要的隐含要件并把 is_hidden_element 设为 true。"
        + fallback_context + "\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step4Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：step2 和 step3 都没有可用候选时跳过
        has_req = (
            state.step2 is not None
            and len(state.step2.request_basis_candidates) > 0
        )
        has_def = (
            state.step3 is not None
            and len(state.step3.defense_basis_candidates) > 0
        )
        if not has_req and not has_def:
            output = Step4Output()
            state.step4 = output
            logger.warning("Step4：step2/step3 均无候选规则单元，跳过要件拆解")
            return output

        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(STEP4_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step4Output, result, fallback=Step4Output())
        state.step4 = output
        logger.info(
            "Step4 完成：element_matrix 共 %d 行", len(output.element_matrix)
        )
        return output
