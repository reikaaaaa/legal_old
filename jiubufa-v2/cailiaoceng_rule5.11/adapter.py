"""
材料规范层 v3.0 — 适配器

将 NormalizedCaseInput 转换为 jiubufa-v2 可直接消费的 CaseInput。
"""
from __future__ import annotations

import copy
from typing import Optional

try:
    from .material_schemas import NormalizedCaseInput
except ImportError:
    from material_schemas import NormalizedCaseInput


def to_case_input(
    normalized: NormalizedCaseInput,
    *,
    fallback_user_choice: Optional[str] = None,
) -> "CaseInput":
    """
    将 NormalizedCaseInput 转换为 jiubufa-v2 的 CaseInput。

    NormalizedCaseInput 与 CaseInput 的字段结构完全一致，
    转换实质上是：
      1. 去除 evidence_meta（审核元数据，不进入 CaseInput）
      2. 去除 original_input（仅用于追溯）
      3. 添加 fallback_user_choice（工作流执行选项）

    参数：
        normalized: 阶段二规范化输出
        fallback_user_choice: 保底裁判机制用户选择
            supplement / continue_weak_judgment / partial_output_only
    """
    # 动态导入避免硬依赖 jiubufa-v2 路径
    import sys
    from pathlib import Path

    _JIUBUFA_V2 = Path(__file__).resolve().parent.parent / "jiubufa-v2"
    if str(_JIUBUFA_V2) not in sys.path:
        sys.path.insert(0, str(_JIUBUFA_V2))

    from schemas.inputs import (
        CaseBasicInfo,
        CaseInput,
        ClaimFactObject,
        ClaimObject,
        CounterclaimObject,
        CrossExaminationObject,
        DefenseObject,
        EvidenceObject,
        LegalArgumentObject,
        PartyInfo,
        ProceduralInfo,
    )

    return CaseInput(
        case_basic_info=CaseBasicInfo(**normalized.case_basic_info.model_dump()),
        party_info=[PartyInfo(**p.model_dump()) for p in normalized.party_info],
        claims=[ClaimObject(**c.model_dump()) for c in normalized.claims],
        claim_facts=[ClaimFactObject(**f.model_dump()) for f in normalized.claim_facts],
        defense_opinions=[DefenseObject(**d.model_dump()) for d in normalized.defense_opinions],
        counterclaims=[CounterclaimObject(**cc.model_dump()) for cc in normalized.counterclaims],
        evidence_list=[EvidenceObject(**e.model_dump()) for e in normalized.evidence_list],
        cross_examinations=[
            CrossExaminationObject(**cx.model_dump()) for cx in normalized.cross_examinations
        ],
        court_records=list(normalized.court_records),
        legal_arguments=[
            LegalArgumentObject(**la.model_dump()) for la in normalized.legal_arguments
        ],
        procedural_info=(
            ProceduralInfo(**normalized.procedural_info.model_dump())
            if normalized.procedural_info
            else None
        ),
        existing_judgment_or_mediation=normalized.existing_judgment_or_mediation,
        fallback_user_choice=fallback_user_choice,
    )


def normalized_to_api_payload(
    normalized: NormalizedCaseInput,
    fallback_user_choice: Optional[str] = None,
) -> dict:
    """
    直接产出 POST /api/workflow/run 的请求体 JSON。

    用法：
        payload = normalized_to_api_payload(normalized)
        requests.post("http://127.0.0.1:8000/api/workflow/run", json=payload)
    """
    case_input = to_case_input(normalized, fallback_user_choice=fallback_user_choice)
    return {"case_input": case_input.model_dump(mode="json", exclude_none=False)}
