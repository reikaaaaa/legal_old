"""
Debug API — 仅在 DEBUG_TRACE=true 时挂载。

端点：
    GET  /debug/traces           — 列出所有 trace
    GET  /debug/traces/{id}      — 获取单个 trace 详情
    GET  /debug/static/{file}    — 静态文件 (index.html, app.js, style.css)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .trace_collector import TRACE_DIR, MAX_TRACES

logger = logging.getLogger("debug_viewer.router")

router = APIRouter(prefix="/debug", tags=["debug"])

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ── Trace 列表 ──────────────────────────

@router.get("/traces")
def list_traces() -> List[dict]:
    """返回最近 trace 列表（按时间倒序）。"""
    if not TRACE_DIR.exists():
        return []
    files = sorted(TRACE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            result.append({
                "trace_id": data.get("trace_id"),
                "status": data.get("status"),
                "duration_seconds": data.get("duration_seconds"),
                "step_count": data.get("step_count"),
                "started_at": data.get("started_at"),
            })
        except Exception:
            continue
        if len(result) >= MAX_TRACES:
            break
    return result


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """获取单个 trace 的完整链路详情。"""
    filepath = TRACE_DIR / f"{trace_id}.json"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Trace 不存在或已过期")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 静态文件 ────────────────────────────

@router.get("/static/{filename:path}")
def serve_static(filename: str):
    """提供 debug viewer 前端静态文件。"""
    filepath = STATIC_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    if filename.endswith(".html"):
        return HTMLResponse(filepath.read_text(encoding="utf-8"))
    return FileResponse(str(filepath))


@router.get("/")
def debug_index():
    """Debug Viewer 首页。"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Debug Viewer — 静态文件缺失</h1>")
