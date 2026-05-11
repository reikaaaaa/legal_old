"""
上下文构建工具。

为每个步骤构建完整的上下文信息，包括：
1. 原始案件信息（案件事实、证据、答辩等）
2. 前面所有步骤的输出结果
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .state import WorkflowState
from .utils import models_to_dicts


def build_full_context(
    state: WorkflowState,
    current_step: str,
    include_original_case: bool = True,
    include_previous_steps: bool = True,
    max_case_facts_length: int = 3000,
) -> str:
    """
    构建完整的上下文信息。
    
    参数：
        state: 工作流状态
        current_step: 当前步骤标识（如 "step2_request_basis"）
        include_original_case: 是否包含原始案件信息
        include_previous_steps: 是否包含前面步骤的输出
        max_case_facts_length: 案件事实文本最大长度（避免token过多）
    
    返回：
        格式化的上下文字符串
    """
    sections = []
    
    # 1. 原始案件信息（如果启用）
    if include_original_case:
        sections.append(_build_case_context(state, max_case_facts_length))
    
    # 2. 前面步骤的输出（如果启用）
    if include_previous_steps:
        sections.append(_build_steps_context(state, current_step))
    
    # 过滤空内容并拼接
    valid_sections = [s for s in sections if s.strip()]
    if not valid_sections:
        return ""
    
    return "\n\n".join(valid_sections)


def _build_case_context(state: WorkflowState, max_length: int) -> str:
    """构建原始案件信息上下文"""
    case_input = state.case_input
    parts = ["【原始案件信息】"]
    
    # 案件基本信息
    if case_input.case_basic_info:
        basic = case_input.case_basic_info
        parts.append(f"\n案件名称：{basic.case_name or '未提供'}")
        parts.append(f"案由：{basic.case_cause_text or '未提供'}")
        parts.append(f"审理法院：{basic.court or '未提供'}")
        parts.append(f"程序阶段：{basic.procedure_stage or '未提供'}")
        if basic.case_summary:
            summary = basic.case_summary[:500]
            parts.append(f"案件摘要：{summary}")
    
    # 诉讼请求
    if case_input.claims:
        parts.append("\n【诉讼请求】")
        for claim in case_input.claims:
            parts.append(f"- {claim.claim_id}: {claim.claim_text_original[:200]}")
    
    # 事实主张（截断避免过长）
    if case_input.claim_facts:
        parts.append("\n【事实主张】")
        fact_text = ""
        for fact in case_input.claim_facts:
            fact_line = f"- {fact.fact_id}: {fact.fact_text_original[:200]}\n"
            if len(fact_text) + len(fact_line) < max_length:
                fact_text += fact_line
            else:
                fact_text += "- ...（更多事实主张已截断）\n"
                break
        parts.append(fact_text.rstrip())
    
    # 答辩意见
    if case_input.defense_opinions:
        parts.append("\n【答辩意见】")
        for defense in case_input.defense_opinions:
            text = defense.defense_text_original[:200]
            parts.append(f"- {defense.defense_id}: {text}")
    
    # 证据清单（简化版）
    if case_input.evidence_list:
        parts.append("\n【证据清单】")
        for ev in case_input.evidence_list:
            parts.append(f"- {ev.evidence_id}: {ev.evidence_name}（{ev.evidence_type or '未知类型'}）")
    
    # 庭审笔录（简化版）
    if case_input.court_records:
        parts.append("\n【庭审笔录摘要】")
        for i, record in enumerate(case_input.court_records[:3], 1):
            parts.append(f"{i}. {record[:150]}")
        if len(case_input.court_records) > 3:
            parts.append(f"...（共 {len(case_input.court_records)} 条笔录）")
    
    return "\n".join(parts)


def _build_steps_context(state: WorkflowState, current_step: str) -> str:
    """构建前面步骤的输出上下文"""
    step_order = [
        "step1", "step2", "step3", "step4", "step5",
        "step6", "step7", "step8", "step9"
    ]
    
    # 确定当前步骤的索引
    current_idx = -1
    for i, step_name in enumerate(step_order):
        if current_step.startswith(step_name):
            current_idx = i
            break
    
    if current_idx <= 0:
        return ""  # 第一步或无法识别，无历史步骤
    
    # 收集前面步骤的输出
    previous_steps = []
    for i in range(current_idx):
        step_name = step_order[i]
        step_output = getattr(state, step_name, None)
        if step_output is not None:
            step_info = _format_step_output(step_name, step_output)
            if step_info:
                previous_steps.append(step_info)
    
    if not previous_steps:
        return ""
    
    header = "【前面步骤的输出结果】"
    return header + "\n\n" + "\n\n".join(previous_steps)


def _format_step_output(step_name: str, step_output: Any) -> Optional[str]:
    """格式化步骤输出为可读文本"""
    try:
        # 转换为字典
        if hasattr(step_output, 'model_dump'):
            data = step_output.model_dump(exclude_none=True)
        else:
            return None
        
        if not data:
            return None
        
        # 根据不同步骤提取关键信息
        if step_name == "step1":
            return _format_step1(data)
        elif step_name == "step2":
            return _format_step2(data)
        elif step_name == "step3":
            return _format_step3(data)
        elif step_name == "step4":
            return _format_step4(data)
        elif step_name == "step5":
            return _format_step5(data)
        elif step_name == "step6":
            return _format_step6(data)
        elif step_name == "step7":
            return _format_step7(data)
        elif step_name == "step8":
            return _format_step8(data)
        else:
            return f"[{step_name}]\n{json.dumps(data, ensure_ascii=False, indent=2)}"
    except Exception:
        return None


def _format_step1(data: Dict) -> str:
    """格式化 Step 1 输出"""
    lines = ["[Step 1: 固定权利请求]"]
    
    if data.get("case_cause_inferred"):
        lines.append(f"推断案由：{', '.join(data['case_cause_inferred'])}")
    
    if data.get("legal_domain_inferred"):
        lines.append(f"法律领域：{', '.join(data['legal_domain_inferred'])}")
    
    fixed_claims = data.get("fixed_claims", [])
    if fixed_claims:
        lines.append(f"\n固定诉请（{len(fixed_claims)}项）：")
        for claim in fixed_claims[:5]:
            claim_id = claim.get("claim_id", "?")
            claim_text = claim.get("claim_text_normalized", "")[:100]
            claim_type = ", ".join(claim.get("claim_type", []))
            lines.append(f"  - {claim_id}: {claim_text}")
            if claim_type:
                lines.append(f"    类型：{claim_type}")
    
    return "\n".join(lines)


def _format_step2(data: Dict) -> str:
    """格式化 Step 2 输出"""
    lines = ["[Step 2: 确定请求权基础]"]
    
    candidates = data.get("request_basis_candidates", [])
    if candidates:
        lines.append(f"\n选定请求权基础（{len(candidates)}项）：")
        for cand in candidates[:5]:
            claim_id = cand.get("claim_id", "?")
            ref = cand.get("rule_unit_ref", {})
            law_name = ref.get("law_name", "?")
            article_no = ref.get("article_no", "?")
            rule_text = ref.get("rule_unit_text", "")[:100]
            lines.append(f"  - {claim_id}: {law_name} {article_no}")
            if rule_text:
                lines.append(f"    内容：{rule_text}")
    
    return "\n".join(lines)


def _format_step3(data: Dict) -> str:
    """格式化 Step 3 输出"""
    lines = ["[Step 3: 确定抗辩权基础]"]
    
    candidates = data.get("defense_basis_candidates", [])
    if candidates:
        lines.append(f"\n选定抗辩权基础（{len(candidates)}项）：")
        for cand in candidates[:5]:
            defense_id = cand.get("defense_id", "?")
            ref = cand.get("rule_unit_ref", {})
            if ref:
                law_name = ref.get("law_name", "?")
                article_no = ref.get("article_no", "?")
                rule_text = ref.get("rule_unit_text", "")[:100]
                lines.append(f"  - {defense_id}: {law_name} {article_no}")
                if rule_text:
                    lines.append(f"    内容：{rule_text}")
    
    return "\n".join(lines)


def _format_step4(data: Dict) -> str:
    """格式化 Step 4 输出"""
    lines = ["[Step 4: 构成要件分析]"]
    
    matrix = data.get("element_matrix", [])
    if matrix:
        lines.append(f"\n要件矩阵（{len(matrix)}项）：")
        for row in matrix[:5]:
            target_id = row.get("target_id", "?")
            rule_unit_id = row.get("rule_unit_id", "?")
            elements = row.get("elements", [])
            lines.append(f"  - {target_id} ({rule_unit_id}): {len(elements)}个要件")
    
    return "\n".join(lines)


def _format_step5(data: Dict) -> str:
    """格式化 Step 5 输出"""
    lines = ["[Step 5: 诉讼主张检索]"]
    
    mapping = data.get("claim_fact_mapping", [])
    if mapping:
        lines.append(f"\n事实映射（{len(mapping)}项）：")
        for item in mapping[:5]:
            claim_id = item.get("claim_id", "?")
            facts = item.get("mapped_facts", [])
            lines.append(f"  - {claim_id}: 映射{len(facts)}个事实")
    
    return "\n".join(lines)


def _format_step6(data: Dict) -> str:
    """格式化 Step 6 输出"""
    lines = ["[Step 6: 争点整理]"]
    
    issues = data.get("issues", [])
    if issues:
        lines.append(f"\n争议焦点（{len(issues)}项）：")
        for issue in issues[:5]:
            issue_id = issue.get("issue_id", "?")
            issue_text = issue.get("issue_text", "")[:100]
            lines.append(f"  - {issue_id}: {issue_text}")
    
    return "\n".join(lines)


def _format_step7(data: Dict) -> str:
    """格式化 Step 7 输出"""
    lines = ["[Step 7: 举证质证]"]
    
    proof_plan = data.get("proof_plan", [])
    if proof_plan:
        lines.append(f"\n举证计划（{len(proof_plan)}项）：")
        for plan in proof_plan[:5]:
            element_id = plan.get("element_id", "?")
            burden = plan.get("burden_party", "?")
            lines.append(f"  - {element_id}: 举证责任方={burden}")
    
    return "\n".join(lines)


def _format_step8(data: Dict) -> str:
    """格式化 Step 8 输出"""
    lines = ["[Step 8: 事实认定]"]
    
    findings = data.get("fact_findings", [])
    if findings:
        lines.append(f"\n事实认定（{len(findings)}项）：")
        for finding in findings[:5]:
            element_id = finding.get("element_id", "?")
            status = finding.get("finding_status", "?")
            lines.append(f"  - {element_id}: 认定状态={status}")
    
    return "\n".join(lines)
