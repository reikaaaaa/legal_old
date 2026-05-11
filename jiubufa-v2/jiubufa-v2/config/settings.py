"""
全局配置中心。

按用户要求：API Key 明文写在这里，方便本地开发与调试。
生产环境请通过环境变量覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # jiubufa/
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_KB_PATH = DATA_DIR / "articles_annotated.jsonl"

# 兼容外部路径：如果项目数据放在 legal_kb/data/processed/ 下，自动探测
_EXTERNAL_KB_CANDIDATES = [
    PROJECT_ROOT.parent / "legal_kb" / "data" / "processed" / "articles_annotated.jsonl",
    Path("/mnt/project/legal_kb/data/processed/articles_annotated.jsonl"),
]


def resolve_kb_path() -> Path:
    """探测法条库实际路径。"""
    env_path = os.environ.get("JIUBUFA_KB_PATH")
    if env_path:
        return Path(env_path)
    if DEFAULT_KB_PATH.exists():
        return DEFAULT_KB_PATH
    for p in _EXTERNAL_KB_CANDIDATES:
        if p.exists():
            return p
    return DEFAULT_KB_PATH  # 即使不存在也返回，由 loader 提示


# ---------------------------------------------------------------------------
# 模型 API（DashScope 兼容 OpenAI 模式）
# ---------------------------------------------------------------------------

DASHSCOPE_API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY",
    "sk-69b24c1abe964a0389c794d35bba9fd3",  # 明文写入，按用户要求
)
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# 模型注册表：model_id -> 实际模型名
MODEL_REGISTRY: Dict[str, str] = {
    "dashscope-qwen": "qwen3.6-max-preview",
    "dashscope-qwen-plus": "qwen3.5-plus",
    "dashscope-qwen3.6-plus": "qwen3.6-plus",
    "dashscope-qwen3.6-flash": "qwen3.6-flash",
    "dashscope-deepseek": "deepseek-v4-flash",
}

# 默认模型（综合考虑速度与质量，标注阶段也用这个）
DEFAULT_MODEL_ID = "dashscope-qwen-plus"

# 每步可单独指定模型；未指定则用 DEFAULT_MODEL_ID
STEP_MODEL_OVERRIDES: Dict[str, str] = {
    # 例如对涉及法律推理较重的步骤换更强的模型：
    # "step9_subsumption": "dashscope-qwen",
    # "step6_issues": "dashscope-qwen3.6-plus",
}


def get_model_name(model_id: str) -> str:
    """把 model_id 解析为实际模型名。未注册时按字面量直传。"""
    return MODEL_REGISTRY.get(model_id, model_id)


def get_step_model_id(step_key: str) -> str:
    return STEP_MODEL_OVERRIDES.get(step_key, DEFAULT_MODEL_ID)


# ---------------------------------------------------------------------------
# LLM 调用参数
# ---------------------------------------------------------------------------

LLM_TIMEOUT_SECONDS = 180.0
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2.0
LLM_TEMPERATURE = 0.2  # 法律推理偏低温
LLM_MAX_TOKENS = 12800


# ---------------------------------------------------------------------------
# 检索参数
# ---------------------------------------------------------------------------

# 第二步、第三步候选规则单元最多返回多少条进入 LLM
KB_TOPK_REQUEST_BASIS = 12
KB_TOPK_DEFENSE_BASIS = 10


# ---------------------------------------------------------------------------
# 联网搜索参数
# ---------------------------------------------------------------------------

# 是否启用联网搜索补充法条
ENABLE_WEB_SEARCH = True

# 联网搜索使用的模型（deepseek-v4-flash 支持联网）
WEB_SEARCH_MODEL = "dashscope-deepseek"

# 联网搜索返回的法条数量（默认2个）
WEB_SEARCH_TOP_K = 2

# 启用联网搜索的步骤
WEB_SEARCH_STEPS = ["step2_request_basis", "step3_defense_basis", "step9_subsumption"]


# ---------------------------------------------------------------------------
# 保底机制阈值
# ---------------------------------------------------------------------------

SUFFICIENCY_THRESHOLD_STRONG = 80
SUFFICIENCY_THRESHOLD_MEDIUM = 60
SUFFICIENCY_THRESHOLD_WEAK = 40


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("JIUBUFA_LOG_LEVEL", "INFO")
