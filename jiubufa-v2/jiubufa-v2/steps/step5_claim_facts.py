"""第五步：诉讼主张检索。

把当事人事实主张与 element_matrix 中的要件做覆盖比对。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from llm import LLMClient
from prompts import STEP5_SYSTEM
from schemas import Step5Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step5")

STEP_KEY = "step5_claim_fact_search"


def _build_user_prompt(state: WorkflowState) -> str:
    payload: Dict[str, Any] = {
        "element_matrix": (
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
        "claim_facts": models_to_dicts(state.case_input.claim_facts),
        "defense_opinions": models_to_dicts(state.case_input.defense_opinions),
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
        "请把当事人事实主张映射到要件矩阵的每一行，判断主张状态。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step5Output:
    with time_step(state, STEP_KEY):
        if state.step4 is None or not state.step4.element_matrix:
            output = Step5Output()
            state.step5 = output
            logger.info("Step5：element_matrix 为空，跳过")
            return output

        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(STEP5_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step5Output, result, fallback=Step5Output())
        state.step5 = output
        logger.info(
            "Step5 完成：claim_fact_mapping 共 %d 行",
            len(output.claim_fact_mapping),
        )
        return output
