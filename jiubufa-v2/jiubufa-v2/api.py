"""
FastAPI 服务层。

启动方式：
    uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1

主要端点：
    GET  /api/health                      —— 健康检查 + 模型注册表
    POST /api/workflow/run                —— 跑完整九步法工作流
    POST /api/workflow/score_only         —— 仅跑 step1~step8 + 评分（不出裁判）
    GET  /api/kb/stats                    —— 知识库加载状态
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import DEFAULT_MODEL_ID, MODEL_REGISTRY
from kb import get_default_kb
from material_router import material_router
from orchestrator import run_workflow
from schemas import CaseInput, WorkflowResult
from task_router import task_router
from task_store import RUNTIME_DIR, cleanup_expired

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jiubufa.api")


app = FastAPI(
    title="九步法审案工作流",
    description="基于五层法律标签库与九步法的智能裁判后端。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册材料规范层路由
app.include_router(material_router)

# 注册异步任务路由（轮询/SSE 模式）
app.include_router(task_router)

# ── 启动事件 ──
@app.on_event("startup")
async def on_startup():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    removed = cleanup_expired()
    if removed:
        logger.info("启动时清理了 %d 个过期任务文件", removed)
    logger.info("runtime_tasks 目录已就绪: %s", RUNTIME_DIR)


# ── Debug Viewer（仅 DEBUG_TRACE=true 时挂载） ──
if os.getenv("DEBUG_TRACE", "false").lower() == "true":
    from debug_viewer.debug_router import router as debug_router
    app.include_router(debug_router)
    logger.info("DEBUG_TRACE=true，已挂载 /debug 检阅器路由")

# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    default_model: str
    models: Dict[str, Any]
    kb_loaded: bool
    kb_size: int


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        kb = get_default_kb()
        kb_loaded = True
        kb_size = len(kb.rule_units)
    except Exception as exc:  # noqa: BLE001
        logger.warning("知识库加载失败：%s", exc)
        kb_loaded = False
        kb_size = 0

    return HealthResponse(
        default_model=DEFAULT_MODEL_ID,
        models={k: v for k, v in MODEL_REGISTRY.items()},
        kb_loaded=kb_loaded,
        kb_size=kb_size,
    )


# ---------------------------------------------------------------------------
# 知识库统计
# ---------------------------------------------------------------------------


@app.get("/api/kb/stats")
def kb_stats() -> Dict[str, Any]:
    try:
        kb = get_default_kb()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"知识库加载失败：{exc}")
    return {
        "total_rule_units": len(kb.rule_units),
        "by_workflow_step": {k: len(v) for k, v in kb._idx_workflow_step.items()},
        "by_legal_domain": {k: len(v) for k, v in kb._idx_legal_domain.items()},
        "by_norm_type": {k: len(v) for k, v in kb._idx_norm_type.items()},
        "by_claim_type": {k: len(v) for k, v in kb._idx_claim_type.items()},
        "by_defense_type": {k: len(v) for k, v in kb._idx_defense_type.items()},
    }


# ---------------------------------------------------------------------------
# 工作流执行
# ---------------------------------------------------------------------------


class RunWorkflowRequest(BaseModel):
    """与 CaseInput 字段一致；额外允许 model_name 覆盖默认模型。"""

    case_input: CaseInput
    model_name: Optional[str] = None


@app.post("/api/workflow/run", response_model=WorkflowResult)
def workflow_run(req: RunWorkflowRequest) -> WorkflowResult:
    """执行完整的九步法工作流。"""
    trace = None
    if os.getenv("DEBUG_TRACE", "false").lower() == "true":
        from debug_viewer.trace_collector import TraceCollector
        trace = TraceCollector()
        trace.log_step(step_name="接收请求", input_data=req.model_dump(mode="json"),
                       logic=["接收前端 /api/workflow/run 请求", "校验 model_name 与 CaseInput"])
    try:
        if req.model_name and req.model_name not in MODEL_REGISTRY:
            raise HTTPException(
                status_code=400,
                detail=f"未注册的模型：{req.model_name}。可用：{list(MODEL_REGISTRY)}",
            )
        result = run_workflow(req.case_input, trace=trace)
        if trace:
            trace.log_step(step_name="返回结果", output_data={"status": result.status, "errors": result.errors, "warnings": result.warnings})
            trace.finish(status=result.status)
        return result
    except HTTPException:
        if trace:
            trace.finish(status="blocked")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_run 内部异常")
        if trace:
            trace.log_step(step_name="异常捕获", error=str(exc))
            trace.finish(status="failed")
        raise HTTPException(status_code=500, detail=f"工作流执行失败：{exc}")


@app.post("/api/workflow/score_only")
def workflow_score_only(req: RunWorkflowRequest) -> Dict[str, Any]:
    """
    仅跑前 8 步并返回评分 + 用户选择门，不输出裁判倾向。

    用于前端在调用方还没拿到用户选择时，先看一下输入完整度。
    """
    # 强制不让前端用户在此端点接收裁判输出
    case = req.case_input.model_copy(update={"fallback_user_choice": None})
    result = run_workflow(case)

    # 把裁判结果剥离掉
    return {
        "case_id": result.case_id,
        "status": result.status,
        "sufficiency_score": (
            result.fallback_gate.model_dump() if result.fallback_gate else None
        ),
        "errors": result.errors,
        "warnings": result.warnings,
        "timings_ms": result.timings_ms,
    }


# ---------------------------------------------------------------------------
# 前端页面
# ---------------------------------------------------------------------------


@app.get("/app", response_class=HTMLResponse)
async def frontend():
    """返回前端应用页面"""
    html_path = Path(__file__).parent / "front_test" / "app.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>前端文件未找到</h1>"
