"""第六步：争点整理。"""

from __future__ import annotations

import json
import logging

from llm import LLMClient
from prompts import STEP6_SYSTEM
from schemas import Step6Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step6")

STEP_KEY = "step6_issue_organize"


def _build_user_prompt(state: WorkflowState) -> str:
    payload = {
        "element_matrix": (
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
        "claim_fact_mapping": (
            models_to_dicts(state.step5.claim_fact_mapping) if state.step5 else []
        ),
        "defense_opinions": models_to_dicts(state.case_input.defense_opinions),
        "evidence_brief": [
            {
                "evidence_id": e.evidence_id,
                "evidence_type": e.evidence_type,
                "submitted_by": e.submitted_by,
                "proof_purpose": e.proof_purpose_normalized or e.proof_purpose_original,
                "linked_element_ids": e.linked_element_ids,
                "opponent_cross_examination": e.opponent_cross_examination,
            }
            for e in state.case_input.evidence_list
        ],
        "legal_arguments": models_to_dicts(state.case_input.legal_arguments),
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
        "请基于要件矩阵、要件覆盖结果、答辩与质证概况整理争点。注意控制颗粒度。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step6Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：step4 无要件矩阵且无诉请事实时跳过
        has_elements = state.step4 is not None and len(state.step4.element_matrix) > 0
        has_claims = (
            state.step1 is not None and len(state.step1.fixed_claims) > 0
        )
        if not has_elements and not has_claims:
            output = Step6Output()
            state.step6 = output
            logger.warning("Step6：无可用的要件矩阵或固定诉请，跳过争点整理")
            return output

        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(STEP6_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step6Output, result, fallback=Step6Output())
        state.step6 = output
        logger.info("Step6 完成：%d 个争点", len(output.issues))
        return output
