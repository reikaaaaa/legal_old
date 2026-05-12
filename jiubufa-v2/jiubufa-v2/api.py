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
    try:
        if req.model_name and req.model_name not in MODEL_REGISTRY:
            raise HTTPException(
                status_code=400,
                detail=f"未注册的模型：{req.model_name}。可用：{list(MODEL_REGISTRY)}",
            )
        # model_name 通过环境/配置层切换；当前 LLMClient 无 per-call alias，
        # 走默认客户端即可；如需覆盖默认模型，请改 settings.DEFAULT_MODEL。
        result = run_workflow(req.case_input)
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow_run 内部异常")
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
