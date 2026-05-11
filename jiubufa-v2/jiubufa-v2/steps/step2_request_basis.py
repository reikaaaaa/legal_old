"""第二步：确定请求权基础规范。

工作流：
1) 用 step1 的 claim_type / case_cause / legal_domain 查标签库召回候选 rule_units
2) 把候选喂给 LLM，让它按"特别法优先""有法律效果""支持请求类型"等原则做出最终选择
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from config import ENABLE_WEB_SEARCH, KB_TOPK_REQUEST_BASIS, WEB_SEARCH_TOP_K
from kb import format_web_laws_for_prompt, search_request_basis, search_request_basis_online
from llm import LLMClient
from prompts import STEP2_SYSTEM
from schemas import Step2Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step2")

STEP_KEY = "step2_request_basis"


def _retrieve_candidates_for_claim(
    claim_types: List[str],
    case_causes: List[str],
    legal_domains: List[str],
    keyword_hints: List[str],
) -> List[Dict[str, Any]]:
    scored = search_request_basis(
        case_causes=case_causes or None,
        legal_domains=legal_domains or None,
        claim_types=claim_types or None,
        keyword_hints=keyword_hints or None,
        top_k=KB_TOPK_REQUEST_BASIS,
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
    assert state.step1 is not None, "step2 依赖 step1"
    case_causes = state.step1.case_cause_inferred or []
    if state.case_input.case_basic_info.case_cause_text:
        case_causes = list(
            dict.fromkeys(case_causes + [state.case_input.case_basic_info.case_cause_text])
        )
    legal_domains = state.step1.legal_domain_inferred

    per_claim_blocks: List[Dict[str, Any]] = []
    for claim in state.step1.fixed_claims:
        keywords: List[str] = []
        if claim.claim_text_normalized:
            keywords.append(claim.claim_text_normalized[:30])
        candidates = _retrieve_candidates_for_claim(
            claim_types=claim.claim_type,
            case_causes=case_causes,
            legal_domains=legal_domains,
            keyword_hints=keywords,
        )
        per_claim_blocks.append(
            {
                "claim_id": claim.claim_id,
                "claim_text_normalized": claim.claim_text_normalized,
                "claim_type": claim.claim_type,
                "candidate_rule_units": candidates,
            }
        )

    payload = {
        "case_causes_inferred": case_causes,
        "legal_domains_inferred": legal_domains,
        "claims_with_candidates": per_claim_blocks,
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
        "请基于以下「已固定的诉讼请求」与「已用五层标签预筛的候选规则单元」，"
        "为每项请求选择最适合的请求权基础规范。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    
    if web_laws_text:
        prompt_parts.append(f"\n\n{web_laws_text}")
    
    prompt_parts.append(
        "\n\n请严格按 system 规定的 JSON schema 输出。"
        "请优先在 candidate_rule_units 中选择；如果都不合适，输出空 candidates 并在 competition_analysis 中说明。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step2Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：step1 没有产出时跳过
        if state.step1 is None or not state.step1.fixed_claims:
            output = Step2Output()
            state.step2 = output
            logger.warning("Step2：step1 无固定诉请，跳过请求权基础检索")
            return output

        # 联网搜索补充法条
        web_laws_text = ""
        if ENABLE_WEB_SEARCH:
            try:
                logger.info("Step2：开始联网搜索请求权基础法条...")
                case_causes = state.step1.case_cause_inferred or []
                legal_domains = state.step1.legal_domain_inferred or []
                
                # 为每个诉请搜索相关法条
                all_web_laws = []
                for claim in state.step1.fixed_claims[:3]:  # 最多搜索前3个诉请
                    claim_laws = search_request_basis_online(
                        claim_text=claim.claim_text_normalized or "",
                        claim_types=claim.claim_type,
                        case_causes=case_causes,
                        legal_domains=legal_domains,
                        top_k=WEB_SEARCH_TOP_K,
                        llm=llm,
                    )
                    all_web_laws.extend(claim_laws)
                
                if all_web_laws:
                    web_laws_text = format_web_laws_for_prompt(all_web_laws)
                    logger.info(f"Step2：联网搜索完成，获取 {len(all_web_laws)} 个法条")
            except Exception as e:
                logger.error(f"Step2：联网搜索失败：{e}")

        user_prompt = _build_user_prompt(state, web_laws_text)
        result = llm.chat_json(STEP2_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step2Output, result, fallback=Step2Output())
        state.step2 = output
        logger.info(
            "Step2 完成：%d 个 request_basis_candidates",
            len(output.request_basis_candidates),
        )
        return output
