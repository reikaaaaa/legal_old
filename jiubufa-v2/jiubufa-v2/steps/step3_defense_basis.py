"""第三步：确定抗辩权基础规范。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from config import ENABLE_WEB_SEARCH, KB_TOPK_DEFENSE_BASIS, WEB_SEARCH_TOP_K
from kb import format_web_laws_for_prompt, search_defense_basis, search_defense_basis_online
from llm import LLMClient
from prompts import STEP3_SYSTEM
from schemas import Step3Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step3")

STEP_KEY = "step3_defense_basis"


def _retrieve_candidates(
    defense_types: List[str],
    case_causes: List[str],
    legal_domains: List[str],
    keyword_hints: List[str],
) -> List[Dict[str, Any]]:
    scored = search_defense_basis(
        defense_types=defense_types or None,
        case_causes=case_causes or None,
        legal_domains=legal_domains or None,
        keyword_hints=keyword_hints or None,
        top_k=KB_TOPK_DEFENSE_BASIS,
    )
    return [
        {
            "score": round(s.score, 2),
            "matched": s.matched_dimensions,
            **s.rule_unit.to_brief(),
        }
        for s in scored
    ]


def _build_user_prompt(state: WorkflowState, web_laws_text: str = "") -> str:
    case_causes: List[str] = []
    legal_domains: List[str] = []
    if state.step1 is not None:
        case_causes = list(state.step1.case_cause_inferred)
        legal_domains = list(state.step1.legal_domain_inferred)
    if state.case_input.case_basic_info.case_cause_text:
        case_causes.append(state.case_input.case_basic_info.case_cause_text)
        case_causes = list(dict.fromkeys(case_causes))

    # 把所有 defense_opinions 的候选 defense_type 合并去重，做一次大检索
    all_defense_types = list(
        {
            t
            for d in state.case_input.defense_opinions
            for t in d.defense_type_candidate
        }
    )
    keywords = [
        (d.defense_text_normalized or d.defense_text_original or "")[:30]
        for d in state.case_input.defense_opinions
    ]
    candidates = _retrieve_candidates(
        defense_types=all_defense_types,
        case_causes=case_causes,
        legal_domains=legal_domains,
        keyword_hints=[k for k in keywords if k],
    )

    payload = {
        "fixed_claims": models_to_dicts(state.step1.fixed_claims) if state.step1 else [],
        "request_basis_candidates": (
            models_to_dicts(state.step2.request_basis_candidates) if state.step2 else []
        ),
        "defense_opinions": models_to_dicts(state.case_input.defense_opinions),
        "candidate_rule_units": candidates,
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
        "请基于以下被告答辩与候选抗辩规则单元，识别承认/否认/抗辩，并为真正抗辩选定基础规范。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    
    if web_laws_text:
        prompt_parts.append(f"\n\n{web_laws_text}")
    
    prompt_parts.append(
        "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step3Output:
    with time_step(state, STEP_KEY):
        # 即使没有任何 defense_opinions 也跑：返回空数组
        if not state.case_input.defense_opinions:
            output = Step3Output()
            state.step3 = output
            logger.info("Step3：无答辩输入，跳过实质处理")
            return output

        # 联网搜索补充法条
        web_laws_text = ""
        if ENABLE_WEB_SEARCH:
            try:
                logger.info("Step3：开始联网搜索抗辩权基础法条...")
                case_causes: List[str] = []
                legal_domains: List[str] = []
                if state.step1 is not None:
                    case_causes = list(state.step1.case_cause_inferred)
                    legal_domains = list(state.step1.legal_domain_inferred)
                
                # 为每个答辩意见搜索相关法条
                all_web_laws = []
                for defense in state.case_input.defense_opinions[:3]:  # 最多搜索前3个答辩
                    defense_laws = search_defense_basis_online(
                        defense_text=defense.defense_text_normalized or defense.defense_text_original or "",
                        defense_types=defense.defense_type_candidate,
                        case_causes=case_causes,
                        legal_domains=legal_domains,
                        top_k=WEB_SEARCH_TOP_K,
                        llm=llm,
                    )
                    all_web_laws.extend(defense_laws)
                
                if all_web_laws:
                    web_laws_text = format_web_laws_for_prompt(all_web_laws)
                    logger.info(f"Step3：联网搜索完成，获取 {len(all_web_laws)} 个法条")
            except Exception as e:
                logger.error(f"Step3：联网搜索失败：{e}")

        user_prompt = _build_user_prompt(state, web_laws_text)
        result = llm.chat_json(STEP3_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step3Output, result, fallback=Step3Output())
        state.step3 = output
        logger.info(
            "Step3 完成：%d 个 defense_basis_candidates",
            len(output.defense_basis_candidates),
        )
        return output
