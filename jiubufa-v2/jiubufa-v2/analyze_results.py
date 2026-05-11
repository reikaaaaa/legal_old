"""
结果提取与分析脚本

从并发测试的结果中提取关键字段，进行统计分析，生成对比报告。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

RESULTS_DIR = Path(__file__).parent / "test_results"

EVALUATION_DIMENSIONS = [
    "法律适用准确性",
    "逻辑推理严密性",
    "事实认定完整性",
    "证据分析深度",
    "裁判结果合理性",
    "结构化程度",
    "可解释性",
    "专业性",
]


def find_latest_test_run() -> Path:
    if not RESULTS_DIR.exists():
        print(f"错误: 结果目录 {RESULTS_DIR} 不存在")
        sys.exit(1)

    test_runs = sorted(RESULTS_DIR.glob("test_run_*"))
    if not test_runs:
        print("错误: 未找到任何测试运行结果")
        sys.exit(1)

    latest = test_runs[-1]
    print(f"使用最新的测试结果目录: {latest}")
    return latest


def load_all_results(test_run_dir: Path) -> List[Dict[str, Any]]:
    results_file = test_run_dir / "all_results.json"
    if not results_file.exists():
        print(f"错误: 未找到 {results_file}")
        sys.exit(1)

    with open(results_file, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_scores(evaluation: Dict[str, Any]) -> Dict[str, float]:
    if not evaluation or evaluation.get("status") != "success":
        return {}

    eval_data = evaluation.get("evaluation", {})
    if not eval_data:
        return {}

    scores = eval_data.get("scores", {})
    result = {}
    for dim in EVALUATION_DIMENSIONS:
        if dim in scores:
            result[dim] = scores[dim].get("score", 0)
    result["overall_score"] = eval_data.get("overall_score", 0)
    return result


def extract_key_judgment_info(result: Dict[str, Any], method: str) -> Dict[str, Any]:
    if not result or result.get("status") != "success":
        return {"status": "failed", "error": result.get("error", "unknown")}

    info = {
        "status": "success",
        "elapsed_seconds": result.get("elapsed_seconds"),
    }

    if method == "direct_llm":
        judgment = result.get("result", {})
        info["content_preview"] = str(judgment)[:500] if judgment else ""
    elif method == "jiubufa_workflow":
        wf_result = result.get("result", {})
        info["workflow_status"] = wf_result.get("status")
        info["has_strong_judgment"] = bool(wf_result.get("strong_judgment"))
        info["has_weak_judgment"] = bool(wf_result.get("weak_judgment"))
        info["has_partial_output"] = bool(wf_result.get("partial_output"))
        info["errors_count"] = len(wf_result.get("errors", []))
        info["warnings_count"] = len(wf_result.get("warnings", []))
        info["total_time_ms"] = wf_result.get("timings_ms", {}).get("total", 0)

        if wf_result.get("strong_judgment"):
            strong = wf_result["strong_judgment"]
            info["risk_level"] = strong.get("risk_level")
            if strong.get("sufficiency_score"):
                info["sufficiency_score"] = strong["sufficiency_score"].get("total")
                info["sufficiency_level"] = strong["sufficiency_score"].get("level")

    return info


def calculate_statistics(scores_list: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    if not scores_list:
        return {}

    stats = {}
    all_keys = set()
    for scores in scores_list:
        all_keys.update(scores.keys())

    for key in all_keys:
        values = [s[key] for s in scores_list if key in s]
        if values:
            stats[key] = {
                "mean": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "std": round(
                    (sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)) ** 0.5,
                    2,
                ),
                "count": len(values),
            }

    return stats


def generate_comparison_report(
    direct_scores: List[Dict[str, float]],
    workflow_scores: List[Dict[str, float]],
    direct_info_list: List[Dict[str, Any]],
    workflow_info_list: List[Dict[str, Any]],
) -> str:
    report = []
    report.append("=" * 100)
    report.append("九步法工作流 vs 直接LLM裁判 - 对比分析报告")
    report.append("=" * 100)
    report.append("")

    report.append(f"测试数量: {len(direct_info_list)}")
    report.append(f"裁判模型: qwen3.6-plus")
    report.append(f"评估模型: deepseek-v4-flash")
    report.append("")

    report.append("-" * 100)
    report.append("一、执行成功率")
    report.append("-" * 100)
    direct_success = sum(1 for info in direct_info_list if info.get("status") == "success")
    workflow_success = sum(1 for info in workflow_info_list if info.get("status") == "success")
    report.append(f"直接LLM裁判: {direct_success}/{len(direct_info_list)} ({direct_success/len(direct_info_list)*100:.1f}%)")
    report.append(f"九步法工作流: {workflow_success}/{len(workflow_info_list)} ({workflow_success/len(workflow_info_list)*100:.1f}%)")
    report.append("")

    report.append("-" * 100)
    report.append("二、执行耗时统计（秒）")
    report.append("-" * 100)
    direct_times = [info["elapsed_seconds"] for info in direct_info_list if info.get("status") == "success" and "elapsed_seconds" in info]
    workflow_times = [info["elapsed_seconds"] for info in workflow_info_list if info.get("status") == "success" and "elapsed_seconds" in info]

    if direct_times:
        report.append(f"直接LLM裁判:")
        report.append(f"  平均耗时: {sum(direct_times)/len(direct_times):.2f}s")
        report.append(f"  最小耗时: {min(direct_times):.2f}s")
        report.append(f"  最大耗时: {max(direct_times):.2f}s")
    if workflow_times:
        report.append(f"九步法工作流:")
        report.append(f"  平均耗时: {sum(workflow_times)/len(workflow_times):.2f}s")
        report.append(f"  最小耗时: {min(workflow_times):.2f}s")
        report.append(f"  最大耗时: {max(workflow_times):.2f}s")
    report.append("")

    report.append("-" * 100)
    report.append("三、7维度评分对比")
    report.append("-" * 100)

    direct_stats = calculate_statistics(direct_scores)
    workflow_stats = calculate_statistics(workflow_scores)

    report.append(f"{'维度':<20} {'直接LLM(均值)':<20} {'九步法(均值)':<20} {'差异':<20}")
    report.append("-" * 80)

    for dim in EVALUATION_DIMENSIONS + ["overall_score"]:
        direct_mean = direct_stats.get(dim, {}).get("mean", 0)
        workflow_mean = workflow_stats.get(dim, {}).get("mean", 0)
        diff = workflow_mean - direct_mean
        report.append(f"{dim:<20} {direct_mean:<20.2f} {workflow_mean:<20.2f} {diff:+.2f}")

    report.append("")

    report.append("-" * 100)
    report.append("四、直接LLM评分详细统计")
    report.append("-" * 100)
    for dim, stats in direct_stats.items():
        report.append(f"{dim}:")
        report.append(f"  均值: {stats['mean']:.2f}, 最小: {stats['min']:.2f}, 最大: {stats['max']:.2f}, 标准差: {stats['std']:.2f}")
    report.append("")

    report.append("-" * 100)
    report.append("五、九步法工作流评分详细统计")
    report.append("-" * 100)
    for dim, stats in workflow_stats.items():
        report.append(f"{dim}:")
        report.append(f"  均值: {stats['mean']:.2f}, 最小: {stats['min']:.2f}, 最大: {stats['max']:.2f}, 标准差: {stats['std']:.2f}")
    report.append("")

    report.append("-" * 100)
    report.append("六、九步法工作流特性分析")
    report.append("-" * 100)
    strong_count = sum(1 for info in workflow_info_list if info.get("has_strong_judgment"))
    weak_count = sum(1 for info in workflow_info_list if info.get("has_weak_judgment"))
    partial_count = sum(1 for info in workflow_info_list if info.get("has_partial_output"))
    report.append(f"强裁判输出: {strong_count}/{len(workflow_info_list)}")
    report.append(f"弱裁判输出: {weak_count}/{len(workflow_info_list)}")
    report.append(f"部分输出: {partial_count}/{len(workflow_info_list)}")

    avg_errors = sum(info.get("errors_count", 0) for info in workflow_info_list) / len(workflow_info_list)
    avg_warnings = sum(info.get("warnings_count", 0) for info in workflow_info_list) / len(workflow_info_list)
    report.append(f"平均错误数: {avg_errors:.2f}")
    report.append(f"平均警告数: {avg_warnings:.2f}")
    report.append("")

    report.append("-" * 100)
    report.append("七、综合评估")
    report.append("-" * 100)

    if direct_stats and workflow_stats:
        direct_overall = direct_stats.get("overall_score", {}).get("mean", 0)
        workflow_overall = workflow_stats.get("overall_score", {}).get("mean", 0)

        if workflow_overall > direct_overall:
            report.append(f"✓ 九步法工作流在综合评分上优于直接LLM裁判（{workflow_overall:.2f} vs {direct_overall:.2f}）")
        elif direct_overall > workflow_overall:
            report.append(f"✓ 直接LLM裁判在综合评分上优于九步法工作流（{direct_overall:.2f} vs {workflow_overall:.2f}）")
        else:
            report.append(f"✓ 两种方法综合评分相同（{direct_overall:.2f}）")

        better_dims = []
        worse_dims = []
        for dim in EVALUATION_DIMENSIONS:
            d_mean = direct_stats.get(dim, {}).get("mean", 0)
            w_mean = workflow_stats.get(dim, {}).get("mean", 0)
            if w_mean > d_mean:
                better_dims.append((dim, w_mean - d_mean))
            elif d_mean > w_mean:
                worse_dims.append((dim, d_mean - w_mean))

        if better_dims:
            report.append(f"\n九步法工作流优势维度：")
            for dim, diff in sorted(better_dims, key=lambda x: x[1], reverse=True):
                report.append(f"  - {dim}: +{diff:.2f}")

        if worse_dims:
            report.append(f"\n直接LLM裁判优势维度：")
            for dim, diff in sorted(worse_dims, key=lambda x: x[1], reverse=True):
                report.append(f"  - {dim}: +{diff:.2f}")

    report.append("")
    report.append("=" * 100)
    report.append("报告生成完毕")
    report.append("=" * 100)

    return "\n".join(report)


def analyze_test_run(test_run_dir: Path = None):
    if test_run_dir is None:
        test_run_dir = find_latest_test_run()

    all_results = load_all_results(test_run_dir)

    direct_scores = []
    workflow_scores = []
    direct_info_list = []
    workflow_info_list = []

    for result in all_results:
        test_id = result.get("test_id")

        direct_result = result.get("direct_llm", {})
        direct_info = extract_key_judgment_info(direct_result, "direct_llm")
        direct_info["test_id"] = test_id
        direct_info_list.append(direct_info)

        direct_eval = result.get("direct_evaluation")
        if direct_eval:
            scores = extract_scores(direct_eval)
            if scores:
                direct_scores.append(scores)

        workflow_result = result.get("jiubufa_workflow", {})
        workflow_info = extract_key_judgment_info(workflow_result, "jiubufa_workflow")
        workflow_info["test_id"] = test_id
        workflow_info_list.append(workflow_info)

        workflow_eval = result.get("workflow_evaluation")
        if workflow_eval:
            scores = extract_scores(workflow_eval)
            if scores:
                workflow_scores.append(scores)

    report = generate_comparison_report(
        direct_scores, workflow_scores, direct_info_list, workflow_info_list
    )

    report_file = test_run_dir / "analysis_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    summary_data = {
        "direct_scores": direct_scores,
        "workflow_scores": workflow_scores,
        "direct_info": direct_info_list,
        "workflow_info": workflow_info_list,
        "direct_statistics": calculate_statistics(direct_scores),
        "workflow_statistics": calculate_statistics(workflow_scores),
    }

    summary_file = test_run_dir / "analysis_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(report)
    print(f"\n分析报告已保存至: {report_file}")
    print(f"分析摘要已保存至: {summary_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_dir = Path(sys.argv[1])
        analyze_test_run(test_dir)
    else:
        analyze_test_run()
