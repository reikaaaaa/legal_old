"""
命令行入口：从 JSON 文件读取 CaseInput，跑工作流，把结果写到输出文件。

用法：
    python run_workflow.py --input examples/sample_case.json --out result.json
    python run_workflow.py --input case.json --out result.json --pretty
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from orchestrator import run_workflow
from schemas import CaseInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jiubufa.cli")


def main() -> int:
    parser = argparse.ArgumentParser(description="九步法审案工作流命令行入口。")
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="案件输入 JSON 文件路径（与 CaseInput schema 对齐）。",
    )
    parser.add_argument(
        "--out",
        "-o",
        required=True,
        help="结果输出 JSON 文件路径。",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="是否对输出 JSON 做缩进美化。",
    )
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.is_file():
        logger.error("输入文件不存在：%s", in_path)
        return 2

    try:
        raw = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("输入文件 JSON 解析失败：%s", exc)
        return 2

    try:
        case_input = CaseInput(**raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("CaseInput 字段校验失败：%s", exc)
        return 2

    case_id_for_log = (
        case_input.case_basic_info.case_id if case_input.case_basic_info else "<未指定>"
    )
    logger.info("开始执行工作流，case_id=%s", case_id_for_log)
    result = run_workflow(case_input)
    logger.info(
        "工作流完成，status=%s，errors=%d，warnings=%d",
        result.status,
        len(result.errors),
        len(result.warnings),
    )

    payload = result.model_dump(mode="json", exclude_none=False)
    if args.pretty:
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    logger.info("结果已写入：%s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
