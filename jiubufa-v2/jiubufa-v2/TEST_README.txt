========================================
20并发测试脚本使用说明
========================================

一、文件说明
----------------------------------------
1. test_marriage_case.json
   - 详细的婚姻纠纷案例（符合九步法工作流输入规范）
   - 包含完整的当事人信息、诉讼请求、事实主张、答辩意见、证据、质证意见等

2. concurrent_test.py
   - 主测试脚本
   - 执行20个并发测试
   - 每个测试包含：
     * 直接LLM裁判分析（提示词仅"请你裁判分析"）- 使用 qwen3.6-plus
     * 九步法工作流分析 - 使用 qwen3.6-plus
     * 7维度评估 - 使用 deepseek-v4-flash
   - 保存所有中间结果

3. analyze_results.py
   - 结果提取与分析脚本
   - 从测试结果中提取关键字段
   - 生成多维度对比分析报告

二、运行方式
----------------------------------------

步骤1：运行并发测试
  python concurrent_test.py

  说明：
  - 会自动创建 test_results/test_run_YYYYMMDD_HHMMSS/ 目录
  - 每个测试的结果保存在 test_XX/ 子目录下
  - 包含以下文件：
    * direct_llm_result.json - 直接LLM裁判结果
    * workflow_result.json - 九步法工作流结果
    * direct_llm_evaluation.json - 直接LLM的7维度评估
    * workflow_evaluation.json - 九步法的7维度评估
    * extracted_results.json - 提取的关键字段
  - 所有结果汇总在 all_results.json

步骤2：运行结果分析
  python analyze_results.py

  说明：
  - 自动找到最新的测试结果目录
  - 提取关键字段和评分
  - 生成对比分析报告（analysis_report.txt）
  - 生成分析摘要（analysis_summary.json）

  也可以指定特定的测试目录：
  python analyze_results.py test_results/test_run_20240520_123456

三、评估维度
----------------------------------------
7个评估维度（每个满分100分）：
1. 法律适用准确性
2. 事实认定完整性
3. 逻辑推理严密性
4. 裁判结果合理性
5. 程序规范性
6. 证据分析充分性
7. 文书规范性

四、模型配置
----------------------------------------
- 裁判分析模型：qwen3.6-plus (dashscope-qwen3.6-plus)
- 评估模型：deepseek-v4-flash (dashscope-deepseek)

五、输出结构
----------------------------------------
test_results/
  └── test_run_YYYYMMDD_HHMMSS/
      ├── test_case.json                    # 测试用例
      ├── all_results.json                  # 所有测试结果汇总
      ├── analysis_report.txt               # 分析报告
      ├── analysis_summary.json             # 分析摘要
      ├── test_01/
      │   ├── direct_llm_result.json        # 直接LLM裁判结果
      │   ├── workflow_result.json          # 九步法工作流结果
      │   ├── direct_llm_evaluation.json    # 直接LLM评估
      │   ├── workflow_evaluation.json      # 九步法评估
      │   └── extracted_results.json        # 提取的关键字段
      ├── test_02/
      │   └── ...
      ...
      └── test_20/
          └── ...

六、注意事项
----------------------------------------
1. 确保已安装所有依赖（requirements.txt）
2. 确保API Key配置正确（config/settings.py）
3. 20个并发测试会消耗较多API调用次数，请注意配额
4. 测试过程中会保存所有中间结果，确保磁盘空间充足
5. 九步法工作流需要加载知识库（data/articles_annotated.jsonl）

七、分析报告内容
----------------------------------------
分析报告包含以下内容：
1. 执行成功率对比
2. 执行耗时统计
3. 7维度评分对比（均值、差异）
4. 直接LLM评分详细统计（均值、最小、最大、标准差）
5. 九步法工作流评分详细统计
6. 九步法工作流特性分析（强裁判/弱裁判/部分输出比例）
7. 综合评估（优势维度对比）
