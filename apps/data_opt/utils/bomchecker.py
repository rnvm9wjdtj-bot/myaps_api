import pandas as pd
import json
from collections import defaultdict
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def process_json_bom_data(json_data, field_mapper):
    """
    处理JSON格式的BOM数据，转换为适合校验的结构
    """

    # 如果输入是字符串，先解析为JSON
    if isinstance(json_data, str):
        try:
            bom_list = json.loads(json_data)
        except json.JSONDecodeError:
            # 如果已经是列表格式，直接使用
            bom_list = eval(json_data)
    else:
        bom_list = json_data
    
    # 转换为DataFrame
    df_data = []
    for item in bom_list:
        row = {k: item.get(v, '') if v is not None else '' for k, v in field_mapper.items()}
        df_data.append(row)
    return pd.DataFrame(df_data)

def comprehensive_bom_check_json(json_bom_data, field_mapper, parent_column='pn', child_column='mn', qty_column='n'):
    """
    专门处理JSON格式BOM数据的综合检查函数
    """
    try:
        # 处理JSON数据
        bom_df = process_json_bom_data(json_bom_data, field_mapper=field_mapper)
        
        if bom_df.empty:
            return {
                'success': False,
                'message': 'BOM数据为空或格式错误',
                'issue_summary': {},
                'marked_data': []
            }
        
        # 执行BOM检查
        results = comprehensive_bom_check_with_multiple_issues(bom_df, parent_column, child_column, qty_column)
        marked_data = results['marked_data']
        
        # 准备返回结果
        return {
            'success': True,
            'message': f'BOM检查完成，共检查 {len(bom_df)} 条记录',
            'issue_summary': results['issue_summary'],
            'marked_data': marked_data.to_dict('records'),
            'statistics': {
                'total_records': len(bom_df),
                'error_records': len(marked_data[marked_data['E'] != '']),
                'warning_records': len(marked_data[marked_data['W'] != '']),
                'clean_records': len(marked_data[(marked_data['E'] == '') & (marked_data['W'] == '')])
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'message': f'BOM检查过程中出错: {str(e)}',
            'issue_summary': {},
            'marked_data': []
        }

def comprehensive_bom_check_with_multiple_issues(bom_data, parent_column, child_column, qty_column):
    """
    BOM检查核心函数（适配JSON数据结构）
    """
    marked_data = bom_data.copy()
    
    # 初始化结果列
    marked_data['E'] = marked_data.apply(lambda _: [], axis=1)
    marked_data['W'] = marked_data.apply(lambda _: [], axis=1)
    marked_data['I'] = marked_data.apply(lambda _: [], axis=1)
    
    # 初始化问题汇总
    issue_summary = {
        'structural_issues': {
            'circular_references': [],
            'parent_child_same': [],
            'orphan_items': [],
            'multi_parents': defaultdict(list)
        },
        'data_quality_issues': {
            'non_parent': [],
            'non_child': [],
            'invalid_qty': [],
            'missing_cols': [],
            'duplicate_relations': []
        }
    }
    
    # 检查必要列
    required_cols = [parent_column, child_column, qty_column]
    missing_cols = [col for col in required_cols if col not in marked_data.columns]
    
    if missing_cols:
        for idx in marked_data.index:
            marked_data.at[idx, 'E'] = [f'缺少必要列: {missing_cols}']
            marked_data.at[idx, 'I'] = ['系统性错误']
        issue_summary['data_quality_issues']['missing_cols'] = missing_cols
        return {
            'marked_data': marked_data,
            'issue_summary': issue_summary
        }
    
    # 构建关系映射
    parent_to_child = defaultdict(list)
    child_to_parent = defaultdict(list)
    all_items = set()
    seen_relations = set()
    relation_indices = defaultdict(list)
    
    # 第一轮：收集关系和检查简单问题
    for idx, row in marked_data.iterrows():
        parent = row[parent_column]
        child = row[child_column]
        qty = row[qty_column]
        
        # 跳过空值行
        if pd.isna(parent) or parent == '':
            continue
            
        # 检查无父级料号
        if pd.isna(parent) or str(parent).strip() == '':
            issue_summary['data_quality_issues']['non_parent'].append((parent, child))
            marked_data.at[idx, 'E'].append('无父级料号')
            marked_data.at[idx, 'I'].append('数据质量问题')
            continue

        # 检查无子级料号
        if pd.isna(child) or str(child).strip() == '':
            issue_summary['data_quality_issues']['non_child'].append((parent, child))
            marked_data.at[idx, 'E'].append('无子级料号')
            marked_data.at[idx, 'I'].append('数据质量问题')
            continue

        # 检查无效数量
        if pd.isna(qty) or qty <= 0:
            issue_summary['data_quality_issues']['invalid_qty'].append((parent, child))
            marked_data.at[idx, 'E'].append('无效数量')
            marked_data.at[idx, 'I'].append('数据质量问题')
        
        # 记录关系
        relation = (str(parent), str(child))
        relation_indices[relation].append(idx)
        
        if relation in seen_relations:
            issue_summary['data_quality_issues']['duplicate_relations'].append((parent, child))
            marked_data.at[idx, 'W'].append('重复关系')
            marked_data.at[idx, 'I'].append('数据质量问题')
        else:
            seen_relations.add(relation)
            parent_to_child[str(parent)].append(str(child))
            child_to_parent[str(child)].append(str(parent))
        
        all_items.add(str(parent))
        all_items.add(str(child))
    
    # 第二轮：检查结构性问题
    
    # 1. 检查父子同号
    parent_child_same = [
        parent for parent in parent_to_child 
        if parent in parent_to_child[parent]
    ]
    issue_summary['structural_issues']['parent_child_same'] = parent_child_same
    
    # 标记父子同号问题
    for relation, indices in relation_indices.items():
        parent, child = relation
        if parent == child:
            for idx in indices:
                marked_data.at[idx, 'E'].append('父子同号')
                marked_data.at[idx, 'I'].append('结构性问题')
    
    # 2. 检查循环引用
    def has_cycle(node, visited=None, path=None):
        if visited is None:
            visited = set()
        if path is None:
            path = []
        
        if node in visited:
            return False
        
        visited.add(node)
        path.append(node)
        
        for neighbor in parent_to_child.get(node, []):
            if neighbor in path or has_cycle(neighbor, visited.copy(), path.copy()):
                return True
        return False
    
    circular_items = [item for item in all_items if has_cycle(item)]
    issue_summary['structural_issues']['circular_references'] = circular_items
    
    # 标记循环引用问题
    for relation, indices in relation_indices.items():
        parent, child = relation
        if parent in circular_items or child in circular_items:
            for idx in indices:
                marked_data.at[idx, 'E'].append('循环引用')
                marked_data.at[idx, 'I'].append('结构性问题')
    
    # 3. 检查孤立项目
    # 找出所有在BOM中出现过的物料
    all_bom_items = set(parent_to_child.keys()).union(set(child_to_parent.keys()))
    
    # 找出有子项的物料（父项）
    parent_items = set(parent_to_child.keys())
    
    # 找出被引用的物料（子项）
    child_items = set(child_to_parent.keys())
    
    # 孤立项目：在BOM中出现但没有父子关系的项目
    orphan_items = all_bom_items - parent_items - child_items
    issue_summary['structural_issues']['orphan_items'] = list(orphan_items)
    
    # 标记孤立项目问题
    for idx, row in marked_data.iterrows():
        item = str(row[parent_column])
        if item in orphan_items:
            marked_data.at[idx, 'W'].append('孤立项目')
            marked_data.at[idx, 'I'].append('结构性问题')
    
    # 4. 检查多父项
    multi_parents = defaultdict(list)
    for child, parents in child_to_parent.items():
        if len(parents) > 1:
            multi_parents[child] = parents
    
    issue_summary['structural_issues']['multi_parents'] = dict(multi_parents)
    
    # 标记多父项问题
    for relation, indices in relation_indices.items():
        parent, child = relation
        if child in multi_parents:
            for idx in indices:
                marked_data.at[idx, 'W'].append('多父项')
                marked_data.at[idx, 'I'].append('结构性问题')
    
    # 格式化输出
    def format_issues(issues):
        return ', '.join(sorted(set(issues))) if issues else ''

    marked_data['E'] = marked_data['E'].apply(format_issues)
    marked_data['W'] = marked_data['W'].apply(format_issues)
    marked_data['I'] = marked_data['I'].apply(
        lambda x: ', '.join(sorted(set(x))) if x else '')
    
    return {
        'marked_data': marked_data,
        'issue_summary': issue_summary
    }

def export_bom_check_results(results, output_file=None):
    """
    导出BOM检查结果到Excel文件
    """
    if not results.get('success'):
        return {'success': False, 'message': '无法导出，检查未成功'}
    
    try:
        marked_data = results.get('marked_data', [])
        if not marked_data:
            return {'success': False, 'message': '无数据可导出'}
        
        # 转换为DataFrame
        df = pd.DataFrame(marked_data)
        
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f'BOM检查结果_{timestamp}.xlsx'
        
        # 导出到Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # 主数据表
            df.to_excel(writer, sheet_name='BOM检查详情', index=False)
            
            # 问题汇总表
            summary_data = []
            issue_summary = results.get('issue_summary', {})
            
            # 结构性问题
            for issue_type, issues in issue_summary.get('structural_issues', {}).items():
                if issues:
                    if isinstance(issues, list):
                        for issue in issues:
                            summary_data.append({'问题类型': '结构性问题', '具体问题': issue_type, '详情': str(issue)})
                    elif isinstance(issues, dict):
                        for key, value in issues.items():
                            summary_data.append({'问题类型': '结构性问题', '具体问题': issue_type, '详情': f'{key}: {value}'})
            
            # 数据质量问题
            for issue_type, issues in issue_summary.get('data_quality_issues', {}).items():
                if issues:
                    for issue in issues:
                        summary_data.append({'问题类型': '数据质量问题', '具体问题': issue_type, '详情': str(issue)})
            
            if summary_data:
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='问题汇总', index=False)
        
        return {
            'success': True, 
            'message': f'结果已导出到: {output_file}',
            'file_path': output_file
        }
    
    except Exception as e:
        return {'success': False, 'message': f'导出失败: {str(e)}'}

#################################################################################
if __name__ == '__main__':
    import requests


    Session = requests.Session()
    response = Session.get('http://192.168.201.2:8000/zrestful_test2?sap-client=800', headers={'interface': 'bom', 'werks': '1600'})
    bom_json_data = response.json()['data']

    field_mapper = {
        "pn": "matnr",   # 产品料号
        "pu": "bmein",   # 产品单位
        "mn": "idnrk",   # 物料料号
        "mu": "meins",   # 物料单位n
        "n": "menge",   # 数量
        "d": "bmeng",   # 分母
        # "memo": None,
    }
    # 1. 执行BOM检查
    results = comprehensive_bom_check_json(bom_json_data, field_mapper=field_mapper)
    if results.get('success'):
        print(results['marked_data'])

    # 2. 打印结果摘要
    # if results['success']:
    #     stats = results['statistics']
    #     print(f"检查完成: {stats['total_records']} 条记录")
    #     print(f"错误记录: {stats['error_records']} 条")
    #     print(f"警告记录: {stats['warning_records']} 条")
    #     print(f"正常记录: {stats['clean_records']} 条")
        
    #     # 3. 导出结果
    #     export_result = export_bom_check_results(results)
    #     if export_result['success']:
    #         print(export_result['message'])