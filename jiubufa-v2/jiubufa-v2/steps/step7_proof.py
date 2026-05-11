"""第七步：要件事实证明。"""

from __future__ import annotations

import json
import logging

from llm import LLMClient
from prompts import STEP7_SYSTEM
from schemas import Step7Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step7")

STEP_KEY = "step7_proof"


def _build_user_prompt(state: WorkflowState) -> str:
    payload = {
        "element_matrix": (
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
        "issues": models_to_dicts(state.step6.issues) if state.step6 else [],
        "evidence_list": models_to_dicts(state.case_input.evidence_list),
        "cross_examinations": models_to_dicts(state.case_input.cross_examinations),
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
        "请围绕事实争点和关键要件，组织证明计划，明确举证责任、证据覆盖与缺口。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step7Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：step4 和 step6 都无可用数据时跳过
        has_elements = state.step4 is not None and len(state.step4.element_matrix) > 0
        has_issues = state.step6 is not None and len(state.step6.issues) > 0
        has_evidence = len(state.case_input.evidence_list) > 0
        if not has_elements and not has_issues and not has_evidence:
            output = Step7Output()
            state.step7 = output
            logger.warning("Step7：无可用要件/争点/证据，跳过证明计划")
            return output

        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(STEP7_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step7Output, result, fallback=Step7Output())
        state.step7 = output
        logger.info("Step7 完成：proof_plan 共 %d 行", len(output.proof_plan))
        return output
