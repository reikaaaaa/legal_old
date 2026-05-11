"""第八步：事实认定。"""

from __future__ import annotations

import json
import logging

from llm import LLMClient
from prompts import STEP8_SYSTEM
from schemas import Step8Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step8")

STEP_KEY = "step8_fact_finding"


def _build_user_prompt(state: WorkflowState) -> str:
    payload = {
        "proof_plan": models_to_dicts(state.step7.proof_plan) if state.step7 else [],
        "evidence_list": models_to_dicts(state.case_input.evidence_list),
        "cross_examinations": models_to_dicts(state.case_input.cross_examinations),
        "element_matrix": (
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
    }
    
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
        "请基于证据三性与证明力，对每个 element_id 给出 proved / not_proved / unknown 的认定。"
        "对真伪不明事实必须适用举证责任后果。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step8Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：proof_plan 和 element_matrix 都无数据时跳过
        has_proof = state.step7 is not None and len(state.step7.proof_plan) > 0
        has_elements = state.step4 is not None and len(state.step4.element_matrix) > 0
        has_evidence = len(state.case_input.evidence_list) > 0
        if not has_proof and not has_elements and not has_evidence:
            output = Step8Output()
            state.step8 = output
            logger.warning("Step8：无可用证明计划/要件/证据，跳过事实认定")
            return output

        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(STEP8_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step8Output, result, fallback=Step8Output())
        state.step8 = output
        logger.info("Step8 完成：%d 项事实认定", len(output.fact_findings))
        return output
