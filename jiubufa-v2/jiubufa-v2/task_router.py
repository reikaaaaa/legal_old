"""
异步任务路由 —— 将耗时的材料层+九步法改为后台执行+前端轮询。

端点:
    POST /api/case/start       — 提交案件，立即返回 task_id
    GET  /api/case/status/{id} — 轮询任务进度
    GET  /api/case/result/{id} — 拉取最终结果
    GET  /api/case/events/{id} — SSE 实时进度推送
    GET  /api/case/list        — 列出最近任务
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from task_store import (
    RUNTIME_DIR,
    cleanup_expired,
    create_task,
    get_task,
    get_task_result,
    get_task_status,
    update_task,
)
from llm_recorder import TaskProgressRecorder, make_orchestrator_callback

logger = logging.getLogger("task_router")

task_router = APIRouter(prefix="/api/case", tags=["async_case"])

# 后台任务引用（用于取消）
_bg_tasks: Dict[str, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════════════════════

class CaseStartRequest(BaseModel):
    raw_material: str = Field(..., description="用户提交的原始案件材料文本")
    case_module: str = Field(default="无法确定", description="案由类型提示")
    run_mode: str = Field(default="full", description="full | material_only | jiubufa_only")
    model_name: Optional[str] = Field(default=None, description="九步法模型，默认 dashscope-qwen-plus")


# ═══════════════════════════════════════════════════════════════════════════
# 后台执行器
# ═══════════════════════════════════════════════════════════════════════════

async def _run_full_pipeline(
    task_id: str,
    raw_material: str,
    case_module: str,
    model_name: Optional[str],
) -> None:
    """后台执行：材料审核 → 规范化 → 九步法。"""
    rec = TaskProgressRecorder(task_id)
    total_steps = 14  # 材料审核(1) + 规范化(1) + 九步法9步 + 裁判门(1) + 裁决(1) + 报告(1)

    update_task(task_id, status="running",
                current_step="材料审核", message="正在审核案件材料…")

    try:
        # ── 阶段一：材料审核 ──
        rec.step_start(0, "材料审核", "正在分析材料完整性…")
        pipeline = _get_material_pipeline()

        loop = asyncio.get_event_loop()
        review = await loop.run_in_executor(None, pipeline.review, raw_material)
        rec.step_done(0, "材料审核", progress=7,
                      summary=f"审核{'通过' if review.can_proceed else '未通过'}，"
                              f"案由：{review.case_module}，"
                              f"核心材料提供率：{int(review.case_type_check.core_provided_rate * 100)}%",
                      step_result={"can_proceed": review.can_proceed,
                                   "case_module": review.case_module,
                                   "missing_core": review.missing_core_materials[:5]})

        # ── 阶段二：材料规范化 ──
        rec.step_start(1, "材料规范化", "正在将案件材料转为结构化输入…")
        normalized = await loop.run_in_executor(
            None, pipeline.normalize, raw_material, review.case_module
        )
        rec.step_done(1, "材料规范化", progress=14,
                      summary=f"已抽取 {len(normalized.party_info)} 方当事人、"
                              f"{len(normalized.claims)} 项诉请、"
                              f"{len(normalized.claim_facts)} 条事实、"
                              f"{len(normalized.evidence_list)} 件证据")

        case_module_detected = review.case_module or case_module

        # ── 构建 CaseInput ──
        case_input_dict = _normalized_to_case_input_dict(normalized)

        # ── 阶段三：九步法 ──
        orchestrator_callback = make_orchestrator_callback(rec, base_progress=14, step_range=77)
        _import_orchestrator()
        from orchestrator import run_workflow  # noqa: E402

        # 包装 orchestrator 使其在每个 step 后回调
        wrapped_result = await loop.run_in_executor(
            None,
            _run_jiubufa_with_hooks,
            case_input_dict,
            model_name,
            orchestrator_callback,
        )

        result, jiubufa_result = wrapped_result

        if result.get("status") == "error":
            rec.fail(result.get("message", "九步法执行失败"))
            return

        # ── 构建最终输出 ──
        final_result = {
            "review": review.model_dump(mode="json"),
            "normalized": normalized.model_dump(mode="json"),
            "jiubufa": jiubufa_result,
            "case_module": case_module_detected,
            "case_preview": raw_material[:200],
            "timings_ms": jiubufa_result.get("timings_ms", {}) if jiubufa_result else {},
        }

        if jiubufa_result:
            errs = jiubufa_result.get("errors", [])
            warns = jiubufa_result.get("warnings", [])
            if errs:
                rec.set_errors(errs)
            if warns:
                rec.set_warnings(warns)

        rec.finish(result=final_result)

    except Exception as exc:
        logger.exception("后台任务 %s 失败", task_id)
        rec.fail(f"任务执行异常: {exc}")
    finally:
        _bg_tasks.pop(task_id, None)


def _run_jiubufa_with_hooks(
    case_input_dict: Dict[str, Any],
    model_name: Optional[str],
    progress_callback,
):
    """在同步线程中跑九步法，通过 progress_callback 报告进度。

    需要 hack orchestrator._safe_run_step 来在每个 step 后回调。
    策略：monkey-patch 临时替换 _safe_run_step，执行完后恢复。
    """
    import orchestrator as orch
    from orchestrator import run_workflow
    from schemas import CaseInput

    case_input = CaseInput(**case_input_dict)

    original_safe_run = orch._safe_run_step
    step_counter = [0]  # mutable counter
    step_names = {
        "step1": "Step1 固定权利请求",
        "step2": "Step2 请求权基础规范",
        "step3": "Step3 抗辩权基础规范",
        "step4": "Step4 构成要件分析",
        "step5": "Step5 诉讼主张检索",
        "step6": "Step6 争点整理",
        "step7": "Step7 要件事实证明",
        "step8": "Step8 事实认定",
        "step9": "Step9 要件归入与裁判",
        "fallback": "保底裁判门与裁决",
        "strong_branch": "强裁判分支",
        "weak_branch": "弱裁判分支",
        "partial": "部分输出生成",
    }

    def hooked_safe_run(state, step_attr, fn):
        result = original_safe_run(state, step_attr, fn)
        step_counter[0] += 1
        name = step_names.get(step_attr, step_attr)
        status_str = "ok" if not any(e for e in state.errors if step_attr in str(e)) else "error"
        summary = f"{name} 完成"
        try:
            progress_callback(step_counter[0], name, status_str, summary)
        except Exception:
            pass
        return result

    orch._safe_run_step = hooked_safe_run

    try:
        if model_name:
            os.environ["JIUBUFA_MODEL_OVERRIDE"] = model_name
        result = run_workflow(case_input)
        result_dict = result.model_dump(mode="json")
        return {"status": "ok"}, result_dict
    except Exception as exc:
        logger.exception("九步法执行失败")
        return {"status": "error", "message": str(exc)}, None
    finally:
        orch._safe_run_step = original_safe_run


def _normalized_to_case_input_dict(normalized) -> Dict[str, Any]:
    """将 NormalizedCaseInput 转为 CaseInput 的 dict。"""
    return {
        "case_basic_info": normalized.case_basic_info.model_dump(mode="json")
            if hasattr(normalized.case_basic_info, "model_dump") else {},
        "party_info": [p.model_dump(mode="json") if hasattr(p, "model_dump") else {}
                        for p in (normalized.party_info or [])],
        "claims": [c.model_dump(mode="json") if hasattr(c, "model_dump") else {}
                    for c in (normalized.claims or [])],
        "claim_facts": [f.model_dump(mode="json") if hasattr(f, "model_dump") else {}
                         for f in (normalized.claim_facts or [])],
        "defense_opinions": [d.model_dump(mode="json") if hasattr(d, "model_dump") else {}
                              for d in (normalized.defense_opinions or [])],
        "counterclaims": [c.model_dump(mode="json") if hasattr(c, "model_dump") else {}
                           for c in (normalized.counterclaims or [])],
        "evidence_list": [e.model_dump(mode="json") if hasattr(e, "model_dump") else {}
                           for e in (normalized.evidence_list or [])],
        "cross_examinations": [x.model_dump(mode="json") if hasattr(x, "model_dump") else {}
                                for x in (normalized.cross_examinations or [])],
        "court_records": normalized.court_records or [],
        "legal_arguments": [a.model_dump(mode="json") if hasattr(a, "model_dump") else {}
                             for a in (normalized.legal_arguments or [])],
        "procedural_info": normalized.procedural_info.model_dump(mode="json")
            if normalized.procedural_info and hasattr(normalized.procedural_info, "model_dump")
            else None,
        "existing_judgment_or_mediation": normalized.existing_judgment_or_mediation or None,
        "fallback_user_choice": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Material pipeline 懒加载
# ═══════════════════════════════════════════════════════════════════════════

_pipeline = None


def _get_material_pipeline():
    global _pipeline
    if _pipeline is None:
        _import_material()
        from material_agent import MaterialPipeline  # noqa: E402
        _pipeline = MaterialPipeline()
    return _pipeline


def _import_material():
    """确保 cailiaoceng_rule5.11 在 sys.path 最前面。"""
    material_dir = str(Path(__file__).resolve().parent.parent / "cailiaoceng_rule5.11")
    curdir = str(Path(__file__).resolve().parent)
    for p in [curdir, material_dir]:
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, material_dir)
    sys.path.insert(0, curdir)


def _import_orchestrator():
    """确保 jiubufa-v2 的 schemas 在 material 之前加载。"""
    curdir = str(Path(__file__).resolve().parent)
    material_dir = str(Path(__file__).resolve().parent.parent / "cailiaoceng_rule5.11")
    if curdir in sys.path:
        sys.path.remove(curdir)
    if material_dir in sys.path:
        sys.path.remove(material_dir)
    sys.path.insert(0, curdir)


# ═══════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════

@task_router.post("/start")
async def case_start(req: CaseStartRequest):
    """提交案件材料，启动后台分析，立即返回 task_id。"""
    if not req.raw_material or not req.raw_material.strip():
        raise HTTPException(status_code=400, detail="案件材料不能为空")

    # 清理过期任务（惰性）
    try:
        cleanup_expired()
    except Exception:
        pass

    task_id = create_task(
        case_preview=req.raw_material[:200],
        run_mode=req.run_mode,
        model_name=req.model_name or "dashscope-qwen-plus",
    )

    # 启动后台任务（不 await，让 FastAPI 事件循环管理）
    bg = asyncio.create_task(
        _run_full_pipeline(
            task_id,
            req.raw_material,
            req.case_module,
            req.model_name,
        )
    )
    bg.add_done_callback(
        lambda t: logger.error("后台任务 %s 异常: %s", task_id, t.exception())
        if t.exception() else None
    )
    _bg_tasks[task_id] = bg

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "任务已创建，后台开始执行",
        "poll_url": f"/api/case/status/{task_id}",
        "result_url": f"/api/case/result/{task_id}",
        "events_url": f"/api/case/events/{task_id}",
    }


@task_router.get("/status/{task_id}")
async def case_status(task_id: str):
    """轮询任务状态与进度。"""
    status = get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return status


@task_router.get("/result/{task_id}")
async def case_result(task_id: str):
    """获取任务最终结果（仅 finished 状态时返回完整结果）。"""
    data = get_task(task_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    if data["status"] == "failed":
        return {
            "task_id": task_id,
            "status": "failed",
            "message": data.get("message", ""),
            "errors": data.get("errors", []),
            "step_results": data.get("step_results", []),
        }

    result = get_task_result(task_id)
    if result is None:
        return {
            "task_id": task_id,
            "status": data["status"],
            "progress": data["progress"],
            "current_step": data["current_step"],
            "message": "任务尚未完成",
            "step_results": data.get("step_results", []),
        }

    return result


@task_router.get("/events/{task_id}")
async def case_events(task_id: str):
    """SSE 端点：持续推送任务进度事件。

    事件类型:
    - progress: {progress, current_step, message}
    - step_done: {step_index, step_name, summary}
    - finished: {result}
    - failed: {message}
    - heartbeat: 每 15 秒保活
    """

    async def _event_stream():
        last_progress = -1
        heartbeat_count = 0

        while True:
            data = get_task(task_id)
            if data is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'}, ensure_ascii=False)}\n\n"
                return

            status = data["status"]

            # 进度更新事件
            current_progress = data.get("progress", 0)
            if current_progress != last_progress:
                last_progress = current_progress
                yield f"data: {json.dumps({'type': 'progress', 'progress': current_progress, 'current_step': data.get('current_step', ''), 'message': data.get('message', '')}, ensure_ascii=False)}\n\n"

            # 新步骤完成事件
            step_results = data.get("step_results", [])
            if step_results:
                latest_step = step_results[-1]
                yield f"data: {json.dumps({'type': 'step_done', **latest_step}, ensure_ascii=False)}\n\n"
                # 只消费一次（通过更新 task 的 step_results 为已发送标记）
                # 简化处理：靠 progress 变化去重

            if status == "finished":
                yield f"data: {json.dumps({'type': 'finished', 'result': data.get('result')}, ensure_ascii=False)}\n\n"
                return

            if status == "failed":
                yield f"data: {json.dumps({'type': 'failed', 'message': data.get('message', '')}, ensure_ascii=False)}\n\n"
                return

            # 心跳（每 ~15 秒一次）
            heartbeat_count += 1
            if heartbeat_count % 5 == 0:  # 5 * 3s = 15s
                yield f"data: {json.dumps({'type': 'heartbeat', 'ts': time.time()})}\n\n"

            await asyncio.sleep(3)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@task_router.get("/list")
async def case_list(limit: int = 20):
    """列出最近的任务（按修改时间倒序）。"""
    files = sorted(
        RUNTIME_DIR.glob("task_*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    tasks = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tasks.append({
                "task_id": data.get("task_id"),
                "status": data.get("status"),
                "progress": data.get("progress"),
                "current_step": data.get("current_step"),
                "case_preview": data.get("case_preview", "")[:100],
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return {"tasks": tasks, "total": len(tasks)}
