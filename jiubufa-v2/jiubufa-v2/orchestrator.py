"""
九步法工作流编排器（orchestrator）。

职责：
1. 接收 `CaseInput`，按 step1→step8 顺序串行执行；
2. 在 step8 之后、step9 之前进行硬性拦截检查 + 充足度评分 + 用户选择门构造；
3. 根据评分等级与用户选择分支：
   - hard_block / score<40 / 用户选择 supplement → status=blocked，不输出裁判倾向；
   - 弱裁判（用户选择 continue_weak_judgment）→ 调用 LLM 走弱裁判通道；
   - 部分输出（用户选择 partial_output_only）→ 仅输出要件、争点、缺口；
   - 中风险且用户选择 proceed_with_risk_notes → 继续 step9，附风险提示；
   - 强裁判（评分≥80 或用户显式选 proceed_with_risk_notes）→ 跑 step9，构造裁判文书框架；
4. 任何步骤抛出异常都写入 `state.errors` 并尽力推进后续步骤，不会让整个工作流崩溃；
5. 评分为 medium 但 `case_input.fallback_user_choice` 为空时，返回 `awaiting_user_choice`，
   由前端 / API 调用方接收 fallback_gate 后再回传一次带 user_choice 的请求。

使用方式：
    from orchestrator import run_workflow
    result = run_workflow(case_input)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fallback import (
    build_fallback_gate,
    check_hard_block,
    generate_partial_output,
    generate_weak_judgment,
    score_sufficiency,
)
from kb import get_default_kb
from llm import LLMClient, get_default_client
from schemas import (
    CaseInput,
    FallbackGate,
    StrongJudgmentOutput,
    SubsumptionResult,
    SufficiencyScore,
    WorkflowResult,
)
from steps import (
    WorkflowState,
    step1_fix_claims,
    step2_request_basis,
    step3_defense_basis,
    step4_elements,
    step5_claim_facts,
    step6_issues,
    step7_proof,
    step8_facts,
    step9_subsumption,
)
from steps.utils import models_to_dicts

logger = logging.getLogger("jiubufa.orchestrator")


# ---------------------------------------------------------------------------
# 用户选择常量
# ---------------------------------------------------------------------------

CHOICE_SUPPLEMENT = "supplement"
CHOICE_CONTINUE_WEAK = "continue_weak_judgment"
CHOICE_PARTIAL_ONLY = "partial_output_only"
CHOICE_PROCEED_WITH_RISK = "proceed_with_risk_notes"
CHOICE_PROCEED_STRONG = "proceed_strong_judgment"


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run_workflow(
    case_input: CaseInput,
    *,
    llm: Optional[LLMClient] = None,
) -> WorkflowResult:
    """
    跑一遍九步法工作流并返回 WorkflowResult。

    参数：
        case_input：案件输入，已通过 Pydantic 校验。
        llm：可选的 LLMClient；不传则使用默认全局客户端。
    """
    llm = llm or get_default_client()
    state = WorkflowState(case_input=case_input)
    started_at = time.time()

    # ---------- step1: 诉求固定 ----------
    _safe_run_step(state, "step1", lambda: step1_fix_claims.run(state, llm=llm))

    # ---------- step2: 请求权基础检索 ----------
    _safe_run_step(state, "step2", lambda: step2_request_basis.run(state, llm=llm))

    # ---------- step3: 抗辩权基础检索 ----------
    _safe_run_step(state, "step3", lambda: step3_defense_basis.run(state, llm=llm))

    # ---------- step4: 要件分析 ----------
    _safe_run_step(state, "step4", lambda: step4_elements.run(state, llm=llm))

    # ---------- step5: 待证事实搜索 ----------
    _safe_run_step(state, "step5", lambda: step5_claim_facts.run(state, llm=llm))

    # ---------- step6: 争点整理 ----------
    _safe_run_step(state, "step6", lambda: step6_issues.run(state, llm=llm))

    # ---------- step7: 举证质证 ----------
    _safe_run_step(state, "step7", lambda: step7_proof.run(state, llm=llm))

    # ---------- step8: 事实认定 ----------
    _safe_run_step(state, "step8", lambda: step8_facts.run(state, llm=llm))

    # ---------- 保底裁判机制：硬拦截 + 评分 + 选择门 ----------
    hard_reasons = check_hard_block(state)
    extra_reasons: List[str] = []
    # 把累积的 step 错误也作为风险因素加入
    if state.errors:
        extra_reasons.append(
            f"工作流推进过程中累计 {len(state.errors)} 个步骤异常，可能影响推理质量。"
        )

    score = score_sufficiency(state, llm=llm)
    state.sufficiency_score = score

    gate = build_fallback_gate(
        score=score,
        hard_block_reasons=hard_reasons,
        extra_reasons=extra_reasons,
    )
    state.fallback_gate = gate

    # ---------- 分支：硬拦截 ----------
    if gate.hard_block:
        return _make_result(state, status="blocked", started_at=started_at)

    # ---------- 分支：根据评分等级 + 用户选择决定终态 ----------
    user_choice = (case_input.fallback_user_choice or "").strip() or None
    level = score.level()  # strong / medium / weak_optional / block

    # 1) 评分=block：禁止强/中风险继续
    if level == "block":
        if user_choice == CHOICE_PARTIAL_ONLY:
            partial = generate_partial_output(state, score=score)
            return _make_result(
                state, status="ok", partial=partial, started_at=started_at
            )
        # 其它选择一律阻断
        return _make_result(state, status="blocked", started_at=started_at)

    # 2) 评分=weak_optional：必须由用户选择
    if level == "weak_optional":
        if user_choice is None:
            return _make_result(
                state, status="awaiting_user_choice", started_at=started_at
            )
        if user_choice == CHOICE_SUPPLEMENT:
            return _make_result(state, status="blocked", started_at=started_at)
        if user_choice == CHOICE_PARTIAL_ONLY:
            partial = generate_partial_output(state, score=score)
            return _make_result(
                state, status="ok", partial=partial, started_at=started_at
            )
        if user_choice == CHOICE_CONTINUE_WEAK:
            try:
                weak = generate_weak_judgment(
                    state,
                    llm=llm,
                    score=score,
                    risk_level="high",
                    user_choice=CHOICE_CONTINUE_WEAK,
                )
                return _make_result(
                    state, status="ok", weak=weak, started_at=started_at
                )
            except Exception as exc:  # noqa: BLE001
                state.errors.append(f"弱裁判生成失败：{exc}")
                logger.exception("弱裁判生成失败")
                # 失败回退为 partial
                partial = generate_partial_output(state, score=score)
                return _make_result(
                    state, status="ok", partial=partial, started_at=started_at
                )
        # 不识别的选择，阻断
        state.warnings.append(f"未识别的 fallback_user_choice：{user_choice}，按阻断处理。")
        return _make_result(state, status="blocked", started_at=started_at)

    # 3) 评分=medium：默认继续强裁判但带风险提示，亦允许用户改选弱/部分输出
    if level == "medium":
        if user_choice == CHOICE_SUPPLEMENT:
            return _make_result(state, status="blocked", started_at=started_at)
        if user_choice == CHOICE_PARTIAL_ONLY:
            partial = generate_partial_output(state, score=score)
            return _make_result(
                state, status="ok", partial=partial, started_at=started_at
            )
        if user_choice == CHOICE_CONTINUE_WEAK:
            try:
                weak = generate_weak_judgment(
                    state,
                    llm=llm,
                    score=score,
                    risk_level="medium",
                    user_choice=CHOICE_CONTINUE_WEAK,
                )
                return _make_result(
                    state, status="ok", weak=weak, started_at=started_at
                )
            except Exception as exc:  # noqa: BLE001
                state.errors.append(f"弱裁判生成失败：{exc}")
                logger.exception("弱裁判生成失败")
                partial = generate_partial_output(state, score=score)
                return _make_result(
                    state, status="ok", partial=partial, started_at=started_at
                )
        # 默认或显式 proceed_with_risk_notes：跑 step9 并带风险提示
        return _run_strong_branch(
            state, llm=llm, score=score, started_at=started_at, with_risk_notes=True
        )

    # 4) 评分=strong：直接强裁判（即便用户传了别的选择也尊重之）
    if user_choice == CHOICE_PARTIAL_ONLY:
        partial = generate_partial_output(state, score=score)
        return _make_result(state, status="ok", partial=partial, started_at=started_at)
    if user_choice == CHOICE_CONTINUE_WEAK:
        try:
            weak = generate_weak_judgment(
                state,
                llm=llm,
                score=score,
                risk_level="low",
                user_choice=CHOICE_CONTINUE_WEAK,
            )
            return _make_result(state, status="ok", weak=weak, started_at=started_at)
        except Exception as exc:  # noqa: BLE001
            state.errors.append(f"弱裁判生成失败：{exc}")
    if user_choice == CHOICE_SUPPLEMENT:
        return _make_result(state, status="blocked", started_at=started_at)

    return _run_strong_branch(
        state, llm=llm, score=score, started_at=started_at, with_risk_notes=False
    )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _safe_run_step(state: WorkflowState, step_attr: str, fn) -> None:
    """跑一个步骤；异常不让整个工作流爆掉，只记录到 state.errors。"""
    try:
        result = fn()
        setattr(state, step_attr, result)
    except Exception as exc:  # noqa: BLE001
        msg = f"{step_attr} 执行异常：{exc}"
        state.errors.append(msg)
        logger.exception(msg)


def _run_strong_branch(
    state: WorkflowState,
    *,
    llm: LLMClient,
    score: SufficiencyScore,
    started_at: float,
    with_risk_notes: bool,
) -> WorkflowResult:
    """跑 step9 并构建强裁判输出。"""
    try:
        state.step9 = step9_subsumption.run(state, llm=llm)
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"step9 执行异常：{exc}")
        logger.exception("step9 执行异常")

    subs: List[SubsumptionResult] = (
        list(state.step9.subsumption_results) if state.step9 else []
    )

    document_skeleton = _build_document_skeleton(state, subs)
    consistency_check = _build_consistency_check(state, subs)

    risk_level = "medium" if with_risk_notes else "low"
    strong = StrongJudgmentOutput(
        sufficiency_score=score,
        risk_level=risk_level,
        subsumption_results=subs,
        document_skeleton=document_skeleton,
        consistency_check=consistency_check,
    )

    if with_risk_notes:
        state.warnings.append(
            "评分处于中风险区间，已按 proceed_with_risk_notes 输出强裁判结果，请关注风险提示。"
        )

    return _make_result(state, status="ok", strong=strong, started_at=started_at)


def _resolve_rule_ref(rule_unit_id: str) -> Dict[str, str]:
    """通过 KB 把 rule_unit_id 解析为 {law_name, article_no, text}。"""
    try:
        kb = get_default_kb()
        ru = kb.get(rule_unit_id)
        if ru:
            return {
                "rule_unit_id": rule_unit_id,
                "law_name": ru.law_name or "",
                "article_no": ru.article_no or "",
                "rule_unit_text": ru.rule_unit_text or "",
            }
    except Exception:
        pass
    return {"rule_unit_id": rule_unit_id, "law_name": "", "article_no": "", "rule_unit_text": ""}


def _build_document_skeleton(
    state: WorkflowState, subs: List[SubsumptionResult]
) -> Dict[str, Any]:
    """裁判文书框架（草稿版）。"""
    fixed_claims = (
        models_to_dicts(state.step1.fixed_claims) if state.step1 else []
    )
    defenses = [d.model_dump() for d in state.case_input.defense_opinions]
    issues = models_to_dicts(state.step6.issues) if state.step6 else []
    fact_findings = (
        models_to_dicts(state.step8.fact_findings) if state.step8 else []
    )

    judgment_main_text: List[str] = []
    cited_ids: List[str] = []
    for s in subs:
        cited_ids.extend(s.cited_rules)
        if s.judgment_result == "supported":
            judgment_main_text.append(f"支持原告关于 {s.claim_id} 的诉讼请求。")
        elif s.judgment_result == "partially_supported":
            judgment_main_text.append(f"部分支持原告关于 {s.claim_id} 的诉讼请求。")
        elif s.judgment_result == "rejected":
            judgment_main_text.append(f"驳回原告关于 {s.claim_id} 的诉讼请求。")
        elif s.judgment_result == "procedural_dismissal":
            judgment_main_text.append(f"驳回原告关于 {s.claim_id} 的起诉。")

    # 去重 ID → 通过 KB 解析为完整法条信息
    unique_ids = sorted(set(cited_ids))
    cited_rules_resolved = [_resolve_rule_ref(rid) for rid in unique_ids]

    return {
        "原告诉讼请求": fixed_claims,
        "被告辩称": defenses,
        "争议焦点": issues,
        "本院查明": fact_findings,
        "本院认为": [s.model_dump() for s in subs],
        "判决主文": judgment_main_text,
        "引用法条": cited_rules_resolved,
    }


def _build_consistency_check(
    state: WorkflowState, subs: List[SubsumptionResult]
) -> Dict[str, Any]:
    """\"八个一致\"校验（粗校验，精确版可由后续模块补强）。"""
    claim_ids_input = {c.claim_id for c in state.case_input.claims}
    claim_ids_step1 = (
        {c.claim_id for c in state.step1.fixed_claims} if state.step1 else set()
    )
    claim_ids_step9 = {s.claim_id for s in subs}

    missing_in_step9 = claim_ids_step1 - claim_ids_step9
    extra_in_step9 = claim_ids_step9 - claim_ids_step1

    return {
        "诉求-固定一致": sorted(claim_ids_input ^ claim_ids_step1) == [],
        "固定-涵摄一致": not missing_in_step9 and not extra_in_step9,
        "缺漏的诉求（涵摄阶段未覆盖）": sorted(missing_in_step9),
        "多出的诉求（涵摄阶段凭空出现）": sorted(extra_in_step9),
        "争点已使用": bool(state.step6 and state.step6.issues),
        "事实已认定": bool(state.step8 and state.step8.fact_findings),
        "法条已引用": any(s.cited_rules for s in subs),
    }


def _make_result(
    state: WorkflowState,
    *,
    status: str,
    started_at: float,
    strong: Optional[StrongJudgmentOutput] = None,
    weak: Optional[Any] = None,
    partial: Optional[Any] = None,
) -> WorkflowResult:
    state.timings_ms["total"] = int((time.time() - started_at) * 1000)
    return WorkflowResult(
        case_id=state.case_input.case_basic_info.case_id
        if state.case_input.case_basic_info
        else None,
        status=status,
        fallback_gate=state.fallback_gate,
        step1=state.step1,
        step2=state.step2,
        step3=state.step3,
        step4=state.step4,
        step5=state.step5,
        step6=state.step6,
        step7=state.step7,
        step8=state.step8,
        step9=state.step9,
        strong_judgment=strong,
        weak_judgment=weak,
        partial_output=partial,
        timings_ms=dict(state.timings_ms),
        errors=list(state.errors),
        warnings=list(state.warnings),
    )


__all__ = ["run_workflow"]
