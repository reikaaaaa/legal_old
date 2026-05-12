"""
材料规范层 v3.0 — Material Agent（DashScope 原生 SDK）

实现阶段一（材料审核）和阶段二（材料规范化）的 LLM Agent。
使用 DashScope 原生 API（Generation.call），非 OpenAI 兼容模式。

用法：
    from material_agent import MaterialPipeline

    pipeline = MaterialPipeline()

    # 仅审核
    review = pipeline.review("用户原始材料...")

    # 审核 + 规范化
    full = pipeline.full("用户原始材料...")
    if full.review.can_proceed:
        case_input = to_case_input(full.normalized)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Union

import dashscope
from dashscope import Generation

# 确保本模块所在目录优先，避免与 jiubufa-v2 的 schemas 重名冲突
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

try:
    from . import material_prompts as prompts
    from .material_schemas import (
        CaseBasicInfo,
        CaseTypeMaterialCheck,
        ClaimFactObject,
        ClaimObject,
        CounterclaimObject,
        CrossExaminationObject,
        DefenseObject,
        EvidenceMeta,
        EvidenceObject,
        LegalArgumentObject,
        MaterialFullResult,
        MaterialItem,
        MaterialReviewResult,
        NormalizedCaseInput,
        PartyInfo,
        ProceduralInfo,
        StepRequirementCheck,
    )
except ImportError:
    import material_prompts as prompts  # type: ignore[no-redef]
    from material_schemas import (  # type: ignore[no-redef]
        CaseBasicInfo,
        CaseTypeMaterialCheck,
        ClaimFactObject,
        ClaimObject,
        CounterclaimObject,
        CrossExaminationObject,
        DefenseObject,
        EvidenceMeta,
        EvidenceObject,
        LegalArgumentObject,
        MaterialFullResult,
        MaterialItem,
        MaterialReviewResult,
        NormalizedCaseInput,
        PartyInfo,
        ProceduralInfo,
        StepRequirementCheck,
    )

logger = logging.getLogger("material_agent")

# ============================================================================
# DashScope 配置
# ============================================================================

dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"

DASHSCOPE_API_KEY = "sk-69b24c1abe964a0389c794d35bba9fd3"

# 模型配置
REVIEW_MODEL = "qwen3-max"       # 材料审核（需要强推理能力）
NORMALIZE_MODEL = "qwen3-max"    # 材料规范化（需要精确提取 + 结构化输出）

# 重试配置
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0


# ============================================================================
# JSON 容错解析
# ============================================================================

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.DOTALL)


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON 块。"""
    text = text.strip()
    # 去除 ```json ... ``` 包裹
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text, count=1)
    text = text.strip()
    # 抓取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_json_safely(text: str) -> Any:
    """容错解析 LLM 返回的 JSON。"""
    if not text:
        raise ValueError("LLM 返回为空")
    candidate = _extract_json(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # 去掉尾随逗号后重试
        cleaned = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试修复常见错误
            cleaned = re.sub(r",\s*,", ",", cleaned)
            cleaned = re.sub(r"\[\s*,", "[", cleaned)
            return json.loads(cleaned)


# ============================================================================
# DashScope 调用封装
# ============================================================================


def _call_dashscope(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = REVIEW_MODEL,
    enable_thinking: bool = True,
    max_retries: int = MAX_RETRIES,
) -> str:
    """
    调用 DashScope Generation API，返回模型输出的文本内容。
    支持自动重试 + 思考过程日志。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.time()
            response = Generation.call(
                api_key=DASHSCOPE_API_KEY,
                model=model,
                messages=messages,
                result_format="message",
                enable_thinking=enable_thinking,
            )

            if response.status_code == 200:
                elapsed = time.time() - t0
                choice = response.output.choices[0].message
                content = choice.content or ""

                # 打印思考过程（如有）
                reasoning = getattr(choice, "reasoning_content", "")
                if reasoning:
                    logger.info(
                        "DashScope[%s] thinking (%d chars, %.1fs): %s...",
                        model, len(reasoning), elapsed, reasoning[:200],
                    )

                logger.info(
                    "DashScope[%s] ok in %.1fs, output=%d chars",
                    model, elapsed, len(content),
                )
                return content
            else:
                last_error = RuntimeError(
                    f"DashScope HTTP {response.status_code}: code={response.code} msg={response.message}"
                )
                logger.warning(
                    "DashScope call failed (attempt %d/%d): %s",
                    attempt, max_retries, last_error,
                )

        except Exception as exc:
            last_error = exc
            logger.warning(
                "DashScope call exception (attempt %d/%d): %s",
                attempt, max_retries, exc,
            )

        if attempt < max_retries:
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            time.sleep(wait)

    raise RuntimeError(f"DashScope 调用失败（已重试 {max_retries} 次）：{last_error}")


# ============================================================================
# Agent
# ============================================================================


def _build_review_system_prompt() -> str:
    """构建阶段一 System Prompt（含案由清单动态注入）。"""
    checklist_block = "\n\n".join(prompts.CASE_TYPE_CHECKLISTS.values())
    return prompts.MATERIAL_REVIEW_SYSTEM_PROMPT.replace(
        "[$OUTPUT_SCHEMA]",
        """```json
{
  "case_module": "合同纠纷 | 婚姻家庭 | 侵权纠纷 | 劳动争议 | 民间借贷 | 其他民事案件 | 无法确定",
  "case_type_check": {
    "case_module": "string",
    "core_provided_rate": 0.0,
    "special_rules_note": "string",
    "checklist": [
      {
        "name": "string",
        "source_element": "string",
        "legal_basis": "string",
        "is_core": true,
        "status": "已提供 | 部分提供 | 缺失",
        "dimension": "案由专项",
        "description": "string",
        "suggestion": "string"
      }
    ]
  },
  "step_checks": [
    {
      "step_index": 1,
      "step_name": "string",
      "status": "充足 | 部分不足 | 严重缺失",
      "has_required": ["..."],
      "missing_items": ["..."],
      "suggestion": "string",
      "special_note": "string"
    }
  ],
  "overall_status": "材料充足 | 材料基本完整 | 材料不完整 | 仅有案件摘要",
  "can_proceed": true,
  "missing_core_materials": ["..."],
  "missing_optional_materials": ["..."],
  "upload_instructions": "string",
  "confidence": "高 | 中 | 低"
}
```""",
    ).replace(
        "[$CASE_TYPE_CHECKLISTS]",
        checklist_block,
    )


def _build_normalize_system_prompt() -> str:
    """构建阶段二 System Prompt（含输出 Schema）。"""
    return prompts.MATERIAL_NORMALIZE_SYSTEM_PROMPT.replace(
        "[$OUTPUT_SCHEMA]",
        """```json
{
  "case_basic_info": {...},
  "party_info": [{"party_id": "p1", "party_name": "string", ...}],
  "claims": [{"claim_id": "c1", "claim_text_original": "string", ...}],
  "claim_facts": [{"fact_id": "f1", "fact_text_original": "string", ...}],
  "defense_opinions": [{"defense_id": "d1", ...}],
  "counterclaims": [],
  "evidence_list": [{"evidence_id": "e1", ...}],
  "evidence_meta": [{"evidence_id": "e1", ...}],
  "cross_examinations": [],
  "court_records": [],
  "legal_arguments": [],
  "procedural_info": null,
  "existing_judgment_or_mediation": null,
  "original_input": "string"
}
```""",
    )


class MaterialPipeline:
    """材料审核 + 规范化流水线。"""

    def __init__(
        self,
        review_model: str = REVIEW_MODEL,
        normalize_model: str = NORMALIZE_MODEL,
    ) -> None:
        self.review_model = review_model
        self.normalize_model = normalize_model
        self._review_system = _build_review_system_prompt()
        self._normalize_system = _build_normalize_system_prompt()

    # ------------------------------------------------------------------
    # 阶段一：材料审核
    # ------------------------------------------------------------------

    def review(self, raw_material: str) -> MaterialReviewResult:
        """
        对用户原始材料执行双维度审核。

        参数:
            raw_material: 用户提交的口语化原始案件材料

        返回:
            MaterialReviewResult（含 can_proceed、缺失清单、补充指引）
        """
        logger.info("=== 阶段一：材料审核开始 ===")
        user_prompt = prompts.build_review_user_prompt(raw_material)

        content = _call_dashscope(
            self._review_system,
            user_prompt,
            model=self.review_model,
            enable_thinking=True,
        )

        data = parse_json_safely(content)

        # 解析为 Pydantic 对象
        result = MaterialReviewResult(
            case_module=_find_in_set(data.get("case_module"), _VALID_CASE_MODULES, "无法确定"),
            case_type_check=_parse_case_type_check(data.get("case_type_check", {})),
            step_checks=[
                StepRequirementCheck(
                    step_index=s.get("step_index", i + 1),
                    step_name=s.get("step_name", ""),
                    status=_normalize_step_status(s.get("status", "部分不足")),
                    has_required=s.get("has_required", []),
                    missing_items=s.get("missing_items", []),
                    suggestion=s.get("suggestion", ""),
                    special_note=s.get("special_note", ""),
                )
                for i, s in enumerate(data.get("step_checks", []))
            ],
            overall_status=_find_in_set(data.get("overall_status"), _VALID_OVERALL_STATUS, "材料不完整"),
            can_proceed=data.get("can_proceed", False),
            missing_core_materials=data.get("missing_core_materials", []),
            missing_optional_materials=data.get("missing_optional_materials", []),
            upload_instructions=data.get("upload_instructions", ""),
            confidence=_find_in_set(data.get("confidence"), _VALID_CONFIDENCE, "中"),
        )

        logger.info(
            "阶段一完成: case_module=%s can_proceed=%s core_rate=%.0f%%",
            result.case_module,
            result.can_proceed,
            result.case_type_check.core_provided_rate * 100,
        )
        return result

    # ------------------------------------------------------------------
    # 阶段二：材料规范化
    # ------------------------------------------------------------------

    def normalize(
        self,
        raw_material: str,
        case_module: str = "无法确定",
    ) -> NormalizedCaseInput:
        """
        将用户原始材料规范化为 NormalizedCaseInput（对齐 CaseInput）。

        参数:
            raw_material: 用户提交的口语化原始案件材料
            case_module: 阶段一审出的案由类型（提升规范化准确性）

        返回:
            NormalizedCaseInput
        """
        logger.info("=== 阶段二：材料规范化开始（case_module=%s）===", case_module)
        user_prompt = prompts.build_normalize_user_prompt(raw_material, case_module)

        content = _call_dashscope(
            self._normalize_system,
            user_prompt,
            model=self.normalize_model,
            enable_thinking=True,
        )

        data = parse_json_safely(content)
        result = _parse_normalized_case_input(data)
        logger.info(
            "阶段二完成: parties=%d claims=%d facts=%d evidence=%d",
            len(result.party_info),
            len(result.claims),
            len(result.claim_facts),
            len(result.evidence_list),
        )
        return result

    # ------------------------------------------------------------------
    # 串联：审核 + 规范化
    # ------------------------------------------------------------------

    def full(self, raw_material: str) -> MaterialFullResult:
        """
        执行完整的两阶段流水线：先审核，can_proceed=true 时继续规范化。

        参数:
            raw_material: 用户提交的口语化原始案件材料

        返回:
            MaterialFullResult（review + normalized）
        """
        review = self.review(raw_material)

        if not review.can_proceed:
            logger.warning("材料审核未通过，跳过规范化。缺失核心材料: %s", review.missing_core_materials)
            return MaterialFullResult(review=review, normalized=None)

        normalized = self.normalize(raw_material, review.case_module)
        return MaterialFullResult(review=review, normalized=normalized)


# ============================================================================
# 解析辅助函数
# ============================================================================


def _normalize_status(raw: str) -> str:
    """将 LLM 可能输出的带注释状态归一化为标准枚举值。"""
    if raw is None:
        return "缺失"
    raw = raw.strip()
    if "已提供" in raw:
        return "已提供"
    if "部分提供" in raw or "部分" in raw:
        return "部分提供"
    if "缺失" in raw:
        return "缺失"
    # 兜底
    if raw in ("已提供", "部分提供", "缺失"):
        return raw
    return "缺失"


_VALID_OVERALL_STATUS = {"材料充足", "材料基本完整", "材料不完整", "仅有案件摘要"}
_VALID_CASE_MODULES = {"合同纠纷", "婚姻家庭", "侵权纠纷", "劳动争议", "民间借贷", "其他民事案件", "无法确定"}
_VALID_CONFIDENCE = {"高", "中", "低"}


def _find_in_set(raw: str, valid: set, default: str) -> str:
    """模糊匹配：在 raw 中查找是否包含 valid 集合中的某个值。"""
    if raw is None:
        return default
    raw = raw.strip()
    if raw in valid:
        return raw
    for v in valid:
        if v in raw:
            return v
    return default


def _normalize_step_status(raw: str) -> str:
    """将 LLM 输出的步骤状态归一化。"""
    if raw is None:
        return "部分不足"
    raw = raw.strip()
    if "充足" in raw and "不足" not in raw:
        return "充足"
    if "严重" in raw and "缺失" in raw:
        return "严重缺失"
    if "部分" in raw or "不足" in raw:
        return "部分不足"
    if raw in ("充足", "部分不足", "严重缺失"):
        return raw
    return "部分不足"


def _parse_case_type_check(data: dict) -> CaseTypeMaterialCheck:
    items = data.get("checklist", [])
    return CaseTypeMaterialCheck(
        case_module=data.get("case_module", ""),
        checklist=[
            MaterialItem(
                name=item.get("name", ""),
                source_element=item.get("source_element", ""),
                legal_basis=item.get("legal_basis", ""),
                is_core=item.get("is_core", False),
                status=_normalize_status(item.get("status", "缺失")),
                dimension=item.get("dimension", "案由专项"),
                description=item.get("description", ""),
                suggestion=item.get("suggestion", ""),
            )
            for item in items
        ],
        core_provided_rate=data.get("core_provided_rate", 0.0),
        special_rules_note=data.get("special_rules_note", ""),
    )


def _ensure_list(val: Any) -> list:
    """确保值为 list 类型（LLM 可能返回空字符串/null/单值）。"""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip() == "":
        return []
    if isinstance(val, (str, dict)):
        return [val] if val else []
    return []


def _ensure_str(val: Any, default: str = "") -> str:
    """确保值为 str 类型。"""
    if val is None:
        return default
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def _ensure_float(val: Any) -> Optional[float]:
    """确保值为 float 或 None。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace(",", "").replace("，", "").replace("元", "").strip())
        except ValueError:
            return None
    return None


def _ensure_bool(val: Any, default: bool = False) -> bool:
    """确保值为 bool。"""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "是", "yes", "1")
    return bool(val)


def _safe_party_info(p: dict) -> PartyInfo:
    return PartyInfo(
        party_id=_ensure_str(p.get("party_id"), f"p{p.get('party_id', '?')}"),
        party_name=p.get("party_name"),
        party_role=p.get("party_role"),
        legal_status=p.get("legal_status"),
        relationship_to_case=p.get("relationship_to_case"),
        identity_evidence=_ensure_list(p.get("identity_evidence")),
        standing_issue=_ensure_bool(p.get("standing_issue")),
    )


def _safe_claim(c: dict) -> ClaimObject:
    return ClaimObject(
        claim_id=_ensure_str(c.get("claim_id"), "c_unknown"),
        claim_text_original=_ensure_str(c.get("claim_text_original")),
        claim_text_normalized=c.get("claim_text_normalized"),
        claimant=_safe_optional_str(c.get("claimant")),
        respondent=_safe_optional_str(c.get("respondent")),
        claim_type_candidate=_ensure_list(c.get("claim_type_candidate")),
        object_type=_safe_optional_str(c.get("object_type")),
        amount=_ensure_float(c.get("amount")),
        behavior_requested=_safe_optional_str(c.get("behavior_requested")),
        is_clear=_ensure_bool(c.get("is_clear"), True),
        is_executable=_ensure_bool(c.get("is_executable"), True),
        supplement_needed=_ensure_bool(c.get("supplement_needed")),
        priority_type=_safe_optional_str(c.get("priority_type")),
    )


def _safe_optional_str(val: Any) -> Optional[str]:
    """确保值为 Optional[str]（LLM 可能返回 list/dict/None）。"""
    if val is None:
        return None
    if isinstance(val, str):
        return val if val.strip() else None
    if isinstance(val, list) and val:
        return str(val[0]) if val[0] else None
    if isinstance(val, (int, float)):
        return str(val)
    return None


def _safe_fact(f: dict) -> ClaimFactObject:
    return ClaimFactObject(
        fact_id=_ensure_str(f.get("fact_id"), "f_unknown"),
        fact_text_original=_ensure_str(f.get("fact_text_original")),
        fact_text_normalized=f.get("fact_text_normalized"),
        fact_time=f.get("fact_time"),
        fact_actor=f.get("fact_actor"),
        fact_counterparty=f.get("fact_counterparty"),
        fact_type_candidate=_ensure_list(f.get("fact_type_candidate")),
        linked_claim_id=_safe_optional_str(f.get("linked_claim_id")),
        linked_evidence_ids=_ensure_list(f.get("linked_evidence_ids")),
        possible_fact_slot=_ensure_list(f.get("possible_fact_slot")),
        clarity_status=f.get("clarity_status"),
        opponent_response=f.get("opponent_response"),
    )


def _safe_defense(d: dict) -> DefenseObject:
    return DefenseObject(
        defense_id=_ensure_str(d.get("defense_id"), "d_unknown"),
        defense_text_original=_ensure_str(d.get("defense_text_original")),
        defense_text_normalized=d.get("defense_text_normalized"),
        defense_target_claim_id=_safe_optional_str(d.get("defense_target_claim_id")),
        response_type=_safe_optional_str(d.get("response_type")),
        defense_type_candidate=_ensure_list(d.get("defense_type_candidate")),
        new_fact_asserted=_ensure_bool(d.get("new_fact_asserted")),
        linked_evidence_ids=_ensure_list(d.get("linked_evidence_ids")),
        possible_defense_basis=_ensure_list(d.get("possible_defense_basis")),
        clarification_needed=_ensure_bool(d.get("clarification_needed")),
    )


def _safe_evidence(e: dict) -> EvidenceObject:
    return EvidenceObject(
        evidence_id=_ensure_str(e.get("evidence_id"), "e_unknown"),
        evidence_name=_ensure_str(e.get("evidence_name"), "未命名证据"),
        submitted_by=_safe_optional_str(e.get("submitted_by")),
        evidence_type=_safe_optional_str(e.get("evidence_type")),
        proof_purpose_original=_safe_optional_str(e.get("proof_purpose_original")),
        proof_purpose_normalized=_safe_optional_str(e.get("proof_purpose_normalized")),
        linked_claim_id=_safe_optional_str(e.get("linked_claim_id")),
        linked_defense_id=_safe_optional_str(e.get("linked_defense_id")),
        linked_fact_ids=_ensure_list(e.get("linked_fact_ids")),
        linked_element_ids=_ensure_list(e.get("linked_element_ids")),
        opponent_cross_examination=_safe_optional_str(e.get("opponent_cross_examination")),
        legality_status=_safe_optional_str(e.get("legality_status")),
        relevance_status=_safe_optional_str(e.get("relevance_status")),
        authenticity_status=_safe_optional_str(e.get("authenticity_status")),
        probative_force=_safe_optional_str(e.get("probative_force")),
        adopted_status=_safe_optional_str(e.get("adopted_status")),
    )


def _parse_normalized_case_input(data: dict) -> NormalizedCaseInput:
    """将 LLM 返回的 JSON dict 解析为 NormalizedCaseInput（带类型容错）。"""
    return NormalizedCaseInput(
        case_basic_info=CaseBasicInfo(**data.get("case_basic_info", {})),
        party_info=[_safe_party_info(p) for p in data.get("party_info", [])],
        claims=[_safe_claim(c) for c in data.get("claims", [])],
        claim_facts=[_safe_fact(f) for f in data.get("claim_facts", [])],
        defense_opinions=[_safe_defense(d) for d in data.get("defense_opinions", [])],
        counterclaims=[
            CounterclaimObject(
                counterclaim_id=_ensure_str(cc.get("counterclaim_id"), "cc_unknown"),
                counterclaim_text=_ensure_str(cc.get("counterclaim_text")),
                counterclaim_type_candidate=_ensure_list(cc.get("counterclaim_type_candidate")),
                linked_evidence_ids=_ensure_list(cc.get("linked_evidence_ids")),
            )
            for cc in data.get("counterclaims", [])
        ],
        evidence_list=[_safe_evidence(e) for e in data.get("evidence_list", [])],
        evidence_meta=[
            EvidenceMeta(
                evidence_id=_ensure_str(em.get("evidence_id"), "e_unknown"),
                subtype=_ensure_str(em.get("subtype")),
                completeness=em.get("completeness", "待核实"),
                authenticity_note=_ensure_str(em.get("authenticity_note")),
                standalone_capable=_ensure_bool(em.get("standalone_capable"), True),
                standalone_limitation=_ensure_str(em.get("standalone_limitation")),
            )
            for em in data.get("evidence_meta", [])
        ],
        cross_examinations=[
            CrossExaminationObject(
                cross_id=_ensure_str(cx.get("cross_id"), "x_unknown"),
                evidence_id=_ensure_str(cx.get("evidence_id")),
                opponent=cx.get("opponent"),
                legality_opinion=cx.get("legality_opinion"),
                relevance_opinion=cx.get("relevance_opinion"),
                authenticity_opinion=cx.get("authenticity_opinion"),
                probative_force_opinion=cx.get("probative_force_opinion"),
                reason=cx.get("reason"),
                need_supplementary_proof=_ensure_bool(cx.get("need_supplementary_proof")),
            )
            for cx in data.get("cross_examinations", [])
        ],
        court_records=_ensure_list(data.get("court_records")),
        legal_arguments=[
            LegalArgumentObject(
                argument_id=_ensure_str(la.get("argument_id"), "la_unknown"),
                submitted_by=la.get("submitted_by"),
                target_claim_or_defense=la.get("target_claim_or_defense"),
                cited_law_name=la.get("cited_law_name"),
                cited_article_no=la.get("cited_article_no"),
                argument_text=la.get("argument_text"),
                norm_type_candidate=_ensure_list(la.get("norm_type_candidate")),
                dispute_status=la.get("dispute_status"),
                court_view_needed=_ensure_bool(la.get("court_view_needed")),
            )
            for la in data.get("legal_arguments", [])
        ],
        procedural_info=(
            ProceduralInfo(**data["procedural_info"])
            if data.get("procedural_info")
            else None
        ),
        existing_judgment_or_mediation=data.get("existing_judgment_or_mediation"),
        original_input=_ensure_str(data.get("original_input")),
    )
