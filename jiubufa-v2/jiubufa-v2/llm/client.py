"""
DashScope LLM 客户端封装。

特性：
- OpenAI 兼容模式（Base URL = compatible-mode/v1）
- 同步与异步两套调用接口
- JSON 强制输出 + 容错解析（去除 ```json``` 包裹、修复尾随逗号等）
- 指数退避重试
- 按 step_key 自动选择模型
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import APIError, AsyncOpenAI, OpenAI, RateLimitError

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    DEFAULT_MODEL_ID,
    LLM_MAX_RETRIES,
    LLM_MAX_TOKENS,
    LLM_RETRY_BASE_DELAY,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
    get_model_name,
    get_step_model_id,
)

logger = logging.getLogger("jiubufa.llm")


# ---------------------------------------------------------------------------
# JSON 容错解析
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.DOTALL)


def _strip_fences(text: str) -> str:
    text = text.strip()
    # 整体外层去除 ```json ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text, count=1)
    return text.strip()


def _extract_json_block(text: str) -> str:
    """从模型输出中抽出最外层 JSON 块。"""
    text = _strip_fences(text)
    # 最常见情况：模型直接返回 JSON
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # 退化策略：抓第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    # 数组
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_json_safely(text: str) -> Any:
    """容错解析 LLM 返回的 JSON。"""
    if text is None:
        raise ValueError("LLM 返回为空")
    candidate = _extract_json_block(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # 二次尝试：去掉常见尾随逗号
        cleaned = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(
                f"LLM 输出无法解析为 JSON：{exc}。原文前 500 字：{text[:500]}"
            ) from exc


# ---------------------------------------------------------------------------
# Client 封装
# ---------------------------------------------------------------------------


@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    model_id: Optional[str] = None
    temperature: float = LLM_TEMPERATURE
    max_tokens: int = LLM_MAX_TOKENS
    response_format_json: bool = True


class LLMClient:
    """同步客户端。"""

    def __init__(
        self,
        api_key: str = DASHSCOPE_API_KEY,
        base_url: str = DASHSCOPE_BASE_URL,
        timeout: float = LLM_TIMEOUT_SECONDS,
    ) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model_id: Optional[str] = None,
        step_key: Optional[str] = None,
        temperature: float = LLM_TEMPERATURE,
        max_tokens: int = LLM_MAX_TOKENS,
    ) -> Any:
        """发起一次 JSON 输出对话。返回解析后的 Python 对象。"""

        resolved_model_id = model_id or (
            get_step_model_id(step_key) if step_key else DEFAULT_MODEL_ID
        )
        model_name = get_model_name(resolved_model_id)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Optional[Exception] = None
        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = self._client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                elapsed = time.time() - t0
                content = response.choices[0].message.content or ""
                logger.info(
                    "LLM[%s/%s] step=%s ok in %.2fs len=%d",
                    resolved_model_id,
                    model_name,
                    step_key,
                    elapsed,
                    len(content),
                )
                return parse_json_safely(content)
            except (RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                wait = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    LLM_MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < LLM_MAX_RETRIES:
                    time.sleep(wait)
            except Exception as exc:  # noqa: BLE001
                # 一些 DashScope 不支持 response_format 的回退
                if "response_format" in str(exc).lower():
                    logger.warning("response_format 不支持，回退为文本模式")
                    try:
                        response = self._client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        content = response.choices[0].message.content or ""
                        return parse_json_safely(content)
                    except Exception as exc2:  # noqa: BLE001
                        last_error = exc2
                else:
                    last_error = exc
                wait = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                if attempt < LLM_MAX_RETRIES:
                    time.sleep(wait)
        raise RuntimeError(f"LLM 调用失败（已重试 {LLM_MAX_RETRIES} 次）：{last_error}")


class AsyncLLMClient:
    """异步客户端。"""

    def __init__(
        self,
        api_key: str = DASHSCOPE_API_KEY,
        base_url: str = DASHSCOPE_BASE_URL,
        timeout: float = LLM_TIMEOUT_SECONDS,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model_id: Optional[str] = None,
        step_key: Optional[str] = None,
        temperature: float = LLM_TEMPERATURE,
        max_tokens: int = LLM_MAX_TOKENS,
    ) -> Any:
        resolved_model_id = model_id or (
            get_step_model_id(step_key) if step_key else DEFAULT_MODEL_ID
        )
        model_name = get_model_name(resolved_model_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Optional[Exception] = None
        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                t0 = time.time()
                response = await self._client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                elapsed = time.time() - t0
                content = response.choices[0].message.content or ""
                logger.info(
                    "LLM[%s/%s] step=%s ok in %.2fs len=%d (async)",
                    resolved_model_id,
                    model_name,
                    step_key,
                    elapsed,
                    len(content),
                )
                return parse_json_safely(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                wait = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "AsyncLLM call failed (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    LLM_MAX_RETRIES,
                    exc,
                    wait,
                )
                if attempt < LLM_MAX_RETRIES:
                    await asyncio.sleep(wait)
        raise RuntimeError(f"LLM 调用失败（已重试 {LLM_MAX_RETRIES} 次）：{last_error}")


# 模块级单例
_default_sync_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    global _default_sync_client
    if _default_sync_client is None:
        _default_sync_client = LLMClient()
    return _default_sync_client
