"""第九步：要件归入并作出裁判。"""

from __future__ import annotations

import json
import logging

from config import ENABLE_WEB_SEARCH, WEB_SEARCH_TOP_K
from kb import format_web_laws_for_prompt, search_laws_online
from llm import LLMClient
from prompts import STEP9_SYSTEM
from schemas import Step9Output

from .context_builder import build_full_context
from .state import WorkflowState
from .utils import models_to_dicts, parse_into, time_step

logger = logging.getLogger("jiubufa.steps.step9")

STEP_KEY = "step9_subsumption"


def _build_user_prompt(state: WorkflowState, web_laws_text: str = "") -> str:
    payload = {
        "fixed_claims": models_to_dicts(state.step1.fixed_claims) if state.step1 else [],
        "request_basis_candidates": (
            models_to_dicts(state.step2.request_basis_candidates) if state.step2 else []
        ),
        "defense_basis_candidates": (
            models_to_dicts(state.step3.defense_basis_candidates) if state.step3 else []
        ),
        "element_matrix": (
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
        "fact_findings": (
            models_to_dicts(state.step8.fact_findings) if state.step8 else []
        ),
        "issues": models_to_dicts(state.step6.issues) if state.step6 else [],
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
        "请按诉讼请求逐项做要件归入：先审请求权要件→再审抗辩→适用 L5 法律效果→输出裁判结论。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    
    if web_laws_text:
        prompt_parts.append(f"\n\n{web_laws_text}")
    
    prompt_parts.append(
        "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    
    return "".join(prompt_parts)


def run(state: WorkflowState, *, llm: LLMClient) -> Step9Output:
    with time_step(state, STEP_KEY):
        # 数据依赖检查：step1 无固定诉请时无法归入
        if state.step1 is None or not state.step1.fixed_claims:
            output = Step9Output()
            state.step9 = output
            logger.warning("Step9：无固定诉请，跳过要件归入")
            return output

        # 联网搜索补充法条
        web_laws_text = ""
        if ENABLE_WEB_SEARCH:
            try:
                logger.info("Step9：开始联网搜索裁判相关法条...")
                case_causes = []
                legal_domains = []
                if state.step1 is not None:
                    case_causes = list(state.step1.case_cause_inferred or [])
                    legal_domains = list(state.step1.legal_domain_inferred or [])
                
                # 搜索裁判相关法条
                all_web_laws = []
                
                # 为每个诉请搜索
                for claim in (state.step1.fixed_claims if state.step1 else [])[:2]:
                    claim_laws = search_laws_online(
                        query_text=claim.claim_text_normalized or "",
                        case_cause="、".join(case_causes) if case_causes else None,
                        legal_domain="、".join(legal_domains) if legal_domains else None,
                        claim_type="、".join(claim.claim_type) if claim.claim_type else None,
                        top_k=WEB_SEARCH_TOP_K,
                        llm=llm,
                    )
                    all_web_laws.extend(claim_laws)
                
                if all_web_laws:
                    web_laws_text = format_web_laws_for_prompt(all_web_laws)
                    logger.info(f"Step9：联网搜索完成，获取 {len(all_web_laws)} 个法条")
            except Exception as e:
                logger.error(f"Step9：联网搜索失败：{e}")

        user_prompt = _build_user_prompt(state, web_laws_text)
        result = llm.chat_json(STEP9_SYSTEM, user_prompt, step_key=STEP_KEY)
        output = parse_into(Step9Output, result, fallback=Step9Output())
        state.step9 = output
        logger.info(
            "Step9 完成：%d 项裁判结论", len(output.subsumption_results)
        )
        return output
