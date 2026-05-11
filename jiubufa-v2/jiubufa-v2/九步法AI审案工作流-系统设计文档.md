# 九步法 AI 审案工作流 —— 系统设计文档

> 文档版本：V1.0
> 编写日期：2026-05-08
> 项目名称：九步法 AI 审案工作流（后端系统）
> 技术栈：Python 3.12 + FastAPI + Pydantic + OpenAI SDK（DashScope 兼容模式）

---

## 目录

- [一、概要设计](#一概要设计)
  - [1.1 项目背景](#11-项目背景)
  - [1.2 建设目标](#12-建设目标)
  - [1.3 系统定位](#13-系统定位)
  - [1.4 设计原则](#14-设计原则)
  - [1.5 系统总体架构](#15-系统总体架构)
  - [1.6 技术选型](#16-技术选型)
- [二、详细设计](#二详细设计)
  - [2.1 系统架构设计](#21-系统架构设计)
  - [2.2 模块划分](#22-模块划分)
  - [2.3 核心模块详细设计](#23-核心模块详细设计)
    - [2.3.1 工作流编排器（Orchestrator）](#231-工作流编排器orchestrator)
    - [2.3.2 九步法步骤模块（Steps）](#232-九步法步骤模块steps)
    - [2.3.3 法律知识库模块（KB）](#233-法律知识库模块kb)
    - [2.3.4 LLM 客户端模块（LLM Client）](#234-llm-客户端模块llm-client)
    - [2.3.5 保底裁判模块（Fallback）](#235-保底裁判模块fallback)
    - [2.3.6 Prompt 模板模块（Prompts）](#236-prompt-模板模块prompts)
    - [2.3.7 API 服务层（API）](#237-api-服务层api)
    - [2.3.8 配置中心（Config）](#238-配置中心config)
  - [2.4 数据流设计](#24-数据流设计)
  - [2.5 状态管理设计](#25-状态管理设计)
  - [2.6 错误处理与容错设计](#26-错误处理与容错设计)
- [三、接口文档（API 规范）](#三接口文档api-规范)
  - [3.1 接口概述](#31-接口概述)
  - [3.2 通用约定](#32-通用约定)
  - [3.3 接口详情](#33-接口详情)
    - [3.3.1 GET /api/health — 健康检查](#331-get-apihealth--健康检查)
    - [3.3.2 GET /api/kb/stats — 知识库统计](#332-get-apikbstats--知识库统计)
    - [3.3.3 POST /api/workflow/run — 执行完整工作流](#333-post-apiworkflowrun--执行完整工作流)
    - [3.3.4 POST /api/workflow/score_only — 仅评分](#334-post-apiworkflowscore_only--仅评分)
  - [3.4 错误码定义](#34-错误码定义)
- [四、数据字典](#四数据字典)
  - [4.1 输入数据模型](#41-输入数据模型)
  - [4.2 中间数据模型](#42-中间数据模型)
  - [4.3 输出数据模型](#43-输出数据模型)
  - [4.4 知识库数据模型](#44-知识库数据模型)
  - [4.5 枚举值字典](#45-枚举值字典)
- [五、部署与运维](#五部署与运维)
  - [5.1 环境要求](#51-环境要求)
  - [5.2 部署方案](#52-部署方案)
  - [5.3 配置管理](#53-配置管理)
  - [5.4 日志与监控](#54-日志与监控)

---

## 一、概要设计

### 1.1 项目背景

随着人工智能技术在法律领域的深入应用，司法审判辅助系统正从简单的文书检索向结构化推理方向发展。"要件审判九步法"是中国大陆法院广泛采用的审判方法论，将案件审理过程分解为九个逻辑严密的步骤。本项目旨在将这一方法论与 AI 大语言模型相结合，构建一个能够自动完成从诉讼请求固定到裁判输出的智能审案工作流系统。

系统通过五层法律标签体系（L1-L5）对法律条文进行结构化标注，结合 LLM 的自然语言理解能力，实现法律推理的结构化、可追溯和可解释。

### 1.2 建设目标

1. **自动化审判推理**：按照九步法逻辑自动完成案件分析，输出裁判文书框架
2. **知识增强**：结合结构化法律知识库，确保法律适用准确性，减少 LLM 幻觉
3. **渐进式裁判**：根据输入材料充足度动态调整裁判策略，避免在材料不足时"硬判"
4. **可追溯性**：完整保留每步推理中间产物，支持推理链路回溯
5. **工程健壮**：完善的容错、重试、日志机制，适合生产环境部署

### 1.3 系统定位

- **系统类型**：后端服务（Backend Service）
- **服务对象**：法律智能辅助系统、案件分析平台、法律文书生成系统
- **调用方式**：HTTP RESTful API / 命令行工具
- **部署方式**：独立服务部署，无状态设计，支持水平扩展

### 1.4 设计原则

| 原则 | 说明 |
|------|------|
| **数据驱动** | 所有法律推理基于输入案件材料和知识库规则单元，LLM 不"自由发挥" |
| **结构化输出** | 所有 LLM 调用强制 JSON 输出，通过 Pydantic 严格校验 |
| **容错优先** | 每步异常不阻断整体流程，LLM 调用失败自动重试 |
| **渐进式裁判** | 根据材料充足度动态选择强裁判/弱裁判/部分输出/阻断 |
| **可追溯性** | 每步中间产物完整保留，裁判结果关联到要件/事实/证据/法条 |
| **标签约束** | 所有法律标签使用预定义枚举，禁止自创新标签 |

### 1.5 系统总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Web 前端 │  │ 移动端   │  │ 第三方   │  │ 命令行 CLI   │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
└───────┼─────────────┼─────────────┼────────────────┼───────────┘
        │             │             │                │
        └─────────────┴──────┬──────┴────────────────┘
                             │ HTTP / JSON File
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     API 网关层                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI Application (api.py)                            │  │
│  │  - CORS 中间件                                            │  │
│  │  - 请求校验（Pydantic）                                   │  │
│  │  - 路由分发                                               │  │
│  └────────────────────────┬─────────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     业务逻辑层                                   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  工作流编排器 (orchestrator.py)                           │  │
│  │  - Step 1~9 顺序调度                                      │  │
│  │  - 保底裁判分支决策                                       │  │
│  │  - 错误收集与状态管理                                     │  │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │                                                       │
│  ┌──────┴──────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Steps 模块  │  │ KB 模块  │  │ LLM 模块 │  │ Fallback   │  │
│  │ (九步法)    │  │ (知识库) │  │ (大模型) │  │ (保底机制) │  │
│  └─────────────┘  └──────────┘  └──────────┘  └────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Prompts 模块（Prompt 模板管理）                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     数据层                                       │
│                                                                 │
│  ┌──────────────────────┐  ┌────────────────────────────────┐  │
│  │  法律知识库           │  │  LLM 服务（DashScope）          │  │
│  │  articles_annotated  │  │  - qwen3.5-plus（默认）        │  │
│  │  .jsonl              │  │  - qwen3.6-max-preview         │  │
│  │  (JSONL 文件)        │  │  - deepseek-v4-flash           │  │
│  └──────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.6 技术选型

| 组件 | 技术选型 | 版本要求 | 选型理由 |
|------|----------|----------|----------|
| 编程语言 | Python | 3.12+ | 生态丰富，AI/ML 首选语言 |
| Web 框架 | FastAPI | ≥0.110.0 | 高性能异步框架，自动生成 OpenAPI 文档 |
| 数据校验 | Pydantic | ≥2.5.0 | 强类型校验，与 FastAPI 深度集成 |
| ASGI 服务器 | Uvicorn | ≥0.27.0 | FastAPI 推荐服务器 |
| LLM 客户端 | OpenAI SDK | ≥1.40.0 | DashScope 兼容 OpenAI 协议 |
| 文件解析 | python-multipart | ≥0.0.9 | 表单数据处理 |

---

## 二、详细设计

### 2.1 系统架构设计

系统采用**分层架构**设计，自下而上分为四层：

#### 数据层（Data Layer）

- **法律知识库**：JSONL 格式的结构化法条数据，包含五层标签（L1-L5）
- **LLM 服务**：外部大语言模型服务，通过 DashScope API 调用

#### 基础设施层（Infrastructure Layer）

- **KB Loader**：法条库加载器，解析 JSONL 并构建内存索引
- **KB Retriever**：五层标签检索引擎，加权打分召回规则单元
- **LLM Client**：LLM 调用封装，支持重试、JSON 容错解析
- **Config**：全局配置中心（API Key、模型、路径、阈值）

#### 业务逻辑层（Business Logic Layer）

- **Steps（九步法步骤）**：每个步骤的独立实现，接收 State 并写回 State
- **Prompts（模板）**：每个步骤的 System Prompt 和 User Prompt 模板
- **Orchestrator（编排器）**：工作流总调度器，按序执行步骤并处理分支
- **Fallback（保底机制）**：评分、拦截、弱裁判生成

#### 接口层（API Layer）

- **FastAPI Application**：HTTP 服务入口，路由分发，请求校验
- **CLI Entry**：命令行入口，文件读写

### 2.2 模块划分

系统共划分为 **8 个核心模块**，模块间依赖关系如下：

```
                    ┌───────────┐
                    │   api.py  │
                    │ (服务层)  │
                    └─────┬─────┘
                          │
                    ┌─────┴──────────┐
                    │ orchestrator.py │
                    │  (编排器)       │
                    └──┬──┬──┬──┬───┘
                       │  │  │  │
              ┌────────┘  │  │  └────────┐
              │           │  │           │
        ┌─────┴─────┐ ┌──┴──┴──┐ ┌──────┴──────┐
        │  steps/   │ │ kb/    │ │  fallback/  │
        │ (九步法)  │ │(知识库)│ │ (保底机制)  │
        └──┬───┬────┘ └───┬────┘ └──────┬──────┘
           │   │          │             │
           │   └──────────┼─────────────┘
           │              │
        ┌──┴──────────────┴──┐
        │    llm/client.py   │
        │   (LLM 客户端)     │
        └──────────┬─────────┘
                   │
        ┌──────────┴─────────┐
        │  prompts/templates │
        │  (Prompt 模板)     │
        └────────────────────┘
                   │
        ┌──────────┴─────────┐
        │  config/settings   │
        │  (配置中心)        │
        └────────────────────┘
```

#### 模块清单

| 模块 | 文件/目录 | 职责 | 依赖 |
|------|-----------|------|------|
| **API 服务层** | `api.py` | HTTP 接口定义、路由分发、请求校验 | orchestrator, schemas, config, kb |
| **工作流编排器** | `orchestrator.py` | Step 1~9 调度、保底分支决策、结果组装 | steps, llm, schemas, fallback |
| **九步法步骤** | `steps/` | 每个步骤的具体实现 | llm, prompts, schemas, kb |
| **法律知识库** | `kb/` | 法条加载、标签检索 | schemas, config |
| **LLM 客户端** | `llm/client.py` | LLM 调用封装、重试、JSON 容错 | config |
| **保底裁判** | `fallback/` | 评分、拦截、弱裁判/部分输出生成 | llm, prompts, schemas, steps |
| **Prompt 模板** | `prompts/templates.py` | 所有步骤的 Prompt 定义 | — |
| **配置中心** | `config/settings.py` | 全局配置管理 | — |
| **数据模型** | `schemas/` | 所有输入/中间/输出的 Pydantic 定义 | — |

### 2.3 核心模块详细设计

#### 2.3.1 工作流编排器（Orchestrator）

**文件**：`orchestrator.py`

**职责**：
1. 接收 `CaseInput`，按 Step 1→Step 8 顺序串行执行
2. 在 Step 8 之后执行硬性拦截检查 + 充足度评分 + 用户选择门构造
3. 根据评分等级和用户选择进行分支决策
4. 执行 Step 9（强裁判分支）或生成弱裁判/部分输出
5. 任何步骤异常不阻断流程，写入 `state.errors` 继续推进
6. 组装最终 `WorkflowResult` 并返回

**核心函数**：

```python
def run_workflow(
    case_input: CaseInput,
    *,
    llm: Optional[LLMClient] = None,
) -> WorkflowResult
```

**执行流程**：

```
1. 初始化 WorkflowState(case_input=case_input)
2. 记录开始时间
3. 顺序执行 Step 1~8（每步通过 _safe_run_step 包裹异常）
4. 执行硬性拦截检查：check_hard_block(state)
5. 执行充足度评分：score_sufficiency(state, llm)
6. 构造用户选择门：build_fallback_gate(score, hard_block_reasons)
7. 分支决策：
   7.1 硬拦截存在 → status=blocked，返回补正清单
   7.2 评分 < 40 (block) → 仅允许 partial_output_only，否则 blocked
   7.3 评分 40-59 (weak_optional) → 等待用户选择
       - 无选择 → awaiting_user_choice
       - supplement → blocked
       - partial_output_only → 生成部分输出
       - continue_weak_judgment → 生成弱裁判
   7.4 评分 60-79 (medium) → 默认继续 Step 9（带风险提示）
       - supplement → blocked
       - partial_output_only → 生成部分输出
       - continue_weak_judgment → 生成弱裁判
       - 默认/proceed_with_risk → 执行 Step 9
   7.5 评分 ≥ 80 (strong) → 直接执行 Step 9
8. 构造 WorkflowResult 并返回
```

**分支决策矩阵**：

| 评分等级 | 用户选择 | 结果状态 | 输出类型 |
|----------|----------|----------|----------|
| 任意 | — | 硬拦截存在 | blocked | 补正清单 |
| block (<40) | partial_output_only | ok | PartialOutput |
| block (<40) | 其他/无 | blocked | 补正清单 |
| weak_optional (40-59) | 无 | awaiting_user_choice | FallbackGate |
| weak_optional (40-59) | supplement | blocked | 补正清单 |
| weak_optional (40-59) | partial_output_only | ok | PartialOutput |
| weak_optional (40-59) | continue_weak_judgment | ok | WeakJudgmentOutput |
| medium (60-79) | supplement | blocked | 补正清单 |
| medium (60-79) | partial_output_only | ok | PartialOutput |
| medium (60-79) | continue_weak_judgment | ok | WeakJudgmentOutput |
| medium (60-79) | 无/proceed_with_risk | ok | StrongJudgmentOutput（带风险提示） |
| strong (≥80) | 任意（除 supplement） | ok | StrongJudgmentOutput |
| strong (≥80) | supplement | blocked | 补正清单 |

**辅助函数**：

| 函数 | 说明 |
|------|------|
| `_safe_run_step(state, step_attr, fn)` | 安全执行单个步骤，异常不抛出，写入 state.errors |
| `_run_strong_branch(state, llm, score, started_at, with_risk_notes)` | 执行强裁判分支（Step 9 + 文书框架 + 一致性校验） |
| `_build_document_skeleton(state, subs)` | 构建裁判文书框架（诉讼请求/辩称/焦点/查明/认为/主文/法条） |
| `_build_consistency_check(state, subs)` | 执行"八个一致"校验 |
| `_make_result(state, status, started_at, strong, weak, partial)` | 组装最终 WorkflowResult |

---

#### 2.3.2 九步法步骤模块（Steps）

**目录**：`steps/`

**公共组件**：

- `state.py`：定义 `WorkflowState` 数据类，承载所有中间产物
- `utils.py`：工具函数（`parse_into`、`time_step`、`models_to_dicts`、`safe_dump`）

**每个步骤的统一接口**：

```python
def run(state: WorkflowState, *, llm: LLMClient) -> StepXOutput:
    """执行第 X 步，写回 state.stepX 并返回。"""
    with time_step(state, STEP_KEY):
        user_prompt = _build_user_prompt(state)
        result = llm.chat_json(SYSTEM_PROMPT, user_prompt, step_key=STEP_KEY)
        output = parse_into(StepXOutput, result, fallback=StepXOutput())
        state.stepX = output
        return output
```

**九个步骤详细设计**：

##### Step 1：固定权利请求（step1_fix_claims.py）

| 项目 | 内容 |
|------|------|
| **输入** | CaseInput（claims, party_info, claim_facts, legal_arguments） |
| **输出** | Step1Output（fixed_claims, case_cause_inferred, legal_domain_inferred, overall_clarification） |
| **处理逻辑** | 1. 规范化每项诉讼请求<br>2. 判断明确性和可执行性<br>3. 映射到 L3 claim_type 标签<br>4. 推断 legal_domain 和 case_cause<br>5. 识别请求权竞合/聚合/备位关系<br>6. 生成释明问题 |
| **LLM 调用** | 1 次，step_key="step1_claim_fixing" |
| **知识库检索** | 无 |

##### Step 2：确定请求权基础规范（step2_request_basis.py）

| 项目 | 内容 |
|------|------|
| **输入** | Step1Output（fixed_claims） |
| **输出** | Step2Output（request_basis_candidates, competition_analysis） |
| **处理逻辑** | 1. 从 fixed_claims 提取 claim_type、case_cause、legal_domain<br>2. 调用 kb.search_request_basis() 检索候选规则单元（top-k=12）<br>3. 将候选规则单元和诉求喂给 LLM 选择最适合的请求权基础<br>4. 标注 priority（primary/alternative/supplementary）<br>5. 处理请求权竞合 |
| **LLM 调用** | 1 次，step_key="step2_request_basis" |
| **知识库检索** | search_request_basis()，按 L2/L3 标签硬过滤 + 加权打分 |

##### Step 3：确定抗辩权基础规范（step3_defense_basis.py）

| 项目 | 内容 |
|------|------|
| **输入** | defense_opinions + fixed_claims + request_basis_candidates |
| **输出** | Step3Output（defense_basis_candidates） |
| **处理逻辑** | 1. 将答辩分类为：承认/否认/抗辩/抗辩权/程序性异议<br>2. 区分"否认"与"真正抗辩"<br>3. 映射到 L3 defense_type 标签<br>4. 调用 kb.search_defense_basis() 检索候选规则单元（top-k=10）<br>5. 为真正抗辩选择支持规则单元 |
| **LLM 调用** | 1 次，step_key="step3_defense_basis" |
| **知识库检索** | search_defense_basis() |

##### Step 4：构成要件分析（step4_elements.py）

| 项目 | 内容 |
|------|------|
| **输入** | request_basis_candidates + defense_basis_candidates + 知识库 L4 要件 |
| **输出** | Step4Output（element_matrix） |
| **处理逻辑** | 1. 从选定的请求权/抗辩权基础中提取 L4 构成要件<br>2. 构建要件矩阵（element_matrix）<br>3. 标注要件类型、逻辑关系、隐藏要件、消极要件、例外要件<br>4. 标注事实槽位、举证责任方、证明标准、建议证据类型 |
| **LLM 调用** | 1 次，step_key="step4_elements" |
| **知识库检索** | 直接读取已选规则单元的 L4_elements_proof |

##### Step 5：诉讼主张检索（step5_claim_facts.py）

| 项目 | 内容 |
|------|------|
| **输入** | element_matrix + claim_facts |
| **输出** | Step5Output（claim_fact_mapping） |
| **处理逻辑** | 1. 将要件映射到需要证明的事实<br>2. 匹配当事人已主张的事实<br>3. 标注主张状态：asserted/missing/vague/conflicting<br>4. 对缺失/模糊事实生成释明问题 |
| **LLM 调用** | 1 次，step_key="step5_claim_facts" |
| **知识库检索** | 无 |

##### Step 6：争点整理（step6_issues.py）

| 项目 | 内容 |
|------|------|
| **输入** | element_matrix + claim_fact_mapping + defense_basis_candidates |
| **输出** | Step6Output（issues, review_order） |
| **处理逻辑** | 1. 识别事实争点和法律争点<br>2. 关联要件、诉求、抗辩、证据<br>3. 确定争点优先级（high/medium/low）<br>4. 确定审理顺序 |
| **LLM 调用** | 1 次，step_key="step6_issues" |
| **知识库检索** | 无 |

##### Step 7：举证质证（step7_proof.py）

| 项目 | 内容 |
|------|------|
| **输入** | issues + element_matrix + evidence_list + cross_examinations |
| **输出** | Step7Output（proof_plan） |
| **处理逻辑** | 1. 为每个要件/争点制定举证计划<br>2. 匹配现有证据<br>3. 识别证明缺口<br>4. 建议补充证据类型<br>5. 标注真伪不明时的法律后果 |
| **LLM 调用** | 1 次，step_key="step7_proof" |
| **知识库检索** | 无 |

##### Step 8：事实认定（step8_facts.py）

| 项目 | 内容 |
|------|------|
| **输入** | proof_plan + evidence_list + cross_examinations |
| **输出** | Step8Output（fact_findings） |
| **处理逻辑** | 1. 对每个要件事实进行认定<br>2. 采信/不采信证据并说明理由<br>3. 标注认定状态：proved/not_proved/unknown<br>4. 处理真伪不明时的举证责任后果 |
| **LLM 调用** | 1 次，step_key="step8_fact_finding" |
| **知识库检索** | 无 |

##### Step 9：要件归入并裁判（step9_subsumption.py）

| 项目 | 内容 |
|------|------|
| **输入** | fixed_claims + request_basis + defense_basis + element_matrix + fact_findings + issues |
| **输出** | Step9Output（subsumption_results） |
| **处理逻辑** | 1. 逐项将认定事实归入要件<br>2. 审查请求权是否成立<br>3. 审查抗辩是否成立<br>4. 适用 L5 法律效果标签<br>5. 生成裁判结论（supported/partially_supported/rejected/procedural_dismissal） |
| **LLM 调用** | 1 次，step_key="step9_subsumption" |
| **知识库检索** | 无（使用已选规则单元的 L5 法律效果） |

---

#### 2.3.3 法律知识库模块（KB）

**目录**：`kb/`

##### 加载器（loader.py）

**核心类**：`KnowledgeBase`

**职责**：
1. 从 `articles_annotated.jsonl` 读取数据
2. 解析每个 article 的 annotation.rule_units
3. 将每个 rule_unit 反序列化为 `RuleUnit` Pydantic 对象
4. 构建多维度倒排索引

**索引结构**：

```python
class KnowledgeBase:
    rule_units: List[RuleUnit]           # 所有规则单元列表
    _by_id: Dict[str, RuleUnit]          # rule_unit_id → RuleUnit 映射
    
    # 倒排索引（标签值 → rule_unit_id 集合）
    _idx_workflow_step: Dict[str, Set[str]]    # workflow_step → ids
    _idx_norm_type: Dict[str, Set[str]]        # norm_type → ids
    _idx_claim_type: Dict[str, Set[str]]       # claim_type → ids
    _idx_defense_type: Dict[str, Set[str]]     # defense_type → ids
    _idx_legal_domain: Dict[str, Set[str]]     # legal_domain → ids
    _idx_case_cause: Dict[str, Set[str]]       # case_cause → ids
    _idx_effective: Dict[str, Set[str]]        # effective_status → ids
```

**加载流程**：

```
1. 探测法条库文件路径（resolve_kb_path）
   - 优先级：环境变量 > ./data/ > 外部路径
2. 逐行读取 JSONL 文件
3. 对每行 JSON：
   - 提取 annotation.rule_units 列表
   - 将父法条信息（law_name, article_no）冗余注入每个 rule_unit
4. 对每个 rule_unit：
   - Pydantic 校验（RuleUnit.model_validate）
   - 校验失败记录日志并跳过
5. 构建倒排索引
6. 返回 KnowledgeBase 实例
```

**单例管理**：

```python
_default_kb: Optional[KnowledgeBase] = None

def get_default_kb() -> KnowledgeBase:
    """获取全局单例知识库，首次调用时自动加载。"""
    
def reset_default_kb() -> None:
    """测试时手动重置。"""
```

##### 检索器（retriever.py）

**核心类**：`Retriever`

**查询对象**：`RetrievalQuery`

```python
@dataclass
class RetrievalQuery:
    workflow_step: str                    # 必需：九步法步骤标识
    norm_types: List[str] | None = None   # 期望的规范功能
    claim_types: List[str] | None = None  # 请求类型
    defense_types: List[str] | None = None # 抗辩类型
    case_causes: List[str] | None = None  # 案由（任意级别）
    legal_domains: List[str] | None = None # 法律领域
    require_effective: bool = True        # 是否仅检索现行有效
    must_norm_type: List[str] | None = None # 必须命中的规范类型（硬过滤）
    keyword_hints: List[str] | None = None  # 关键词兜底匹配
```

**检索流程**：

```
1. 候选集合构建：
   - 用 workflow_step 做第一道硬过滤
   - 若该 step 无标注，退化为遍历全库

2. 效力过滤：
   - require_effective=True 时，仅保留"现行有效"的规则单元

3. 规范类型硬过滤：
   - must_norm_type 不为空时，必须命中其中之一

4. 加权打分（对每个候选规则单元）：
   - workflow_step 命中：+1
   - norm_type 命中：+3/个
   - claim_type 命中：+5/个
   - defense_type 命中：+5/个
   - case_cause_l4 命中：+4/个
   - case_cause_l3 命中：+3/个
   - case_cause_l2 命中：+2/个
   - case_cause_l1 命中：+1/个
   - legal_domain 命中：+2/个
   - special_priority="特别规则"：+1
   - keyword_hints 命中：+0.5/个

5. 排序：按总分降序

6. 截断：返回 top-k 个 ScoredRuleUnit
```

**便捷检索函数**：

| 函数 | 说明 |
|------|------|
| `search_request_basis(...)` | 检索请求权基础（Step 2 使用），top-k=12 |
| `search_defense_basis(...)` | 检索抗辩权基础（Step 3 使用），top-k=10 |

---

#### 2.3.4 LLM 客户端模块（LLM Client）

**文件**：`llm/client.py`

**核心类**：`LLMClient`

**职责**：
1. 封装 DashScope OpenAI 兼容模式的 API 调用
2. 支持同步和异步两套接口
3. JSON 强制输出 + 容错解析
4. 指数退避重试
5. 按 step_key 自动选择模型

**配置参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| API Key | `sk-69b24c1abe964a0389c794d35bba9fd3` | DashScope API Key |
| Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容端点 |
| 默认模型 | `dashscope-qwen-plus` → `qwen3.5-plus` | 默认 LLM 模型 |
| Temperature | 0.2 | 法律推理偏低温 |
| Max Tokens | 4096 | 最大输出长度 |
| Timeout | 180s | 单次调用超时 |
| Max Retries | 3 | 最大重试次数 |
| Retry Base Delay | 2s | 重试基础延迟（指数退避） |

**模型注册表**：

| Model ID | 实际模型名 | 说明 |
|----------|------------|------|
| `dashscope-qwen` | `qwen3.6-max-preview` | 最强模型 |
| `dashscope-qwen-plus` | `qwen3.5-plus` | 默认模型（综合性价比） |
| `dashscope-qwen3.6-plus` | `qwen3.6-plus` | 增强版 |
| `dashscope-qwen3.6-flash` | `qwen3.6-flash` | 快速版 |
| `dashscope-deepseek` | `deepseek-v4-flash` | DeepSeek 模型 |

**核心方法**：

```python
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
```

**模型选择逻辑**：

```
1. 若传入 model_id → 使用该模型
2. 若传入 step_key → 查 STEP_MODEL_OVERRIDES 映射表
3. 否则 → 使用 DEFAULT_MODEL_ID
```

**JSON 容错解析流程**：

```
1. 去除 markdown 代码块包裹（```json ... ```）
2. 尝试直接 json.loads()
3. 失败 → 提取第一个 { 到最后一个 } 之间的内容
4. 仍失败 → 尝试数组格式 [ ... ]
5. 仍失败 → 修复尾随逗号（,} → }）
6. 仍失败 → 抛出 ValueError，附带原文前 500 字
```

**重试策略**：

```
捕获异常类型：RateLimitError, APIError, ValueError
重试次数：最多 3 次
退避策略：指数退避
  - 第 1 次失败：等待 2s
  - 第 2 次失败：等待 4s
  - 第 3 次失败：等待 8s，然后抛出异常

特殊回退：
  - 若 DashScope 不支持 response_format → 回退为文本模式
```

---

#### 2.3.5 保底裁判模块（Fallback）

**文件**：`fallback/weak_judgment.py`

**职责**：
1. 硬性拦截检查（check_hard_block）
2. 输入充足度评分（score_sufficiency）
3. 构造用户选择门（build_fallback_gate）
4. 生成弱裁判（generate_weak_judgment）
5. 生成部分输出（generate_partial_output）

##### 硬性拦截（check_hard_block）

**拦截条件**：

| 条件 | 拦截原因 |
|------|----------|
| `case.claims` 为空 | 没有任何诉讼请求，不能裁判 |
| `case.party_info` 为空 | 没有当事人信息，无法识别主体 |
| 所有 `fixed_claims.is_executable` = False | 所有诉求都不可执行，无法形成判决主文 |

**返回**：`List[str]` — 拦截原因列表，空列表表示无拦截

##### 充足度评分（score_sufficiency）

**评分策略**：优先使用 LLM 评分，失败时回退到规则法兜底

**七维度评分表**：

| 维度 | 满分 | 评分依据（规则法） |
|------|------|-------------------|
| claim_clarity | 20 | 每项 fixed_claim 的 is_clear(+6)、is_executable(+6)、有金额/行为(+3)，取平均 |
| legal_relation_stability | 15 | legal_domain 推断(+8) + case_cause 推断(+7) |
| request_basis_stability | 15 | 请求权基础候选数量：5 + 2×候选数，上限 15 |
| defense_path_completeness | 15 | 有答辩且有抗辩基础(+10)；有答辩无基础(+5)；无答辩(+4) |
| element_fact_coverage | 15 | asserted 事实数 / 总要件事实数 × 15 |
| evidence_coverage | 15 | 有证据覆盖的举证计划数 / 总举证计划数 × 15 |
| fact_finding_reliability | 10 | 已认定事实数（proved+not_proved）/ 总事实数 × 10 |

**评分等级**：

| 总分范围 | 等级 | 说明 |
|----------|------|------|
| ≥ 80 | strong | 材料充足，可直接裁判 |
| 60-79 | medium | 材料中等，可裁判但需风险提示 |
| 40-59 | weak_optional | 材料不足，需用户选择 |
| < 40 | block | 材料严重不足，硬性阻断 |

##### 用户选择门（build_fallback_gate）

**构造逻辑**：

```python
def build_fallback_gate(score, hard_block_reasons, extra_reasons) -> FallbackGate:
    """根据评分和拦截原因构造用户选择门。"""
```

**输出结构**：`FallbackGate`

| 字段 | 类型 | 说明 |
|------|------|------|
| risk_triggered | bool | 是否触发风险 |
| risk_level | str | 风险等级：low/medium/high/critical |
| reason | List[str] | 风险原因列表 |
| recommended_action | str | 推荐操作 |
| available_choices | List[Dict] | 可用选择列表 |
| default_choice | str | 默认选择 |
| hard_block | bool | 是否硬性拦截 |

**可用选择定义**：

| choice 值 | 标签 | 说明 |
|-----------|------|------|
| `supplement` | 补充材料 | 阻断裁判，返回补正清单 |
| `continue_weak_judgment` | 继续弱裁判 | 在材料不足下生成弱裁判（附风险提示） |
| `partial_output_only` | 仅部分输出 | 仅输出要件、争点、证据缺口，不输出裁判倾向 |
| `proceed_with_risk_notes` | 带风险继续 | 接受风险继续强裁判（medium 等级可用） |

##### 弱裁判生成（generate_weak_judgment）

**触发条件**：用户选择 `continue_weak_judgment`

**处理逻辑**：
1. 调用 LLM 基于已有中间产物生成弱裁判
2. 标注缺失输入、使用假设、未支持要件
3. 标注证据缺口、法律适用风险、事实认定风险、举证风险
4. 生成弱涵摄结果（weak_subsumption_results）
5. 列出升级到强裁判所需条件

**输出**：`WeakJudgmentOutput`

##### 部分输出生成（generate_partial_output）

**触发条件**：用户选择 `partial_output_only`

**处理逻辑**：
1. 提取 Step 1~6 的中间产物
2. 不执行 Step 9，不输出裁判倾向
3. 列出证据缺口和缺失输入

**输出**：`PartialOutput`

---

#### 2.3.6 Prompt 模板模块（Prompts）

**文件**：`prompts/templates.py`

**设计原则**：
1. System Prompt 给角色 + 总约束 + 输出 Schema 强约束（必须返回 JSON）
2. User Prompt 由每个步骤在运行时用具体输入材料拼接
3. 所有模板明确禁止"自由发挥"，要求严格沿输入数据和候选标签作答
4. 标签枚举值与五层标签体系严格一致

**公共前缀**：`COMMON_SYSTEM_PREFIX`

所有步骤共享的系统前缀，包含：
- 角色设定：中国大陆法律领域资深法律分析师
- 方法论：要件审判九步法 + 五层标签体系
- 通用约束：
  - 严格按输入数据和候选标签作答，禁止虚构
  - 信息不足必须标注 "missing" 或生成释明问题
  - 标签值使用给定枚举集合，不得自创新值
  - 输出必须是合法 JSON，不要 markdown 代码块包裹
  - 空列表必须返回 `[]`，不得省略字段

**各步骤 Prompt**：

| Prompt 常量 | 对应步骤 | 核心任务 |
|-------------|----------|----------|
| `STEP1_SYSTEM` | Step 1 | 固定权利请求 |
| `STEP2_SYSTEM` | Step 2 | 确定请求权基础规范 |
| `STEP3_SYSTEM` | Step 3 | 确定抗辩权基础规范 |
| `STEP4_SYSTEM` | Step 4 | 构成要件分析 |
| `STEP5_SYSTEM` | Step 5 | 诉讼主张检索 |
| `STEP6_SYSTEM` | Step 6 | 争点整理 |
| `STEP7_SYSTEM` | Step 7 | 举证质证 |
| `STEP8_SYSTEM` | Step 8 | 事实认定 |
| `STEP9_SYSTEM` | Step 9 | 要件归入并裁判 |
| `SUFFICIENCY_SCORING_SYSTEM` | 评分 | 七维度充足度评分 |
| `WEAK_JUDGMENT_SYSTEM` | 弱裁判 | 弱裁判生成 |

每个 System Prompt 包含：
- 公共前缀
- 当前步骤的任务描述
- 输入数据说明
- 输出 JSON Schema（严格定义）
- 标签枚举值列表

---

#### 2.3.7 API 服务层（API）

**文件**：`api.py`

**框架**：FastAPI

**中间件**：

| 中间件 | 配置 | 说明 |
|--------|------|------|
| CORS | allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"] | 允许所有来源跨域请求 |

**端点列表**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 + 模型注册表 |
| GET | `/api/kb/stats` | 知识库加载状态与统计 |
| POST | `/api/workflow/run` | 执行完整九步法工作流 |
| POST | `/api/workflow/score_only` | 仅跑 Step 1~8 + 评分（不出裁判） |

**请求模型**：

```python
class RunWorkflowRequest(BaseModel):
    case_input: CaseInput              # 案件输入
    model_name: Optional[str] = None   # 可选：覆盖默认模型
```

**启动命令**：

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1
```

---

#### 2.3.8 配置中心（Config）

**文件**：`config/settings.py`

**配置项分类**：

##### 路径配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROJECT_ROOT` | 项目根目录 | 通过 `__file__` 计算 |
| `DATA_DIR` | `PROJECT_ROOT/data/` | 数据目录 |
| `DEFAULT_KB_PATH` | `DATA_DIR/articles_annotated.jsonl` | 默认法条库路径 |

**路径探测优先级**：
1. 环境变量 `JIUBUFA_KB_PATH`
2. `./data/articles_annotated.jsonl`
3. `../legal_kb/data/processed/articles_annotated.jsonl`
4. `/mnt/project/legal_kb/data/processed/articles_annotated.jsonl`

##### LLM 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DASHSCOPE_API_KEY` | 环境变量或明文 Key | API 密钥 |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | API 端点 |
| `DEFAULT_MODEL_ID` | `dashscope-qwen-plus` | 默认模型 ID |
| `MODEL_REGISTRY` | 见模型注册表 | 模型 ID → 实际模型名映射 |
| `STEP_MODEL_OVERRIDES` | 空字典 | 每步单独指定模型 |

##### LLM 调用参数

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_TIMEOUT_SECONDS` | 180.0 | 超时时间 |
| `LLM_MAX_RETRIES` | 3 | 最大重试次数 |
| `LLM_RETRY_BASE_DELAY` | 2.0 | 重试基础延迟（秒） |
| `LLM_TEMPERATURE` | 0.2 | 温度参数 |
| `LLM_MAX_TOKENS` | 4096 | 最大输出 Token 数 |

##### 检索参数

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `KB_TOPK_REQUEST_BASIS` | 12 | Step 2 候选规则单元最大返回数 |
| `KB_TOPK_DEFENSE_BASIS` | 10 | Step 3 候选规则单元最大返回数 |

##### 保底机制阈值

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SUFFICIENCY_THRESHOLD_STRONG` | 80 | 强裁判最低分 |
| `SUFFICIENCY_THRESHOLD_MEDIUM` | 60 | 中风险最低分 |
| `SUFFICIENCY_THRESHOLD_WEAK` | 40 | 弱裁判最低分 |

##### 日志配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LOG_LEVEL` | 环境变量或 "INFO" | 日志级别 |

---

### 2.4 数据流设计

#### 2.4.1 整体数据流

```
CaseInput (JSON)
    │
    ├─→ API 层 / CLI 层
    │       │
    │       ▼
    │   Pydantic 校验（CaseInput）
    │       │
    │       ▼
    │   Orchestrator.run_workflow()
    │       │
    │       ▼
    │   初始化 WorkflowState
    │       │
    │       ├─→ Step 1 ──→ state.step1 (Step1Output)
    │       │                  │
    │       ├─→ Step 2 ──→ state.step2 (Step2Output)
    │       │                  │
    │       ├─→ Step 3 ──→ state.step3 (Step3Output)
    │       │                  │
    │       ├─→ Step 4 ──→ state.step4 (Step4Output)
    │       │                  │
    │       ├─→ Step 5 ──→ state.step5 (Step5Output)
    │       │                  │
    │       ├─→ Step 6 ──→ state.step6 (Step6Output)
    │       │                  │
    │       ├─→ Step 7 ──→ state.step7 (Step7Output)
    │       │                  │
    │       ├─→ Step 8 ──→ state.step8 (Step8Output)
    │       │                  │
    │       ▼                  ▼
    │   保底机制检查
    │   ├─ check_hard_block() → hard_block_reasons
    │   ├─ score_sufficiency() → SufficiencyScore
    │   └─ build_fallback_gate() → FallbackGate
    │       │
    │       ▼
    │   分支决策
    │   ├─ blocked ──→ WorkflowResult(status="blocked")
    │   ├─ awaiting_user_choice ──→ WorkflowResult(status="awaiting_user_choice")
    │   ├─ weak_judgment ──→ generate_weak_judgment() → WeakJudgmentOutput
    │   ├─ partial_output ──→ generate_partial_output() → PartialOutput
    │   └─ strong_judgment ──→ Step 9 ──→ state.step9 (Step9Output)
    │                              │
    │                              ▼
    │                      构建裁判文书框架
    │                      执行一致性校验
    │                      生成 StrongJudgmentOutput
    │       │
    │       ▼
    │   组装 WorkflowResult
    │       │
    │       ▼
    │   返回给调用方（JSON 序列化）
    │
    └─→ 客户端 / 输出文件
```

#### 2.4.2 Step 间数据依赖

```
Step 1 (固定诉求)
  ├─ 输入: CaseInput.claims, party_info, claim_facts
  └─ 输出: fixed_claims → Step 2, Step 3, Step 5, Step 9

Step 2 (请求权基础)
  ├─ 输入: fixed_claims + KB 检索结果
  └─ 输出: request_basis_candidates → Step 3, Step 4, Step 9

Step 3 (抗辩权基础)
  ├─ 输入: defense_opinions + fixed_claims + request_basis + KB 检索
  └─ 输出: defense_basis_candidates → Step 4, Step 9

Step 4 (构成要件)
  ├─ 输入: request_basis + defense_basis + KB L4 要件
  └─ 输出: element_matrix → Step 5, Step 6, Step 7, Step 9

Step 5 (诉讼主张检索)
  ├─ 输入: element_matrix + claim_facts
  └─ 输出: claim_fact_mapping → Step 6

Step 6 (争点整理)
  ├─ 输入: element_matrix + claim_fact_mapping + defense_basis
  └─ 输出: issues → Step 7, Step 9

Step 7 (举证质证)
  ├─ 输入: issues + element_matrix + evidence_list + cross_examinations
  └─ 输出: proof_plan → Step 8

Step 8 (事实认定)
  ├─ 输入: proof_plan + evidence_list + cross_examinations
  └─ 输出: fact_findings → Step 9

Step 9 (要件归入裁判)
  ├─ 输入: fixed_claims + request_basis + defense_basis
  │        + element_matrix + fact_findings + issues
  └─ 输出: subsumption_results → StrongJudgmentOutput
```

---

### 2.5 状态管理设计

#### WorkflowState 设计

**类型**：Python dataclass

**设计模式**：共享可变状态对象（Shared Mutable State）

**生命周期**：

```
1. 创建：Orchestrator.run_workflow() 入口处
   state = WorkflowState(case_input=case_input)

2. 填充：每个步骤写回 state.stepX
   state.step1 = step1_output
   state.step2 = step2_output
   ...

3. 扩展：保底机制写入评分和选择门
   state.sufficiency_score = score
   state.fallback_gate = gate

4. 记录：每步异常和警告累积
   state.errors.append("...")
   state.warnings.append("...")
   state.timings_ms["step1"] = 1234

5. 消费：_make_result() 读取所有字段组装 WorkflowResult
```

**线程安全性**：当前为单线程同步执行，无需锁。如需并发处理多个案件，每个案件独立创建 WorkflowState 实例，天然隔离。

---

### 2.6 错误处理与容错设计

#### 2.6.1 错误分类

| 错误类型 | 处理方式 | 影响范围 |
|----------|----------|----------|
| **输入校验错误** | Pydantic 自动校验，返回 422 | 请求级别，阻断 |
| **LLM 调用失败** | 指数退避重试（最多 3 次） | 步骤级别 |
| **LLM JSON 解析失败** | 容错解析（去代码块、修尾逗号） | 步骤级别 |
| **步骤执行异常** | _safe_run_step 捕获，写入 state.errors | 步骤级别，不阻断流程 |
| **知识库加载失败** | 返回空 KB，检索返回空结果 | 影响 Step 2/3 检索 |
| **评分失败** | 回退到规则法兜底评分 | 保底机制级别 |
| **弱裁判生成失败** | 回退到 partial_output | 分支级别 |
| **Step 9 执行异常** | 记录错误，用已有中间产物构建裁判 | 裁判级别 |

#### 2.6.2 容错策略

**层级 1：LLM 调用容错**
- JSON 容错解析（4 层降级策略）
- 指数退避重试（3 次）
- response_format 不支持时回退文本模式

**层级 2：步骤执行容错**
- `_safe_run_step()` 包裹每个步骤
- 异常不向上抛出，写入 `state.errors`
- 后续步骤继续执行（可能因缺少前置数据而产出空结果）

**层级 3：保底机制容错**
- LLM 评分失败 → 回退规则法评分
- 弱裁判生成失败 → 回退部分输出
- 部分输出生成始终成功（基于已有中间产物）

**层级 4：最终结果容错**
- `_make_result()` 始终返回合法 WorkflowResult
- 即使所有步骤都失败，也返回 status + errors + warnings

---

## 三、接口文档（API 规范）

### 3.1 接口概述

系统提供 4 个 RESTful API 端点，基于 FastAPI 框架实现，支持自动生成的 OpenAPI/Swagger 文档。

**服务地址**：`http://{host}:{port}/api/`

**默认端口**：8000

**OpenAPI 文档**：`http://{host}:{port}/docs`

**ReDoc 文档**：`http://{host}:{port}/redoc`

### 3.2 通用约定

#### 请求约定

| 约定 | 说明 |
|------|------|
| 请求格式 | JSON（Content-Type: application/json） |
| 字符编码 | UTF-8 |
| 语言环境 | 中国大陆法律体系 |

#### 响应约定

| 约定 | 说明 |
|------|------|
| 响应格式 | JSON |
| 字符编码 | UTF-8（ensure_ascii=False） |
| 成功状态码 | 200 |
| 客户端错误 | 400, 422 |
| 服务端错误 | 500 |

#### 分页约定

当前版本不涉及分页。

### 3.3 接口详情

#### 3.3.1 GET /api/health — 健康检查

**接口描述**：检查服务健康状态，返回模型注册表和知识库加载状态。

**请求方式**：GET

**请求路径**：`/api/health`

**请求参数**：无

**响应结构**：

```json
{
  "status": "ok",
  "default_model": "dashscope-qwen-plus",
  "models": {
    "dashscope-qwen": "qwen3.6-max-preview",
    "dashscope-qwen-plus": "qwen3.5-plus",
    "dashscope-qwen3.6-plus": "qwen3.6-plus",
    "dashscope-qwen3.6-flash": "qwen3.6-flash",
    "dashscope-deepseek": "deepseek-v4-flash"
  },
  "kb_loaded": true,
  "kb_size": 12345
}
```

**响应字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 是 | 固定值 "ok" |
| default_model | string | 是 | 当前默认模型 ID |
| models | object | 是 | 模型注册表（model_id → model_name） |
| kb_loaded | boolean | 是 | 知识库是否成功加载 |
| kb_size | integer | 是 | 知识库中规则单元总数 |

**状态码**：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |

---

#### 3.3.2 GET /api/kb/stats — 知识库统计

**接口描述**：返回法律知识库的加载状态和多维度统计信息。

**请求方式**：GET

**请求路径**：`/api/kb/stats`

**请求参数**：无

**响应结构**：

```json
{
  "total_rule_units": 12345,
  "by_workflow_step": {
    "step2_request_basis": 3456,
    "step3_defense_basis": 2345,
    "step4_elements": 4567
  },
  "by_legal_domain": {
    "合同": 4567,
    "侵权": 2345,
    "物权": 1234
  },
  "by_norm_type": {
    "request_basis": 2345,
    "defense_basis": 1234,
    "definition": 890
  },
  "by_claim_type": {
    "payment_claim": 1234,
    "damages_claim": 890
  },
  "by_defense_type": {
    "limitation_defense": 567,
    "setoff_defense": 345
  }
}
```

**响应字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| total_rule_units | integer | 是 | 规则单元总数 |
| by_workflow_step | object | 是 | 按九步法步骤分组的数量统计 |
| by_legal_domain | object | 是 | 按法律领域分组的数量统计 |
| by_norm_type | object | 是 | 按规范功能分组的数量统计 |
| by_claim_type | object | 是 | 按请求类型分组的数量统计 |
| by_defense_type | object | 是 | 按抗辩类型分组的数量统计 |

**状态码**：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 500 | 知识库加载失败 |

**错误响应**：

```json
{
  "detail": "知识库加载失败：{error_message}"
}
```

---

#### 3.3.3 POST /api/workflow/run — 执行完整工作流

**接口描述**：执行完整的九步法审案工作流，返回裁判结果。

**请求方式**：POST

**请求路径**：`/api/workflow/run`

**请求头**：

| 头字段 | 值 | 必填 |
|--------|-----|------|
| Content-Type | application/json | 是 |

**请求体结构**：

```json
{
  "case_input": {
    "case_basic_info": {
      "case_id": "case-2024-mc-0001",
      "case_name": "甲公司诉乙公司买卖合同纠纷案",
      "case_cause_text": "买卖合同纠纷",
      "court": "示例市某区人民法院",
      "procedure_stage": "一审",
      "filing_date": "2024-06-15",
      "material_sources": ["起诉状", "答辩状", "证据清单"],
      "case_summary": "案件摘要..."
    },
    "party_info": [
      {
        "party_id": "p1",
        "party_name": "甲公司",
        "party_role": "原告",
        "legal_status": "法人",
        "relationship_to_case": "买卖合同的出卖人"
      },
      {
        "party_id": "p2",
        "party_name": "乙公司",
        "party_role": "被告",
        "legal_status": "法人",
        "relationship_to_case": "买卖合同的买受人"
      }
    ],
    "claims": [
      {
        "claim_id": "c1",
        "claim_text_original": "请求判令被告支付货款500,000元",
        "claimant": "p1",
        "respondent": "p2",
        "amount": 500000,
        "object_type": "金钱"
      }
    ],
    "claim_facts": [
      {
        "fact_id": "f1",
        "fact_text_original": "原被告签订买卖合同，原告已交付货物",
        "fact_time": "2024-01-10",
        "linked_claim_id": "c1"
      }
    ],
    "defense_opinions": [],
    "evidence_list": [],
    "fallback_user_choice": null
  },
  "model_name": null
}
```

**请求字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_input | CaseInput | 是 | 案件输入对象（详见数据字典 4.1） |
| model_name | string | 否 | 覆盖默认模型，必须在 MODEL_REGISTRY 中注册 |

**响应结构**：

```json
{
  "case_id": "case-2024-mc-0001",
  "status": "ok",
  "fallback_gate": {
    "risk_triggered": false,
    "risk_level": "low",
    "reason": [],
    "recommended_action": "proceed",
    "available_choices": [],
    "default_choice": "proceed",
    "hard_block": false
  },
  "step1": { /* Step1Output */ },
  "step2": { /* Step2Output */ },
  "step3": { /* Step3Output */ },
  "step4": { /* Step4Output */ },
  "step5": { /* Step5Output */ },
  "step6": { /* Step6Output */ },
  "step7": { /* Step7Output */ },
  "step8": { /* Step8Output */ },
  "step9": { /* Step9Output */ },
  "strong_judgment": {
    "mode": "strong_judgment",
    "sufficiency_score": { /* SufficiencyScore */ },
    "risk_level": "low",
    "subsumption_results": [ /* SubsumptionResult[] */ ],
    "document_skeleton": {
      "原告诉讼请求": [ /* ... */ ],
      "被告辩称": [ /* ... */ ],
      "争议焦点": [ /* ... */ ],
      "本院查明": [ /* ... */ ],
      "本院认为": [ /* ... */ ],
      "判决主文": [ /* ... */ ],
      "引用法条": [ /* ... */ ]
    },
    "consistency_check": { /* ... */ }
  },
  "weak_judgment": null,
  "partial_output": null,
  "timings_ms": {
    "step1_claim_fixing": 3200,
    "step2_request_basis": 4500,
    "total": 45000
  },
  "errors": [],
  "warnings": []
}
```

**响应字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | string | 否 | 案件 ID（从输入中提取） |
| status | string | 是 | 工作流状态：ok/blocked/awaiting_user_choice |
| fallback_gate | FallbackGate | 否 | 保底选择门（评分和风险信息的完整结构） |
| step1~step9 | StepXOutput | 否 | 各步骤中间产物（成功执行的步骤才有值） |
| strong_judgment | StrongJudgmentOutput | 否 | 强裁判输出（评分≥80 或 medium 继续时填充） |
| weak_judgment | WeakJudgmentOutput | 否 | 弱裁判输出（用户选择 continue_weak_judgment 时填充） |
| partial_output | PartialOutput | 否 | 部分输出（用户选择 partial_output_only 时填充） |
| timings_ms | object | 是 | 各步骤耗时（毫秒），含 total |
| errors | string[] | 是 | 错误列表 |
| warnings | string[] | 是 | 警告列表 |

**状态说明**：

| status 值 | 说明 | 前端处理建议 |
|-----------|------|-------------|
| `ok` | 工作流完成，已输出裁判 | 展示裁判结果（strong/weak/partial 三选一） |
| `awaiting_user_choice` | 等待用户选择保底方案 | 渲染 fallback_gate.available_choices，用户选择后重新提交（带 fallback_user_choice） |
| `blocked` | 硬性阻断 | 展示补正清单，提示用户补充材料 |

**状态码**：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功（工作流执行完成） |
| 400 | 请求参数错误（如 model_name 未注册） |
| 422 | 请求体校验失败（Pydantic 校验不通过） |
| 500 | 工作流执行异常 |

**错误响应示例**：

```json
{
  "detail": "未注册的模型：gpt-4。可用：['dashscope-qwen', 'dashscope-qwen-plus', ...]"
}
```

```json
{
  "detail": "工作流执行失败：{error_message}"
}
```

---

#### 3.3.4 POST /api/workflow/score_only — 仅评分

**接口描述**：仅执行 Step 1~8 并返回评分和用户选择门，不生成裁判输出。适用于前端在用户做出保底选择前先评估输入完整度。

**请求方式**：POST

**请求路径**：`/api/workflow/score_only`

**请求头**：

| 头字段 | 值 | 必填 |
|--------|-----|------|
| Content-Type | application/json | 是 |

**请求体结构**：与 `/api/workflow/run` 完全相同

**特殊处理**：
- 强制将 `case_input.fallback_user_choice` 设为 `null`，确保不触发裁判输出
- 剥离响应中的裁判结果（strong_judgment、weak_judgment、partial_output）

**响应结构**：

```json
{
  "case_id": "case-2024-mc-0001",
  "status": "awaiting_user_choice",
  "sufficiency_score": {
    "risk_triggered": true,
    "risk_level": "high",
    "reason": ["证据覆盖率较低", "事实认定可靠性不足"],
    "recommended_action": "supplement_and_retry",
    "available_choices": [
      {
        "choice": "supplement",
        "label": "补充材料",
        "description": "补充缺失材料后重新运行工作流"
      },
      {
        "choice": "continue_weak_judgment",
        "label": "继续弱裁判",
        "description": "在材料不足情况下生成弱裁判（附风险提示）"
      },
      {
        "choice": "partial_output_only",
        "label": "仅部分输出",
        "description": "仅输出要件、争点和证据缺口"
      }
    ],
    "default_choice": "supplement",
    "hard_block": false
  },
  "errors": [],
  "warnings": [],
  "timings_ms": {
    "step1_claim_fixing": 3200,
    "step2_request_basis": 4500,
    "total": 38000
  }
}
```

**响应字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| case_id | string | 否 | 案件 ID |
| status | string | 是 | 工作流状态 |
| sufficiency_score | FallbackGate | 否 | 评分和用户选择门（注意：字段名为 sufficiency_score 但实际是 FallbackGate 对象） |
| errors | string[] | 是 | 错误列表 |
| warnings | string[] | 是 | 警告列表 |
| timings_ms | object | 是 | 各步骤耗时 |

**状态码**：

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 422 | 请求体校验失败 |
| 500 | 工作流执行异常 |

---

### 3.4 错误码定义

| HTTP 状态码 | 错误类型 | 触发条件 | 处理建议 |
|-------------|----------|----------|----------|
| 200 | 成功 | 正常执行 | — |
| 400 | Bad Request | model_name 未注册 | 使用可用模型列表中的模型 |
| 422 | Unprocessable Entity | Pydantic 校验失败 | 检查请求体字段是否符合 Schema |
| 500 | Internal Server Error | 工作流内部异常 | 查看 errors 字段和服务器日志 |

**业务状态码**（在响应体的 `status` 字段中）：

| status 值 | 含义 | 触发条件 |
|-----------|------|----------|
| `ok` | 成功完成 | 工作流正常完成，已输出裁判 |
| `awaiting_user_choice` | 等待用户选择 | 评分处于 weak_optional 区间且未提供 fallback_user_choice |
| `blocked` | 阻断 | 硬性拦截条件触发或评分 < 40 且未选择 partial_output_only |

---

## 四、数据字典

### 4.1 输入数据模型

#### 4.1.1 CaseInput（顶层案件输入）

**定义文件**：`schemas/inputs.py`

**类型**：Pydantic BaseModel

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| case_basic_info | CaseBasicInfo | 否 | 空对象 | 案件基本信息 |
| party_info | List[PartyInfo] | 否 | [] | 当事人信息列表 |
| claims | List[ClaimObject] | 否 | [] | 诉讼请求列表（硬性拦截：为空则阻断） |
| claim_facts | List[ClaimFactObject] | 否 | [] | 事实主张列表 |
| defense_opinions | List[DefenseObject] | 否 | [] | 答辩/抗辩意见列表 |
| counterclaims | List[CounterclaimObject] | 否 | [] | 反诉列表 |
| evidence_list | List[EvidenceObject] | 否 | [] | 证据列表 |
| cross_examinations | List[CrossExaminationObject] | 否 | [] | 质证意见列表 |
| court_records | List[str] | 否 | [] | 庭审笔录原文段落 |
| legal_arguments | List[LegalArgumentObject] | 否 | [] | 法律意见列表 |
| procedural_info | ProceduralInfo | 否 | null | 程序事项 |
| existing_judgment_or_mediation | str | 否 | null | 已有判决或调解文书 |
| fallback_user_choice | str | 否 | null | 保底裁判用户选择 |

---

#### 4.1.2 CaseBasicInfo（案件基本信息）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| case_id | str | 否 | null | 案件编号/案号 |
| case_name | str | 否 | null | 案件名称 |
| case_cause_text | str | 否 | null | 案由文本（如"买卖合同纠纷"） |
| court | str | 否 | null | 审理法院 |
| procedure_stage | str | 否 | null | 程序阶段：一审/二审/再审/执行异议/程序性审查 |
| filing_date | str | 否 | null | 立案日期（ISO 格式） |
| material_sources | List[str] | 否 | [] | 材料来源列表（如"起诉状"、"答辩状"） |
| case_summary | str | 否 | null | 案件摘要 |

---

#### 4.1.3 PartyInfo（当事人信息）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| party_id | str | **是** | — | 当事人唯一标识 |
| party_name | str | 否 | null | 当事人名称 |
| party_role | str | 否 | null | 诉讼角色：原告/被告/第三人/申请人/被申请人 |
| legal_status | str | 否 | null | 法律主体类型：自然人/法人/非法人组织 |
| relationship_to_case | str | 否 | null | 与案件的关系描述 |
| identity_evidence | List[str] | 否 | [] | 身份证明材料列表 |
| standing_issue | bool | 否 | false | 是否存在主体资格争议 |

---

#### 4.1.4 ClaimObject（诉讼请求）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| claim_id | str | **是** | — | 诉求唯一标识 |
| claim_text_original | str | **是** | — | 诉求原文 |
| claim_text_normalized | str | 否 | null | 规范化后的诉求文本 |
| claimant | str | 否 | null | 请求方 party_id |
| respondent | str | 否 | null | 被请求方 party_id |
| claim_type_candidate | List[str] | 否 | [] | 请求类型候选标签 |
| object_type | str | 否 | null | 标的类型：金钱/物/行为/权利 |
| amount | float | 否 | null | 标的金额 |
| behavior_requested | str | 否 | null | 请求的行为 |
| is_clear | bool | 否 | null | 诉求是否明确 |
| is_executable | bool | 否 | null | 诉求是否可执行 |
| conflict_with_other_claims | List[str] | 否 | [] | 冲突的其他诉求 ID 列表 |
| supplement_needed | bool | 否 | false | 是否需要补充 |
| priority_type | str | 否 | null | 优先级类型：primary/alternative/parallel/selective |

---

#### 4.1.5 ClaimFactObject（事实主张）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| fact_id | str | **是** | — | 事实唯一标识 |
| fact_text_original | str | **是** | — | 事实主张原文 |
| fact_text_normalized | str | 否 | null | 规范化后的事实文本 |
| fact_time | str | 否 | null | 事实发生时间 |
| fact_actor | str | 否 | null | 事实行为方 party_id |
| fact_counterparty | str | 否 | null | 事实相对方 party_id |
| fact_type_candidate | List[str] | 否 | [] | 事实类型候选标签 |
| linked_claim_id | str | 否 | null | 关联的诉求 ID |
| linked_evidence_ids | List[str] | 否 | [] | 关联的证据 ID 列表 |
| possible_fact_slot | List[str] | 否 | [] | 可能对应的事实槽位 |
| clarity_status | str | 否 | null | 清晰度：明确/模糊/矛盾/遗漏 |
| opponent_response | str | 否 | null | 对方回应：承认/否认/不明确/抗辩 |

---

#### 4.1.6 DefenseObject（答辩/抗辩）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| defense_id | str | **是** | — | 答辩唯一标识 |
| defense_text_original | str | **是** | — | 答辩原文 |
| defense_text_normalized | str | 否 | null | 规范化后的答辩文本 |
| defense_target_claim_id | str | 否 | null | 针对的诉求 ID |
| response_type | str | 否 | null | 回应类型：承认/否认/抗辩/抗辩权/程序性异议 |
| defense_type_candidate | List[str] | 否 | [] | 抗辩类型候选标签 |
| new_fact_asserted | bool | 否 | false | 是否主张了新事实 |
| linked_evidence_ids | List[str] | 否 | [] | 关联的证据 ID 列表 |
| possible_defense_basis | List[str] | 否 | [] | 可能的抗辩依据 |
| clarification_needed | bool | 否 | false | 是否需要释明 |

---

#### 4.1.7 EvidenceObject（证据）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| evidence_id | str | **是** | — | 证据唯一标识 |
| evidence_name | str | **是** | — | 证据名称 |
| submitted_by | str | 否 | null | 提交方 party_id |
| evidence_type | str | 否 | null | 证据类型：书证/物证/证人证言/鉴定意见/电子数据等 |
| proof_purpose_original | str | 否 | null | 证明目的原文 |
| proof_purpose_normalized | str | 否 | null | 规范化后的证明目的 |
| linked_claim_id | str | 否 | null | 关联的诉求 ID |
| linked_defense_id | str | 否 | null | 关联的答辩 ID |
| linked_fact_ids | List[str] | 否 | [] | 关联的事实 ID 列表 |
| linked_element_ids | List[str] | 否 | [] | 关联的要件 ID 列表 |
| opponent_cross_examination | str | 否 | null | 对方质证意见 |
| legality_status | str | 否 | null | 合法性状态 |
| relevance_status | str | 否 | null | 关联性状态 |
| authenticity_status | str | 否 | null | 真实性状态 |
| probative_force | str | 否 | null | 证明力：强/中/弱/不采信 |
| adopted_status | str | 否 | null | 采信状态：采信/不采信/部分采信/待补充 |

---

#### 4.1.8 CrossExaminationObject（质证意见）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| cross_id | str | **是** | — | 质证唯一标识 |
| evidence_id | str | **是** | — | 关联的证据 ID |
| opponent | str | 否 | null | 质证方 party_id |
| legality_opinion | str | 否 | null | 合法性意见 |
| relevance_opinion | str | 否 | null | 关联性意见 |
| authenticity_opinion | str | 否 | null | 真实性意见 |
| probative_force_opinion | str | 否 | null | 证明力意见 |
| reason | str | 否 | null | 质证理由 |
| need_supplementary_proof | bool | 否 | false | 是否需要补充证明 |

---

#### 4.1.9 LegalArgumentObject（法律意见）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| argument_id | str | **是** | — | 法律意见唯一标识 |
| submitted_by | str | 否 | null | 提交方 party_id |
| target_claim_or_defense | str | 否 | null | 针对的诉求或答辩 ID |
| cited_law_name | str | 否 | null | 引用的法律名称 |
| cited_article_no | str | 否 | null | 引用的条文编号 |
| argument_text | str | 否 | null | 法律意见文本 |
| norm_type_candidate | List[str] | 否 | [] | 规范类型候选标签 |
| dispute_status | str | 否 | null | 争议状态 |
| court_view_needed | bool | 否 | false | 是否需要法院观点 |

---

#### 4.1.10 ProceduralInfo（程序事项）

| 字段名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| jurisdiction | str | 否 | null | 管辖权情况 |
| limitation_period_status | str | 否 | null | 诉讼时效状态 |
| proof_period_status | str | 否 | null | 举证期限状态 |
| other_notes | str | 否 | null | 其他程序事项说明 |

---

### 4.2 中间数据模型

#### 4.2.1 WorkflowState（工作流状态）

**定义文件**：`steps/state.py`

**类型**：Python dataclass

| 字段名 | 类型 | 说明 |
|--------|------|------|
| case_input | CaseInput | 原始案件输入 |
| step1 | Step1Output | 第一步输出：固定权利请求 |
| step2 | Step2Output | 第二步输出：请求权基础候选 |
| step3 | Step3Output | 第三步输出：抗辩权基础候选 |
| step4 | Step4Output | 第四步输出：构成要件矩阵 |
| step5 | Step5Output | 第五步输出：待证事实映射 |
| step6 | Step6Output | 第六步输出：争点列表 |
| step7 | Step7Output | 第七步输出：举证计划 |
| step8 | Step8Output | 第八步输出：事实认定结果 |
| step9 | Step9Output | 第九步输出：要件归入结果 |
| sufficiency_score | SufficiencyScore | 输入充足度评分 |
| fallback_gate | FallbackGate | 保底选择门 |
| timings_ms | Dict[str, int] | 各步骤耗时（毫秒） |
| errors | List[str] | 错误列表 |
| warnings | List[str] | 警告列表 |

---

#### 4.2.2 Step1Output（固定权利请求）

**定义文件**：`schemas/intermediates.py`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| case_cause_inferred | List[str] | 推断的案由列表 |
| legal_domain_inferred | List[str] | 推断的法律领域列表 |
| fixed_claims | List[FixedClaim] | 固定后的诉讼请求列表 |
| overall_clarification | List[str] | 整体释明问题列表 |

**FixedClaim 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_id | str | 诉求 ID |
| claim_text_normalized | str | 规范化后的诉求文本 |
| claim_type | List[str] | 请求类型标签列表（L3 claim_type 枚举值） |
| object_type | str | 标的类型 |
| amount | float | 标的金额 |
| claimant | str | 请求方 |
| respondent | str | 被请求方 |
| is_clear | bool | 是否明确 |
| is_executable | bool | 是否可执行 |
| issues | List[str] | 问题列表 |
| clarification_questions | List[str] | 释明问题列表 |
| priority_type | str | 优先级类型 |
| competition_note | str | 请求权竞合/聚合/备位说明 |

---

#### 4.2.3 Step2Output（请求权基础候选）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| request_basis_candidates | List[RequestBasisCandidate] | 请求权基础候选列表 |
| competition_analysis | str | 请求权竞合分析说明 |

**RequestBasisCandidate 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_id | str | 关联的诉求 ID |
| rule_unit_ref | RuleUnitRef | 规则单元引用 |
| norm_type | List[str] | 规范功能标签 |
| claim_type | List[str] | 请求类型标签 |
| legal_effect_tags | List[str] | 法律效果标签 |
| selection_reason | str | 选择理由 |
| priority | str | 优先级：primary/alternative/supplementary |
| risk_note | str | 风险提示 |

---

#### 4.2.4 Step3Output（抗辩权基础候选）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| defense_basis_candidates | List[DefenseBasisCandidate] | 抗辩权基础候选列表 |

**DefenseBasisCandidate 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| defense_id | str | 关联的答辩 ID |
| target_claim_id | str | 针对的诉求 ID |
| response_type | str | 回应类型 |
| defense_type | List[str] | 抗辩类型标签 |
| rule_unit_ref | RuleUnitRef | 规则单元引用 |
| legal_effect_tags | List[str] | 法律效果标签 |
| selection_reason | str | 选择理由 |
| clarification_needed | bool | 是否需要释明 |
| risk_note | str | 风险提示 |

---

#### 4.2.5 Step4Output（构成要件矩阵）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| element_matrix | List[ElementMatrixRow] | 构成要件矩阵行列表 |

**ElementMatrixRow 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| element_id | str | 要件唯一标识 |
| rule_unit_id | str | 来源规则单元 ID |
| element_name | str | 要件名称 |
| element_type | str | 要件类型 |
| element_logic | str | 逻辑关系：AND/OR/NOT |
| is_hidden_element | bool | 是否为隐藏要件 |
| negative_element | bool | 是否为消极要件 |
| exception_element | bool | 是否为例外要件 |
| fact_slot | str | 事实槽位 |
| burden_party | str | 举证责任方 |
| proof_standard | str | 证明标准 |
| suggested_evidence_types | List[str] | 建议证据类型列表 |
| used_for | str | 用途：request_basis/defense_basis |
| target_id | str | 关联的 claim_id 或 defense_id |
| note | str | 备注 |

---

#### 4.2.6 Step5Output（待证事实映射）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_fact_mapping | List[ClaimFactMappingRow] | 待证事实映射行列表 |

**ClaimFactMappingRow 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| element_id | str | 关联的要件 ID |
| fact_slot | str | 事实槽位 |
| required_fact | str | 需要证明的事实 |
| asserted_fact_ids | List[str] | 已主张的事实 ID 列表 |
| assertion_status | str | 主张状态：asserted/missing/vague/conflicting |
| burden_party | str | 举证责任方 |
| clarification_question | str | 释明问题 |
| risk_note | str | 风险提示 |

---

#### 4.2.7 Step6Output（争点整理）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| issues | List[Issue] | 争点列表 |
| review_order | List[str] | 审理顺序（issue_id 列表） |

**Issue 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| issue_id | str | 争点唯一标识 |
| issue_type | str | 争点类型：fact_issue/legal_issue |
| issue_text | str | 争点文本 |
| linked_element_ids | List[str] | 关联的要件 ID 列表 |
| linked_claim_id | str | 关联的诉求 ID |
| linked_defense_id | str | 关联的答辩 ID |
| burden_party | str | 举证责任方 |
| linked_evidence_ids | List[str] | 关联的证据 ID 列表 |
| priority | str | 优先级：high/medium/low |

---

#### 4.2.8 Step7Output（举证计划）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| proof_plan | List[ProofPlanRow] | 举证计划行列表 |

**ProofPlanRow 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| issue_id | str | 关联的争点 ID |
| element_id | str | 关联的要件 ID |
| fact_to_prove | str | 待证事实 |
| burden_party | str | 举证责任方 |
| proof_standard | str | 证明标准 |
| existing_evidence_ids | List[str] | 现有证据 ID 列表 |
| suggested_evidence_types | List[str] | 建议证据类型列表 |
| proof_gap | str | 证明缺口 |
| effect_if_unknown | str | 真伪不明时的法律后果 |

---

#### 4.2.9 Step8Output（事实认定）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| fact_findings | List[FactFinding] | 事实认定结果列表 |

**FactFinding 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| fact_finding_id | str | 事实认定唯一标识 |
| element_id | str | 关联的要件 ID |
| fact_slot | str | 事实槽位 |
| finding_status | str | 认定状态：proved/not_proved/unknown |
| adopted_evidence_ids | List[str] | 采信的证据 ID 列表 |
| rejected_evidence_ids | List[str] | 不采信的证据 ID 列表 |
| reasoning | str | 认定理由 |
| burden_party | str | 举证责任方 |
| effect_if_unknown | str | 真伪不明时的法律后果 |

---

#### 4.2.10 Step9Output（要件归入结果）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| subsumption_results | List[SubsumptionResult] | 涵摄结果列表 |

**SubsumptionResult 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_id | str | 关联的诉求 ID |
| request_basis_rule_unit_id | str | 请求权基础规则单元 ID |
| request_elements_result | List[ElementResult] | 请求权要件认定结果 |
| defense_results | List[DefenseReviewResult] | 抗辩审查结果 |
| legal_effect_tags | List[str] | 适用的法律效果标签 |
| disposition_type | str | 裁判类型 |
| judgment_result | str | 裁判结论：supported/partially_supported/rejected/procedural_dismissal |
| reasoning_summary | str | 推理摘要 |
| cited_rules | List[str] | 引用法条（rule_unit_id 列表） |

**ElementResult 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| element_id | str | 要件 ID |
| element_name | str | 要件名称 |
| finding_status | str | 认定状态：proved/not_proved/unknown |
| note | str | 备注 |

**DefenseReviewResult 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| defense_id | str | 答辩 ID |
| defense_type | List[str] | 抗辩类型标签 |
| elements_status | List[ElementResult] | 抗辩要件认定结果 |
| accepted | bool | 抗辩是否成立 |
| effect | str | 抗辩效果：阻却/消灭/限制/延缓/减责 |

---

#### 4.2.11 SufficiencyScore（充足度评分）

| 字段名 | 类型 | 取值范围 | 说明 |
|--------|------|----------|------|
| claim_clarity | int | 0-20 | 诉求清晰度 |
| legal_relation_stability | int | 0-15 | 法律关系稳定性 |
| request_basis_stability | int | 0-15 | 请求权基础稳定性 |
| defense_path_completeness | int | 0-15 | 抗辩路径完整性 |
| element_fact_coverage | int | 0-15 | 要件事实覆盖率 |
| evidence_coverage | int | 0-15 | 证据覆盖率 |
| fact_finding_reliability | int | 0-10 | 事实认定可靠性 |

**计算属性**：
- `total`：七维度总分（0-100）
- `level()`：评分等级 → strong/medium/weak_optional/block

---

#### 4.2.12 FallbackGate（保底选择门）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| risk_triggered | bool | 是否触发风险 |
| risk_level | str | 风险等级：low/medium/high/critical |
| reason | List[str] | 风险原因列表 |
| recommended_action | str | 推荐操作 |
| available_choices | List[Dict] | 可用选择列表（含 choice/label/description） |
| default_choice | str | 默认选择 |
| hard_block | bool | 是否硬性拦截 |

---

### 4.3 输出数据模型

#### 4.3.1 WorkflowResult（工作流最终输出）

**定义文件**：`schemas/outputs.py`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| case_id | str | 案件 ID |
| status | str | 状态：ok/blocked/awaiting_user_choice |
| fallback_gate | FallbackGate | 保底选择门 |
| step1 | Step1Output | 第一步输出 |
| step2 | Step2Output | 第二步输出 |
| step3 | Step3Output | 第三步输出 |
| step4 | Step4Output | 第四步输出 |
| step5 | Step5Output | 第五步输出 |
| step6 | Step6Output | 第六步输出 |
| step7 | Step7Output | 第七步输出 |
| step8 | Step8Output | 第八步输出 |
| step9 | Step9Output | 第九步输出 |
| strong_judgment | StrongJudgmentOutput | 强裁判输出 |
| weak_judgment | WeakJudgmentOutput | 弱裁判输出 |
| partial_output | PartialOutput | 部分输出 |
| timings_ms | Dict[str, int] | 各步骤耗时 |
| errors | List[str] | 错误列表 |
| warnings | List[str] | 警告列表 |

---

#### 4.3.2 StrongJudgmentOutput（强裁判输出）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| mode | str | 固定值 "strong_judgment" |
| sufficiency_score | SufficiencyScore | 充足度评分 |
| risk_level | str | 风险等级：low/medium |
| subsumption_results | List[SubsumptionResult] | 涵摄结果列表 |
| document_skeleton | Dict[str, Any] | 裁判文书框架 |
| consistency_check | Dict[str, Any] | "八个一致"校验结果 |

**document_skeleton 结构**：

```json
{
  "原告诉讼请求": [ /* FixedClaim[] */ ],
  "被告辩称": [ /* DefenseObject[] */ ],
  "争议焦点": [ /* Issue[] */ ],
  "本院查明": [ /* FactFinding[] */ ],
  "本院认为": [ /* SubsumptionResult[] */ ],
  "判决主文": [ /* 判决主文文本列表 */ ],
  "引用法条": [ /* rule_unit_id 列表 */ ]
}
```

**consistency_check 结构**：

```json
{
  "诉求-固定一致": true,
  "固定-涵摄一致": true,
  "缺漏的诉求（涵摄阶段未覆盖）": [],
  "多出的诉求（涵摄阶段凭空出现）": [],
  "争点已使用": true,
  "事实已认定": true,
  "法条已引用": true
}
```

---

#### 4.3.3 WeakJudgmentOutput（弱裁判输出）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| mode | str | 固定值 "weak_judgment" |
| sufficiency_score | SufficiencyScore | 充足度评分 |
| risk_level | str | 固定值 "high" |
| user_choice | str | 固定值 "continue_weak_judgment" |
| missing_inputs | List[str] | 缺失输入列表 |
| assumptions_used | List[str] | 使用的假设列表 |
| unsupported_elements | List[str] | 未支持的要件列表 |
| evidence_gaps | List[str] | 证据缺口列表 |
| law_application_risks | List[str] | 法律适用风险列表 |
| fact_finding_risks | List[str] | 事实认定风险列表 |
| proof_risks | List[str] | 举证风险列表 |
| fallback_path | List[FallbackPathItem] | 回退路径 |
| weak_subsumption_results | List[WeakSubsumptionResult] | 弱涵摄结果列表 |
| upgrade_to_strong_judgment_requirements | List[str] | 升级到强裁判所需条件 |

**WeakSubsumptionResult 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_id | str | 诉求 ID |
| candidate_rule_unit_id | str | 候选规则单元 ID |
| conditioned_element_result | List[Dict] | 有条件要件认定结果 |
| defense_review_status | str | 抗辩审查状态：not_available/limited/reviewed |
| tentative_judgment_result | str | 暂定裁判结论：likely_supported/likely_partially_supported/likely_rejected/uncertain |
| confidence | str | 置信度：low/medium |
| reasoning_summary | str | 推理摘要 |
| risk_note | str | 风险提示 |

**FallbackPathItem 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| return_to_step | str | 回退到的步骤 |
| reason | str | 回退原因 |

---

#### 4.3.4 PartialOutput（部分输出）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| mode | str | 固定值 "partial_output_only" |
| sufficiency_score | SufficiencyScore | 充足度评分 |
| fixed_claims | List[Dict] | 固定后的诉求 |
| request_basis_candidates | List[Dict] | 请求权基础候选 |
| defense_basis_candidates | List[Dict] | 抗辩权基础候选 |
| element_matrix | List[Dict] | 构成要件矩阵 |
| issues | List[Dict] | 争点列表 |
| evidence_gaps | List[str] | 证据缺口列表 |
| missing_inputs | List[str] | 缺失输入列表 |
| note | str | 固定值 "在材料不足以裁判时仅输出要件、争点与证据缺口，不输出裁判倾向。" |

---

### 4.4 知识库数据模型

#### 4.4.1 RuleUnit（规则单元）

**定义文件**：`schemas/kb.py`

**说明**：法条库的最小检索单位，一个法条可能拆出多个 rule_unit。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| rule_unit_id | str | 规则单元唯一标识 |
| rule_unit_text | str | 规则单元文本 |
| law_name | str | 所属法律名称（冗余字段） |
| article_no | str | 所属条文编号（冗余字段） |
| L1_source_case | L1SourceCase | L1 法源定位与案由关系层 |
| L2_workflow_norm | L2WorkflowNorm | L2 九步法位置与规范功能层 |
| L3_claim_defense | L3ClaimDefense | L3 请求/抗辩对象层 |
| L4_elements_proof | L4ElementsProof | L4 构成要件与证明层 |
| L5_effect_judgment | L5EffectJudgment | L5 法律效果与裁判输出层 |

---

#### 4.4.2 L1SourceCase（法源定位与案由关系层）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| source_type | str | 法源类型：法律/司法解释/行政法规/部门规章/地方性法规等 |
| effective_status | str | 效力状态：现行有效/已废止/尚未生效 |
| effective_date | str | 生效日期 |
| legal_domain | List[str] | 法律领域：合同/侵权/物权/婚姻家事/继承/公司/劳动/程序/人格权/总则/其他 |
| case_cause_l1 | List[str] | 案由一级分类 |
| case_cause_l2 | List[str] | 案由二级分类 |
| case_cause_l3 | List[str] | 案由三级分类 |
| case_cause_l4 | List[str] | 案由四级分类 |
| special_priority | str | 特别优先标记：特别规则/一般规则 |

---

#### 4.4.3 L2WorkflowNorm（九步法位置与规范功能层）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| workflow_steps | List[str] | 适用的九步法步骤：step2_request_basis/step3_defense_basis/step4_elements 等 |
| norm_type | List[str] | 规范功能：request_basis/defense_basis/definition/program_rule/evidence_rule/liability_rule 等 |

---

#### 4.4.4 L3ClaimDefense（请求/抗辩对象层）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| claim_type | List[str] | 请求类型（见枚举值字典） |
| defense_type | List[str] | 抗辩类型（见枚举值字典） |
| right_type | str | 权利类型 |
| liability_type | str | 责任类型 |
| party_role | List[str] | 适用的当事人角色 |
| object_type | str | 标的类型 |

---

#### 4.4.5 L4ElementsProof（构成要件与证明层）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| elements | List[Element] | 构成要件列表 |

**Element 子对象**：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| element_id | str | 要件唯一标识 |
| element_name | str | 要件名称 |
| element_description | str | 要件描述 |
| element_type | str | 要件类型 |
| element_logic | str | 逻辑关系：AND/OR/NOT |
| is_hidden_element | bool | 是否为隐藏要件 |
| negative_element | bool | 是否为消极要件 |
| exception_element | bool | 是否为例外要件 |
| fact_slot | str | 事实槽位 |
| burden_party | str | 举证责任方 |
| proof_standard | str | 证明标准 |
| suggested_evidence_types | List[str] | 建议证据类型 |
| fact_finding_note | str | 事实认定备注 |

---

#### 4.4.6 L5EffectJudgment（法律效果与裁判输出层）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| legal_effect_tags | List[str] | 法律效果标签（见枚举值字典） |
| legal_effect_text | str | 法律效果文本描述 |
| disposition_type | List[str] | 裁判类型 |
| effect_if_satisfied | str | 要件满足时的效果 |
| effect_if_not_satisfied | str | 要件不满足时的效果 |
| effect_if_unknown | str | 真伪不明时的效果 |
| calculation_formula | str | 计算公式 |
| adjustment_rule | str | 调整规则 |

---

#### 4.4.7 RuleUnitRef（规则单元引用）

**说明**：在中间产物中替代完整 RuleUnit 对象，节省 token 消耗。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| rule_unit_id | str | 规则单元 ID |
| law_name | str | 法律名称 |
| article_no | str | 条文编号 |
| rule_unit_text | str | 规则单元文本 |
| norm_type | List[str] | 规范功能标签 |
| claim_type | List[str] | 请求类型标签 |
| defense_type | List[str] | 抗辩类型标签 |
| legal_effect_tags | List[str] | 法律效果标签 |

---

### 4.5 枚举值字典

#### 4.5.1 L3 claim_type（请求类型）

| 枚举值 | 中文说明 |
|--------|----------|
| confirmation_claim | 确认请求 |
| payment_claim | 给付请求（金钱） |
| delivery_claim | 交付请求（物） |
| performance_claim | 履行请求（行为） |
| termination_claim | 解除请求 |
| revocation_claim | 撤销请求 |
| damages_claim | 损害赔偿请求 |
| restitution_claim | 返还请求 |
| repair_replace_remake_claim | 修理/更换/重作请求 |
| injunction_claim | 禁令请求 |
| apology_reputation_claim | 赔礼道歉/恢复名誉请求 |

---

#### 4.5.2 L3 defense_type（抗辩类型）

| 枚举值 | 中文说明 |
|--------|----------|
| denial | 否认 |
| limitation_defense | 时效抗辩 |
| performance_completed_defense | 履行完毕抗辩 |
| setoff_defense | 抵销抗辩 |
| simultaneous_performance_defense | 同时履行抗辩 |
| first_performance_defense | 先履行抗辩 |
| insecurity_defense | 不安抗辩 |
| invalidity_defense | 无效抗辩 |
| termination_defense | 解除抗辩 |
| force_majeure_defense | 不可抗力抗辩 |
| fault_reduction_defense | 过错减轻抗辩 |
| no_causation_defense | 无因果关系抗辩 |
| subject_ineligible_defense | 主体不适格抗辩 |
| jurisdiction_defense | 管辖权抗辩 |

---

#### 4.5.3 L2 norm_type（规范功能）

| 枚举值 | 中文说明 |
|--------|----------|
| request_basis | 请求权基础 |
| defense_basis | 抗辩权基础 |
| formation_right_basis | 形成权基础 |
| definition | 定义规则 |
| program_rule | 程序规则 |
| evidence_rule | 证据规则 |
| liability_rule | 责任规则 |
| exemption_rule | 免责规则 |
| exception_rule | 例外规则 |

---

#### 4.5.4 L5 legal_effect_tags（法律效果标签）

| 枚举值 | 中文说明 |
|--------|----------|
| liability_arises | 责任产生 |
| liability_exempted | 责任免除 |
| liability_reduced | 责任减轻 |
| performance_suspended | 履行中止 |
| claim_rejected | 请求驳回 |
| contract_invalid | 合同无效 |
| contract_terminated | 合同解除 |
| procedure_dismissal | 程序驳回 |
| right_confirmed | 权利确认 |
| right_extinguished | 权利消灭 |

---

#### 4.5.5 legal_domain（法律领域）

| 枚举值 | 说明 |
|--------|------|
| 合同 | 合同法领域 |
| 侵权 | 侵权法领域 |
| 物权 | 物权法领域 |
| 婚姻家事 | 婚姻家事法领域 |
| 继承 | 继承法领域 |
| 公司 | 公司法领域 |
| 劳动 | 劳动法领域 |
| 程序 | 程序法领域 |
| 人格权 | 人格权法领域 |
| 总则 | 民法总则领域 |
| 其他 | 其他法律领域 |

---

#### 4.5.6 response_type（回应类型）

| 枚举值 | 说明 |
|--------|------|
| 承认 | 对对方主张予以承认 |
| 否认 | 对对方主张予以否认 |
| 抗辩 | 提出抗辩事由 |
| 抗辩权 | 行使法定抗辩权 |
| 程序性异议 | 提出程序性异议 |

---

#### 4.5.7 finding_status / assertion_status（认定/主张状态）

| 枚举值 | 说明 |
|--------|------|
| proved / asserted | 已证明 / 已主张 |
| not_proved / missing | 未证明 / 缺失 |
| unknown / vague | 真伪不明 / 模糊 |
| conflicting | 矛盾 |

---

#### 4.5.8 judgment_result（裁判结论）

| 枚举值 | 说明 |
|--------|------|
| supported | 支持 |
| partially_supported | 部分支持 |
| rejected | 驳回 |
| procedural_dismissal | 程序性驳回（驳回起诉） |

---

#### 4.5.9 tentative_judgment_result（暂定裁判结论）

| 枚举值 | 说明 |
|--------|------|
| likely_supported | 可能支持 |
| likely_partially_supported | 可能部分支持 |
| likely_rejected | 可能驳回 |
| uncertain | 不确定 |

---

#### 4.5.10 priority_type（优先级类型）

| 枚举值 | 说明 |
|--------|------|
| primary | 主要请求 |
| alternative | 备位请求 |
| parallel | 并行请求 |
| selective | 选择请求 |

---

#### 4.5.11 priority（候选优先级）

| 枚举值 | 说明 |
|--------|------|
| primary | 主要候选 |
| alternative | 备选候选 |
| supplementary | 补充候选 |

---

#### 4.5.12 issue_priority（争点优先级）

| 枚举值 | 说明 |
|--------|------|
| high | 高优先级（核心争点） |
| medium | 中优先级 |
| low | 低优先级 |

---

#### 4.5.13 probative_force（证明力等级）

| 枚举值 | 说明 |
|--------|------|
| 强 | 证明力强 |
| 中 | 证明力中等 |
| 弱 | 证明力弱 |
| 不采信 | 不予采信 |

---

#### 4.5.14 adopted_status（采信状态）

| 枚举值 | 说明 |
|--------|------|
| 采信 | 予以采信 |
| 不采信 | 不予采信 |
| 部分采信 | 部分采信 |
| 待补充 | 待补充证明 |

---

## 五、部署与运维

### 5.1 环境要求

| 组件 | 最低版本 | 推荐版本 | 说明 |
|------|----------|----------|------|
| Python | 3.10 | 3.12 | 运行时环境 |
| pip | 23.0 | 最新 | 包管理器 |
| 内存 | 2 GB | 4 GB | 知识库加载到内存 |
| 磁盘 | 500 MB | 1 GB | 含虚拟环境和法条库 |
| 网络 | 可访问 DashScope API | — | LLM 调用依赖 |

### 5.2 部署方案

#### 5.2.1 本地开发部署

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 放置法条库
# 将 articles_annotated.jsonl 放到 ./data/ 目录

# 4. 启动服务
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1 --reload
```

#### 5.2.2 生产部署

```bash
# 使用 gunicorn + uvicorn worker
pip install gunicorn

gunicorn api:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300 \
  --access-logfile - \
  --error-logfile -
```

#### 5.2.3 Docker 部署

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 放置法条库
COPY data/articles_annotated.jsonl ./data/

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### 5.3 配置管理

#### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DASHSCOPE_API_KEY` | DashScope API 密钥 | settings.py 中的明文 Key |
| `JIUBUFA_KB_PATH` | 法条库文件路径 | 自动探测 |
| `JIUBUFA_LOG_LEVEL` | 日志级别 | INFO |

#### 配置文件

| 文件 | 说明 |
|------|------|
| `config/settings.py` | 全局配置（API Key、模型、阈值、路径） |

### 5.4 日志与监控

#### 日志格式

```
%(asctime)s [%(levelname)s] %(name)s: %(message)s
```

**示例**：
```
2026-05-08 10:30:15,234 [INFO] jiubufa.orchestrator: 开始执行工作流，case_id=case-2024-mc-0001
2026-05-08 10:30:18,456 [INFO] jiubufa.llm: LLM[dashscope-qwen-plus/qwen3.5-plus] step=step1_claim_fixing ok in 3.22s len=1234
2026-05-08 10:31:00,789 [INFO] jiubufa.orchestrator: 工作流完成，status=ok，errors=0，warnings=1
```

#### 日志级别

| 级别 | 使用场景 |
|------|----------|
| DEBUG | 开发调试，输出 LLM 请求/响应详情 |
| INFO | 生产环境，输出关键步骤完成信息 |
| WARNING | 告警，如 LLM 重试、评分回退 |
| ERROR | 错误，如步骤执行失败、知识库加载失败 |

#### 关键监控指标

| 指标 | 来源 | 说明 |
|------|------|------|
| 工作流总耗时 | `result.timings_ms["total"]` | 通常 30-60 秒 |
| 每步耗时 | `result.timings_ms["stepX"]` | 单步通常 3-8 秒 |
| LLM 调用失败率 | 日志 WARNING 计数 | 应 < 5% |
| 评分分布 | `result.fallback_gate.risk_level` | 监控输入质量 |
| 错误数 | `len(result.errors)` | 应 = 0 |
| 知识库大小 | `/api/health` → kb_size | 监控数据完整性 |

---

## 附录

### A. 九步法步骤速查表

| 步骤 | 文件名 | 核心任务 | LLM 调用 | KB 检索 | 输出 |
|------|--------|----------|----------|---------|------|
| Step 1 | step1_fix_claims.py | 固定权利请求 | 1 次 | 无 | fixed_claims |
| Step 2 | step2_request_basis.py | 确定请求权基础 | 1 次 | search_request_basis (top-12) | request_basis_candidates |
| Step 3 | step3_defense_basis.py | 确定抗辩权基础 | 1 次 | search_defense_basis (top-10) | defense_basis_candidates |
| Step 4 | step4_elements.py | 构成要件分析 | 1 次 | 读取 L4 要件 | element_matrix |
| Step 5 | step5_claim_facts.py | 诉讼主张检索 | 1 次 | 无 | claim_fact_mapping |
| Step 6 | step6_issues.py | 争点整理 | 1 次 | 无 | issues, review_order |
| Step 7 | step7_proof.py | 举证质证 | 1 次 | 无 | proof_plan |
| Step 8 | step8_facts.py | 事实认定 | 1 次 | 无 | fact_findings |
| Step 9 | step9_subsumption.py | 要件归入裁判 | 1 次 | 读取 L5 效果 | subsumption_results |

### B. 评分阈值速查表

| 评分区间 | 等级 | 默认行为 | 可用选择 |
|----------|------|----------|----------|
| ≥ 80 | strong | 强裁判 | supplement / partial_only / continue_weak |
| 60-79 | medium | 强裁判（带风险提示） | supplement / partial_only / continue_weak |
| 40-59 | weak_optional | 等待用户选择 | supplement / partial_only / continue_weak |
| < 40 | block | 阻断 | partial_only |

### C. 文件清单

```
jiubufa/
├── api.py                          # FastAPI 服务入口
├── orchestrator.py                 # 工作流编排器
├── run_workflow.py                 # CLI 入口
├── requirements.txt                # Python 依赖
├── config/
│   ├── __init__.py
│   └── settings.py                 # 全局配置
├── schemas/
│   ├── __init__.py
│   ├── inputs.py                   # 输入数据模型
│   ├── intermediates.py            # 中间数据模型
│   ├── kb.py                       # 知识库数据模型
│   └── outputs.py                  # 输出数据模型
├── llm/
│   ├── __init__.py
│   └── client.py                   # LLM 客户端
├── kb/
│   ├── __init__.py
│   ├── loader.py                   # 知识库加载器
│   └── retriever.py                # 知识库检索器
├── prompts/
│   ├── __init__.py
│   └── templates.py                # Prompt 模板
├── steps/
│   ├── __init__.py
│   ├── state.py                    # 工作流状态
│   ├── utils.py                    # 工具函数
│   ├── step1_fix_claims.py         # 第一步
│   ├── step2_request_basis.py      # 第二步
│   ├── step3_defense_basis.py      # 第三步
│   ├── step4_elements.py           # 第四步
│   ├── step5_claim_facts.py        # 第五步
│   ├── step6_issues.py             # 第六步
│   ├── step7_proof.py              # 第七步
│   ├── step8_facts.py              # 第八步
│   └── step9_subsumption.py        # 第九步
├── fallback/
│   ├── __init__.py
│   └── weak_judgment.py            # 保底裁判机制
├── data/
│   └── articles_annotated.jsonl    # 法条库数据
└── examples/
    └── sample_case.json            # 示例案件
```

---

> **文档结束**
> 本文档涵盖了九步法 AI 审案工作流后端系统的完整设计，包括概要设计、详细设计、接口规范和数据字典。
> 如需了解更多运行细节，请参考 [项目运行逻辑说明文档.md](./项目运行逻辑说明文档.md)。