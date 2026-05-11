"""
保底裁判机制。

实现内容：
1) `score_sufficiency` —— 第八步后、第九步前，对工作流到目前为止的中间产物打分。
2) `build_fallback_gate` —— 根据评分等级和硬性拦截条件构造用户选择门。
3) `should_hard_block` —— 检查是否触发硬性拦截（无诉讼请求、无主体等）。
4) `generate_weak_judgment` —— 用户选择 continue_weak_judgment 时，调用 LLM 生成弱裁判结果。
5) `generate_partial_output` —— 用户选择 partial_output_only 时，仅输出要件、争点、缺口。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from llm import LLMClient
from prompts import SUFFICIENCY_SCORING_SYSTEM, WEAK_JUDGMENT_SYSTEM
from schemas import (
    FallbackGate,
    PartialOutput,
    Step1Output,
    Step2Output,
    Step3Output,
    Step4Output,
    Step5Output,
    Step6Output,
    Step7Output,
    Step8Output,
    SufficiencyScore,
    WeakJudgmentOutput,
    WeakSubsumptionResult,
)
from schemas.outputs import FallbackPathItem
from steps.state import WorkflowState
from steps.utils import models_to_dicts

logger = logging.getLogger("jiubufa.fallback")


# ---------------------------------------------------------------------------
# 硬性拦截
# ---------------------------------------------------------------------------


def check_hard_block(state: WorkflowState) -> List[str]:
    """返回硬性拦截原因列表；空列表表示没有硬性拦截。"""
    reasons: List[str] = []
    case = state.case_input

    if not case.claims:
        reasons.append("案件输入中没有任何诉讼请求（claims 为空），不能裁判。")

    if not case.party_info:
        reasons.append("没有提供任何当事人信息（party_info 为空），无法识别主体。")

    # 第一步如果跑过，但所有 fixed_claims.is_executable 都是 False
    if state.step1 and state.step1.fixed_claims:
        if all(not fc.is_executable for fc in state.step1.fixed_claims):
            reasons.append("所有诉讼请求都不可执行，无法形成判决主文。")

    return reasons


# ---------------------------------------------------------------------------
# 评分
# ---------------------------------------------------------------------------


def score_sufficiency(
    state: WorkflowState, *, llm: Optional[LLMClient] = None
) -> SufficiencyScore:
    """
    优先用 LLM 给七维度打分，失败时回退到规则法兜底。
    """
    if llm is not None:
        try:
            return _score_with_llm(state, llm)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 评分失败，使用规则法回退：%s", exc)
            state.warnings.append(f"sufficiency LLM 评分失败：{exc}")
    return _score_with_rules(state)


def _score_with_llm(state: WorkflowState, llm: LLMClient) -> SufficiencyScore:
    payload: Dict[str, Any] = {
        "fixed_claims": models_to_dicts(state.step1.fixed_claims) if state.step1 else [],
        "request_basis_candidates": (
            models_to_dicts(state.step2.request_basis_candidates)
            if state.step2
            else []
        ),
        "defense_basis_candidates": (
            models_to_dicts(state.step3.defense_basis_candidates)
            if state.step3
            else []
        ),
        "element_matrix_size": len(state.step4.element_matrix) if state.step4 else 0,
        "claim_fact_mapping": (
            models_to_dicts(state.step5.claim_fact_mapping) if state.step5 else []
        ),
        "issues": models_to_dicts(state.step6.issues) if state.step6 else [],
        "proof_plan": models_to_dicts(state.step7.proof_plan) if state.step7 else [],
        "fact_findings": (
            models_to_dicts(state.step8.fact_findings) if state.step8 else []
        ),
        "evidence_count": len(state.case_input.evidence_list),
    }
    user_prompt = (
        "请基于以下九步法中间产物给出输入完整度七维度评分。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n请严格按 system 规定的 JSON schema 输出。"
    )
    raw = llm.chat_json(
        SUFFICIENCY_SCORING_SYSTEM,
        user_prompt,
        step_key="sufficiency_scoring",
    )
    score = SufficiencyScore(
        claim_clarity=int(raw.get("claim_clarity", 0)),
        legal_relation_stability=int(raw.get("legal_relation_stability", 0)),
        request_basis_stability=int(raw.get("request_basis_stability", 0)),
        defense_path_completeness=int(raw.get("defense_path_completeness", 0)),
        element_fact_coverage=int(raw.get("element_fact_coverage", 0)),
        evidence_coverage=int(raw.get("evidence_coverage", 0)),
        fact_finding_reliability=int(raw.get("fact_finding_reliability", 0)),
    )
    return score


def _score_with_rules(state: WorkflowState) -> SufficiencyScore:
    """规则法兜底打分。逻辑保守。"""
    s = SufficiencyScore()

    # claim_clarity：每项 fixed_claim 最多 5 分（is_clear+is_executable+amount/behavior）
    if state.step1 and state.step1.fixed_claims:
        clear_total = 0
        for fc in state.step1.fixed_claims:
            base = 0
            if fc.is_clear:
                base += 6
            if fc.is_executable:
                base += 6
            if fc.amount or fc.object_type or fc.claimant:
                base += 3
            clear_total += base
        s.claim_clarity = min(20, clear_total // max(1, len(state.step1.fixed_claims)))

    # legal_relation_stability
    if state.step1:
        if state.step1.legal_domain_inferred:
            s.legal_relation_stability += 8
        if state.step1.case_cause_inferred:
            s.legal_relation_stability += 7
        s.legal_relation_stability = min(15, s.legal_relation_stability)

    # request_basis_stability
    if state.step2 and state.step2.request_basis_candidates:
        s.request_basis_stability = min(15, 5 + 2 * len(state.step2.request_basis_candidates))

    # defense_path_completeness
    if state.case_input.defense_opinions:
        if state.step3 and state.step3.defense_basis_candidates:
            s.defense_path_completeness = 10
        else:
            s.defense_path_completeness = 5
    else:
        # 没有答辩输入：默认认为缺口
        s.defense_path_completeness = 4

    # element_fact_coverage
    if state.step5 and state.step5.claim_fact_mapping:
        total = len(state.step5.claim_fact_mapping)
        asserted = sum(1 for r in state.step5.claim_fact_mapping if r.assertion_status == "asserted")
        s.element_fact_coverage = int(15 * asserted / max(1, total))

    # evidence_coverage
    if state.case_input.evidence_list:
        if state.step7 and state.step7.proof_plan:
            covered = sum(
                1 for p in state.step7.proof_plan if p.existing_evidence_ids
            )
            total = len(state.step7.proof_plan)
            s.evidence_coverage = int(15 * covered / max(1, total))
        else:
            s.evidence_coverage = 5

    # fact_finding_reliability
    if state.step8 and state.step8.fact_findings:
        total = len(state.step8.fact_findings)
        determined = sum(
            1 for f in state.step8.fact_findings if f.finding_status in ("proved", "not_proved")
        )
        s.fact_finding_reliability = int(10 * determined / max(1, total))

    return s


# ---------------------------------------------------------------------------
# 用户选择门
# ---------------------------------------------------------------------------


def build_fallback_gate(
    *,
    score: SufficiencyScore,
    hard_block_reasons: List[str],
    extra_reasons: Optional[List[str]] = None,
) -> FallbackGate:
    extra_reasons = extra_reasons or []
    if hard_block_reasons:
        return FallbackGate(
            risk_triggered=True,
            risk_level="critical",
            reason=hard_block_reasons + extra_reasons,
            recommended_action="hard_block_no_judgment",
            available_choices=[
                {
                    "choice": "supplement",
                    "description": "补充缺失材料后重新执行",
                }
            ],
            default_choice="supplement",
            hard_block=True,
        )

    level = score.level()
    if level == "strong":
        return FallbackGate(
            risk_triggered=False,
            risk_level="low",
            reason=[],
            recommended_action="proceed_strong_judgment",
            available_choices=[],
            default_choice="proceed_strong_judgment",
        )
    if level == "medium":
        return FallbackGate(
            risk_triggered=True,
            risk_level="medium",
            reason=extra_reasons + [f"输入完整度评分 {score.total} 处于中风险区间。"],
            recommended_action="proceed_with_risk_notes",
            available_choices=[
                {"choice": "supplement", "description": "停止裁判输出，按缺口清单补充材料后回退"},
                {"choice": "proceed_with_risk_notes", "description": "继续输出强裁判结果并附风险提示"},
                {"choice": "continue_weak_judgment", "description": "改用弱裁判通道（更保守）"},
            ],
            default_choice="proceed_with_risk_notes",
        )
    if level == "weak_optional":
        return FallbackGate(
            risk_triggered=True,
            risk_level="high",
            reason=extra_reasons + [
                f"输入完整度评分 {score.total} 处于弱裁判区间，需用户选择是否继续。"
            ],
            recommended_action="supplement_and_retry",
            available_choices=[
                {"choice": "supplement", "description": "停止裁判输出，按缺口清单补充材料后回退执行"},
                {"choice": "continue_weak_judgment", "description": "在明示风险和假设前提下，继续生成弱裁判结果"},
                {"choice": "partial_output_only", "description": "仅输出请求、法条、要件、争点、证据缺口，不输出裁判倾向"},
            ],
            default_choice="supplement",
        )
    # block
    return FallbackGate(
        risk_triggered=True,
        risk_level="critical",
        reason=extra_reasons + [
            f"输入完整度评分 {score.total} 过低（<40），不宜输出裁判倾向。"
        ],
        recommended_action="supplement_and_retry",
        available_choices=[
            {"choice": "supplement", "description": "补充关键材料后重新执行"},
            {"choice": "partial_output_only", "description": "仅输出已有的要件/争点/缺口（不含裁判倾向）"},
        ],
        default_choice="supplement",
        hard_block=False,
    )


# ---------------------------------------------------------------------------
# 弱裁判生成
# ---------------------------------------------------------------------------


def generate_weak_judgment(
    state: WorkflowState,
    *,
    llm: LLMClient,
    score: SufficiencyScore,
    risk_level: str,
    user_choice: str = "continue_weak_judgment",
) -> WeakJudgmentOutput:
    """调用 LLM 生成弱裁判结论。"""

    payload: Dict[str, Any] = {
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
        "claim_fact_mapping": (
            models_to_dicts(state.step5.claim_fact_mapping) if state.step5 else []
        ),
        "issues": models_to_dicts(state.step6.issues) if state.step6 else [],
        "proof_plan": models_to_dicts(state.step7.proof_plan) if state.step7 else [],
        "fact_findings": (
            models_to_dicts(state.step8.fact_findings) if state.step8 else []
        ),
        "sufficiency_score": score.model_dump(),
        "risk_level": risk_level,
    }

    user_prompt = (
        "用户已选择 continue_weak_judgment。请按 system 中规定的 schema "
        "生成弱裁判结果，必须列明假设、缺口、风险与回退路径。\n\n"
        "【输入】\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    raw = llm.chat_json(
        WEAK_JUDGMENT_SYSTEM,
        user_prompt,
        step_key="weak_judgment",
    )

    weak_results: List[WeakSubsumptionResult] = []
    for item in raw.get("weak_subsumption_results", []) or []:
        try:
            weak_results.append(WeakSubsumptionResult(**item))
        except Exception as exc:  # noqa: BLE001
            logger.warning("弱裁判子项构造失败：%s", exc)

    fallback_path: List[FallbackPathItem] = []
    for fp in raw.get("fallback_path", []) or []:
        try:
            fallback_path.append(FallbackPathItem(**fp))
        except Exception:  # noqa: BLE001
            continue

    return WeakJudgmentOutput(
        sufficiency_score=score,
        risk_level=risk_level,
        user_choice=user_choice,
        missing_inputs=list(raw.get("missing_inputs", []) or []),
        assumptions_used=list(raw.get("assumptions_used", []) or []),
        unsupported_elements=list(raw.get("unsupported_elements", []) or []),
        evidence_gaps=list(raw.get("evidence_gaps", []) or []),
        law_application_risks=list(raw.get("law_application_risks", []) or []),
        fact_finding_risks=list(raw.get("fact_finding_risks", []) or []),
        proof_risks=list(raw.get("proof_risks", []) or []),
        fallback_path=fallback_path,
        weak_subsumption_results=weak_results,
        upgrade_to_strong_judgment_requirements=list(
            raw.get("upgrade_to_strong_judgment_requirements", []) or []
        ),
    )


# ---------------------------------------------------------------------------
# Partial 输出（仅缺口）
# ---------------------------------------------------------------------------


def generate_partial_output(
    state: WorkflowState, *, score: SufficiencyScore
) -> PartialOutput:
    evidence_gaps: List[str] = []
    missing_inputs: List[str] = []

    if state.step5:
        for r in state.step5.claim_fact_mapping:
            if r.assertion_status in ("missing", "vague", "conflicting"):
                tip = r.clarification_question or r.risk_note or r.required_fact or ""
                missing_inputs.append(
                    f"要件 {r.element_id} 主张状态={r.assertion_status}：{tip}"
                )

    if state.step7:
        for p in state.step7.proof_plan:
            if p.proof_gap:
                evidence_gaps.append(f"要件 {p.element_id}：{p.proof_gap}")

    return PartialOutput(
        sufficiency_score=score,
        fixed_claims=(
            models_to_dicts(state.step1.fixed_claims) if state.step1 else []
        ),
        request_basis_candidates=(
            models_to_dicts(state.step2.request_basis_candidates) if state.step2 else []
        ),
        defense_basis_candidates=(
            models_to_dicts(state.step3.defense_basis_candidates) if state.step3 else []
        ),
        element_matrix=(
            models_to_dicts(state.step4.element_matrix) if state.step4 else []
        ),
        issues=(models_to_dicts(state.step6.issues) if state.step6 else []),
        evidence_gaps=evidence_gaps,
        missing_inputs=missing_inputs,
    )
