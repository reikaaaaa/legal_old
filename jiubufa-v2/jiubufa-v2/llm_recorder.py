"""
LLM 进度记录器 —— 包装 task_store，提供语义化的步骤进度更新。

用法:
    from task_store import create_task, update_task
    from llm_recorder import TaskProgressRecorder

    task_id = create_task(case_preview=..., total_steps=12)
    rec = TaskProgressRecorder(task_id)

    # 材料层
    rec.step_start(0, "材料审核")
    # ... LLM 调用 ...
    rec.step_done(0, "材料审核", summary="审核通过，案由：买卖合同纠纷")

    # 九步法
    rec.step_start(1, "Step1 固定权利请求")
    # ... LLM 调用 ...
    rec.step_done(1, "Step1 固定权利请求", summary="识别 2 项诉请")

    rec.finish(result={...})
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from task_store import get_task, update_task


class TaskProgressRecorder:
    """任务的步骤级进度记录器。"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def step_start(self, index: int, name: str, message: str = "") -> None:
        update_task(
            self.task_id,
            status="running",
            current_step_index=index,
            current_step=name,
            message=message or f"正在执行: {name}",
        )

    def step_done(
        self,
        index: int,
        name: str,
        *,
        summary: str = "",
        progress: Optional[int] = None,
        step_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "step_index": index,
            "step_name": name,
            "summary": summary,
        }
        if step_result:
            payload.update(step_result)

        kwargs: Dict[str, Any] = {
            "current_step": name,
            "message": summary or f"{name} 完成",
            "step_result": payload,
        }
        if progress is not None:
            kwargs["progress"] = progress

        update_task(self.task_id, **kwargs)

    def set_errors(self, errors: list[str]) -> None:
        update_task(self.task_id, errors=errors)

    def set_warnings(self, warnings: list[str]) -> None:
        update_task(self.task_id, warnings=warnings)

    def finish(self, result: Any = None) -> None:
        update_task(
            self.task_id,
            status="finished",
            message="分析完成",
            result=result,
        )

    def fail(self, message: str) -> None:
        data = get_task(self.task_id)
        errors = list(data.get("errors") or []) if data else []
        errors.append(message)
        update_task(
            self.task_id,
            status="failed",
            message=message,
            errors=errors,
        )


def make_orchestrator_callback(
    recorder: TaskProgressRecorder,
    base_progress: int = 20,
    step_range: int = 70,
) -> Callable:
    """
    生成 orchestrator 的 progress_callback。

    orchestrator 有 9 个步骤 (step1→step9) + 保底裁判门 + 裁决分支，
    共 ~11 个子步骤。base_progress 是起始进度值（材料层占前 20%），
    step_range 是九步法占总进度的百分比（70%）。

    回调签名: callback(step_number: int, step_name: str, status: str, summary: str)
    """
    total_substeps = 11

    def callback(step_number: int, step_name: str, status: str, summary: str) -> None:
        progress = base_progress + int(step_range * step_number / total_substeps)
        recorder.step_done(
            index=step_number,
            name=step_name,
            summary=summary,
            progress=min(progress, 98),
        )

    return callback
