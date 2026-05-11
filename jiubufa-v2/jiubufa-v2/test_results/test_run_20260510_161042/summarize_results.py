"""
汇总测试结果的脚本
提取每个test的direct_llm_evaluation.json和workflow_evaluation.json中的分数和优缺点分析
生成Excel表格，包含详细的评分、优缺点和风险标识
"""

import json
import os
import csv
from pathlib import Path
from datetime import datetime


def load_json(file_path):
    """加载JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取文件 {file_path} 失败: {e}")
        return None


def extract_evaluation_data(data, method_name, run_time=None):
    """提取评估数据，处理缺失值"""
    if not data:
        return None
    
    # 检查status字段，如果失败则标记
    status = data.get('status', 'unknown')
    if status != 'success':
        return {
            'test_id': data.get('test_id'),
            'method': method_name,
            'status': status,
            'run_time': run_time,
            'overall_score': None,
            'scores': {},
            'strengths': [],
            'weaknesses': [],
            'risk_flags': [],
            'overall_comment': f'测试失败，状态: {status}',
            'recommended_use': '',
            'has_error': True
        }
    
    if 'evaluation' not in data:
        return {
            'test_id': data.get('test_id'),
            'method': method_name,
            'status': 'missing_evaluation',
            'run_time': run_time,
            'overall_score': None,
            'scores': {},
            'strengths': [],
            'weaknesses': [],
            'risk_flags': [],
            'overall_comment': '缺少evaluation字段',
            'recommended_use': '',
            'has_error': True
        }
    
    evaluation = data['evaluation']
    
    result = {
        'test_id': data.get('test_id'),
        'method': method_name,
        'status': status,
        'run_time': run_time,
        'overall_score': evaluation.get('overall_score'),
        'scores': {},
        'score_reasons': {},
        'strengths': evaluation.get('strengths', []),
        'weaknesses': evaluation.get('weaknesses', []),
        'risk_flags': evaluation.get('risk_flags', []),
        'overall_comment': evaluation.get('overall_comment', ''),
        'recommended_use': evaluation.get('recommended_use', ''),
        'auxiliary_value': evaluation.get('auxiliary_value_judgment', {}),
        'judge_workbench': evaluation.get('judge_workbench_value', {}),
        'has_error': False
    }
    
    # 提取各项分数和原因
    if 'scores' in evaluation:
        for key, value in evaluation['scores'].items():
            result['scores'][key] = value.get('score')
            result['score_reasons'][key] = value.get('reason', '')
    
    return result


def generate_summary(test_results_dir):
    """生成汇总报告"""
    base_path = Path(test_results_dir)
    
    # 存储所有测试结果
    all_results = {
        'direct_llm': [],
        'workflow': []
    }
    
    # 遍历所有test文件夹
    test_dirs = sorted([d for d in base_path.iterdir() if d.is_dir() and d.name.startswith('test_')])
    
    for test_dir in test_dirs:
        test_name = test_dir.name
        
        # 读取direct_llm_result.json获取运行时间
        direct_llm_result_file = test_dir / 'direct_llm_result.json'
        direct_llm_run_time = None
        if direct_llm_result_file.exists():
            result_data = load_json(direct_llm_result_file)
            if result_data:
                direct_llm_run_time = result_data.get('elapsed_seconds')
        
        # 读取direct_llm_evaluation.json
        direct_llm_file = test_dir / 'direct_llm_evaluation.json'
        if direct_llm_file.exists():
            data = load_json(direct_llm_file)
            if data:
                extracted = extract_evaluation_data(data, 'direct_llm', direct_llm_run_time)
                if extracted:
                    all_results['direct_llm'].append(extracted)
        
        # 读取workflow_result.json获取运行时间
        workflow_result_file = test_dir / 'workflow_result.json'
        workflow_run_time = None
        if workflow_result_file.exists():
            result_data = load_json(workflow_result_file)
            if result_data:
                workflow_run_time = result_data.get('elapsed_seconds')
        
        # 读取workflow_evaluation.json
        workflow_file = test_dir / 'workflow_evaluation.json'
        if workflow_file.exists():
            data = load_json(workflow_file)
            if data:
                extracted = extract_evaluation_data(data, 'workflow', workflow_run_time)
                if extracted:
                    all_results['workflow'].append(extracted)
    
    return all_results, len(test_dirs)


def export_to_excel(all_results, total_tests, output_file):
    """导出为Excel表格"""
    try:
        import pandas as pd
        use_pandas = True
    except ImportError:
        use_pandas = False
        print("注意: pandas未安装，将使用CSV格式导出")
    
    metric_names = [
        '系统定位契合度',
        '审理路径组织能力',
        '请求权基础与抗辩路径识别',
        '争议焦点归纳能力',
        '事实证据要件对应性',
        '法律适用与涵摄辅助能力',
        '程序实体风险识别能力',
        '可审查性与裁判心证支持'
    ]
    
    # 1. 创建分数对比表
    score_rows = []
    for i in range(max(len(all_results['direct_llm']), len(all_results['workflow']))):
        direct = all_results['direct_llm'][i] if i < len(all_results['direct_llm']) else None
        workflow = all_results['workflow'][i] if i < len(all_results['workflow']) else None
        
        test_id = (direct['test_id'] if direct else workflow['test_id']) if (direct or workflow) else i+1
        
        row = {'测试ID': f"Test {test_id}"}
        
        # Direct LLM分数和运行时间
        if direct and not direct.get('has_error'):
            row['Direct_LLM_总分'] = direct['overall_score']
            row['Direct_LLM_运行时间(s)'] = direct['run_time'] if direct['run_time'] is not None else 'N/A'
            for metric in metric_names:
                row[f'Direct_LLM_{metric}'] = direct['scores'].get(metric, 'N/A')
        elif direct and direct.get('has_error'):
            row['Direct_LLM_总分'] = f"失败({direct['status']})"
            row['Direct_LLM_运行时间(s)'] = direct['run_time'] if direct['run_time'] is not None else 'N/A'
            for metric in metric_names:
                row[f'Direct_LLM_{metric}'] = 'N/A'
        else:
            row['Direct_LLM_总分'] = '缺失'
            row['Direct_LLM_运行时间(s)'] = 'N/A'
            for metric in metric_names:
                row[f'Direct_LLM_{metric}'] = 'N/A'
        
        # Workflow分数和运行时间
        if workflow and not workflow.get('has_error'):
            row['Workflow_总分'] = workflow['overall_score']
            row['Workflow_运行时间(s)'] = workflow['run_time'] if workflow['run_time'] is not None else 'N/A'
            for metric in metric_names:
                row[f'Workflow_{metric}'] = workflow['scores'].get(metric, 'N/A')
        elif workflow and workflow.get('has_error'):
            row['Workflow_总分'] = f"失败({workflow['status']})"
            row['Workflow_运行时间(s)'] = workflow['run_time'] if workflow['run_time'] is not None else 'N/A'
            for metric in metric_names:
                row[f'Workflow_{metric}'] = 'N/A'
        else:
            row['Workflow_总分'] = '缺失'
            row['Workflow_运行时间(s)'] = 'N/A'
            for metric in metric_names:
                row[f'Workflow_{metric}'] = 'N/A'
        
        # 计算差异
        if (direct and not direct.get('has_error') and 
            workflow and not workflow.get('has_error') and
            isinstance(direct['overall_score'], (int, float)) and
            isinstance(workflow['overall_score'], (int, float))):
            row['总分差异'] = workflow['overall_score'] - direct['overall_score']
        else:
            row['总分差异'] = 'N/A'
        
        score_rows.append(row)
    
    # 2. 创建优缺点表（简化版）
    pros_cons_rows = []
    for i in range(max(len(all_results['direct_llm']), len(all_results['workflow']))):
        direct = all_results['direct_llm'][i] if i < len(all_results['direct_llm']) else None
        workflow = all_results['workflow'][i] if i < len(all_results['workflow']) else None
        
        test_id = (direct['test_id'] if direct else workflow['test_id']) if (direct or workflow) else i+1
        
        row = {'测试ID': f"Test {test_id}"}
        
        # Direct LLM优缺点（简化：只保留前2条）
        if direct and not direct.get('has_error'):
            row['Direct_LLM_优点'] = ' | '.join(direct['strengths'][:2])
            row['Direct_LLM_缺点'] = ' | '.join(direct['weaknesses'][:2])
            row['Direct_LLM_风险类型'] = ', '.join(list(set([r.get('risk_type', '') for r in direct['risk_flags']])))
        else:
            row['Direct_LLM_优点'] = 'N/A'
            row['Direct_LLM_缺点'] = 'N/A'
            row['Direct_LLM_风险类型'] = 'N/A'
        
        # Workflow优缺点（简化：只保留前2条）
        if workflow and not workflow.get('has_error'):
            row['Workflow_优点'] = ' | '.join(workflow['strengths'][:2])
            row['Workflow_缺点'] = ' | '.join(workflow['weaknesses'][:2])
            row['Workflow_风险类型'] = ', '.join(list(set([r.get('risk_type', '') for r in workflow['risk_flags']])))
        else:
            row['Workflow_优点'] = 'N/A'
            row['Workflow_缺点'] = 'N/A'
            row['Workflow_风险类型'] = 'N/A'
        
        pros_cons_rows.append(row)
    
    # 3. 创建辅助价值判断表（简化版）
    comments_rows = []
    for i in range(max(len(all_results['direct_llm']), len(all_results['workflow']))):
        direct = all_results['direct_llm'][i] if i < len(all_results['direct_llm']) else None
        workflow = all_results['workflow'][i] if i < len(all_results['workflow']) else None
        
        test_id = (direct['test_id'] if direct else workflow['test_id']) if (direct or workflow) else i+1
        
        row = {'测试ID': f"Test {test_id}"}
        
        # Direct LLM辅助价值判断
        if direct and not direct.get('has_error'):
            aux = direct.get('auxiliary_value', {})
            row['Direct_LLM_定位'] = '辅助工具' if aux.get('is_more_like_judicial_assistant', False) else ('判决代写' if aux.get('is_more_like_judgment_ghostwriter', False) else '未知')
            bench = direct.get('judge_workbench', {})
            helps_count = sum([
                bench.get('helps_identify_issues', False),
                bench.get('helps_verify_evidence', False),
                bench.get('helps_identify_risks', False),
                bench.get('helps_organize_hearing_path', False),
                bench.get('helps_form_stable_inner_conviction', False)
            ])
            row['Direct_LLM_辅助功能数'] = f"{helps_count}/5"
        else:
            row['Direct_LLM_定位'] = 'N/A'
            row['Direct_LLM_辅助功能数'] = 'N/A'
        
        # Workflow辅助价值判断
        if workflow and not workflow.get('has_error'):
            aux = workflow.get('auxiliary_value', {})
            row['Workflow_定位'] = '辅助工具' if aux.get('is_more_like_judicial_assistant', False) else ('判决代写' if aux.get('is_more_like_judgment_ghostwriter', False) else '未知')
            bench = workflow.get('judge_workbench', {})
            helps_count = sum([
                bench.get('helps_identify_issues', False),
                bench.get('helps_verify_evidence', False),
                bench.get('helps_identify_risks', False),
                bench.get('helps_organize_hearing_path', False),
                bench.get('helps_form_stable_inner_conviction', False)
            ])
            row['Workflow_辅助功能数'] = f"{helps_count}/5"
        else:
            row['Workflow_定位'] = 'N/A'
            row['Workflow_辅助功能数'] = 'N/A'
        
        comments_rows.append(row)
    
    # 4. 创建风险详情表
    risk_rows = []
    for i in range(max(len(all_results['direct_llm']), len(all_results['workflow']))):
        direct = all_results['direct_llm'][i] if i < len(all_results['direct_llm']) else None
        workflow = all_results['workflow'][i] if i < len(all_results['workflow']) else None
        
        test_id = (direct['test_id'] if direct else workflow['test_id']) if (direct or workflow) else i+1
        
        # Direct LLM风险
        if direct and not direct.get('has_error'):
            for risk in direct['risk_flags']:
                risk_rows.append({
                    '测试ID': f"Test {test_id}",
                    '方法': 'Direct LLM',
                    '风险类型': risk.get('risk_type', ''),
                    '风险等级': risk.get('risk_level', ''),
                    '风险描述': risk.get('description', ''),
                    '建议核查': risk.get('suggested_judge_check', '')
                })
        
        # Workflow风险
        if workflow and not workflow.get('has_error'):
            for risk in workflow['risk_flags']:
                risk_rows.append({
                    '测试ID': f"Test {test_id}",
                    '方法': 'Workflow',
                    '风险类型': risk.get('risk_type', ''),
                    '风险等级': risk.get('risk_level', ''),
                    '风险描述': risk.get('description', ''),
                    '建议核查': risk.get('suggested_judge_check', '')
                })
    
    # 导出文件
    if use_pandas:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            pd.DataFrame(score_rows).to_excel(writer, sheet_name='分数对比', index=False)
            pd.DataFrame(pros_cons_rows).to_excel(writer, sheet_name='优缺点分析', index=False)
            pd.DataFrame(comments_rows).to_excel(writer, sheet_name='辅助价值判断', index=False)
            pd.DataFrame(risk_rows).to_excel(writer, sheet_name='风险详情', index=False)
        print(f"\n✓ Excel表格已保存到: {output_file}")
        print(f"  包含以下工作表:")
        print(f"  - 分数对比: 总分、8项指标分数及差异")
        print(f"  - 优缺点分析: 核心优缺点(前2条)和风险类型")
        print(f"  - 辅助价值判断: 系统定位和辅助功能数量")
        print(f"  - 风险详情: 所有风险详细信息")
    else:
        # 使用CSV导出
        base_name = output_file.replace('.xlsx', '').replace('.csv', '')
        
        with open(f'{base_name}_分数对比.csv', 'w', encoding='utf-8-sig', newline='') as f:
            if score_rows:
                writer = csv.DictWriter(f, fieldnames=score_rows[0].keys())
                writer.writeheader()
                writer.writerows(score_rows)
        
        with open(f'{base_name}_优缺点分析.csv', 'w', encoding='utf-8-sig', newline='') as f:
            if pros_cons_rows:
                writer = csv.DictWriter(f, fieldnames=pros_cons_rows[0].keys())
                writer.writeheader()
                writer.writerows(pros_cons_rows)
        
        with open(f'{base_name}_辅助价值判断.csv', 'w', encoding='utf-8-sig', newline='') as f:
            if comments_rows:
                writer = csv.DictWriter(f, fieldnames=comments_rows[0].keys())
                writer.writeheader()
                writer.writerows(comments_rows)
        
        with open(f'{base_name}_风险详情.csv', 'w', encoding='utf-8-sig', newline='') as f:
            if risk_rows:
                writer = csv.DictWriter(f, fieldnames=risk_rows[0].keys())
                writer.writeheader()
                writer.writerows(risk_rows)
        
        print(f"\n✓ CSV表格已保存到:")
        print(f"  - {base_name}_分数对比.csv")
        print(f"  - {base_name}_优缺点分析.csv")
        print(f"  - {base_name}_辅助价值判断.csv")
        print(f"  - {base_name}_风险详情.csv")


def print_summary_table(all_results, total_tests):
    """打印汇总表格到控制台"""
    metric_names = [
        '系统定位契合度',
        '审理路径组织能力',
        '请求权基础与抗辩路径识别',
        '争议焦点归纳能力',
        '事实证据要件对应性',
        '法律适用与涵摄辅助能力',
        '程序实体风险识别能力',
        '可审查性与裁判心证支持'
    ]
    
    print("=" * 120)
    print("测试结果汇总表格")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试总数: {total_tests}")
    print("=" * 120)
    
    # 分数对比表
    print(f"\n{'测试ID':<10} {'Direct总分':<12} {'Workflow总分':<14} {'差异':<8} {'Direct运行(s)':<15} {'Workflow运行(s)':<17}")
    print("-" * 80)
    
    direct_scores = []
    workflow_scores = []
    direct_times = []
    workflow_times = []
    
    for i in range(max(len(all_results['direct_llm']), len(all_results['workflow']))):
        direct = all_results['direct_llm'][i] if i < len(all_results['direct_llm']) else None
        workflow = all_results['workflow'][i] if i < len(all_results['workflow']) else None
        
        test_id = (direct['test_id'] if direct else workflow['test_id']) if (direct or workflow) else i+1
        
        # Direct LLM
        if direct and not direct.get('has_error'):
            d_score = direct['overall_score']
            d_time = direct['run_time']
            if isinstance(d_score, (int, float)):
                direct_scores.append(d_score)
            if isinstance(d_time, (int, float)):
                direct_times.append(d_time)
            d_score_str = str(d_score)
            d_time_str = f"{d_time:.1f}" if isinstance(d_time, (int, float)) else 'N/A'
        elif direct and direct.get('has_error'):
            d_score_str = f"失败"
            d_time = direct['run_time']
            d_time_str = f"{d_time:.1f}" if isinstance(d_time, (int, float)) else 'N/A'
        else:
            d_score_str = '缺失'
            d_time_str = 'N/A'
        
        # Workflow
        if workflow and not workflow.get('has_error'):
            w_score = workflow['overall_score']
            w_time = workflow['run_time']
            if isinstance(w_score, (int, float)):
                workflow_scores.append(w_score)
            if isinstance(w_time, (int, float)):
                workflow_times.append(w_time)
            w_score_str = str(w_score)
            w_time_str = f"{w_time:.1f}" if isinstance(w_time, (int, float)) else 'N/A'
        elif workflow and workflow.get('has_error'):
            w_score_str = f"失败"
            w_time = workflow['run_time']
            w_time_str = f"{w_time:.1f}" if isinstance(w_time, (int, float)) else 'N/A'
        else:
            w_score_str = '缺失'
            w_time_str = 'N/A'
        
        # 差异
        if (direct and not direct.get('has_error') and 
            workflow and not workflow.get('has_error') and
            isinstance(direct['overall_score'], (int, float)) and
            isinstance(workflow['overall_score'], (int, float))):
            diff = workflow['overall_score'] - direct['overall_score']
            diff_str = f"+{diff}" if diff > 0 else str(diff)
        else:
            diff_str = 'N/A'
        
        print(f"Test {test_id:<5} {d_score_str:<12} {w_score_str:<14} {diff_str:<8} {d_time_str:<15} {w_time_str:<17}")
    
    print("-" * 80)
    if direct_scores and workflow_scores:
        d_avg = sum(direct_scores) / len(direct_scores)
        w_avg = sum(workflow_scores) / len(workflow_scores)
        diff_avg = w_avg - d_avg
        print(f"平均分:    {d_avg:<12.2f} {w_avg:<14.2f} {'+' if diff_avg > 0 else ''}{diff_avg:<7.2f}", end='')
    
    if direct_times and workflow_times:
        d_time_avg = sum(direct_times) / len(direct_times)
        w_time_avg = sum(workflow_times) / len(workflow_times)
        print(f"  {d_time_avg:<15.1f} {w_time_avg:<17.1f}")
    else:
        print()
    
    # 各项指标平均分
    print(f"\n{'评估指标':<35} {'Direct LLM':<15} {'Workflow':<15} {'差异':<10}")
    print("-" * 80)
    
    for metric in metric_names:
        direct_metric_scores = []
        workflow_metric_scores = []
        
        for result in all_results['direct_llm']:
            if not result.get('has_error') and metric in result['scores']:
                score = result['scores'][metric]
                if isinstance(score, (int, float)):
                    direct_metric_scores.append(score)
        
        for result in all_results['workflow']:
            if not result.get('has_error') and metric in result['scores']:
                score = result['scores'][metric]
                if isinstance(score, (int, float)):
                    workflow_metric_scores.append(score)
        
        direct_avg = sum(direct_metric_scores) / len(direct_metric_scores) if direct_metric_scores else 0
        workflow_avg = sum(workflow_metric_scores) / len(workflow_metric_scores) if workflow_metric_scores else 0
        diff = workflow_avg - direct_avg
        
        print(f"{metric:<35} {direct_avg:<15.2f} {workflow_avg:<15.2f} {'+' if diff > 0 else ''}{diff:<9.2f}")
    
    print("\n" + "=" * 120)


if __name__ == '__main__':
    import sys
    
    # 支持命令行参数指定目录，否则使用脚本所在目录
    if len(sys.argv) > 1:
        test_results_dir = sys.argv[1]
    else:
        # 使用脚本所在目录作为测试结果目录
        test_results_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"测试结果目录: {test_results_dir}")
    
    # 生成汇总
    all_results, total_tests = generate_summary(test_results_dir)
    
    # 打印汇总表格
    print_summary_table(all_results, total_tests)
    
    # 导出为Excel或CSV
    output_file = os.path.join(test_results_dir, 'summary_report.xlsx')
    export_to_excel(all_results, total_tests, output_file)
