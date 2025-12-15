import pandas as pd, json, warnings

from typing import Dict, List, Any#, Set, Tuple
from collections import defaultdict
from datetime import datetime


warnings.filterwarnings('ignore')

MD_CTRLID = {
    'parent_no': 'pn',
    'child_no': 'cn',
    'parent_version': 'pv',
    'parent_unit': 'pu',
    'child_unit': 'cu',
    'numerator': 'n',
    'denominator': 'd',
    'dto': 'dto',
}

def process_json_bom_data(
        json_data: str | List[Dict[str, Any]], 
        mainfield_mapper: dict, 
        dtofield_mapper: dict={},
        numerator_col: str=MD_CTRLID['numerator'], 
        denominator_col: str=MD_CTRLID['denominator']
    ) -> pd.DataFrame:
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
    
    num_columns_set = set([numerator_col, denominator_col])

    # 转换为DataFrame
    df_data = []
    for item in bom_list:
        row = {mk: 0 if mk in num_columns_set and not item.get(ok) else item.get(ok, '') for mk, ok in mainfield_mapper.items()}
        row[MD_CTRLID['dto']] = {mk: item.get(ok, '') for mk, ok in dtofield_mapper.items()} if dtofield_mapper else None
        df_data.append(row)


    df = pd.DataFrame(df_data)
    df = df.astype({
        numerator_col: 'float32',
        denominator_col: 'float32'
    })
    
    # 若分母全为0，则说明原始数据缺少整列，则统一设为1
    if (df[denominator_col] == 0).all():
        df[denominator_col] = 1

    return df

def bom_check(
        bom_df: pd.DataFrame,
        parent_col: str = MD_CTRLID['parent_no'],
        child_col: str = MD_CTRLID['child_no'],
        numerator_col: str = MD_CTRLID['numerator'],
        denominator_col: str = MD_CTRLID['denominator'],
        parentversion_col: str = MD_CTRLID['parent_version']
    ) -> dict:
    """
    专门处理JSON格式BOM数据的综合检查函数
    """
    try:
        
        if bom_df.empty:
            return {
                'success': False,
                'message': 'BOM数据为空或格式错误',
                'issue_summary': {},
                'marked_data': []
            }
        
        # 执行BOM检查
        results = bom_check_core_processor(
            bom_df,
            parent_column=parent_col,
            child_column=child_col,
            numerator_column=numerator_col,
            denominator_column=denominator_col,
            parentversion_column=parentversion_col
        )
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

def bom_check_core_processor(
        bom_df: pd.DataFrame,
        parent_column: str = MD_CTRLID['parent_no'],
        child_column: str = MD_CTRLID['child_no'],
        denominator_column: str = MD_CTRLID['denominator'],
        numerator_column: str = MD_CTRLID['numerator'],
        parentversion_column: str = MD_CTRLID['parent_version']
    ) -> dict:
    """
    BOM检查核心函数（适配JSON数据结构）
    """
    marked_data = bom_df.copy()
    
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
    if denominator_column not in marked_data.columns:
        marked_data[denominator_column] = 1
    
    # 如果version_column不存在，添加一个空列
    if parentversion_column not in marked_data.columns:
        marked_data[parentversion_column] = ''
        
    required_cols = [parent_column, child_column, numerator_column, denominator_column]
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
        numerator = row[numerator_column]
        denominator = row[denominator_column]
        
        # 获取版本号，如果parentversion_column存在
        parentversion = row.get(parentversion_column, '')
        parentversion_str = '' if pd.isna(parentversion) else str(parentversion)
        
        # 统一创建元组变量
        data_key = (parent, child, parentversion_str)
            
        # 检查无父级料号
        if pd.isna(parent) or str(parent).strip() == '':
            issue_summary['data_quality_issues']['non_parent'].append(data_key)
            marked_data.at[idx, 'E'].append('无父级料号')
            marked_data.at[idx, 'I'].append('数据质量问题')


        # 检查无子级料号
        if pd.isna(child) or str(child).strip() == '':
            issue_summary['data_quality_issues']['non_child'].append(data_key)
            marked_data.at[idx, 'E'].append('无子级料号')
            marked_data.at[idx, 'I'].append('数据质量问题')


        # 检查无效数量（分子）
        if pd.isna(numerator) or numerator <= 0:
            issue_summary['data_quality_issues']['invalid_qty'].append(data_key)
            marked_data.at[idx, 'E'].append('无效数量')
            marked_data.at[idx, 'I'].append('数据质量问题')
        

        # 检查无效数量（分母）
        if pd.isna(denominator) or denominator <= 0:
            issue_summary['data_quality_issues']['invalid_qty'].append(data_key)
            marked_data.at[idx, 'E'].append('无效数量')
            marked_data.at[idx, 'I'].append('数据质量问题')
        
        # 检查长度（APS数据库要求）
        # if len(parentversion_str) > 4:
        #     issue_summary['data_quality_issues']['invalid_qty'].append((parent, child, parentversion_str))
        #     marked_data.at[idx, 'E'].append('版本号超长')
        #     marked_data.at[idx, 'I'].append('数据质量问题')

        # 记录关系 - 包含版本号，形成(parent, child, version)的唯一标识
        relation = (str(parent), str(child), parentversion_str)
        relation_indices[relation].append(idx)
        
        if relation in seen_relations:
            issue_summary['data_quality_issues']['duplicate_relations'].append((parent, child, parentversion_str))
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
        # 正确处理三元组 (parent, child, parentversion)
        if len(relation) == 3:
            parent, child, _ = relation  # 忽略版本号，只使用parent和child
        else:
            parent, child = relation  # 兼容原有二元组格式
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
        # 正确处理三元组 (parent, child, parentversion)
        if len(relation) == 3:
            parent, child, _ = relation  # 忽略版本号，只使用parent和child
        else:
            parent, child = relation  # 兼容原有二元组格式
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
        # 正确处理三元组 (parent, child, parentversion)
        if len(relation) == 3:
            parent, child, _ = relation  # 忽略版本号，只使用parent和child
        else:
            parent, child = relation  # 兼容原有二元组格式
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

def export_bom_check_results_as_excel(results, output_file=None):
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

def output_bom_check_result_as_markdown(results):
    """
    将BOM检查结果转换为Markdown格式
    """

    output = "### BOM检查结果\n"
    if results['success']:
        stats = results['statistics']
        output += f"- 检查完成: {stats['total_records']}\n"
        output += f"- 错误记录: {stats['error_records']}\n"
        output += f"- 警告记录: {stats['warning_records']}\n"
        output += f"- 正常记录: {stats['clean_records']}\n"
    # output += "\n"
    return {'bom_check_result': output}

def bom_unit_check_core_processor(
    df: pd.DataFrame,
    parent_col: str = MD_CTRLID['parent_no'],
    parentunit_col: str = MD_CTRLID['parent_unit'],
    child_col: str = MD_CTRLID['child_no'],
    childunit_col: str = MD_CTRLID['child_unit'],
) -> Dict[str, Any]:
    """
    全面校验BOM中所有料号的单位唯一性（通盘考虑产品料号和物料料号）
    
    参数:
        df: process_json_bom_data函数输出的DataFrame
        product_no_col: 产品料号列名
        product_unit_col: 产品单位列名
        material_no_col: 物料料号列名
        material_unit_col: 物料单位列名
    
    返回:
        Dict: 包含详细校验结果的字典
    """
    if df.empty:
        return {
            'exec_success': False,
            'summary': '输入DataFrame为空',
            'valid': False,
            'details': []
        }

    if parentunit_col not in df.columns or df[parentunit_col].isnull().all() or df[parentunit_col].astype(str).str.strip().eq('').all():
        return {
            'exec_success': False,
            'summary': f'缺少产品单位列 {parentunit_col}',
            'valid': False,
            'details': []
        }
    if childunit_col not in df.columns or df[childunit_col].isnull().all() or df[childunit_col].astype(str).str.strip().eq('').all():
        return {
            'exec_success': False,
            'summary': f'缺少物料单位列 {childunit_col}',
            'valid': False,
            'details': []
        }
    # 存储所有料号及其对应的单位
    material_units_map = {}
    
    # 收集产品料号及其单位
    if parent_col in df.columns and parentunit_col in df.columns:
        product_data = df[[parent_col, parentunit_col]].dropna()
        for _, row in product_data.iterrows():
            material_number = str(row[parent_col])
            unit = str(row[parentunit_col])
            
            if material_number and unit:  # 忽略空值
                if material_number not in material_units_map:
                    material_units_map[material_number] = set()
                material_units_map[material_number].add(unit)
    
    # 收集物料料号及其单位
    if child_col in df.columns and childunit_col in df.columns:
        material_data = df[[child_col, childunit_col]].dropna()
        for _, row in material_data.iterrows():
            material_number = str(row[child_col])
            unit = str(row[childunit_col])
            
            if material_number and unit:  # 忽略空值
                if material_number not in material_units_map:
                    material_units_map[material_number] = set()
                material_units_map[material_number].add(unit)
    
    # 分析每个料号的单位情况
    validation_results = []
    unified_materials = []
    problematic_materials = []
    
    for material_number, units_set in material_units_map.items():
        unique_units = list(units_set)
        
        # 判断该料号是否同时出现在产品角色和物料角色中
        appears_as_product = material_number in df[parent_col].astype(str).values if parent_col in df.columns else False
        appears_as_material = material_number in df[child_col].astype(str).values if child_col in df.columns else False
        
        result = {
            'material_number': material_number,
            'appears_as_product': appears_as_product,
            'appears_as_material': appears_as_material,
            'is_unified': len(unique_units) == 1,
            'unique_units': ','.join(unique_units),
            'unit_count': len(unique_units),
            'occurrence_count': 0  # 初始化，下面会计算
        }
        
        # 计算该料号在数据中出现的总次数
        product_count = len(df[df[parent_col].astype(str) == material_number]) if parent_col in df.columns else 0
        material_count = len(df[df[child_col].astype(str) == material_number]) if child_col in df.columns else 0
        result['occurrence_count'] = product_count + material_count
        
        validation_results.append(result)
        
        if result['is_unified']:
            unified_materials.append(result)
        else:
            problematic_materials.append(result)
    
    # 生成详细的问题分析
    problematic_details = []
    for material in problematic_materials:
        # 获取该料号作为父级时的所有记录
        product_records = []
        if parent_col in df.columns:
            product_mask = df[parent_col].astype(str) == material['material_number']
            if product_mask.any():
                product_records = df[product_mask][[parent_col, parentunit_col]].to_dict('records')
        
        # 获取该料号作为子级时的所有记录
        material_records = []
        if child_col in df.columns:
            material_mask = df[child_col].astype(str) == material['material_number']
            if material_mask.any():
                material_records = df[material_mask][[child_col, childunit_col]].to_dict('records')
        
        # 按单位统计分布
        unit_distribution = {}
        for record in product_records:
            unit = str(record.get(parentunit_col, ''))
            unit_distribution[unit] = unit_distribution.get(unit, 0) + 1
        
        for record in material_records:
            unit = str(record.get(childunit_col, ''))
            unit_distribution[unit] = unit_distribution.get(unit, 0) + 1
        
        problematic_details.append({
            'material_number': material['material_number'],
            'unit_distribution': unit_distribution,
            'product_records_count': len(product_records),
            'material_records_count': len(material_records),
            'product_records_sample': product_records[:3],  # 采样3条记录
            'material_records_sample': material_records[:3]  # 采样3条记录
        })
    
    # 生成摘要统计
    summary = {
        'total_unique_materials': len(material_units_map),
        'unified_materials_count': len(unified_materials),
        'problematic_materials_count': len(problematic_materials),
        'pass_rate_percent': round((len(unified_materials) / len(material_units_map)) * 100, 2) if material_units_map else 0,
        'multi_role_materials_count': len([m for m in validation_results if m['appears_as_product'] and m['appears_as_material']]),
        'check_timestamp': pd.Timestamp.now().isoformat()
    }
    
    return {
        'exec_success': True,
        'summary': summary,
        # 'validation_details': validation_results,
        # 'material_units_map': material_units_map,
        'material_units_map_list': [{'materialno': k, 'unit': ','.join(v)} for k, v in material_units_map.items()],
        'problematic_details': problematic_details,
        'critical_issues': [m for m in problematic_materials if m['appears_as_product'] and m['appears_as_material']]
    }

def output_unit_check_result_as_markdown(unit_check_results):
    if not unit_check_results.get('exec_success'):
        # print(unit_check_results['summary'])
        return {'source_info': unit_check_results}
    
    summary = unit_check_results['summary']
    output = "### 量纲校验结果摘要\n"
    output += f"- 总计校验料号数: {summary['total_unique_materials']}\n"
    output += f"- 单位统一料号数: {summary['unified_materials_count']}\n"
    output += f"- 多角色料号数: {summary['multi_role_materials_count']}\n"
    output += f"- 存在问题的料号数: {summary['problematic_materials_count']}\n"
    output += f"- 通过率: {summary['pass_rate_percent']}%\n---\n"

    problematic_details = unit_check_results['problematic_details']
    output += "##### 问题详情\n---\n"
    if problematic_details:
        for detail in problematic_details:
            output += f"- 料号: {detail['material_number']}, 单位分布: {detail['unit_distribution']}, 作为父级: {detail['product_records_count']}, 作为子级: {detail['material_records_count']}\n"
    else:
        output += "*🈚NONE*\n---\n"

    # print(problematic_details_description)
    critical_issues = unit_check_results['critical_issues']
    output += "##### 关键争议\n"
    if critical_issues:
        for issue in critical_issues:
            output += f"- 料号: {issue['material_number']}, 使用单位: {issue['unique_units']}\n---\n"
    else:
        output += "*🈚NONE*\n---\n"

    # 返回结果与明道云control id对应
    return {
        # 'source_info': unit_check_results,
        'check_timestamp': unit_check_results['summary']['check_timestamp'],
        'unit_check_result': output,
    }
