"""
任务状态存储 —— 文件级 JSON 持久化。

每个任务一个 JSON 文件，位于 runtime_tasks/{task_id}.json。
线程安全（Lock 保护），支持 TTL 自动清理。

存储结构:
    {
        "task_id": "task_20260518_143052_abc123",
        "status": "pending" | "running" | "finished" | "failed",
        "progress": 0-100,
        "current_step": "材料审核",
        "current_step_index": 0,
        "total_steps": 12,
        "message": "正在审核案件材料...",
        "result": null | {...},
        "errors": [],
        "warnings": [],
        "step_results": [],         # 每步 LLM 返回内容的摘要
        "created_at": "ISO8601",
        "updated_at": "ISO8601",
        "finished_at": null | "ISO8601",
        "case_preview": "前200字",
        "run_mode": "full" | "fast" | "material_only",
        "model_name": "qwen3.6-max-preview"
    }
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import PROJECT_ROOT

RUNTIME_DIR = PROJECT_ROOT / "runtime_tasks"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

TTL_SECONDS = 86400  # 24 小时后清理

_write_lock = threading.Lock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _make_task_id() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"task_{ts}_{short}"


def _task_path(task_id: str) -> Path:
    return RUNTIME_DIR / f"{task_id}.json"


def create_task(
    *,
    case_preview: str = "",
    run_mode: str = "full",
    model_name: str = "",
    total_steps: int = 12,
) -> str:
    """创建新任务，返回 task_id。"""
    task_id = _make_task_id()
    now = _now_iso()
    payload: Dict[str, Any] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "current_step": "等待启动",
        "current_step_index": 0,
        "total_steps": total_steps,
        "message": "任务已创建",
        "result": None,
        "errors": [],
        "warnings": [],
        "step_results": [],
        "created_at": now,
        "updated_at": now,
        "finished_at": None,
        "case_preview": case_preview[:200],
        "run_mode": run_mode,
        "model_name": model_name,
    }
    _write(task_id, payload)
    return task_id


def update_task(
    task_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    current_step: Optional[str] = None,
    current_step_index: Optional[int] = None,
    message: Optional[str] = None,
    result: Optional[Any] = None,
    errors: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    step_result: Optional[Dict[str, Any]] = None,
) -> None:
    """增量更新任务状态。只更新传入的非 None 字段。"""
    data = _read(task_id)
    if data is None:
        return

    now = _now_iso()
    data["updated_at"] = now

    if status is not None:
        data["status"] = status
        if status in ("finished", "failed"):
            data["finished_at"] = now
            if status == "finished":
                data["progress"] = 100

    if progress is not None:
        data["progress"] = max(0, min(100, progress))

    if current_step is not None:
        data["current_step"] = current_step

    if current_step_index is not None:
        data["current_step_index"] = current_step_index

    if message is not None:
        data["message"] = message

    if result is not None:
        data["result"] = result

    if errors is not None:
        data["errors"] = errors

    if warnings is not None:
        data["warnings"] = warnings

    if step_result is not None:
        step_results = list(data.get("step_results") or [])
        step_results.append(step_result)
        data["step_results"] = step_results

    _write(task_id, data)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """读取任务完整状态。"""
    return _read(task_id)


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """返回前端轮询所需的精简状态。"""
    data = _read(task_id)
    if data is None:
        return None
    return {
        "task_id": data["task_id"],
        "status": data["status"],
        "progress": data["progress"],
        "current_step": data["current_step"],
        "current_step_index": data["current_step_index"],
        "total_steps": data["total_steps"],
        "message": data["message"],
        "errors": data.get("errors", []),
        "warnings": data.get("warnings", []),
        "step_results": data.get("step_results", []),
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "finished_at": data.get("finished_at"),
        "run_mode": data.get("run_mode", ""),
        "model_name": data.get("model_name", ""),
    }


def get_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    """返回任务的最终结果。仅 finished 状态时返回。"""
    data = _read(task_id)
    if data is None:
        return None
    if data["status"] != "finished":
        return None
    return {
        "task_id": data["task_id"],
        "status": data["status"],
        "result": data.get("result"),
        "errors": data.get("errors", []),
        "warnings": data.get("warnings", []),
        "step_results": data.get("step_results", []),
        "created_at": data["created_at"],
        "finished_at": data.get("finished_at"),
    }


def cleanup_expired(ttl: int = TTL_SECONDS) -> int:
    """删除超过 TTL 的任务文件，返回删除数量。"""
    removed = 0
    now = time.time()
    for f in RUNTIME_DIR.glob("task_*.json"):
        try:
            if now - f.stat().st_mtime > ttl:
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def _read(task_id: str) -> Optional[Dict[str, Any]]:
    path = _task_path(task_id)
    if not path.exists():
        return None
    with _write_lock:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None


def _write(task_id: str, data: Dict[str, Any]) -> None:
    path = _task_path(task_id)
    with _write_lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)  # 原子替换
