"""保底裁判子包：硬性拦截 / 充足度评分 / 用户选择门 / 弱裁判 / 部分输出。"""

from .weak_judgment import (
    build_fallback_gate,
    check_hard_block,
    generate_partial_output,
    generate_weak_judgment,
    score_sufficiency,
)

__all__ = [
    "build_fallback_gate",
    "check_hard_block",
    "generate_partial_output",
    "generate_weak_judgment",
    "score_sufficiency",
]
