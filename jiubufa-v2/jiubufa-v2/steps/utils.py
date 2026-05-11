"""
steps 模块通用工具：计时、prompt 安全 dump、Pydantic 容错构建。
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .state import WorkflowState

logger = logging.getLogger("jiubufa.steps")

T = TypeVar("T", bound=BaseModel)


def safe_dump(obj: Any) -> str:
    """把 Pydantic 对象或字典转成紧凑 JSON 字符串，喂给 LLM。"""
    if isinstance(obj, BaseModel):
        return obj.model_dump_json(exclude_none=False)
    return json.dumps(obj, ensure_ascii=False, default=str)


def parse_into(model_cls: Type[T], data: Any, *, fallback: Optional[T] = None) -> T:
    """容错地把 LLM 返回字典塞进 Pydantic 对象。"""
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "Pydantic 校验失败 model=%s err=%s",
            model_cls.__name__,
            exc.errors()[:2],
        )
        if fallback is not None:
            return fallback
        # 最后兜底：返回空对象
        return model_cls()  # type: ignore[call-arg]


@contextmanager
def time_step(state: WorkflowState, key: str) -> Iterator[None]:
    t0 = time.time()
    try:
        yield
    finally:
        state.timings_ms[key] = int((time.time() - t0) * 1000)


def models_to_dicts(models: List[BaseModel]) -> List[Dict[str, Any]]:
    return [m.model_dump(exclude_none=False) for m in models]
