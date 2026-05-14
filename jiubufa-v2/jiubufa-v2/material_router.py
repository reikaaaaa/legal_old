"""
材料规范层 FastAPI 路由。

挂载到主 api.py 后提供:
    POST /material/full       — 审核 + 规范化（串联）
    POST /material/review     — 仅审核
    POST /material/normalize  — 仅规范化
    POST /material/supplement — 补充材料后重新审核

启动方式——在 api.py 中添加:
    from material_router import material_router
    app.include_router(material_router)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 确保 cailiaoceng_rule5.11 在 path 最前面（避免与 jiubufa-v2 的 schemas 冲突）
_MATERIAL_DIR = Path(__file__).resolve().parent.parent / "cailiaoceng_rule5.11"
# 临时移除可能冲突的路径
_curdir = str(Path(__file__).resolve().parent)
if _curdir in sys.path:
    sys.path.remove(_curdir)
sys.path.insert(0, str(_MATERIAL_DIR))
sys.path.insert(0, _curdir)  # 恢复，但放在 material 之后

from material_agent import MaterialPipeline

logger = logging.getLogger("material_router")

material_router = APIRouter(prefix="/material", tags=["material"])

# 全局流水线实例（单例）
_pipeline: Optional[MaterialPipeline] = None


def get_pipeline() -> MaterialPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = MaterialPipeline()
    return _pipeline


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class MaterialReviewRequest(BaseModel):
    raw_material: str = Field(..., description="用户提交的原始案件材料文本")


class MaterialNormalizeRequest(BaseModel):
    raw_material: str = Field(..., description="用户提交的原始案件材料文本")
    case_module: str = Field(default="无法确定", description="案由提示")


class MaterialSupplementRequest(BaseModel):
    original: str = Field(..., description="原始材料文本")
    supplement: str = Field(..., description="用户补充的材料文本")


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@material_router.post("/review")
async def material_review(req: MaterialReviewRequest):
    """阶段一：材料审核。返回 MaterialReviewResult。"""
    try:
        pipeline = get_pipeline()
        result = pipeline.review(req.raw_material)
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("材料审核失败")
        raise HTTPException(status_code=500, detail=f"材料审核失败：{exc}")


@material_router.post("/normalize")
async def material_normalize(req: MaterialNormalizeRequest):
    """阶段二：材料规范化。返回 NormalizedCaseInput。"""
    try:
        pipeline = get_pipeline()
        result = pipeline.normalize(req.raw_material, req.case_module)
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("材料规范化失败")
        raise HTTPException(status_code=500, detail=f"材料规范化失败：{exc}")


@material_router.post("/full")
async def material_full(req: MaterialReviewRequest):
    """
    完整流水线：先审核，can_proceed=true 时继续规范化。
    返回 MaterialFullResult { review, normalized }。
    """
    trace = None
    if os.getenv("DEBUG_TRACE", "false").lower() == "true":
        from debug_viewer.trace_collector import TraceCollector
        trace = TraceCollector()
        trace.log_step(step_name="材料接收", input_data={"raw_material_preview": req.raw_material[:500]},
                       logic=["接收用户原始案件材料", "传入材料规范层流水线"])

    try:
        pipeline = get_pipeline()
        result = pipeline.full(req.raw_material, trace=trace)

        if trace:
            trace.log_step(step_name="前端返回结果", output_data={"review_keys": list(result.review.model_dump(mode="json").keys()),
                            "can_proceed": result.review.can_proceed, "has_normalized": result.normalized is not None})
            trace.finish(status="success")

        return {
            "review": result.review.model_dump(mode="json"),
            "normalized": (
                result.normalized.model_dump(mode="json")
                if result.normalized
                else None
            ),
        }
    except Exception as exc:
        logger.exception("材料审核+规范化失败")
        if trace:
            trace.log_step(step_name="异常捕获", error=str(exc))
            trace.finish(status="failed")
        raise HTTPException(status_code=500, detail=f"材料处理失败：{exc}")


@material_router.post("/supplement")
async def material_supplement(req: MaterialSupplementRequest):
    """
    补充材料后重新审核 + 规范化。
    将原始材料与补充材料合并后重新执行完整流水线。
    """
    merged = f"{req.original}\n\n【用户补充材料】\n{req.supplement}"

    trace = None
    if os.getenv("DEBUG_TRACE", "false").lower() == "true":
        from debug_viewer.trace_collector import TraceCollector
        trace = TraceCollector()
        trace.log_step(step_name="补充材料接收", input_data={"original_preview": req.original[:300], "supplement_preview": req.supplement[:300]},
                       logic=["合并原始材料与补充材料", "重新执行完整材料规范层流水线"])

    try:
        pipeline = get_pipeline()
        result = pipeline.full(merged, trace=trace)

        if trace:
            trace.finish(status="success")

        return {
            "review": result.review.model_dump(mode="json"),
            "normalized": (
                result.normalized.model_dump(mode="json")
                if result.normalized
                else None
            ),
        }
    except Exception as exc:
        logger.exception("补充材料处理失败")
        if trace:
            trace.log_step(step_name="异常捕获", error=str(exc))
            trace.finish(status="failed")
        raise HTTPException(status_code=500, detail=f"补充材料处理失败：{exc}")
