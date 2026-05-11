"""第一步：固定权利请求。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from llm import LLMClient
from prompts import STEP1_SYSTEM
from schemas import Step1Output

from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step1")

STEP_KEY = "step1_claim_fixing"


def _build_user_prompt(state: WorkflowState) -> str:
    case = state.case_input
    payload: Dict[str, Any] = {
        "case_basic_info": case.case_basic_info.model_dump(exclude_none=True),
        "party_info": models_to_dicts(case.party_info),
        "claims": models_to_dicts(case.claims),
        "claim_facts_brief": [
            {
                "fact_id": f.fact_id,
                "fact_text": f.fact_text_normalized or f.fact_text_original,
            }
            for f in case.claim_facts
        ],
        "legal_arguments": [
            {
                "argument_id": la.argument_id,
                "submitted_by": la.submitted_by,
                "cited_law_name": la.cited_law_name,
                "cited_article_no": la.cited_article_no,
            }
            for la in case.legal_arguments
        ],
    }
    import json as _json

    return (
        "请基于以下案件输入材料执行第一步：固定权利请求。"
        "严格只用我提供的诉讼请求与事实，不要凭空补充其他请求。\n\n"
        "【案件输入】\n"
        + _json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请按 system 中规定的 JSON schema 输出。"
    )


def run(state: WorkflowState, *, llm: LLMClient) -> Step1Output:
    """执行第一步，写回 state.step1 并返回。"""
    with time_step(state, STEP_KEY):
        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(
            STEP1_SYSTEM, user_prompt, step_key=STEP_KEY
        )
        output = parse_into(Step1Output, result, fallback=Step1Output())
        state.step1 = output
        logger.info("Step1 完成：%d 项 fixed_claims", len(output.fixed_claims))
        return output
