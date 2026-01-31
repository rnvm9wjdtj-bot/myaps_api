import pandas as pd, json, os#, warnings
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any, DefaultDict
from collections import defaultdict

from fastapi.responses import StreamingResponse


HAP_CTRLID = {
    'product_no': 'pn',
    'product_version': 'pv',
    'sort_no': 'sn',
    'item_no': 'in',
    'workcenter': 'wc',
    'dto': 'dto'
}


class RouteChecker:
    def __init__(
        self,
        mainfield_mapper: dict={},
        dtofield_mapper: dict={},
        product_col: str = HAP_CTRLID['product_no'],
        productversion_col: str = HAP_CTRLID['product_version'],
        sortno_col: str = HAP_CTRLID['sort_no'],
        itemno_col: str = HAP_CTRLID['item_no'],
        workcenter_col: str = HAP_CTRLID['workcenter']
    ):
        """
        初始化工艺路线校验器
        :param mainfield_mapper: 主字段映射，将外部字段映射到内部字段
        :param dtofield_mapper: DTO字段映射，将DTO字段映射到内部字段
        :param product_col: 映射后的产品号列名
        :param productversion_col: 映射后的产品版本列名
        :param sortno_col: 映射后的顺序号列名
        :param itemno_col: 映射后的工序项列名
        :param workcenter_col: 映射后的工作中心列名
        """
        self.HAP_CTRLID = HAP_CTRLID
        self.route_result = None  # 存储工艺路线检查结果
        # 初始化映射和列名
        self.mainfield_mapper = mainfield_mapper
        self.dtofield_mapper = dtofield_mapper
        self.product_col = product_col
        self.productversion_col = productversion_col
        self.sortno_col = sortno_col
        self.itemno_col = itemno_col
        self.workcenter_col = workcenter_col
    
    def _process_json_route_data(
            self, 
            json_data: str | List[Dict[str, Any]]
        ) -> pd.DataFrame:
        """
        处理JSON格式的工艺路线数据，转换为适合校验的结构
        """

        # 如果输入是字符串，先解析为JSON
        if isinstance(json_data, str):
            try:
                route_list = json.loads(json_data)
            except json.JSONDecodeError:
                # 如果已经是列表格式，直接使用
                route_list = eval(json_data)
        else:
            route_list = json_data

        # 从项目配置获取 ItemNo 前缀和宽度
        try:
            from project_files import project_client
            itemno_prefix = project_client.itemno_prefix
            itemno_width = project_client.itemno_width
        except:
            itemno_prefix = 'P'
            itemno_width = 2
            print(f"⚠️ 未配置 ItemNo 前缀和宽度，默认使用 {itemno_prefix} 作为前缀，宽度为 {itemno_width}")
        
        # 转换为DataFrame
        df_data = []
        for item in route_list:
            row = {mk: item.get(ok, '') for mk, ok in self.mainfield_mapper.items()}
            
            # 填充 ItemNo
            if not row.get(self.HAP_CTRLID['item_no']):
                sort_no = row[self.HAP_CTRLID['sort_no']]
                try:
                    # 先转换为整数，处理可能的异常
                    sort_no = int(sort_no)
                    row[self.HAP_CTRLID['item_no']] = f"{itemno_prefix}{sort_no:0{itemno_width}d}"
                except (ValueError, TypeError):
                    # 处理转换失败的情况，例如使用默认值或记录错误
                    # row[self.HAP_CTRLID['item_no']] = f"{itemno_prefix}{itemno_width * '0'}"  # 默认值
                    row[self.HAP_CTRLID['item_no']] = f"{itemno_prefix}{sort_no}"  # 默认值
            
            # 填充 Workcenter
            if not row.get(self.HAP_CTRLID['workcenter']):
                row[self.HAP_CTRLID['workcenter']] = ''

            row[self.HAP_CTRLID['dto']] = {mk: item.get(ok, '') for mk, ok in self.dtofield_mapper.items()} if self.dtofield_mapper else None
            df_data.append(row)

        df = pd.DataFrame(df_data)
        return df
    
    def _bytesio_to_dataframe(
            self, 
            bytesio_obj: BytesIO
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
        if self.mainfield_mapper:
            # 反转映射，将Excel列名映射到内部字段名
            reverse_mapper = {v: k for k, v in self.mainfield_mapper.items() if v}
            # 重命名列
            df = df.rename(columns=reverse_mapper)
        
        # 填充缺失的ItemNo
        if self.itemno_col in df.columns:
            # 从项目配置获取 ItemNo 前缀和宽度
            try:
                from project_files import project_client
                itemno_prefix = project_client.itemno_prefix
                itemno_width = project_client.itemno_width
            except:
                itemno_prefix = 'P'
                itemno_width = 2
                print(f"⚠️ 未配置 ItemNo 前缀和宽度，默认使用 {itemno_prefix} 作为前缀，宽度为 {itemno_width}")
            
            # 处理缺失的ItemNo
            if self.sortno_col in df.columns:
                for idx in df.index:
                    if pd.isna(df.at[idx, self.itemno_col]) or df.at[idx, self.itemno_col] == '':
                        sort_no = df.at[idx, self.sortno_col]
                        try:
                            sort_no = int(sort_no)
                            df.at[idx, self.itemno_col] = f"{itemno_prefix}{sort_no:0{itemno_width}d}"
                        except (ValueError, TypeError):
                            df.at[idx, self.itemno_col] = f"{itemno_prefix}{sort_no}"
        
        # 填充缺失的Workcenter
        if self.workcenter_col in df.columns:
            df[self.workcenter_col] = df[self.workcenter_col].fillna('')
        
        # 添加dto字段
        if self.dtofield_mapper:
            reverse_dto_mapper = {v: k for k, v in self.dtofield_mapper.items() if v}
            df[self.HAP_CTRLID['dto']] = df.apply(
                lambda row: {mk: row.get(ok, '') for ok, mk in reverse_dto_mapper.items()}, 
                axis=1
            )
        else:
            df[self.HAP_CTRLID['dto']] = None
        
        return df
    
    def _convert_input_to_dataframe(
            self, 
            input_data: Any
        ) -> pd.DataFrame:
        """
        智能判断输入类型并转换为DataFrame
        """
        try:
            if isinstance(input_data, pd.DataFrame):
                return input_data
            elif isinstance(input_data, BytesIO):
                return self._bytesio_to_dataframe(bytesio_obj=input_data)
            elif isinstance(input_data, (str, list)):
                return self._process_json_route_data(json_data=input_data)
            else:
                raise ValueError(f"不支持的输入类型: {type(input_data).__name__}")
        except Exception as e:
            raise ValueError(f"数据转换失败: {str(e)}")
    
    def start_check(
            self, 
            input_data: Any
        ) -> dict:
        """
        工艺路线综合检查函数
        """
        # 智能判断输入类型并转换为DataFrame
        try:
            route_df = self._convert_input_to_dataframe(
                input_data=input_data
            )
        except Exception as e:
            self.route_result = {
                'success': False,
                'message': f'工艺路线数据处理失败: {str(e)}',
                'issue_summary': {},
                'marked_data': []
            }
            return self.route_result
        
        if route_df.empty:
            self.route_result = {
                'success': False,
                'message': '工艺路线数据为空或格式错误',
                'issue_summary': {},
                'marked_data': []
            }
            return self.route_result
        
        try:
            # 执行工艺路线检查
            results = self._route_check(
                route_df=route_df,
                product_column=self.product_col,
                productversion_column=self.productversion_col,
                sortno_column=self.sortno_col,
                itemno_column=self.itemno_col
            )
            marked_data = results['marked_data']
            
            # 准备返回结果
            # 基础统计
            statistics = {
                'total_records': len(route_df),
                'error_records': len(marked_data[marked_data['E'] != '']),
                'warning_records': len(marked_data[marked_data['W'] != '']),
                'clean_records': len(marked_data[(marked_data['E'] == '') & (marked_data['W'] == '')])
            }
            
            # 按错误类型统计
            error_counts = {}
            for error_type in results['issue_summary']['ERROR']:
                error_counts[error_type] = len(results['issue_summary']['ERROR'][error_type])
            statistics['error_counts'] = error_counts
            
            # 按警告类型统计
            warning_counts = {}
            for warning_type in results['issue_summary']['WARNING']:
                warning_counts[warning_type] = len(results['issue_summary']['WARNING'][warning_type])
            statistics['warning_counts'] = warning_counts
            
            self.route_result = {
                'success': True,
                'message': f'工艺路线检查完成，共检查 {len(route_df)} 条记录',
                'issue_summary': results['issue_summary'],
                'marked_data': marked_data.to_dict('records'),
                'statistics': statistics
            }
            
            return self.route_result
        except Exception as e:
            self.route_result = {
                'success': False,
                'message': f'工艺路线检查过程中出错: {str(e)}',
                'issue_summary': {},
                'marked_data': []
            }
            return self.route_result
    
    def _route_check(
        self,
        route_df: pd.DataFrame,
        product_column: str,
        productversion_column: str,
        sortno_column: str,
        itemno_column: str,
    ):
        """
        工艺路线检查核心函数
        """
        marked_data = route_df.copy()
        marked_data['E'] = marked_data.apply(lambda _:[], axis=1)
        marked_data['W'] = marked_data.apply(lambda _:[], axis=1)

        # 初始化摘要
        issue_summary = {
            'ERROR': {
                'sortno_notint': [],
                'itemno_repeat': [],
                'missing_required_cols': [],
                'empty_product_no': [],
                'invalid_itemno_format': []
            },
            'WARNING': {
                'sortno_repeat': [],
                'workcenter_repeat': [],
                'empty_workcenter': [],
                'sortno_sequence_issue': []
            }
        }

        # 检查并添加必要列
        if productversion_column not in marked_data.columns:
            has_version_col = False
            marked_data[productversion_column] = ''
        else:
            has_version_col = True
        
        # 检查必要列是否存在
        required_cols = [product_column, sortno_column, itemno_column]
        missing_cols = [col for col in required_cols if col not in marked_data.columns]
        if missing_cols:
            for idx in marked_data.index:
                marked_data.at[idx, 'E'].append(f'缺少必要列: {missing_cols}')
            issue_summary['ERROR']['missing_required_cols'] = missing_cols
        else:
            # 执行详细检查
            # 使用 defaultdict 自动初始化新键的值
            product_item_map: DefaultDict[tuple, dict] = defaultdict(lambda: {
                'item_no': set[str](),
                'sort_no': set[int | str](),
                'workcenter': set[str](),
            })
            for idx, row in marked_data.iterrows():
                pn = row[product_column]
                pv = str(row[productversion_column])
                sn = row[sortno_column]
                itn = row[itemno_column]
                wc = row.get(self.workcenter_col, '')
                data_key = (pn, pv)
                # 直接获取产品项，defaultdict 会自动初始化不存在的键
                product_item = product_item_map[data_key]

                # 检查产品号是否为空
                if pd.isna(pn) or str(pn).strip() == '':
                    marked_data.at[idx, 'E'].append("产品号为空")
                    issue_summary['ERROR']['empty_product_no'].append(data_key)

                # 检查是否有重复的 ItemNo
                if itn in product_item['item_no']:
                    marked_data.at[idx, 'E'].append("工序项重复")
                    issue_summary['ERROR']['itemno_repeat'].append(data_key)
                else:
                    product_item['item_no'].add(itn)

                # 检查 Workcenter 是否正确
                if pd.isna(wc) or str(wc).strip() == '':
                    marked_data.at[idx, 'W'].append("工作中心为空")
                    issue_summary['WARNING']['empty_workcenter'].append(data_key)
                # 检查是否有重复的 Workcenter
                elif wc in product_item['workcenter']:
                    marked_data.at[idx, 'W'].append(f"工作中心重复")
                    issue_summary['WARNING']['workcenter_repeat'].append(data_key)
                else:
                    product_item['workcenter'].add(wc)

                # SortNo 必须是整数
                try:
                    sort_num = float(sn)
                    assert sort_num % 1 == 0, "顺序号必须是整数"
                except ValueError:
                    marked_data.at[idx, 'E'].append("顺序号非整数")
                    issue_summary['ERROR']['sortno_notint'].append(data_key)

                # 检查是否有重复的 SortNo
                if not pd.isna(sn) and str(sn).strip() != '' and sn in product_item['sort_no']:
                    marked_data.at[idx, 'W'].append(f"顺序号重复")
                    issue_summary['WARNING']['sortno_repeat'].append(data_key)
                else:
                    product_item['sort_no'].add(sn)
        
        for col in ['E', 'W']:
            marked_data[col] = marked_data[col].apply(lambda x: ', '.join(sorted(set(x))) if x else '')

        return {
            'marked_data': marked_data,
            'issue_summary': issue_summary,
        }
    
    def output_results_as_markdown(self) -> Dict[str, str]:
        """
        将工艺路线检查结果转换为Markdown格式
        """
        output = "# 📋 工艺路线检查综合报告\n\n"
        has_results = False
        
        # 添加工艺路线检查结果
        if self.route_result:
            has_results = True
            output += "### 结果汇总\n"
            if self.route_result.get('success'):
                stats = self.route_result.get('statistics', {})
                output += f"- 检查完成: {stats.get('total_records', 0)}\n"
                output += f"- 错误记录: {stats.get('error_records', 0)}\n"
                output += f"- 警告记录: {stats.get('warning_records', 0)}\n"
                output += f"- 正常记录: {stats.get('clean_records', 0)}\n"
                
                output += "\n##### 错误类型统计\n"
                error_counts = stats.get('error_counts', {})
                for error_type, count in error_counts.items():
                    output += f"- {error_type}: {count}\n"
                
                output += "\n##### 警告类型统计\n"
                warning_counts = stats.get('warning_counts', {})
                for warning_type, count in warning_counts.items():
                    output += f"- {warning_type}: {count}\n"
            else:
                output += f"- ❌ 检查失败: {self.route_result.get('message', '未知错误')}\n"
            output += "\n"
        
        if not has_results:
            output += "❌ 无检查结果可显示\n"
        
        result = {'combined_result': output}
        
        result['check_timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return result
    
    def export_results_as_excel(self, output_file=None) -> Any:
        """
        导出工艺路线检查结果到Excel文件或BytesIO对象
        
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
            has_route = self.route_result is not None and 'success' in self.route_result
            
            if not has_route:
                return {'success': False, 'message': '无检查结果可导出'}
            
            # 导出到Excel
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # 导出工艺路线检查结果
                if has_route:
                    # 工艺路线检查结果导出
                    if not self.route_result.get('success'):
                        return {'success': False, 'message': '无法导出，工艺路线检查未成功'}
                    
                    marked_data = self.route_result.get('marked_data', [])
                    if not marked_data:
                        return {'success': False, 'message': '无工艺路线检查数据可导出'}
                    
                    # 主数据表
                    df = pd.DataFrame(marked_data)
                    df.to_excel(writer, sheet_name='工艺路线检查详情', index=False)
                    
                    # 问题汇总表
                    summary_data = []
                    issue_summary = self.route_result.get('issue_summary', {})
                    
                    # 错误问题
                    for issue_type, issues in issue_summary.get('ERROR', {}).items():
                        if issues:
                            for issue in issues:
                                summary_data.append({'问题类型': '错误', '具体问题': issue_type, '详情': str(issue)})
                    
                    # 警告问题
                    for issue_type, issues in issue_summary.get('WARNING', {}).items():
                        if issues:
                            for issue in issues:
                                summary_data.append({'问题类型': '警告', '具体问题': issue_type, '详情': str(issue)})
                    
                    if summary_data:
                        summary_df = pd.DataFrame(summary_data)
                        summary_df.to_excel(writer, sheet_name='工艺路线问题汇总', index=False)
            
            if use_bytesio:
                output_file.seek(0)
                # summary_markdown = self.output_results_as_markdown()
                # ts = summary_markdown.get("check_timestamp", datetime.now().strftime("%Y%m%d%H%M%S")).replace(":", "").replace(" ", "").replace("-", "")
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                return StreamingResponse(
                    output_file,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f"attachment; filename=route_check_results_{ts}.xlsx"
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


if __name__ == '__main__':
    # 测试数据 - 包含各种错误和警告情况
    comprehensive_test_data = [
        {"productno": "A123", "productversion": "V1", "sortno": 1, "itemno": "A001", "workcenter": "WC001"},  # 正常记录
        {"productno": "A123", "productversion": "V1", "sortno": "a", "itemno": "A002", "workcenter": "WC002"},  # 顺序号非整数
        {"productno": "A123", "productversion": "V1", "sortno": "a", "itemno": "A002", "workcenter": "WC003"},  # 工序项重复
        {"productno": "A123", "productversion": "V1", "sortno": 2, "itemno": "A003", "workcenter": "WC001"},  # 工作中心重复
        {"productno": "A123", "productversion": "V1", "sortno": 2, "itemno": "A004", "workcenter": "WC004"},  # 顺序号重复
        {"productno": "", "productversion": "V1", "sortno": 3, "itemno": "A005", "workcenter": "WC005"},  # 产品号为空
        {"productno": "B456", "productversion": "V2", "sortno": -1, "itemno": "B001", "workcenter": "WC006"},  # 顺序号为负数
        {"productno": "B456", "productversion": "V2", "sortno": 4, "itemno": "B002", "workcenter": ""},  # 工作中心为空
        {"productno": "B456", "productversion": "V2", "sortno": 5, "itemno": "123", "workcenter": "WC007"},  # 工序项格式错误
    ]
    
    # 测试映射
    mainfield_mapper = {
        HAP_CTRLID['product_no']: 'productno',
        HAP_CTRLID['product_version']: 'productversion',
        HAP_CTRLID['sort_no']: 'sortno',
        HAP_CTRLID['item_no']: 'itemno',
        HAP_CTRLID['workcenter']: 'workcenter',
    }
    dtofield_mapper = {
        'materialno': 'productno',
        'matver': 'productversion',
    }
    
    print("=== 测试1: JSON字符串输入 ===")
    test_json = json.dumps(comprehensive_test_data)
    checker = RouteChecker(mainfield_mapper=mainfield_mapper, dtofield_mapper=dtofield_mapper)
    result = checker.start_check(test_json)
    print(f"成功: {result['success']}")
    print(f"消息: {result['message']}")
    print(f"统计信息: {result['statistics']}")
    print()
    
    print("=== 测试2: 列表输入 ===")
    checker2 = RouteChecker(mainfield_mapper=mainfield_mapper, dtofield_mapper=dtofield_mapper)
    result2 = checker2.start_check(comprehensive_test_data)
    print(f"成功: {result2['success']}")
    print(f"消息: {result2['message']}")
    print(f"统计信息: {result2['statistics']}")
    print()
    
    print("=== 测试3: DataFrame输入 ===")
    import pandas as pd
    df_test = pd.DataFrame(comprehensive_test_data)
    # 应用字段映射
    df_test_renamed = df_test.rename(columns={v: k for k, v in mainfield_mapper.items()})
    checker3 = RouteChecker()
    result3 = checker3.start_check(df_test_renamed)
    print(f"成功: {result3['success']}")
    print(f"消息: {result3['message']}")
    print(f"统计信息: {result3['statistics']}")
    print()
    
    print("=== 测试4: 问题详情检查 ===")
    print("错误类型统计:")
    for error_type, count in result['statistics']['error_counts'].items():
        print(f"  {error_type}: {count} 条")
    print("\n警告类型统计:")
    for warning_type, count in result['statistics']['warning_counts'].items():
        print(f"  {warning_type}: {count} 条")
    print()
    
    print("=== 测试5: 完整结果输出 ===")
    print("标记后的数据:")
    for i, record in enumerate(result['marked_data']):
        print(f"  记录 {i+1}:")
        print(f"    产品号: {record.get('pn', '')}")
        print(f"    顺序号: {record.get('sn', '')}")
        print(f"    工序项: {record.get('in', '')}")
        print(f"    工作中心: {record.get('wc', '')}")
        print(f"    错误: {record.get('E', '')}")
        print(f"    警告: {record.get('W', '')}")
    print()
    
    print("=== 测试完成 ===")
    
    print("\n=== 测试6: Excel导出功能测试 ===")
    # 创建一个临时文件路径用于测试导出
    import tempfile
    import os
    
    # 先运行检查获取结果
    checker = RouteChecker(mainfield_mapper=mainfield_mapper, dtofield_mapper=dtofield_mapper)
    result = checker.start_check(comprehensive_test_data)
    
    # 测试导出到临时文件
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
        temp_file_path = temp_file.name
    
    export_result = checker.export_results_as_excel(output_file=temp_file_path)
    print(f"导出结果: {export_result}")
    
    # 验证文件是否存在
    if os.path.exists(temp_file_path):
        print(f"✅ Excel文件导出成功，文件路径: {temp_file_path}")
        # 获取文件大小
        file_size = os.path.getsize(temp_file_path)
        print(f"   文件大小: {file_size} 字节")
        # 删除临时文件
        os.unlink(temp_file_path)
        print("   临时文件已删除")
    else:
        print("❌ Excel文件导出失败，文件不存在")
    
    print("\n=== Excel导出功能测试完成 ===")
