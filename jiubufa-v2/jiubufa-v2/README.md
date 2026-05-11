# 九步法 AI 审案工作流（后端实现）

基于"要件审判九步法"和五层法律标签库（L1-L5）的 AI 审案工作流后端系统。

## 目录结构

```
jiubufa/
├── README.md                    # 本文档
├── requirements.txt             # Python 依赖
├── run_workflow.py              # 命令行入口（CLI）
├── api.py                       # FastAPI HTTP 接口
├── orchestrator.py              # 工作流编排器
├── config/
│   └── settings.py              # 全局配置（含 API Key 明文）
├── schemas/                     # Pydantic 数据模型
│   ├── inputs.py                # 案件输入对象
│   ├── kb.py                    # 法条规则单元结构
│   ├── intermediates.py         # 九步法中间产物
│   └── outputs.py               # 最终裁判输出
├── llm/
│   └── client.py                # DashScope（OpenAI 兼容）调用封装
├── kb/
│   ├── loader.py                # 加载 articles_annotated.jsonl
│   └── retriever.py             # 五层标签检索器
├── prompts/                     # 每个节点的 prompt 模板
│   └── templates.py
├── steps/                       # 九步法节点
│   ├── state.py                    # WorkflowState（流转状态对象）
│   ├── utils.py                    # parse_into / time_step / models_to_dicts
│   ├── step1_fix_claims.py
│   ├── step2_request_basis.py
│   ├── step3_defense_basis.py
│   ├── step4_elements.py
│   ├── step5_claim_facts.py
│   ├── step6_issues.py
│   ├── step7_proof.py
│   ├── step8_facts.py
│   └── step9_subsumption.py
├── fallback/
│   └── weak_judgment.py         # 保底裁判机制
├── examples/
│   └── sample_case.json         # 示例案件
└── data/                        # 法条库数据目录（articles_annotated.jsonl 放这里）
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 法条库放置
#    把 articles_annotated.jsonl 放到下列任一位置（按优先级自动探测）：
#      /mnt/project/legal_kb/data/processed/articles_annotated.jsonl
#      ./data/articles_annotated.jsonl
#    或在 config/settings.py 的 KB_PATH 中显式指定路径。

# 3. 命令行运行示例
python run_workflow.py --input examples/sample_case.json --out result.json --pretty

# 4. 或启动 HTTP 服务
uvicorn api:app --host 0.0.0.0 --port 8000
# 然后 POST 到 http://127.0.0.1:8000/api/workflow/run
# 健康检查：GET http://127.0.0.1:8000/api/health
# 知识库统计：GET http://127.0.0.1:8000/api/kb/stats
```

## API Key 与模型

API Key 已明文写入 `config/settings.py`（DashScope 兼容模式）。如需换 Key 或换 Base URL，
只改这一处即可，所有模块共用同一个 LLMClient 单例。

## 工作流分支与状态

`POST /api/workflow/run` 返回的 `WorkflowResult.status` 取值：

- `ok` —— 已完成裁判输出（强裁判 / 弱裁判 / 部分输出之一）
- `awaiting_user_choice` —— 中等风险但未传 `fallback_user_choice`，需要前端把 `fallback_gate.available_choices` 渲染给用户后再请求一次
- `blocked` —— 硬性拦截或评分过低，仅返回缺口清单

## 输入材料规范

参见 `Jiubufa_Workflow_Design_V3_GPT.md` 第 3 节。最小输入示例：

```json
{
  "case_basic_info": { "case_name": "xxx", "case_cause_text": "买卖合同纠纷" },
  "party_info": [...],
  "claims": [...],
  "claim_facts": [...],
  "defense_opinions": [...],
  "evidence_list": [...]
}
```

## 模型与并发

- 默认模型：`qwen3.5-plus`（配置见 `config/settings.py`）
- 可选：`qwen3.6-max-preview`、`qwen3.6-plus`、`qwen3.6-flash`、`deepseek-v4-flash`
- 同步串行执行九步，每步一次或多次 LLM 调用，全程结构化 JSON 输出。

## 保底裁判机制

第九步前会计算 `input_sufficiency_score`（满分 100）：
- ≥80：强裁判
- 60-79：中风险裁判（附风险提示）
- 40-59：触发用户选择门（默认 supplement）
- <40：硬性拦截，仅输出补正清单

工作流接口接受 `fallback_user_choice` 参数：`supplement` / `continue_weak_judgment` / `partial_output_only`。
