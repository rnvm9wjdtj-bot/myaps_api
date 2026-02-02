import pandas as pd
import json
import warnings
from io import BytesIO
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime


from fastapi.responses import StreamingResponse


warnings.filterwarnings('ignore')

HAP_CTRLID = {
    'parent_no': 'pn',
    'child_no': 'cn',
    'parent_version': 'pv',
    'parent_unit': 'pu',
    'child_unit': 'cu',
    'numerator': 'n',
    'denominator': 'd',
    'dto': 'dto',
}

class BOMChecker:
    def __init__(self,
                 mainfield_mapper: dict={},
                 dtofield_mapper: dict={},
                 numerator_col: str = HAP_CTRLID['numerator'],
                 denominator_col: str = HAP_CTRLID['denominator'],
                 parent_col: str = HAP_CTRLID['parent_no'],
                 child_col: str = HAP_CTRLID['child_no'],
                 parentversion_col: str = HAP_CTRLID['parent_version'],
                 parentunit_col: str = HAP_CTRLID['parent_unit'],
                 childunit_col: str = HAP_CTRLID['child_unit']):
        """
        初始化BOM校验器
        :param mainfield_mapper: 主字段映射，将外部字段映射到内部字段
        :param dtofield_mapper: DTO字段映射，将DTO字段映射到内部字段
        :param numerator_col: 映射后的分子列名
        :param denominator_col: 映射后的分母列名
        :param parent_col: 映射后的父料号列名
        :param child_col: 映射后的子料号列名
        :param parentversion_col: 映射后的父版本列名
        :param parentunit_col: 映射后的父单位列名
        :param childunit_col: 映射后的子单位列名
        """
        self.md_ctrlid = HAP_CTRLID
        self.bom_result = None  # 存储BOM检查结果
        self.unit_result = None  # 存储单位检查结果
        # 初始化映射和列名
        self.mainfield_mapper = mainfield_mapper
        self.dtofield_mapper = dtofield_mapper
        self.numerator_col = numerator_col
        self.denominator_col = denominator_col
        self.parent_col = parent_col
        self.child_col = child_col
        self.parentversion_col = parentversion_col
        self.parentunit_col = parentunit_col
        self.childunit_col = childunit_col
    
    def _process_json_bom_data(
            self, 
            json_data: str | List[Dict[str, Any]], 
            mainfield_mapper: dict, 
            dtofield_mapper: dict={},
            numerator_col: str=HAP_CTRLID['numerator'], 
            denominator_col: str=HAP_CTRLID['denominator']
        ) -> pd.DataFrame:
        """
        处理JSON格式的BOM数据，转换为适合校验的结构
        """
        # 解析JSON数据
        if isinstance(json_data, str):
            try:
                bom_list = json.loads(json_data)
            except json.JSONDecodeError:
                raise ValueError("无效的JSON格式")
        else:
            bom_list = json_data
        
        num_columns_set = set([numerator_col, denominator_col])
        
        # 转换为DataFrame
        df_data = []
        for item in bom_list:
            # 如果mainfield_mapper为空，直接使用item的键值对
            if not mainfield_mapper:
                row = item.copy()
                # 确保数值列为数值类型
                for col in num_columns_set:
                    if col in row:
                        if row[col] == '':
                            row[col] = 0
                    else:
                        row[col] = 0
            else:
                row = {mk: 0 if mk in num_columns_set and not item.get(ok) else item.get(ok, '') 
                      for mk, ok in mainfield_mapper.items()}
            
            row[HAP_CTRLID['dto']] = {mk: item.get(ok, '') for mk, ok in dtofield_mapper.items()} if dtofield_mapper else None
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        
        # 确保数值列存在并设置正确的类型
        for col in num_columns_set:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 若分母全为0，则统一设为1
        if (df[denominator_col] == 0).all():
            df[denominator_col] = 1
        
        return df
    
    def _bytesio_to_dataframe(
            self, 
            bytesio_obj, 
            mainfield_mapper: dict, 
            dtofield_mapper: dict={},
            numerator_col: str=HAP_CTRLID['numerator'], 
            denominator_col: str=HAP_CTRLID['denominator']
        ) -> pd.DataFrame:
        """
        将BytesIO对象（Excel文件）转换为适合校验的DataFrame结构
        """
        # 读取Excel文件
        try:
            df = pd.read_excel(bytesio_obj)
        except Exception as e:
            raise ValueError(f"读取Excel文件失败: {str(e)}")
        
        # 如果mainfield_mapper不为空，则进行字段映射
        if mainfield_mapper:
            # 反转映射，将Excel列名映射到hap ctrl id
            reverse_mapper = {v: k for k, v in mainfield_mapper.items() if v}
            # 重命名列
            df = df.rename(columns=reverse_mapper)
        
        num_columns_set = set([numerator_col, denominator_col])
        
        # 处理数值列
        for col in num_columns_set:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 若分母全为0，则统一设为1
        if denominator_col in df.columns and (df[denominator_col] == 0).all():
            df[denominator_col] = 1
        
        # 添加dto字段
        if dtofield_mapper:
            reverse_dto_mapper = {v: k for k, v in dtofield_mapper.items() if v}
            df[HAP_CTRLID['dto']] = df.apply(
                lambda row: {mk: row.get(ok, '') for ok, mk in reverse_dto_mapper.items()}, 
                axis=1
            )
        else:
            df[HAP_CTRLID['dto']] = None
        
        return df
    
    def _convert_input_to_dataframe(
            self, 
            input_data: Any,
            mainfield_mapper: dict={},
            dtofield_mapper: dict={},
            numerator_col: str = HAP_CTRLID['numerator'],
            denominator_col: str = HAP_CTRLID['denominator']
        ) -> pd.DataFrame:
        """
        智能判断输入类型并转换为DataFrame
        """
        try:
            if isinstance(input_data, pd.DataFrame):
                return input_data
            elif isinstance(input_data, BytesIO):
                return self._bytesio_to_dataframe(
                    bytesio_obj=input_data,
                    mainfield_mapper=mainfield_mapper,
                    dtofield_mapper=dtofield_mapper,
                    numerator_col=numerator_col,
                    denominator_col=denominator_col
                )
            elif isinstance(input_data, (str, list)):
                return self._process_json_bom_data(
                    json_data=input_data,
                    mainfield_mapper=mainfield_mapper,
                    dtofield_mapper=dtofield_mapper,
                    numerator_col=numerator_col,
                    denominator_col=denominator_col
                )
            else:
                raise ValueError(f"不支持的输入类型: {type(input_data).__name__}")
        except Exception as e:
            raise ValueError(f"数据转换失败: {str(e)}")
    
    def start_check(
            self, 
            input_data: Any
        ) -> dict:
        """
        BOM综合检查函数
        每次执行BOM检查时，会清除之前的单位检查结果以保证数据一致性
        """
        # 清除单位检查结果以保证数据一致性
        self.unit_result = None
        
        # 智能判断输入类型并转换为DataFrame
        try:
            bom_df = self._convert_input_to_dataframe(
                input_data=input_data,
                mainfield_mapper=self.mainfield_mapper,
                dtofield_mapper=self.dtofield_mapper,
                numerator_col=self.numerator_col,
                denominator_col=self.denominator_col
            )
        except Exception as e:
            self.bom_result = {
                'success': False,
                'message': f'BOM数据处理失败: {str(e)}',
                'issue_summary': {},
                'marked_data': []
            }
            return self.bom_result
        
        if bom_df.empty:
            self.bom_result = {
                'success': False,
                'message': 'BOM数据为空或格式错误',
                'issue_summary': {},
                'marked_data': []
            }
            return self.bom_result
        
        try:
            # 执行BOM检查
            results = self._bom_check(
                bom_df,
                parent_column=self.parent_col,
                child_column=self.child_col,
                numerator_column=self.numerator_col,
                denominator_column=self.denominator_col,
                parentversion_column=self.parentversion_col
            )
            marked_data = results['marked_data']
            
            # 准备返回结果
            statistics = {
                'total_records': len(bom_df),
                'error_records': len(marked_data[marked_data['E'] != '']),
                'warning_records': len(marked_data[marked_data['W'] != '']),
                'clean_records': len(marked_data[(marked_data['E'] == '') & (marked_data['W'] == '')])
            }
            
            self.bom_result = {
                'success': True,
                'message': f'BOM检查完成，共检查 {len(bom_df)} 条记录',
                'issue_summary': results['issue_summary'],
                'marked_data': marked_data.to_dict('records'),
                'statistics': statistics
            }
            
            # 检测pu和cu列是否存在，如果存在则自动执行单位检查
            if self.parentunit_col in bom_df.columns and self.childunit_col in bom_df.columns:
                # 检查列是否有实际数据
                has_parent_unit_data = not bom_df[self.parentunit_col].isnull().all() and not bom_df[self.parentunit_col].astype(str).str.strip().eq('').all()
                has_child_unit_data = not bom_df[self.childunit_col].isnull().all() and not bom_df[self.childunit_col].astype(str).str.strip().eq('').all()
                
                if has_parent_unit_data or has_child_unit_data:
                    # 自动执行单位检查
                    self._unit_check(
                        input_data=input_data
                    )
            
            return self.bom_result
        except Exception as e:
            self.bom_result = {
                'success': False,
                'message': f'BOM检查过程中出错: {str(e)}',
                'issue_summary': {},
                'marked_data': []
            }
            return self.bom_result
    
    def _bom_check(
            self, 
            bom_df: pd.DataFrame,
            parent_column: str,
            child_column: str,
            denominator_column: str,
            numerator_column: str,
            parentversion_column: str
        ) -> dict:
        """
        BOM检查核心函数
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
        
        # 检查并添加必要列
        if denominator_column not in marked_data.columns:
            marked_data[denominator_column] = 1
        
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
            parentversion = str(row.get(parentversion_column, '')) if not pd.isna(row.get(parentversion_column, '')) else ''
            
            # 统一创建关系标识
            relation = (str(parent), str(child), parentversion)
            relation_indices[relation].append(idx)
            
            data_key = relation
            
            # 检查数据质量问题
            errors = []
            issues = []
            
            if pd.isna(parent) or str(parent).strip() == '':
                errors.append('无父级料号')
                issues.append('数据质量问题')
                issue_summary['data_quality_issues']['non_parent'].append(data_key)
            
            if pd.isna(child) or str(child).strip() == '':
                errors.append('无子级料号')
                issues.append('数据质量问题')
                issue_summary['data_quality_issues']['non_child'].append(data_key)
            
            if pd.isna(numerator) or numerator <= 0 or pd.isna(denominator) or denominator <= 0:
                errors.append('无效数量')
                issues.append('数据质量问题')
                issue_summary['data_quality_issues']['invalid_qty'].append(data_key)
            
            # 记录重复关系
            if relation in seen_relations:
                marked_data.at[idx, 'W'].append('重复关系')
                marked_data.at[idx, 'I'].append('数据质量问题')
                issue_summary['data_quality_issues']['duplicate_relations'].append(data_key)
            else:
                seen_relations.add(relation)
                parent_to_child[str(parent)].append(str(child))
                child_to_parent[str(child)].append(str(parent))
            
            # 更新标记数据
            if errors:
                marked_data.at[idx, 'E'].extend(errors)
            if issues:
                marked_data.at[idx, 'I'].extend(issues)
            
            all_items.add(str(parent))
            all_items.add(str(child))
        
        # 第二轮：检查结构性问题
        
        # 1. 检查父子同号
        parent_child_same = [parent for parent in parent_to_child if parent in parent_to_child[parent]]
        issue_summary['structural_issues']['parent_child_same'] = parent_child_same
        
        # 标记父子同号问题
        for relation, indices in relation_indices.items():
            parent, child, _ = relation
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
            parent, child, _ = relation
            if parent in circular_items or child in circular_items:
                for idx in indices:
                    marked_data.at[idx, 'E'].append('循环引用')
                    marked_data.at[idx, 'I'].append('结构性问题')
        
        # 3. 检查孤立项目
        all_bom_items = set(parent_to_child.keys()).union(set(child_to_parent.keys()))
        parent_items = set(parent_to_child.keys())
        child_items = set(child_to_parent.keys())
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
            parent, child, _ = relation
            if child in multi_parents:
                for idx in indices:
                    marked_data.at[idx, 'W'].append('多父项')
                    marked_data.at[idx, 'I'].append('结构性问题')
        
        # 格式化输出
        def format_issues(issues):
            return ','.join(sorted(set(issues))) if issues else ''
        
        for col in ['E', 'W', 'I']:
            marked_data[col] = marked_data[col].apply(format_issues)
        
        return {
            'marked_data': marked_data,
            'issue_summary': issue_summary
        }
    
    def _unit_check(
            self, 
            input_data: Any
        ) -> Dict[str, Any]:
        """
        全面校验BOM中所有料号的单位唯一性（私有方法）
        """
        # 使用统一的数据转换方法
        try:
            df = self._convert_input_to_dataframe(
                input_data=input_data,
                mainfield_mapper=self.mainfield_mapper,
                dtofield_mapper=self.dtofield_mapper,
                numerator_col=self.numerator_col,
                denominator_col=self.denominator_col
            )
        except Exception as e:
            return {
                'exec_success': False,
                'summary': f'输入数据处理失败: {str(e)}',
                'valid': False,
                'details': []
            }
        
        # 存储所有料号及其对应的单位
        material_units_map = defaultdict(set)
        
        # 收集产品料号及其单位
        product_data = df[[self.parent_col, self.parentunit_col]].dropna()
        for _, row in product_data.iterrows():
            material_number = str(row[self.parent_col])
            unit = str(row[self.parentunit_col])
            if material_number and unit:
                material_units_map[material_number].add(unit)
        
        # 收集物料料号及其单位
        material_data = df[[self.child_col, self.childunit_col]].dropna()
        for _, row in material_data.iterrows():
            material_number = str(row[self.child_col])
            unit = str(row[self.childunit_col])
            if material_number and unit:
                material_units_map[material_number].add(unit)
        
        # 分析校验结果
        validation_results = []
        problematic_materials = []
        
        for material_number, units_set in material_units_map.items():
            unique_units = list(units_set)
            appears_as_product = material_number in df[self.parent_col].astype(str).values
            appears_as_material = material_number in df[self.child_col].astype(str).values
            
            result = {
                'material_number': material_number,
                'appears_as_product': appears_as_product,
                'appears_as_material': appears_as_material,
                'is_unified': len(unique_units) == 1,
                'unique_units': unique_units,
                'unit_count': len(unique_units),
                'product_count': len(df[df[self.parent_col].astype(str) == material_number]),
                'material_count': len(df[df[self.child_col].astype(str) == material_number])
            }
            
            validation_results.append(result)
            result['occurrence_count'] = result['product_count'] + result['material_count']
            
            if not result['is_unified']:
                problematic_materials.append(result)
        
        # 生成详细的问题分析
        problematic_details = []
        for material in problematic_materials:
            # 获取该料号的所有相关记录
            product_records = df[df[self.parent_col].astype(str) == material['material_number']][[self.parent_col, self.parentunit_col]].to_dict('records')
            material_records = df[df[self.child_col].astype(str) == material['material_number']][[self.child_col, self.childunit_col]].to_dict('records')
            
            # 统计单位分布
            unit_distribution = defaultdict(int)
            for record in product_records:
                unit_distribution[str(record.get(self.parentunit_col, ''))] += 1
            for record in material_records:
                unit_distribution[str(record.get(self.childunit_col, ''))] += 1
            
            problematic_details.append({
                'material_number': material['material_number'],
                'unit_distribution': dict(unit_distribution),
                'product_records_count': len(product_records),
                'material_records_count': len(material_records),
                'product_records_sample': product_records[:3],
                'material_records_sample': material_records[:3]
            })
        
        # 生成摘要统计
        total_materials = len(material_units_map)
        summary = {
            'total_unique_materials': total_materials,
            'unified_materials_count': total_materials - len(problematic_materials),
            'problematic_materials_count': len(problematic_materials),
            'pass_rate_percent': round(((total_materials - len(problematic_materials)) / total_materials) * 100, 2) if total_materials else 0,
            'multi_role_materials_count': len([m for m in validation_results if m['appears_as_product'] and m['appears_as_material']]),
            'check_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        self.unit_result = {
            'exec_success': True,
            'summary': summary,
            'material_units_map_list': [{'materialno': k, 'unit': ','.join(v)} for k, v in material_units_map.items()],
            'problematic_details': problematic_details,
            'critical_issues': [m for m in problematic_materials if m['appears_as_product'] and m['appears_as_material']]
        }
        return self.unit_result
    
    def export_results_as_excel(self, output_file=None) -> Any:
        """
        导出BOM检查结果和/或单位检查结果到Excel文件或BytesIO对象
        
        参数:
            output_file: 输出文件路径或BytesIO对象。如果为None，将返回BytesIO对象
        
        返回:
            如果output_file是字符串: 返回{'success': True, 'file_path': output_file}
            如果output_file是None或BytesIO对象: 返回BytesIO对象
            如果导出失败: 返回{'success': False, 'message': '错误信息'}
        """
        try:
            use_bytesio = output_file is None or isinstance(output_file, BytesIO)
            
            if output_file is None:
                output_file = BytesIO()
            
            # 检查是否有可导出的结果
            has_bom = self.bom_result is not None and 'success' in self.bom_result
            has_unit = self.unit_result is not None and 'exec_success' in self.unit_result
            
            if not has_bom and not has_unit:
                return {'success': False, 'message': '无检查结果可导出'}
            
            # 导出到Excel
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # 导出BOM检查结果
                if has_bom:
                    # BOM检查结果导出
                    if not self.bom_result.get('success'):
                        return {'success': False, 'message': '无法导出，BOM检查未成功'}
                    
                    marked_data = self.bom_result.get('marked_data', [])
                    if not marked_data:
                        return {'success': False, 'message': '无BOM检查数据可导出'}
                    
                    # 主数据表
                    df = pd.DataFrame(marked_data)
                    df.to_excel(writer, sheet_name='BOM检查详情', index=False)
                    
                    # 问题汇总表
                    summary_data = []
                    issue_summary = self.bom_result.get('issue_summary', {})
                    
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
                        summary_df.to_excel(writer, sheet_name='BOM问题汇总', index=False)
                
                # 导出单位检查结果
                if has_unit:
                    # 单位检查结果导出
                    if not self.unit_result.get('exec_success'):
                        return {'success': False, 'message': '无法导出，单位检查未成功'}
                    
                    # 单位检查摘要
                    summary = self.unit_result.get('summary', {})
                    summary_df = pd.DataFrame([summary])
                    summary_df.to_excel(writer, sheet_name='单位检查摘要', index=False)
                    
                    # 料号单位映射
                    material_units = self.unit_result.get('material_units_map_list', [])
                    if material_units:
                        units_df = pd.DataFrame(material_units)
                        units_df.to_excel(writer, sheet_name='料号单位映射', index=False)
                    
                    # 问题详情
                    problematic_details = self.unit_result.get('problematic_details', [])
                    if problematic_details:
                        details_data = []
                        for detail in problematic_details:
                            for unit, count in detail.get('unit_distribution', {}).items():
                                details_data.append({
                                    '料号': detail.get('material_number', ''),
                                    '单位': unit,
                                    '数量': count,
                                    '作为父级次数': detail.get('product_records_count', 0),
                                    '作为子级次数': detail.get('material_records_count', 0)
                                })
                        if details_data:
                            details_df = pd.DataFrame(details_data)
                            details_df.to_excel(writer, sheet_name='单位问题详情', index=False)
                    
                    # 关键问题
                    critical_issues = self.unit_result.get('critical_issues', [])
                    if critical_issues:
                        critical_data = []
                        for issue in critical_issues:
                            critical_data.append({
                                '料号': issue.get('material_number', ''),
                                '单位列表': ','.join(issue.get('unique_units', [])),
                                '单位数量': issue.get('unit_count', 0),
                                '出现次数': issue.get('occurrence_count', 0),
                                '作为父级': issue.get('appears_as_product', False),
                                '作为子级': issue.get('appears_as_material', False)
                            })
                        if critical_data:
                            critical_df = pd.DataFrame(critical_data)
                            critical_df.to_excel(writer, sheet_name='单位关键问题', index=False)
            
            if use_bytesio:
                output_file.seek(0)
                # summary_markdown = self.output_results_as_markdown()
                # ts = summary_markdown.get("check_timestamp", datetime.now().strftime("%Y%m%d%H%M%S")).replace(":", "").replace(" ", "").replace("-", "")
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                return StreamingResponse(
                    output_file,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename=bom_check_results_{ts}.xlsx"
                    }
                )
            else:
                return {
                    'success': True, 
                    'message': f'结果已导出到: {output_file}',
                    'file_path': output_file
                }
        except Exception as e:
            return {'success': False, 'message': f'导出失败: {str(e)}'}
    
    def output_results_as_markdown(self) -> Dict[str, str]:
        """
        将BOM检查结果和单位检查结果统一转换为Markdown格式
        """
        output = "# 📋 BOM检查综合报告\n\n"
        has_results = False
        
        # 添加BOM检查结果
        if self.bom_result:
            has_results = True
            output += "### 结果汇总\n"
            if self.bom_result.get('success'):
                stats = self.bom_result.get('statistics', {})
                output += f"- 检查完成: {stats.get('total_records', 0)}\n"
                output += f"- 错误记录: {stats.get('error_records', 0)}\n"
                output += f"- 警告记录: {stats.get('warning_records', 0)}\n"
                output += f"- 正常记录: {stats.get('clean_records', 0)}\n"
            else:
                output += f"- ❌ 检查失败: {self.bom_result.get('message', '未知错误')}\n"
            output += "\n"
        
        # 添加单位检查结果
        if self.unit_result:
            has_results = True
            output += "### 量纲校验结果\n"
            if self.unit_result.get('exec_success'):
                summary = self.unit_result.get('summary', {})
                output += f"- 总计校验料号数: {summary.get('total_unique_materials', 0)}\n"
                output += f"- 单位统一料号数: {summary.get('unified_materials_count', 0)}\n"
                output += f"- 多角色料号数: {summary.get('multi_role_materials_count', 0)}\n"
                output += f"- 存在问题的料号数: {summary.get('problematic_materials_count', 0)}\n"
                output += f"- 通过率: {summary.get('pass_rate_percent', 0)}%\n"
                
                output += "\n##### 问题详情\n"
                problematic_details = self.unit_result.get('problematic_details', [])
                if problematic_details:
                    for detail in problematic_details:
                        output += f"- 料号: {detail['material_number']}, 单位分布: {detail['unit_distribution']}, 作为父级: {detail['product_records_count']}, 作为子级: {detail['material_records_count']}\n"
                else:
                    output += "*无问题*\n"
                
                output += "\n##### 关键争议\n"
                critical_issues = self.unit_result.get('critical_issues', [])
                if critical_issues:
                    for issue in critical_issues:
                        output += f"- 料号: {issue['material_number']}, 使用单位: {','.join(issue['unique_units'])}\n"
                else:
                    output += "*无关键争议*\n"
            else:
                output += f"- ❌ 单位检查失败: {self.unit_result.get('summary', '未知错误')}\n"
        
        if not has_results:
            output += "❌ 无检查结果可显示\n"
        
        result = {'combined_result': output}
        
        # 如果有单位检查结果，添加时间戳
        if self.unit_result and self.unit_result.get('exec_success'):
            result['check_timestamp'] = self.unit_result['summary'].get('check_timestamp', '')
        
        return result


    def output_results_to_hap(self, hap_conn) -> dict:
        """
        将BOM检查结果和单位检查结果传输至 HAP
        """
        marked_data = self.bom_result['marked_data']
        if self.unit_result:
            material_units_map_list = self.unit_result['material_units_map_list']
        else:
            material_units_map_list = []
        markdown_result = self.output_results_as_markdown()
        try:
            hap_conn.worksheet('bom_check_summary').create_rows(data_list=[markdown_result])
            hap_conn.worksheet('transit_bom_structure').create_rows(data_list=marked_data)
            hap_conn.worksheet('material_units_map').create_rows(data_list=material_units_map_list)

            return {'status_code': 200, 'success': 1, 'message': '数据成功传输至 HAP'}
        except Exception as e:
            return {'status_code': 500, 'success': 0, 'message': str(e)}


if __name__ == '__main__':
    """
    BOMChecker类的使用示例和测试用例
    直接运行此文件即可查看演示效果
    """
    import json
    from io import BytesIO
    
    # 示例BOM数据
    TEST_BOM_DATA = [
        {"parent_no": "P1", "child_no": "C1", "parent_unit": "EA", "child_unit": "EA", "n": 1, "d": 1},
        {"parent_no": "P1", "child_no": "C2", "parent_unit": "EA", "child_unit": "PC", "n": 2, "d": 1},
        {"parent_no": "P2", "child_no": "C1", "parent_unit": "SET", "child_unit": "EA", "n": 3, "d": 1},
        {"parent_no": "P2", "child_no": "C3", "parent_unit": "SET", "child_unit": "BOX", "n": 1, "d": 1},
        {"parent_no": "P3", "child_no": "P1", "parent_unit": "KIT", "child_unit": "EA", "n": 1, "d": 1},
        # 添加一个单位不一致的料号
        {"parent_no": "P4", "child_no": "C1", "parent_unit": "EA", "child_unit": "PCS", "n": 1, "d": 1}
    ]
    
    def run_example():
        """运行BOMChecker的完整示例"""
        print("=" * 60)
        print("BOMChecker 类使用示例")
        print("=" * 60)
        
        # 1. 创建BOMChecker实例
        print("\n1. 创建BOMChecker实例")
        checker = BOMChecker(
            parent_col="parent_no",
            child_col="child_no",
            parentunit_col="parent_unit",
            childunit_col="child_unit",
            numerator_col="n",
            denominator_col="d"
        )
        
        # 2. 执行BOM检查
        print("\n2. 执行BOM检查")
        result = checker.start_check(input_data=TEST_BOM_DATA)
        
        print(f"BOM检查结果: {'成功' if result['success'] else '失败'}")
        if result['success']:
            print(f"检查记录数: {result['statistics']['total_records']}")
            print(f"错误记录数: {result['statistics']['error_records']}")
            print(f"警告记录数: {result['statistics']['warning_records']}")
            print(f"正常记录数: {result['statistics']['clean_records']}")
        
        # 3. 检查单位一致性（自动执行）
        print("\n3. 单位检查结果")
        if checker.unit_result and checker.unit_result.get('exec_success'):
            summary = checker.unit_result['summary']
            print(f"料号总数: {summary['total_unique_materials']}")
            print(f"单位统一料号: {summary['unified_materials_count']}")
            print(f"单位问题料号: {summary['problematic_materials_count']}")
            print(f"通过率: {summary['pass_rate_percent']}%")
        
        # 4. 生成Markdown报告
        print("\n4. 生成Markdown报告")
        markdown_result = checker.output_results_as_markdown()
        print("Markdown报告生成成功")
        print(f"报告长度: {len(markdown_result['combined_result'])} 字符")
        print("\n报告预览:")
        print(markdown_result['combined_result'].split('\n')[:20])
        
        # 5. 导出到Excel（内存中）
        print("\n5. 导出到Excel")
        excel_result = checker.export_results_as_excel()
        if isinstance(excel_result, BytesIO):
            print(f"Excel导出成功，文件大小: {excel_result.getbuffer().nbytes} 字节")
        else:
            print(f"Excel导出失败: {excel_result.get('message', '未知错误')}")
        
        # 6. 外部数据访问示例
        print("\n6. 外部数据访问示例")
        print("- 从checker.bom_result获取marked_data:")
        if checker.bom_result and checker.bom_result.get('success'):
            marked_data = checker.bom_result['marked_data']
            print(f"  记录数: {len(marked_data)}")
            print(f"  前2条记录示例: {json.dumps(marked_data[:2], ensure_ascii=False)}")
        
        print("\n- 从checker.unit_result获取material_units_map_list:")
        if checker.unit_result and checker.unit_result.get('exec_success'):
            material_units = checker.unit_result['material_units_map_list']
            print(f"  料号数: {len(material_units)}")
            print(f"  料号单位映射: {json.dumps(material_units, ensure_ascii=False)}")
        
        # 7. 测试不同输入格式（JSON字符串）
        print("\n7. 测试JSON字符串输入")
        json_input = json.dumps(TEST_BOM_DATA)
        json_checker = BOMChecker(
            parent_col="parent_no",
            child_col="child_no",
            parentunit_col="parent_unit",
            childunit_col="child_unit",
            numerator_col="n",
            denominator_col="d"
        )
        json_result = json_checker.start_check(input_data=json_input)
        print(f"JSON输入检查结果: {'成功' if json_result['success'] else '失败'}")
        
        print("\n" + "=" * 60)
        print("示例运行完成！")
        print("=" * 60)
    
    # 运行示例
    run_example()


def run_example_from_erp():
    """运行BOMChecker的完整示例"""
    from apps.data_opt.components.yonyou_tplus import TplusConnection, TplusConfig
    from apps.data_opt.components.hap import HapConnection, get_maindata_worksheetinfo, WorksheetProperty


    hap_conn = HapConnection(
        app_key='601ae007d84ca95a',
        sign='ODVlMzNjYzA1ZTg1Yzg3YjI0NmQ5NTFmZGQ3OTk1MWYzMjE4M2JiMzYyNDEzMGU3NTY5YzI0YzEzYTYyYTExZA=='
    )

    hap_conn.regist_worksheet(get_maindata_worksheetinfo())

    hap_conn.regist_worksheet(
            [
                WorksheetProperty(worksheet_id='bom_check_summary'),
                WorksheetProperty(worksheet_id='transit_bom_structure'),
                WorksheetProperty(worksheet_id='material_units_map'),
            ]
        )

    # 创建TplusConnection实例并调用auth方法
    tp = TplusConnection()

    bom = tp.pull_from_source(source_name='bom')

    from apps.data_opt.utils import bomchecker

    checker = bomchecker.BOMChecker(
        mainfield_mapper={
            "pn": "productno",# 与 class TplusMatWcBom(AcceptMatWcBom) 输出保持一致
            "cn": "materialno",
            "pu": 'pu',
            "cu": "cu",
            "n": "qty",
            "d": "denominator"
        },
        dtofield_mapper={
            "productno": "productno",
            "materialno": "materialno",
            "scrap": "scrap",
            "qty": "qty",
            "matver": "matver",
        },
    )

    checker.start_check(bom)

    checker.output_results_to_hap(hap_conn)