可以重构，而且**很适合重构**。但我不建议把它重构成“纯 LangChain Chain”，而是重构成：

> **LangGraph 负责编排九步法状态机，LangChain 负责每个节点里的 LLM 调用、结构化输出、检索、并行化与可观测性。**

原因很简单：你这个项目不是普通的“prompt → llm → parser”链条，而是有 **Step1~Step9、WorkflowState、fallback_gate、blocked / awaiting_user_choice / ok 分支、知识库检索、联网搜索、保底机制、错误记录、耗时统计** 的复杂状态流。你当前文档里也已经把它设计成了一个带状态累积和分支控制的工作流，而不是单轮生成任务。

LangChain 官方也明确区分了 LCEL 和 LangGraph：LCEL 适合简单链；如果应用涉及复杂状态管理、分支、循环或多代理，更建议用 LangGraph，并且可以在 LangGraph 的单个节点内部继续使用 LCEL。([LangChain Python 教程][1])

## 我的判断：可以重构，但目标应该是 LangGraph-first

### 不建议这样重构

```text
CaseInput → LangChain SequentialChain → Step1 → Step2 → ... → Step9
```

这种做法只是把你现有 `orchestrator.py` 换个壳，收益不大，甚至会让分支控制更别扭。

### 建议这样重构

```text
CaseInput
  ↓
LangGraph StateGraph[WorkflowState]
  ↓
step1_fix_claims
  ↓
step2_request_basis
  ↓
step3_defense_basis
  ↓
...
step8_fact_finding
  ↓
sufficiency_gate
  ├── blocked → output_review_only
  ├── awaiting_user_choice → interrupt / human-in-the-loop
  ├── limited_assistive_opinion
  └── step9_subsumption
        ↓
judge_review_dashboard
        ↓
WorkflowResult
```

这和你的项目天然吻合。LangGraph 的定位就是控制复杂 agent 的每一步，支持低层编排、记忆和 human-in-the-loop，这正好对应你现在的九步法、保底选择门和前端用户选择逻辑。([LangChain 文档][2])

---

## 一、哪些部分最适合迁移到 LangGraph

你现在的模块可以这样映射：

| 当前模块                                           | LangChain / LangGraph 重构方式                         |
| ---------------------------------------------- | -------------------------------------------------- |
| `orchestrator.py`                              | 改成 `graph.py`，用 `StateGraph` 编排节点                  |
| `WorkflowState`                                | 保留，改成 `TypedDict` 或 Pydantic state                 |
| `step1_fix_claims.py` ~ `step9_subsumption.py` | 每一步变成 LangGraph node                               |
| `fallback/weak_judgment.py`                    | 变成条件边 `conditional_edges`                          |
| `context_builder.py`                           | 变成每个 node 内的 context selector / context compressor |
| `llm/client.py`                                | 可替换为 LangChain ChatModel 包装                        |
| `kb/retriever.py`                              | 包装成 LangChain Retriever 或 Tool                     |
| `kb/web_search.py`                             | 包装成 Tool，但要加法源校验                                   |
| `schemas/`                                     | 继续保留，用 LangChain structured output 接 Pydantic      |
| `api.py`                                       | 基本保留，只是调用 `compiled_graph.invoke()` 或 `ainvoke()`  |

你现在已经有 Pydantic 的 `CaseInput`、`Step1Output~Step9Output` 和 `WorkflowResult`。这点非常适合 LangChain 的结构化输出，因为 LangChain structured output 支持让 agent 返回 JSON、Pydantic model 或 dataclass，并且会把结构化结果捕获、验证后放入状态里。([LangChain 文档][3])

---

## 二、最应该优先重构的是 orchestrator

现在 `orchestrator.py` 是核心调度器，负责顺序执行 step1~step9、处理分支逻辑和保底机制。你的文档里也明确说它是“工作流总调度器”。

这部分最适合替换为 LangGraph：

```python
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

class WorkflowState(TypedDict, total=False):
    case_input: dict
    step1: dict
    step2: dict
    step3: dict
    step4: dict
    step5: dict
    step6: dict
    step7: dict
    step8: dict
    step9: dict
    sufficiency_score: dict
    fallback_gate: dict
    judge_review_dashboard: dict
    errors: list
    warnings: list
    timings_ms: dict
    status: str
    fallback_user_choice: Optional[str]

def build_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("step1_fix_claims", step1_fix_claims_node)
    graph.add_node("step2_request_basis", step2_request_basis_node)
    graph.add_node("step3_defense_basis", step3_defense_basis_node)
    graph.add_node("step4_elements", step4_elements_node)
    graph.add_node("step5_claim_facts", step5_claim_facts_node)
    graph.add_node("step6_issues", step6_issues_node)
    graph.add_node("step7_proof", step7_proof_node)
    graph.add_node("step8_facts", step8_facts_node)
    graph.add_node("sufficiency_gate", sufficiency_gate_node)
    graph.add_node("step9_subsumption", step9_subsumption_node)
    graph.add_node("review_only_output", review_only_output_node)
    graph.add_node("limited_assistive_opinion", limited_assistive_opinion_node)
    graph.add_node("judge_dashboard", judge_dashboard_node)

    graph.add_edge(START, "step1_fix_claims")
    graph.add_edge("step1_fix_claims", "step2_request_basis")
    graph.add_edge("step2_request_basis", "step3_defense_basis")
    graph.add_edge("step3_defense_basis", "step4_elements")
    graph.add_edge("step4_elements", "step5_claim_facts")
    graph.add_edge("step5_claim_facts", "step6_issues")
    graph.add_edge("step6_issues", "step7_proof")
    graph.add_edge("step7_proof", "step8_facts")
    graph.add_edge("step8_facts", "sufficiency_gate")

    graph.add_conditional_edges(
        "sufficiency_gate",
        route_after_sufficiency_gate,
        {
            "blocked": "review_only_output",
            "awaiting_user_choice": END,
            "limited": "limited_assistive_opinion",
            "full": "step9_subsumption",
        },
    )

    graph.add_edge("step9_subsumption", "judge_dashboard")
    graph.add_edge("limited_assistive_opinion", "judge_dashboard")
    graph.add_edge("review_only_output", "judge_dashboard")
    graph.add_edge("judge_dashboard", END)

    return graph.compile()
```

这个结构比手写 orchestrator 更清楚，尤其适合你现在的保底机制。

---

## 三、Step 2 / Step 3 可以用 RunnableParallel 降低耗时

你现在的 workflow 很慢，一个重要原因是每个步骤和每项诉请、抗辩可能串行处理。LangChain 的 LCEL 有 `RunnableParallel`，可以并发运行多个 runnable；官方说明它可以并发运行多个 runnable，并且异步时基于 `asyncio.gather`。([LangChain Python 教程][1])

比如 Step 2 现在是“为每个诉请检索请求权基础”。这个非常适合并行：

```python
async def step2_request_basis_node(state: WorkflowState) -> WorkflowState:
    fixed_claims = state["step1"]["fixed_claims"]

    tasks = [
        select_request_basis_for_claim.ainvoke({
            "case_input": state["case_input"],
            "claim": claim,
            "local_rules": kb_retriever.search_for_claim(claim),
            "web_rules": await web_rule_search(claim),
        })
        for claim in fixed_claims
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "step2": {
            "request_basis_candidates": normalize_results(results),
            "competition_analysis": build_competition_analysis(results),
        }
    }
```

Step 3 的每条答辩意见、Step 7 的每个争点、Step 8 的每个要件事实，也都可以这样做。这个可能比“换 LangChain”本身更有实际收益。

---

## 四、结构化输出可以大幅减少你现在的 JSON 容错代码

你现在 `llm/client.py` 里做了很多 JSON 解析容错：去 markdown、提取最外层 JSON、修复尾随逗号、数组兼容等。这个是必要的，但维护起来很累。

重构后可以把每个步骤定义成：

```python
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

class Step1Output(BaseModel):
    fixed_claims: list
    case_cause_inferred: str | None = None
    legal_domain_inferred: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)

prompt = ChatPromptTemplate.from_messages([
    ("system", STEP1_SYSTEM_PROMPT),
    ("user", "{context}")
])

step1_chain = prompt | llm.with_structured_output(Step1Output)
```

或者使用 agent 的 `response_format`。LangChain 文档说 structured output 可以直接返回 JSON、Pydantic models 或 dataclasses，并由应用直接使用；传入 schema 后会自动捕获和验证结构化响应。([LangChain 文档][3])

这对你很有价值，因为你的每一步本来就有 `Step1Output~Step9Output`。

---

## 五、知识库检索不一定要完全 LangChain 化

你现在的五层标签检索是很强的业务资产，别为了“框架纯度”把它硬塞成普通向量检索。文档里写得很清楚：你的 `kb/retriever.py` 是基于 L1-L5 法律标签的加权检索，Step 2、Step 3、Step 9 还会结合联网搜索补充法条。

我的建议是：

### 第一阶段：保留原检索器，只包装成 Tool / Runnable

```python
from langchain_core.tools import tool

@tool
def retrieve_request_basis(claim: dict, case_context: dict) -> list[dict]:
    """根据诉请、案由、法律领域和 L1-L5 标签检索请求权基础规范。"""
    return request_basis_retriever.search(
        claim_type=claim.get("claim_type"),
        case_cause=case_context.get("case_cause"),
        legal_domain=case_context.get("legal_domain"),
        top_k=12,
    )
```

### 第二阶段：再加语义召回

```text
标签召回 → BM25/关键词召回 → embedding 召回 → LLM rerank → 法源效力校验
```

不要一上来就把五层标签库替换成向量库。法律检索里，**标签和法源层级比语义相似更重要**。

---

## 六、human-in-the-loop 很适合你的 fallback_gate

你现在有 `awaiting_user_choice`：当前端需要用户选择补充材料、继续弱裁判或仅输出部分结果时，workflow 会停住等待选择。文档也明确说前端要渲染 `fallback_gate.available_choices`，再带 `fallback_user_choice` 重新提交。

这其实就是 LangGraph 很典型的 human-in-the-loop 场景。

重构后可以做成：

```text
step8_facts
  ↓
sufficiency_gate
  ├── sufficient → step9_subsumption
  ├── medium → step9_subsumption + risk_notes
  ├── weak_optional → interrupt 等用户选择
  └── block → review_only_output
```

这会比现在“重新提交整个请求”更优雅。后续如果加 checkpoint，还可以从中断点恢复，而不是重新跑 Step1~Step8。

---

## 七、LangSmith 对你的实验和调试很有用

你前面已经做了 20、50 组对比实验。重构到 LangChain/LangGraph 后，LangSmith 的价值会比较明显：它可以记录 agent 每一步的行为和调用轨迹，也支持测试和评分。官方文档里也把 Observability 描述为“查看 agent 如何思考和行动的详细 tracing”，Evaluation 用于在生产数据或离线数据上测试和评分 agent 行为。([LangChain 文档][2])

你的场景里可以追踪：

```text
case_id
step_name
prompt_version
retrieved_rules
web_rules
structured_output
validation_errors
fallback_gate
risk_flags
timings_ms
final_dashboard_score
```

这对论文/项目报告也很好：不是只展示最终分数，而是展示每一步怎么来的。

---

## 八、建议的重构目录

可以从现在的结构演进成这样：

```text
jiubufa/
├── app/
│   ├── api.py
│   └── cli.py
│
├── graph/
│   ├── state.py
│   ├── graph.py
│   ├── routes.py
│   └── checkpoints.py
│
├── nodes/
│   ├── step1_fix_claims.py
│   ├── step2_request_basis.py
│   ├── step3_defense_basis.py
│   ├── step4_elements.py
│   ├── step5_claim_facts.py
│   ├── step6_issues.py
│   ├── step7_proof.py
│   ├── step8_facts.py
│   ├── sufficiency_gate.py
│   ├── step9_subsumption.py
│   └── judge_dashboard.py
│
├── chains/
│   ├── structured_llm.py
│   ├── prompt_factory.py
│   └── output_parsers.py
│
├── tools/
│   ├── legal_kb_tools.py
│   ├── web_law_search_tool.py
│   ├── consistency_check_tools.py
│   └── risk_check_tools.py
│
├── schemas/
│   ├── inputs.py
│   ├── intermediates.py
│   ├── outputs.py
│   ├── dashboard.py
│   └── kb.py
│
├── kb/
│   ├── loader.py
│   ├── retriever.py
│   ├── reranker.py
│   └── verifier.py
│
├── prompts/
│   ├── step1.py
│   ├── step2.py
│   ├── step3.py
│   └── ...
│
├── evals/
│   ├── direct_strong_baseline.py
│   ├── workflow_eval.py
│   └── statistical_tests.py
│
└── config/
    └── settings.py
```

---

## 九、重构时最容易踩的坑

### 1. 不要把每一步都做成“Agent”

九步法不是让九个 agent 自由讨论。它更适合：

```text
确定性节点 + 结构化输出 + 有限工具调用
```

每一步只允许它完成该步骤的任务，不要让 Step 4 又去重写 Step 2 的请求权基础。

### 2. 不要放弃现有 Pydantic schema

这是你项目最值钱的部分之一。LangChain structured output 正好可以接它，不需要推倒重来。

### 3. 不要让 Tool 自由调用法条

法律辅助系统里，工具调用要可控。建议是：

```text
Step 2 只能调用 request_basis_retriever
Step 3 只能调用 defense_basis_retriever
Step 9 只能调用 verified_law_effect_retriever
```

不要给一个通用 agent 所有工具，否则它会“聪明过头”。

### 4. 不要迷信 LangChain 会自动降耗

LangChain 本身不会自动让你变快。真正降耗来自：

```text
节点内并行
上下文压缩
缓存检索结果
缓存法条搜索
减少重复传全量上下文
中断恢复
失败节点重跑
```

LangGraph只是让这些更容易组织。

---

## 十、我建议的迁移路线

### 第 1 阶段：薄封装，保持结果一致

目标：不改业务逻辑，只把 orchestrator 换成 LangGraph。

做法：

```text
保留原 step 函数
每个 LangGraph node 内部直接调用原 step
保持 WorkflowResult 输出不变
跑原来的 50 样本测试，确认分数不下降
```

这一阶段风险最低。

### 第 2 阶段：结构化输出改造

目标：减少 JSON 容错，提高稳定性。

做法：

```text
每个 step 使用 llm.with_structured_output(StepXOutput)
保留 Pydantic 校验
解析失败进入 retry / repair chain
```

### 第 3 阶段：并行化 Step 2 / Step 3 / Step 7 / Step 8

目标：降低耗时。

做法：

```text
每个诉请并行检索请求权基础
每条答辩并行检索抗辩基础
每个争点并行生成举证计划
每个要件事实并行事实认定
```

### 第 4 阶段：引入 checkpoint / human-in-the-loop

目标：支持 `awaiting_user_choice` 不重跑全流程。

做法：

```text
fallback_gate 中断
前端展示选项
用户选择后从 checkpoint 恢复
```

### 第 5 阶段：加 judge_review_dashboard

目标：把系统定位彻底改成“法官审理工作台”。

输出：

```json
{
  "judge_review_dashboard": {
    "claims_to_review": [],
    "claim_basis_defense_map": [],
    "issue_list": [],
    "element_fact_evidence_matrix": [],
    "risk_alerts": [],
    "hearing_path": [],
    "supplement_needed": [],
    "non_final_notice": "本结果仅供审判辅助，不替代法官裁判"
  }
}
```

---

## 十一、是否值得重构？

我的建议是：

> **值得，但不要为了“用了 LangChain”而重构；要为了状态可控、分支清晰、结构化输出、并行降耗、人机协同和可观测性而重构。**

你现在项目的痛点正好是 LangGraph 能帮上的：

```text
1. 九步法状态流复杂
2. fallback_gate 分支复杂
3. 部分步骤可以并行
4. 每步都需要结构化输出
5. 需要记录中间产物和调试轨迹
6. 需要支持用户补充材料后继续执行
7. 需要做大规模实验和评估
```

所以最终架构建议是：

> **LangGraph 做九步法审判辅助状态机；LangChain LCEL 做每个节点内的 prompt + llm + parser；原五层标签库保留并包装为 retriever/tool；LangSmith 做追踪和实验评估。**

这会比现在的手写 orchestrator 更清晰，也更容易把系统讲成一个真正的“审判辅助工作台”。

[1]: https://python.langchain.ac.cn/docs/concepts/lcel/ "LangChain 表达式语言 (LCEL) | ️ LangChain Python 教程"
[2]: https://docs.langchain.com/ "Home - Docs by LangChain"
[3]: https://docs.langchain.com/oss/python/langchain/structured-output "Structured output - Docs by LangChain"
