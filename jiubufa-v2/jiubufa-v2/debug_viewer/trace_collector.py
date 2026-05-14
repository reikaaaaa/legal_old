"""
TraceCollector — 非侵入式工作流链路记录器。

DEBUG_TRACE=false 时所有 log_step() 调用都是空操作，零性能影响。
DEBUG_TRACE=true 时记录每个步骤的 input/logic/prompt/raw/parsed/output/error。

存储策略：最多保留最近 20 个 trace，单个字段超过 8000 字符截断。
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("debug_viewer.trace_collector")

ENABLED = os.getenv("DEBUG_TRACE", "false").lower() == "true"
MAX_TRACES = 20
MAX_FIELD_LEN = 8000
TRACE_DIR = Path(__file__).resolve().parent / "traces"


def _truncate(value: Any) -> Any:
    """截断超长字段。"""
    if isinstance(value, str) and len(value) > MAX_FIELD_LEN:
        return value[:MAX_FIELD_LEN] + f"\n\n... [截断，原 {len(value)} 字符]"
    if isinstance(value, dict):
        return {k: _truncate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v) for v in value]
    return value


def _auto_cleanup() -> None:
    """保留最近 MAX_TRACES 个 trace 文件。"""
    try:
        if not TRACE_DIR.exists():
            return
        files = sorted(TRACE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[MAX_TRACES:]:
            f.unlink()
    except Exception:
        pass


class TraceCollector:
    """单次工作流运行的链路记录器。"""

    def __init__(self) -> None:
        self.trace_id: str = ""
        self.status: str = "running"
        self.steps: List[Dict[str, Any]] = []
        self._started_at: float = 0.0
        self._step_index: int = 0
        if ENABLED:
            self.trace_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            self._started_at = time.time()

    def log_step(
        self,
        step_name: str,
        *,
        input_data: Any = None,
        output_data: Any = None,
        logic: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        prompt_system: Optional[str] = None,
        llm_raw: Optional[str] = None,
        parsed_json: Any = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一个步骤。DEBUG_TRACE=false 时直接返回。"""
        if not ENABLED:
            return
        self._step_index += 1
        step = {
            "index": self._step_index,
            "step_name": step_name,
            "timestamp": time.strftime("%H:%M:%S"),
            "elapsed_ms": int((time.time() - self._started_at) * 1000),
        }
        if input_data is not None:
            step["input"] = _truncate(input_data)
        if output_data is not None:
            step["output"] = _truncate(output_data)
        if logic:
            step["logic"] = logic
        if prompt_system:
            step["prompt_system"] = _truncate(prompt_system)
        if prompt:
            step["prompt"] = _truncate(prompt)
        if llm_raw is not None:
            step["llm_raw"] = _truncate(llm_raw)
        if parsed_json is not None:
            step["parsed_json"] = _truncate(parsed_json)
        if error:
            step["error"] = error
        if metadata:
            step["metadata"] = metadata
        self.steps.append(step)

    def finish(self, status: str = "success") -> Optional[Dict[str, Any]]:
        """结束记录并持久化。返回 trace 元信息（含 trace_id）或 None。"""
        if not ENABLED:
            return None
        self.status = status
        elapsed = time.time() - self._started_at
        trace = {
            "trace_id": self.trace_id,
            "status": self.status,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(elapsed, 1),
            "step_count": len(self.steps),
            "steps": self.steps,
        }
        try:
            TRACE_DIR.mkdir(parents=True, exist_ok=True)
            filepath = TRACE_DIR / f"{self.trace_id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(trace, f, ensure_ascii=False, indent=2)
            _auto_cleanup()
            logger.info("Trace 已保存: %s (%d 步, %.1fs)", self.trace_id, len(self.steps), elapsed)
        except Exception as exc:
            logger.warning("Trace 保存失败: %s", exc)
        return {
            "trace_id": self.trace_id,
            "status": self.status,
            "duration_seconds": round(elapsed, 1),
            "step_count": len(self.steps),
        }
