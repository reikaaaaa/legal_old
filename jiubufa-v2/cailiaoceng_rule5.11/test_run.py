"""
材料规范层 v3.0 — 功能测试脚本

用法：
    cd cailiaoceng_rule5.11
    python test_run.py                          # 使用内置测试文本
    python test_run.py --input case.txt         # 从文件读入
    python test_run.py --text "我的案件材料..."  # 命令行传入
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from material_agent import MaterialPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 内置测试案例
TEST_MATERIAL = """我是做小生意的，有个客户李某从我这买了混凝土，欠我8万块钱一直不给。
当时也没签什么正式合同，就是微信上说的，他说要买混凝土，我就给他送了。
送了三次货，分别是去年9月20号、9月25号、9月27号。
一开始他用个人微信给我转过一部分钱，后来就不给了。
我有微信聊天记录，他说"你放心，我会付的"，但是一直拖着。
我现在想起诉他，让他把8万货款付了。"""


def format_review_result(review) -> str:
    """格式化阶段一输出为可读文本。"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  案由: {review.case_module}")
    lines.append(f"  综合判定: {review.overall_status}")
    lines.append(f"  can_proceed: {review.can_proceed}")
    lines.append(f"  置信度: {review.confidence}")
    lines.append(f"  核心材料提供率: {review.case_type_check.core_provided_rate:.0%}")
    lines.append(f"  核心缺失 ({len(review.missing_core_materials)}):")
    for m in review.missing_core_materials:
        lines.append(f"    - {m}")
    lines.append(f"  可选缺失 ({len(review.missing_optional_materials)}):")
    for m in review.missing_optional_materials[:3]:
        lines.append(f"    - {m}")
    lines.append(f"  九步法逐步骤诊断:")
    for sc in review.step_checks:
        icon = {"充足": "O", "部分不足": "~", "严重缺失": "X"}.get(sc.status, "?")
        lines.append(f"    [{icon}] Step{sc.step_index} {sc.step_name}: {sc.status}")
        if sc.missing_items:
            lines.append(f"        缺失: {sc.missing_items[:2]}")
    lines.append(f"\n  补充指引:\n{review.upload_instructions[:300]}...")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_normalized(norm) -> str:
    """格式化阶段二输出摘要。"""
    lines = []
    lines.append("-" * 40)
    lines.append(f"  case_name: {norm.case_basic_info.case_name}")
    lines.append(f"  case_cause: {norm.case_basic_info.case_cause_text}")
    lines.append(f"  parties: {len(norm.party_info)}")
    for p in norm.party_info:
        lines.append(f"    {p.party_id}: {p.party_name} ({p.party_role})")
    lines.append(f"  claims: {len(norm.claims)}")
    for c in norm.claims:
        lines.append(f"    {c.claim_id}: {c.claim_text_normalized} amount={c.amount}")
    lines.append(f"  claim_facts: {len(norm.claim_facts)}")
    for f in norm.claim_facts:
        lines.append(f"    {f.fact_id}: [{f.fact_time}] {f.fact_text_original[:60]}...")
    lines.append(f"  defense_opinions: {len(norm.defense_opinions)}")
    for d in norm.defense_opinions:
        lines.append(f"    {d.defense_id}: response_type={d.response_type}")
    lines.append(f"  evidence_list: {len(norm.evidence_list)}")
    for e in norm.evidence_list:
        lines.append(f"    {e.evidence_id}: {e.evidence_name} ({e.evidence_type})")
    lines.append(f"  evidence_meta: {len(norm.evidence_meta)}")
    lines.append("-" * 40)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="材料规范层功能测试")
    parser.add_argument("--input", "-i", help="输入文本文件路径")
    parser.add_argument("--text", "-t", help="直接输入案件材料文本")
    parser.add_argument("--phase1-only", action="store_true", help="仅跑阶段一（审核）")
    parser.add_argument("--phase2-only", action="store_true", help="仅跑阶段二（规范化）")
    parser.add_argument("--out", "-o", help="输出 JSON 文件路径")
    parser.add_argument("--case-module", default="无法确定", help="案由提示（用于阶段二）")
    args = parser.parse_args()

    # 确定输入文本
    if args.text:
        raw = args.text
    elif args.input:
        raw = Path(args.input).read_text(encoding="utf-8")
    else:
        print("使用内置测试案例...\n")
        raw = TEST_MATERIAL

    print(f"输入文本 ({len(raw)} 字符):\n{raw[:200]}...\n")

    pipeline = MaterialPipeline()

    if args.phase1_only:
        review = pipeline.review(raw)
        print(format_review_result(review))
        if args.out:
            Path(args.out).write_text(
                review.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n结果已保存到: {args.out}")

    elif args.phase2_only:
        normalized = pipeline.normalize(raw, args.case_module)
        print(format_normalized(normalized))
        if args.out:
            Path(args.out).write_text(
                normalized.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n结果已保存到: {args.out}")

    else:
        full = pipeline.full(raw)
        print(format_review_result(full.review))
        if full.normalized:
            print(format_normalized(full.normalized))
        if args.out:
            payload = {
                "review": json.loads(full.review.model_dump_json(ensure_ascii=False)),
                "normalized": (
                    json.loads(full.normalized.model_dump_json(ensure_ascii=False))
                    if full.normalized
                    else None
                ),
            }
            Path(args.out).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n结果已保存到: {args.out}")


if __name__ == "__main__":
    main()
