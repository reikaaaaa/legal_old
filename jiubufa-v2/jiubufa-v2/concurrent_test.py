"""
20并发测试脚本：对比直接LLM裁判 vs 九步法工作流

测试流程：
1. 读取同一个婚姻案例
2. 20个并发任务，每个任务执行：
   a. 直接LLM裁判分析（提示词仅"请你裁判分析"）- 使用 qwen3.6-plus
   b. 九步法工作流分析 - 使用 qwen3.6-plus
   c. 8维度评估（使用 deepseek-v4-flash）
3. 保存所有中间结果
4. 生成分析报告
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from openai import AsyncOpenAI

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL
from llm import AsyncLLMClient
from orchestrator import run_workflow
from schemas import CaseInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("concurrent_test")

RESULTS_DIR = Path(__file__).parent / "test_results"
RESULTS_DIR.mkdir(exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TEST_RUN_DIR = RESULTS_DIR / f"test_run_{TIMESTAMP}"
TEST_RUN_DIR.mkdir(exist_ok=True)

CASE_FILE = Path(__file__).parent / "test_marriage_case.json"

NUM_CONCURRENT = 50

MODEL_JUDGMENT = "dashscope-qwen3.6-plus"
MODEL_EVALUATION = "dashscope-deepseek"

EVALUATION_DIMENSIONS = [
    "系统定位契合度",
    "审理路径组织能力",
    "请求权基础与抗辩路径识别",
    "争议焦点归纳能力",
    "事实证据要件对应性",
    "法律适用与涵摄辅助能力",
    "程序实体风险识别能力",
    "可审查性与裁判心证支持",
]


async def load_case() -> CaseInput:
    with open(CASE_FILE, "r", encoding="utf-8") as f:
        case_data = json.load(f)
    return CaseInput(**case_data)


async def direct_llm_judgment(case_input: CaseInput, test_id: int) -> Dict[str, Any]:
    logger.info(f"[Test {test_id}] 开始直接LLM裁判分析...")
    start_time = time.time()

    llm = AsyncLLMClient()

    case_text = json.dumps(case_input.model_dump(), ensure_ascii=False, indent=2)

    system_prompt = "请对以下案件进行裁判分析，并以json格式输出结果。你不是 AI 审案官，而是法官审判辅助工具。请围绕诉请固定、请求权基础、抗辩路径、争议焦点、事实证据对应、法律适用、程序实体风险、待核查事项，输出一份供法官审查的案件辅助分析。"
    user_prompt = f"请你裁判分析\n\n案件材料：\n{case_text}"

    try:
        result = await llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_id=MODEL_JUDGMENT,
            step_key="direct_judgment",
            temperature=0.2,
            max_tokens=12800,
        )

        elapsed = time.time() - start_time
        logger.info(f"[Test {test_id}] 直接LLM裁判分析完成，耗时 {elapsed:.2f}s")

        return {
            "test_id": test_id,
            "method": "direct_llm",
            "model": MODEL_JUDGMENT,
            "elapsed_seconds": round(elapsed, 2),
            "result": result,
            "status": "success",
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[Test {test_id}] 直接LLM裁判分析失败: {e}")
        return {
            "test_id": test_id,
            "method": "direct_llm",
            "model": MODEL_JUDGMENT,
            "elapsed_seconds": round(elapsed, 2),
            "result": None,
            "status": "error",
            "error": str(e),
        }


async def workflow_judgment(case_input: CaseInput, test_id: int) -> Dict[str, Any]:
    logger.info(f"[Test {test_id}] 开始九步法工作流分析...")
    start_time = time.time()

    try:
        case_copy = case_input.model_copy(deep=True)
        result = await asyncio.to_thread(run_workflow, case_copy)

        elapsed = time.time() - start_time
        logger.info(f"[Test {test_id}] 九步法工作流分析完成，耗时 {elapsed:.2f}s")

        result_dict = result.model_dump()

        return {
            "test_id": test_id,
            "method": "jiubufa_workflow",
            "model": MODEL_JUDGMENT,
            "elapsed_seconds": round(elapsed, 2),
            "result": result_dict,
            "status": "success",
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[Test {test_id}] 九步法工作流分析失败: {e}")
        return {
            "test_id": test_id,
            "method": "jiubufa_workflow",
            "model": MODEL_JUDGMENT,
            "elapsed_seconds": round(elapsed, 2),
            "result": None,
            "status": "error",
            "error": str(e),
        }


async def evaluate_result(
    case_input: CaseInput,
    judgment_result: Dict[str, Any],
    method_name: str,
    test_id: int,
) -> Dict[str, Any]:
    logger.info(f"[Test {test_id}] 开始8维度审判辅助价值评估 ({method_name})...")
    start_time = time.time()

    llm = AsyncLLMClient()

    case_text = json.dumps(case_input.model_dump(), ensure_ascii=False, indent=2)
    judgment_text = json.dumps(judgment_result, ensure_ascii=False, indent=2)

    system_prompt = (
        "你是一位资深法官助理型评估专家，负责评价不同AI输出对法官审理案件的辅助价值。"
        "请牢牢记住系统定位：被评估对象是辅助法官审案的审判辅助系统，"
        "不是AI审案官，也不是替代法官直接作出裁判的判决书生成器。"
        "因此，评价标准不是谁写出了更完整、更顺滑的判决书，"
        "而是谁更能帮助法官发现争点、核查证据、识别风险、组织审理路径，"
        "并形成更稳健、更可审查的裁判心证。"
        "评估时应鼓励能够将案件拆解为可核查审理链条的输出，"
        "包括诉请固定、请求权基础、抗辩路径、构成要件、要件事实、争议焦点、"
        "证明评价、涵摄判断和风险提示。"
        "未直接给出具体判决主文，不当然扣分；如果其能暴露事实缺口、法律依据缺口、"
        "证据缺失、程序风险、超诉请风险或输入完整性风险，应作为重要优点评价。"
        "相反，直接给出完整裁判方案的输出，如果缺少中间推理、证据链路、风险提示和可追溯依据，"
        "不得仅因结论具体、文本完整而给高分。"
        "请严格按照8个维度评分，每个维度满分100分，并给出可复核的评分理由。"
    )

    dimensions_text = "\n".join(
        [f"{i+1}. {dim}" for i, dim in enumerate(EVALUATION_DIMENSIONS)]
    )

    user_prompt = f"""请按照“辅助法官审案”的定位，对以下分析结果进行8维度评估。

【一、评估对象定位】
本次评估的对象不是“AI审案官”，也不是替代法官生成终局裁判的系统，而是审判辅助工具。其核心价值在于帮助法官完成案件要素拆解、请求权基础识别、抗辩路径整理、争议焦点归纳、证据与事实对应、法律规则适配、裁判风险提示和审理路径组织。

【二、总评价口径】
请优先判断：哪个结果更能帮助法官发现争点、核查证据、识别风险、组织审理路径，并形成更稳健的裁判心证。

特别注意：
1. 未直接生成完整、可执行的判决主文，不当然扣分。
2. 如果结果能把案件转化为“法官可审查、可校验、可补正”的审理工作台，应给予积极评价。
3. 如果结果只是直接生成看似完整的裁判结论，但隐藏了中间推理、证据链路、抗辩审查、风险识别或诉请边界审查，不应仅因文本完整而高分。
4. 对直接裁判式输出，应重点核查其是否存在“结论先行”“事实推断未明示”“证据支撑不足”“超出诉讼请求”“程序性风险未提示”等问题。
5. 对工作流式输出，应重点核查其是否清楚呈现诉请固定 → 请求权基础 → 抗辩路径 → 构成要件 → 要件事实 → 争议焦点 → 证明评价 → 涵摄判断 → 风险提示的审理链条。
6. 如果工作流输出提示了法律依据缺口、调解程序证据缺失、输入材料完整度风险、子女抚养或财产分割等规则检索缺口，应评价其对法官审理具有辅助价值。

【三、案件材料】
{case_text}

【四、待评估结果】
方法名称：{method_name}

结果内容：
{judgment_text}

【五、评估维度】
每个维度满分100分。请按照以下维度评分：
{dimensions_text}

各维度评分含义：
1. 系统定位契合度：是否体现辅助法官审案，而不是代替法官作出裁判；是否避免把“判决书完整度”作为唯一价值。
2. 审理路径组织能力：是否帮助法官明确该审什么、先审什么、后审什么，以及案件处理链条是否清楚。
3. 请求权基础与抗辩路径识别：是否固定诉请，识别请求权基础、抗辩事由及其审查顺序。
4. 争议焦点归纳能力：是否准确提炼核心争点，并区分已稳事实、待证事实和需补查事项。
5. 事实证据要件对应性：是否把证据、事实、构成要件和证明责任建立清楚对应关系，便于法官核查。
6. 法律适用与涵摄辅助能力：是否正确匹配法律规则，并展示事实如何进入规范要件，而不是只给结论。
7. 程序实体风险识别能力：是否提示程序风险、实体风险、证据缺口、法律依据缺口、输入完整性风险、超诉请风险等。
8. 可审查性与裁判心证支持：是否让中间推理可追踪、可复核、可补正，并帮助法官形成更稳健的裁判心证。

【六、输出要求】
请只输出合法JSON，不要输出Markdown，不要添加JSON以外的解释文字。reason字段要具体指出该结果如何帮助或未能帮助法官审案，避免空泛评价。

请严格按照以下JSON格式输出：
{{
  "evaluation_positioning": "审判辅助价值评估，不评价AI是否替代法官裁判",
  "method": "{method_name}",
  "scores": {{
    "系统定位契合度": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否符合辅助法官审案定位，而非仅评价判决书完整度"
    }},
    "审理路径组织能力": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否帮助法官组织审理链条、明确审理顺序和审查重点"
    }},
    "请求权基础与抗辩路径识别": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否固定诉请、识别请求权基础和抗辩路径"
    }},
    "争议焦点归纳能力": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否归纳争点，并区分已稳事实、待证事实和需补查事项"
    }},
    "事实证据要件对应性": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否建立证据、事实、构成要件和证明责任之间的对应关系"
    }},
    "法律适用与涵摄辅助能力": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否展示法律规则适配和事实涵摄过程"
    }},
    "程序实体风险识别能力": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否提示程序风险、实体风险、证据缺口、法律依据缺口或超诉请风险"
    }},
    "可审查性与裁判心证支持": {{
      "score": 分数(0-100),
      "reason": "评分理由：说明其是否让推理可追踪、可复核、可补正，并支持法官形成稳健心证"
    }}
  }},
  "overall_score": 总分(0-100),
  "overall_comment": "综合评价：围绕审判辅助价值说明该结果的总体表现，不以是否直接生成完整判决为唯一标准",
  "auxiliary_value_judgment": {{
    "is_more_like_judicial_assistant": true或false,
    "is_more_like_judgment_ghostwriter": true或false,
    "explanation": "说明该输出更像审判辅助工作台，还是更像代写判决，并解释利弊"
  }},
  "judge_workbench_value": {{
    "helps_identify_issues": true或false,
    "helps_verify_evidence": true或false,
    "helps_identify_risks": true或false,
    "helps_organize_hearing_path": true或false,
    "helps_form_stable_inner_conviction": true或false,
    "explanation": "说明其如何帮助法官发现争点、核查证据、识别风险、组织审理路径和形成心证"
  }},
  "strengths": ["从审判辅助角度概括优点1", "从审判辅助角度概括优点2"],
  "weaknesses": ["从审判辅助角度概括不足1", "从审判辅助角度概括不足2"],
  "risk_flags": [
    {{
      "risk_type": "例如：超诉请风险/证据缺口/程序风险/法律依据缺口/事实推断未明示/结论先行",
      "risk_level": "低/中/高",
      "description": "具体风险说明",
      "suggested_judge_check": "建议法官进一步核查的事项"
    }}
  ],
  "recommended_use": "说明该结果更适合作为审理工作台、风险清单、争点整理材料、判决草稿参考，或不建议直接采用的原因"
}}"""

    try:
        evaluation = await llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_id=MODEL_EVALUATION,
            step_key="evaluation",
            temperature=0.1,
            max_tokens=12800,
        )

        elapsed = time.time() - start_time
        logger.info(
            f"[Test {test_id}] 8维度审判辅助价值评估完成 ({method_name})，耗时 {elapsed:.2f}s"
        )

        return {
            "test_id": test_id,
            "method": method_name,
            "evaluation_model": MODEL_EVALUATION,
            "elapsed_seconds": round(elapsed, 2),
            "evaluation": evaluation,
            "status": "success",
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[Test {test_id}] 8维度审判辅助价值评估失败 ({method_name}): {e}")
        return {
            "test_id": test_id,
            "method": method_name,
            "evaluation_model": MODEL_EVALUATION,
            "elapsed_seconds": round(elapsed, 2),
            "evaluation": None,
            "status": "error",
            "error": str(e),
        }


def extract_key_fields(result: Dict[str, Any], method: str) -> Dict[str, Any]:
    extracted = {
        "method": method,
        "status": result.get("status"),
        "elapsed_seconds": result.get("elapsed_seconds"),
    }

    if method == "direct_llm":
        if result.get("result"):
            extracted["key_content"] = result["result"]
    elif method == "jiubufa_workflow":
        if result.get("result"):
            wf_result = result["result"]
            extracted["workflow_status"] = wf_result.get("status")
            extracted["fallback_gate"] = wf_result.get("fallback_gate")
            extracted["strong_judgment"] = wf_result.get("strong_judgment")
            extracted["weak_judgment"] = wf_result.get("weak_judgment")
            extracted["partial_output"] = wf_result.get("partial_output")
            extracted["errors"] = wf_result.get("errors")
            extracted["warnings"] = wf_result.get("warnings")
            extracted["timings_ms"] = wf_result.get("timings_ms")

            if wf_result.get("step9"):
                extracted["subsumption_results"] = wf_result["step9"].get(
                    "subsumption_results"
                )
            if wf_result.get("step6"):
                extracted["issues"] = wf_result["step6"].get("issues")
            if wf_result.get("step8"):
                extracted["fact_findings"] = wf_result["step8"].get("fact_findings")

    return extracted


async def run_single_test(case_input: CaseInput, test_id: int) -> Dict[str, Any]:
    logger.info(f"{'='*80}")
    logger.info(f"[Test {test_id}] 开始执行测试")
    logger.info(f"{'='*80}")

    test_dir = TEST_RUN_DIR / f"test_{test_id:02d}"
    test_dir.mkdir(exist_ok=True)

    direct_result = await direct_llm_judgment(case_input, test_id)
    with open(test_dir / "direct_llm_result.json", "w", encoding="utf-8") as f:
        json.dump(direct_result, f, ensure_ascii=False, indent=2)

    workflow_result = await workflow_judgment(case_input, test_id)
    with open(test_dir / "workflow_result.json", "w", encoding="utf-8") as f:
        json.dump(workflow_result, f, ensure_ascii=False, indent=2)

    direct_eval = None
    workflow_eval = None

    if direct_result["status"] == "success" and direct_result["result"]:
        direct_eval = await evaluate_result(
            case_input, direct_result["result"], "direct_llm", test_id
        )
        with open(test_dir / "direct_llm_evaluation.json", "w", encoding="utf-8") as f:
            json.dump(direct_eval, f, ensure_ascii=False, indent=2)

    if workflow_result["status"] == "success" and workflow_result["result"]:
        workflow_eval = await evaluate_result(
            case_input, workflow_result["result"], "jiubufa_workflow", test_id
        )
        with open(test_dir / "workflow_evaluation.json", "w", encoding="utf-8") as f:
            json.dump(workflow_eval, f, ensure_ascii=False, indent=2)

    direct_extracted = extract_key_fields(direct_result, "direct_llm")
    workflow_extracted = extract_key_fields(workflow_result, "jiubufa_workflow")

    with open(test_dir / "extracted_results.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "direct_llm": direct_extracted,
                "jiubufa_workflow": workflow_extracted,
                "direct_evaluation": direct_eval,
                "workflow_evaluation": workflow_eval,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info(f"[Test {test_id}] 测试完成，结果已保存至 {test_dir}")

    return {
        "test_id": test_id,
        "direct_llm": direct_result,
        "jiubufa_workflow": workflow_result,
        "direct_evaluation": direct_eval,
        "workflow_evaluation": workflow_eval,
    }


async def run_all_tests():
    logger.info(f"开始20并发测试，结果保存至: {TEST_RUN_DIR}")
    logger.info(f"裁判模型: {MODEL_JUDGMENT}")
    logger.info(f"评估模型: {MODEL_EVALUATION}")

    case_input = await load_case()
    with open(TEST_RUN_DIR / "test_case.json", "w", encoding="utf-8") as f:
        json.dump(case_input.model_dump(), f, ensure_ascii=False, indent=2)

    tasks = [run_single_test(case_input, i + 1) for i in range(NUM_CONCURRENT)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Test {i+1} 发生异常: {result}")
            all_results.append(
                {
                    "test_id": i + 1,
                    "status": "error",
                    "error": str(result),
                }
            )
        else:
            all_results.append(result)

    with open(TEST_RUN_DIR / "all_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    logger.info(f"{'='*80}")
    logger.info(f"所有测试完成！")
    logger.info(f"结果目录: {TEST_RUN_DIR}")
    logger.info(f"{'='*80}")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_all_tests())
