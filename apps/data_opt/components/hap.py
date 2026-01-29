"""明道云 API v3 封装为 ORM """

import os, re, json
from typing import List, Dict, Any, Optional, Union, Literal, Generator, NamedTuple
from datetime import datetime
from tortoise.models import Model as DbModel
from pydantic import BaseModel as PydanticModel
from decimal import Decimal

# from globalobjects import file_timed_logger
from ..utils.data_processor import DataProcessor
from ._base import get_session, filelog_normal, filelog_error, console_log


# file_logger = file_timed_logger.setup_logging(__name__)

# 调用刷新函数时，距离上次刷新超过这个秒数，才会刷新行数据，否则直接返回缓存数据
REFRESH_INTERVAL_SECONDS = 5

# 自定义JSON编码器，用于处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)



class WorksheetInfo(NamedTuple):
    worksheet_id: str
    display_name: Optional[str] = None
    db_model: Optional[DbModel] = None
    conflict_fields: Optional[List[str]] = None
    related_sheets: Optional[Dict[str, str]] = None  # 关联表字段名 -> 关联表ID


# 工具类，包含通用方法
class HapUtils:
    """
    明道云工具类，包含通用方法
    """
    
    @staticmethod
    def convert_data_to_fieldslist(data: Dict[str, Any] | PydanticModel, exclude_none: bool = True, ignore_fields=[], field_map={}, remain_irrelevant_fields=True) -> List[Dict[str, Any]]:
        """
        将单个数据字典转换为工作表API字段值list
        
        Args:
            data: 行数据字典或 PydanticModel
            exclude_none: 是否排除值为None的字段
            ignore_fields: 忽略的字段列表
            field_map: 字段名称映射规则，将row_data_dict中的字段名称（键）映射为目标工作表control_id
            remain_irrelevant_fields: 是否保留 field_map 未提及的字段
            
        Returns:
            List[Dict[str, Any]]: 字段值列表
        """
        
        if isinstance(data, PydanticModel):
            data = data.model_dump(exclude_unset=True, exclude_none=exclude_none)
        else:
            if exclude_none:
                data = {k: v for k, v in data.items() if v is not None}
            else:
                data = data
        
        fieldlist = []
        for k, v in data.items():
            if k in ignore_fields: 
                continue
            try:
                control_id = field_map[k]
            except:
                if remain_irrelevant_fields:
                    control_id = k
                else:
                    continue

            v_type = type(v)
            if v_type in (dict, list):
                fieldlist.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False, cls=DecimalEncoder)})
            elif v_type in (int, float, Decimal):
                fieldlist.append({'id': control_id, 'value': float(v), 'type': 2})
            elif v_type == str:
                fieldlist.append({'id': control_id, 'value': v, 'type': 2})
            else:
                # 处理枚举类型
                if hasattr(v, 'value'):
                    fieldlist.append({'id': control_id, 'value': v.value, 'type': 2})
                else:
                    # 其他类型，尝试转换为字符串
                    fieldlist.append({'id': control_id, 'value': str(v), 'type': 2})
        
        return fieldlist
    

    @staticmethod
    def expression_to_filter_condition(expression: str) -> dict:
        """
        将逻辑表达式字符串转换为筛选条件JSON结构
        
        参数:
            expression: 逻辑表达式字符串，格式如 "(age__gt=18 && status__in=[\"active\",\"pending\"]) || name__isempty"
            
        返回:
            符合明道云API要求的筛选条件JSON结构
        
        支持的运算符及示例值:
            - eq: 等于, 示例: name__eq="张三"
            - ne: 不等于, 示例: status__ne="inactive"
            - gt: 大于, 示例: age__gt=18
            - ge: 大于等于, 示例: score__ge=60
            - lt: 小于, 示例: price__lt=100
            - le: 小于等于, 示例: count__le=10
            - isempty: 为空, 示例: description__isempty
            - isnotempty: 非空, 示例: email__isnotempty
            - in: 是其中一个, 示例: status__in=["active","pending"]
            - notin: 不是任意一个, 示例: role__notin=["admin","manager"]
            - contains: 包含, 示例: tags__contains="important"
            - notcontains: 不包含, 示例: notes__notcontains="deprecated"
            - concurrent: 同时包含, 示例: skills__concurrent=["python","javascript"]
            - belongsto: 属于, 示例: department__belongsto=["sales"]
            - notbelongsto: 不属于, 示例: team__notbelongsto=["engineering"]
            - startswith: 开头是, 示例: name__startswith="张"
            - notstartswith: 开头不是, 示例: name__notstartswith="李"
            - endswith: 结尾是, 示例: domain__endswith="com"
            - notendswith: 结尾不是, 示例: file__notendswith="txt"
            - between: 在范围内, 示例: date__between=["2025-01-01","2025-01-31"]
            - notbetween: 不在范围内, 示例: age__notbetween=["0","18"]
        """
        # 去除空白字符
        expression = ''.join(expression.split())
        
        def parse(expression):
            # 辅助函数：解析表达式
            
            # 处理括号嵌套
            def find_matching_bracket(expr, start):
                # 找到匹配的右括号索引
                count = 1
                for i in range(start + 1, len(expr)):
                    if expr[i] == '(':
                        count += 1
                    elif expr[i] == ')':
                        count -= 1
                        if count == 0:
                            return i
                return -1
            
            # 如果表达式被括号包围，先解析括号内的内容
            if expression.startswith('(') and find_matching_bracket(expression, 0) == len(expression) - 1:
                return parse(expression[1:-1])
            
            # 查找最高级别的逻辑运算符（先||，后&&）
            bracket_level = 0
            or_pos = -1
            and_pos = -1
            
            for i, char in enumerate(expression):
                if char == '(':
                    bracket_level += 1
                elif char == ')':
                    bracket_level -= 1
                elif bracket_level == 0:
                    if char == '|' and i + 1 < len(expression) and expression[i + 1] == '|':
                        or_pos = i
                        break
                    elif char == '&' and i + 1 < len(expression) and expression[i + 1] == '&':
                        and_pos = i
            
            # 如果找到OR运算符
            if or_pos != -1:
                left = parse(expression[:or_pos])
                right = parse(expression[or_pos + 2:])
                return {
                    "type": "group",
                    "logic": "OR",
                    "children": [left, right]
                }
            
            # 如果找到AND运算符
            elif and_pos != -1:
                left = parse(expression[:and_pos])
                right = parse(expression[and_pos + 2:])
                return {
                    "type": "group",
                    "logic": "AND",
                    "children": [left, right]
                }
            
            # 否则，这是一个条件表达式
            else:
                # 处理 isempty 和 isnotempty 不带等号的情况
                if '__isempty' in expression:
                    field = expression.replace('__isempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isempty",
                        "value": []
                    }
                elif '__isnotempty' in expression:
                    field = expression.replace('__isnotempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isnotempty",
                        "value": []
                    }
                # 处理带等号的情况
                elif '=' in expression:
                    # 分割字段名（包含运算符）和值
                    field_op, value = expression.split('=', 1)
                    
                    # 分割字段名和运算符
                    if '__' in field_op:
                        field, op = field_op.split('__', 1)
                        operator = op
                    else:
                        return {}
                    
                    # 处理需要数组值的运算符
                    array_operators = ['in', 'notin', 'contains', 'notcontains', 'concurrent', 'belongsto', 'notbelongsto', 'between', 'notbetween']
                    
                    if operator in array_operators:
                        # 解析数组格式的值
                        if value.startswith('[') and value.endswith(']'):
                            import json
                            try:
                                array_value = json.loads(value)
                                if isinstance(array_value, list):
                                    return {
                                        "type": "condition",
                                        "field": field.strip(),
                                        "operator": operator,
                                        "value": array_value
                                    }
                            except:
                                pass
                    
                    # 处理普通运算符，去除字符串值的双引号
                    if operator not in array_operators:
                        # 移除字符串值的双引号
                        stripped_value = value.strip()
                        if stripped_value.startswith('"') and stripped_value.endswith('"'):
                            stripped_value = stripped_value[1:-1]
                        return {
                            "type": "condition",
                            "field": field.strip(),
                            "operator": operator,
                        "value": stripped_value
                    }
                return {}
        
        return parse(expression)
    

    @staticmethod
    def str_to_sort_list(sorts: str) -> list:
        """
        将排序字符串转换为排序列表
        
        Args:
            sorts: 排序字符串，格式如 "-x,y"（负号表示降序，正号或无符号表示升序）
            
        Returns:
            list: 排序列表，格式如 [{"field":"x","isAsc":False},{"field":"y","isAsc":True}]
        """
        if not sorts:
            return []
        sort_fields = sorts.split(',')
        sort_list = []
        for field_str in sort_fields:
            field_str = field_str.strip()
            if not field_str:
                continue
            
            # 检查是否以负号开头
            if field_str.startswith('-'):
                field = field_str[1:].strip()
                is_asc = False
            else:
                # 移除可能的正号
                field = field_str.lstrip('+').strip()
                is_asc = True
            
            if field:
                sort_list.append({"field": field, "isAsc": is_asc})
        return sort_list
    

    @staticmethod
    def exclude_sys_fields(data: dict) -> dict:
        """
        排除系统字段
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 排除系统字段后的数据字典
        """
        filtered_data = {}
        for k, v in data.items():
            if not k.startswith('_'):
                filtered_data[k] = v
        return filtered_data
    

    @staticmethod
    def exclude_unamed_fields(data: dict) -> dict:
        """
        排除未命名字段（UUID格式的字段）
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 排除未命名字段后的数据字典
        """
        # 匹配18-24个十六进制字符的正则表达式（不区分大小写）
        uuid_pattern = r'^[0-9a-f]{18,24}$'
        filtered_data = {}
        for k, v in data.items():
            # 检查键名是否匹配UUID格式
            if not re.match(uuid_pattern, k.lower()):
                filtered_data[k] = v
        return filtered_data
    
    @staticmethod
    def process_choice_fields(data: dict) -> dict:
        """
        处理选项字段，将选项字段（list of dict with key and value）转换为逗号分隔的字符串
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 处理后的数据字典
        """
        processed_data = {}
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'key' in v[0] and 'value' in v[0]:
                # 选项字段，提取 value 并用逗号连接
                picked_options = [item['value'] for item in v]
                processed_data[k] = ','.join(picked_options)
            else:
                processed_data[k] = v
        return processed_data



HAP_BASEURL_EXAMPLE = ('https://api.mingdao.com', 'http://127.0.0.1:8080/api')



def get_maindata_worksheetinfo() -> dict:
    """获取MYAPS主数据对应的工作表基本信息
    
    Args:
        worksheet_id: 工作表ID或名称
        
    Returns:
        dict: 工作表配置
    """
    from apps.io_api.utils.db_operation import process_model_or_tablename
    from globalobjects.db_manager import DbManager


    # {"HAP表名": { "在表中作为字段时的名称": "表名称"}}
    worksheet_relations = {
        't_material': {'mat_wc_bom_relation': 't_mat_wc_bom' , 'mat_wc_relation': 't_mat_wc', 'mat_ver_relation': 't_mat_ver'},
        't_workcenter': None,
        't_mat_ver': {'material_relation': 't_material'},
        't_mat_wc': {'material_relation': 't_material', 'workcenter_relation': 't_workcenter', 'mat_ver_relation': 't_mat_ver'},
        't_mat_wc_bom': None,
        't_mold': None,
        't_mat_wc_mold': None
    }

    maindata_worksheetinfo: List[WorksheetInfo] = []

    for mdl_name, relation_dict in worksheet_relations.items():
        
        mdl, table_name = process_model_or_tablename(mdl_name)
        maindata_worksheetinfo.append(WorksheetInfo(
            worksheet_id=mdl_name,
            db_model=mdl,
            conflict_fields=DbManager._get_conflict_fields(mdl),
            related_sheets=relation_dict
        ))
    
    return maindata_worksheetinfo



class HapConnection:
    allowed_worksheets: Dict[str, WorksheetInfo] = {}

    def __init__(self, app_key: str, sign: str, base_url: str=HAP_BASEURL_EXAMPLE[0], max_workers: int=os.cpu_count() * 3):
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
        self.max_workers = max_workers
        self.headers = {
            'HAP-Appkey': app_key,
            'HAP-Sign': sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        
        # 根据 max_workers 动态调整 session 参数，确保至少 20 个连接
        session_pool_size = max(self.max_workers, 20)
        # 初始化Session并配置性能参数
        self.session = get_session(
            retries=3,
            allowed_methods=["GET", "POST", "PATCH", "DELETE"],
            pool_connections=session_pool_size,  # 根据并发度动态调整连接池数量
            pool_maxsize=session_pool_size,     # 根据并发度动态调整最大连接数  
            connect_timeout=5.0,  # 增加连接超时时间
            read_timeout=60.0,    # 增加读取超时时间
        )


    def _post(self, endpoint: str, payload: dict):
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def _get(self, endpoint: str, params: dict=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()


    def _patch(self, endpoint: str, payload: dict):
        url = f"{self.base_url}{endpoint}"
        response = self.session.patch(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def _delete(self, endpoint: str, payload: dict=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.delete(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def worksheet(self, worksheet_id: str) -> 'HapWorksheet':
        """获取工作表对象
        
        Args:
            worksheet_id: 工作表ID或名称
            
        Returns:
            HapWorksheet: 工作表对象
        """
        assert worksheet_id in self.allowed_worksheets, f"Worksheet {worksheet_id} is not registered."
        return HapWorksheet(worksheet_id=worksheet_id, hap_conn=self)


    @classmethod
    def regist_worksheet(cls, worksheet_info: WorksheetInfo | List[WorksheetInfo]):
        """注册工作表
        """
        if isinstance(worksheet_info, WorksheetInfo):
            worksheet_info = [worksheet_info]
        
        for ws_info in worksheet_info:
            cls.allowed_worksheets[ws_info.worksheet_id] = ws_info



class HapWorksheet:
    """工作表类，代表一个明道云工作表"""
    def __init__(self, worksheet_id: str, hap_conn: HapConnection):
        self.worksheet_id = worksheet_id
        try:
            self.conflict_fields = hap_conn.allowed_worksheets[worksheet_id].conflict_fields
        except KeyError:
            self.conflict_fields = None
        self.hap_conn = hap_conn
        

    def rows(self, filter_expression: Optional[str] = None, sort_str: Optional[str] = None, relation_origin_row: Optional['HapWorksheetRow'] = None, relation_field_name: Optional[str] = None) -> 'HapRowsQuery':
        """获取行查询对象
        
        Args:
            filter_expression: 过滤条件表达式，如 "name='test' && age>18"
            sort_str: 排序字符串，如 "name,-age"
            
        Returns:
            HapRowsQuery: 行查询对象，支持链式调用
        """
        return HapRowsQuery(worksheet=self, hap_conn=self.hap_conn, filter_expression=filter_expression, sort_str=sort_str, relation_origin_row=relation_origin_row, relation_field_name=relation_field_name)
        

    def row(self, row_id: str, exclude_unamed_fields: bool = True, exclude_sys_fields: bool = True) -> 'HapWorksheetRow':
        """通过行ID获取单行对象
        
        Args:
            row_id: 行ID
            exclude_unamed_fields: 是否排除未命名字段
            exclude_sys_fields: 是否排除系统字段
            
        Returns:
            HapWorksheetRow: 行对象
        """
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/{row_id}?includeSystemFields=false"
        response = self.hap_conn._get(endpoint=endpoint)
        row_dict = {}
        if response['success']:
            data = response['data']
            # 使用 HapUtils.process_choice_fields 处理选项字段
            row_dict = HapUtils.process_choice_fields(data)

            if exclude_unamed_fields:
                row_dict = HapUtils.exclude_unamed_fields(row_dict)
            if exclude_sys_fields:
                row_dict = HapUtils.exclude_sys_fields(row_dict)
        
        return HapWorksheetRow(
            row_data=row_dict, 
            row_id=row_id, 
            worksheet=self, 
            hap_conn=self.hap_conn
        )


    def create_rows(self, data_list: List[Dict[str, Any] | PydanticModel], trigger_workflow: bool = True, refresh_immediately: bool = False) -> 'HapWorksheetRowSet':
        """创建新行
        
        Args:
            data_list: 行数据字典或 PydanticModel 列表
            trigger_workflow: 是否触发工作流
            refresh_immediately: 是否立即刷新数据，默认False
            
        Returns:
            HapWorksheetRowSet: 新创建的行对象集合
        """
        # 处理 PydanticModel
        processed_data_list = []
        for data in data_list:
            if isinstance(data, PydanticModel):
                processed_data_list.append(data.model_dump())
            else:
                processed_data_list.append(data)
        
        # 分批处理，每批最多100条
        batch_size = 100
        total_rows = len(processed_data_list)
        all_row_ids = []
        all_rows = []
        
        import concurrent.futures
        
        # 定义批次创建函数
        def create_batch(batch_start, batch_end):
            batch_data = processed_data_list[batch_start:batch_end]
            
            # 构建创建请求
            endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/batch"
            # 转换数据为API要求的格式
            rows_data = []
            for data_dict in batch_data:
                row_fields = HapUtils.convert_data_to_fieldslist(data_dict)
                rows_data.append({'fields': row_fields})
            payload = {
                "rows": rows_data,  
                "triggerWorkflow": trigger_workflow
            }
            response = self.hap_conn._post(endpoint, payload)
            
            # 获取当前批次的row_ids
            batch_row_ids = response.get('data', {}).get('rowIds', [])
            
            # 创建当前批次的行对象
            batch_rows = []
            for j, row_id in enumerate(batch_row_ids):
                if batch_start + j < total_rows:
                    row = HapWorksheetRow(
                        row_data=processed_data_list[batch_start + j], 
                        row_id=row_id, 
                        worksheet=self, 
                        hap_conn=self.hap_conn
                    )
                    batch_rows.append(row)
            
            return batch_row_ids, batch_rows
        
        # 使用线程池并发执行批次创建
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = []
            for i in range(0, total_rows, batch_size):
                batch_start = i
                batch_end = i + batch_size
                futures.append(executor.submit(create_batch, batch_start, batch_end))
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                batch_row_ids, batch_rows = future.result()
                all_row_ids.extend(batch_row_ids)
                all_rows.extend(batch_rows)
        
        worksheet_rowset = HapWorksheetRowSet(rows=all_rows, worksheet=self, hap_conn=self.hap_conn)
        if refresh_immediately:
            worksheet_rowset.refresh_all()
        return worksheet_rowset
    

    def delete_rows(self, rows: List['HapWorksheetRow'] | 'HapWorksheetRowSet' | List[str], trigger_workflow: bool = True, permanent: bool = False) -> List[bool]:
        """删除指定行
        
        Args:
            rows: 要删除的行对象列表或行ID列表
            trigger_workflow: 是否触发工作流
            permanent: 是否永久删除，默认False（软删除）
            
        Returns:
            List[bool]: 删除结果列表，每个元素表示对应行的删除是否成功
        """
        # 处理输入参数，获取所有行ID
        if isinstance(rows, HapWorksheetRowSet):
            row_ids = rows.row_ids
        else:
            row_ids = [row.row_id if isinstance(row, HapWorksheetRow) else row for row in rows]
        
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/batch"
        
        # 初始化结果列表，默认所有行删除失败
        results = [False] * len(row_ids)
        
        # 分批处理，每批最多100条
        batch_size = 100
        total_rows = len(row_ids)
        
        import concurrent.futures
        
        # 定义批次删除函数
        def delete_batch(batch_start, batch_end):
            batch_row_ids = row_ids[batch_start:batch_end]
            
            # 发送API请求
            response = self.hap_conn._delete(
                endpoint=endpoint,
                payload={
                    "rowIds": batch_row_ids,
                    "triggerWorkflow": trigger_workflow,
                    "permanent": permanent
                }
            )

            # 检查批次删除是否成功
            if response.get('success'):
                # 由于 HAP 返回的 data 为空没有详细结果，标记该批次所有行为删除成功
                for j in range(batch_start, min(batch_end, total_rows)):
                    results[j] = True
        
        # 使用线程池并发执行批次删除
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = []
            for i in range(0, total_rows, batch_size):
                batch_start = i
                batch_end = i + batch_size
                futures.append(executor.submit(delete_batch, batch_start, batch_end))
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                future.result()  # 抛出可能的异常

        # 刷新数据
        self.refresh_all()
        
        return results


    def upsert(self, data_list: List[Dict[str, Any] | PydanticModel], exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> 'HapWorksheetRowSet':
        """批量 upsert 操作
        
        Args:
            data_list: 行数据字典或 PydanticModel 列表
            exclude_none: 是否排除 data_list None 值字段
            trigger_workflow: 是否触发工作流
            when_value_equal_then: 当字段值相等时的处理方式，默认'jumpover' 跳过 以减少不必要的【工作表事件】，'update' 则无论字段是否与data一样都更新
            
        Returns:
            HapWorksheetRowSet: 处理后的行对象集合
        """
        result_rows = []
        create_list = []  # 存储需要创建的数据
        
        # 检查是否有冲突字段
        has_conflict_fields = bool(self.conflict_fields)
        
        # 如果没有冲突字段，直接批量创建
        if not has_conflict_fields:
            created_rows = self.create_rows(data_list, trigger_workflow=trigger_workflow)
            return HapWorksheetRowSet(rows=created_rows.all(), worksheet=self, hap_conn=self.hap_conn)
        
        import concurrent.futures
        
        # 处理数据列表，转换为字典格式
        processed_data_list = []
        for data in data_list:
            if isinstance(data, PydanticModel):
                processed_data_list.append(data.model_dump(exclude_none=exclude_none))
            else:
                processed_data_list.append(data.copy())
        
        # 定义查询和更新函数
        def process_item(data_dict):
            # 构建查询条件
            filter_conditions = []
            for field in self.conflict_fields:
                if field in data_dict:
                    value = data_dict[field]
                    filter_conditions.append(f'{field}__eq=\"{value}\"')

            # 如果没有有效的冲突字段值，返回需要创建
            if not filter_conditions:
                return (None, data_dict)
            
            # 执行查询
            filter_expression = " && ".join(filter_conditions)
            existing_rows = self.rows(filter_expression=filter_expression).all()
            rows_count = existing_rows.count()
            
            if rows_count == 1:
                # 若有且仅有1条则执行更新
                existing_row = existing_rows.first()
                updated_row = existing_row.update(data_dict, exclude_none=exclude_none, trigger_workflow=trigger_workflow, when_value_equal_then=when_value_equal_then)
                return (updated_row, None)
            if rows_count > 1:
                # 存在多条，则先删除所有匹配行
                existing_rows.delete_all(trigger_workflow=trigger_workflow)
            return (None, data_dict)
        
        # 使用线程池并发处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = [executor.submit(process_item, data_dict) for data_dict in processed_data_list]
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result[0]:  # 更新成功的行
                    result_rows.append(result[0])
                elif result[1]:  # 需要创建的行
                    create_list.append(result[1])
        
        # 批量创建需要新增的行
        if create_list:
            created_rows = self.create_rows(create_list, trigger_workflow=trigger_workflow)
            result_rows.extend(created_rows.all())
        
        return HapWorksheetRowSet(rows=result_rows, worksheet=self, hap_conn=self.hap_conn)


    @classmethod
    def _rows_data_to_fieldslist(cls, rows_data_list: list[dict | PydanticModel], ignore_fields=[], field_map={}, remain_irrelevant_fields=True):
        """
        将行数据字典列表转换为工作表API字段值list
        field_map 将row_data_dict中的字段名称（键）映射规则，将其转换为目标工作表control_id
        remain_irrelevant_fields 是否保留 field_map 未提及的字段
        """
        fields_list = []
        for data_dict in rows_data_list:
            row_fields = HapUtils.convert_data_to_fieldslist(data_dict, ignore_fields, field_map, remain_irrelevant_fields)
            fields_list.append({'fields': row_fields})
        return fields_list

    

class HapRowsQuery:
    """行查询类，支持链式查询操作"""
    def __init__(self, worksheet: HapWorksheet, hap_conn: HapConnection, filter_expression: str = None, sort_str: str = None, page_size: int = 1000, relation_origin_row: Optional['HapWorksheetRow'] = None, relation_field_name: Optional[str] = None):
        self.worksheet = worksheet
        self.hap_conn = hap_conn
        self.filter_expression = filter_expression
        self.filter_condition = HapUtils.expression_to_filter_condition(filter_expression)
        self.page_size = max(1, min(page_size, 1000))
        self.page_index = 1
        self.sort_str = sort_str
        self.sorts = HapUtils.str_to_sort_list(sort_str)
        self.limit = None
        self.relation_origin_row = relation_origin_row
        self.relation_field_name = relation_field_name
        self.last_query_timestamp = None
        

    def filter(self, filter_expression: str) -> 'HapRowsQuery':
        """添加过滤条件
        
        Args:
            filter_expression: 过滤条件表达式
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.filter_expression = filter_expression
        self.filter_condition = HapUtils.expression_to_filter_condition(filter_expression)
        return self
        

    def sort(self, sort_str: str) -> 'HapRowsQuery':
        """添加排序条件
        
        Args:
            sort_str: 排序字符串，格式如 "x,-y"，其中 "-" 表示降序
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.sort_str = sort_str
        self.sorts = HapUtils.str_to_sort_list(sort_str)
        return self

        
    def set_limit(self, limit: int) -> 'HapRowsQuery':
        """设置返回记录数限制
        
        Args:
            limit: 最大返回记录数
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.limit = limit
        return self

        
    def offset(self, offset: int) -> 'HapRowsQuery':
        """设置偏移量
        
        Args:
            offset: 偏移量
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.page_index = offset // self.page_size + 1
        return self

        
    def _execute_query(self, page_size: int, include_total: bool = True) -> 'HapWorksheetRowSet':
        """执行查询并返回结果
        
        Args:
            page_size: 查询的每页记录数
            include_total: 是否包含总记录数
            
        Returns:
            HapWorksheetRowSet: 行对象集合
        """
        # 构建查询参数
        payload = {
            "pageSize": page_size,
            "pageIndex": self.page_index,
            "includeTotalCount": include_total,
        }
        
        payload["filter"] = self.filter_condition
        payload['sorts'] = self.sorts
        
        # 发送请求
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/list"
        response = self.hap_conn._post(endpoint=endpoint, payload=payload)
        self.last_query_timestamp = datetime.now().timestamp()
        
        # 处理响应
        rows = []
        if response.get('success'):
            for row_dict in response.get('data', {}).get('rows', []):
                rows.append(HapWorksheetRow(
                    row_data=row_dict,
                    row_id=row_dict.get('rowId'),
                    worksheet=self.worksheet,
                    hap_conn=self.hap_conn,
                    relation_origin_row=self.relation_origin_row,
                    relation_field_name=self.relation_field_name,
                ))
        
        return HapWorksheetRowSet(rows=rows, worksheet=self.worksheet, hap_conn=self.hap_conn)


    def first(self) -> Optional['HapWorksheetRow']:
        """获取第一条记录
        
        Returns:
            Optional[HapWorksheetRow]: 行对象，如果没有记录则返回None
        """
        # 只获取一条记录，不包含总数
        row_set = self._execute_query(page_size=1, include_total=False)
        return row_set.first()

        
    def all(self) -> 'HapWorksheetRowSet':
        """获取所有匹配的记录
        
        Returns:
            HapWorksheetRowSet: 行对象集合
        
        Note:
            当数据量超过 10000 条时，建议使用 stream() 方法以避免内存溢出
        """
        # 首先获取总数
        total_payload = {
            "pageSize": 1,
            "pageIndex": 1,
            "includeTotalCount": True,
            "filter": self.filter_condition,
            "sorts": self.sorts
        }
        
        # 替换为使用 worksheet_id
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/list"
        total_response = self.hap_conn._post(endpoint=endpoint, payload=total_payload)
        
        if not total_response.get('success'):
            return HapWorksheetRowSet(rows=[], worksheet=self.worksheet, hap_conn=self.hap_conn)
        
        total_count = total_response.get('data', {}).get('total', 0)
        
        # 如果数据量过大，抛出警告
        if total_count > 10000:
            print(f"警告：数据量较大 ({total_count} 条)，可能会导致内存溢出。建议使用 stream() 方法。")
        
        # 计算需要的页数
        page_size = min(self.limit, self.page_size) if self.limit else self.page_size
        page_size = min(page_size, 1000)  # 确保不超过 HAP 系统限制
        total_pages = (total_count + page_size - 1) // page_size
        
        all_rows = []
        
        # 逐页获取数据
        for page in range(1, total_pages + 1):
            # 构建查询参数
            payload = {
                "pageSize": page_size,
                "pageIndex": page,
                "includeTotalCount": False,
                "filter": self.filter_condition,
                "sorts": self.sorts
            }
            
            # 发送请求
            endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/list"
            response = self.hap_conn._post(endpoint=endpoint, payload=payload)
            
            if response.get('success'):
                for row_dict in response.get('data', {}).get('rows', []):
                    all_rows.append(HapWorksheetRow(
                        row_data=row_dict,
                        row_id=row_dict.get('rowId'),
                        worksheet=self.worksheet,
                        hap_conn=self.hap_conn,
                        relation_origin_row=self.relation_origin_row,
                        relation_field_name=self.relation_field_name
                    ))
            
            # 应用 limit
            if self.limit and len(all_rows) >= self.limit:
                all_rows = all_rows[:self.limit]
                break
        
        self.last_query_timestamp = datetime.now().timestamp()
        return HapWorksheetRowSet(rows=all_rows, worksheet=self.worksheet, hap_conn=self.hap_conn, relation_origin_row=self.relation_origin_row, relation_field_name=self.relation_field_name)
    

    def stream(self) -> 'Generator[HapWorksheetRow, None, None]':
        """流式获取所有匹配的记录
        
        Returns:
            Generator[HapWorksheetRow, None, None]: 行对象生成器
        
        Note:
            适合处理大量数据，内存使用低，但只能遍历一次
        """
        # 首先获取总数
        total_payload = {
            "pageSize": 1,
            "pageIndex": 1,
            "includeTotalCount": True,
            "filter": self.filter_condition,
            "sorts": self.sorts
        }
        
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/list"
        total_response = self.hap_conn._post(endpoint=endpoint, payload=total_payload)
        
        if not total_response.get('success'):
            return
        
        total_count = total_response.get('data', {}).get('total', 0)
        
        # 计算需要的页数
        page_size = min(self.limit, self.page_size) if self.limit else self.page_size
        page_size = min(page_size, 1000)  # 确保不超过 HAP 系统限制
        total_pages = (total_count + page_size - 1) // page_size
        
        fetched_count = 0
        
        # 逐页获取数据
        for page in range(1, total_pages + 1):
            # 构建查询参数
            payload = {
                "pageSize": page_size,
                "pageIndex": page,
                "includeTotalCount": False,
                "filter": self.filter_condition,
                "sorts": self.sorts
            }
            
            # 发送请求
            response = self.hap_conn._post(endpoint=endpoint, payload=payload)
            
            if response.get('success'):
                for row_dict in response.get('data', {}).get('rows', []):
                    row = HapWorksheetRow(
                        row_data=row_dict,
                        row_id=row_dict.get('rowId'),
                        worksheet=self.worksheet,
                        hap_conn=self.hap_conn,
                        relation_origin_row=self.relation_origin_row,
                        relation_field_name=self.relation_field_name
                    )
                    # self.last_query_timestamp = datetime.now().timestamp()
                    yield row
                    fetched_count += 1
                    
                    # 应用 limit
                    if self.limit and fetched_count >= self.limit:
                        return


    # def count(self) -> int:
    #     """获取匹配记录的总数
    #     
    #     Returns:
    #         int: 记录总数
    #     """
    #     payload = {
    #         "pageSize": 1,
    #         "pageIndex": 1,
    #         "includeTotalCount": True,
    #     }
    #     
    #     if self.filter_condition:
    #         filter_condtion = self.hap_conn._expression_to_filter_condition(self.filter_condition)
    #         payload["filter"] = filter_condtion
    #     
    #     endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/list"
    #     response = self.hap_conn._post(endpoint=endpoint, payload=payload)
    #     
    #     if response.get('success'):
    #         return response.get('data', {}).get('total', 0)
    #     return 0



    @classmethod
    def _exclude_sys_fields(cls, data: dict) -> dict:
        """排除系统字段"""
        filtered_data = {}
        for k, v in data.items():
            if not k.startswith('_'):
                filtered_data[k] = v
        return filtered_data


    @classmethod
    def _exclude_unamed_fields(cls, data: dict) -> dict:
        # 匹配18-24个十六进制字符的正则表达式（不区分大小写）
        uuid_pattern = r'^[0-9a-f]{18,24}$'
        filtered_data = {}
        for k, v in data.items():
            # 检查键名是否匹配UUID格式
            if not re.match(uuid_pattern, k.lower()):
                filtered_data[k] = v
        return filtered_data


    @classmethod
    def _expression_to_filter_condition(cls, expression: str) -> dict:
        """
        将逻辑表达式字符串转换为筛选条件JSON结构
        
        参数:
            expression: 逻辑表达式字符串，格式如 "(age__gt=18 && status__in=[\"active\",\"pending\"]) || name__isempty"
            
        返回:
            符合明道云API要求的筛选条件JSON结构
        
        支持的运算符及示例值:
            - eq: 等于, 示例: name__eq="张三"
            - ne: 不等于, 示例: status__ne="inactive"
            - gt: 大于, 示例: age__gt=18
            - ge: 大于等于, 示例: score__ge=60
            - lt: 小于, 示例: price__lt=100
            - le: 小于等于, 示例: count__le=10
            - isempty: 为空, 示例: description__isempty
            - isnotempty: 非空, 示例: email__isnotempty
            - in: 是其中一个, 示例: status__in=["active","pending"]
            - notin: 不是任意一个, 示例: role__notin=["admin","manager"]
            - contains: 包含, 示例: tags__contains="important"
            - notcontains: 不包含, 示例: notes__notcontains="deprecated"
            - concurrent: 同时包含, 示例: skills__concurrent=["python","javascript"]
            - belongsto: 属于, 示例: department__belongsto=["sales"]
            - notbelongsto: 不属于, 示例: team__notbelongsto=["engineering"]
            - startswith: 开头是, 示例: name__startswith="张"
            - notstartswith: 开头不是, 示例: name__notstartswith="李"
            - endswith: 结尾是, 示例: domain__endswith="com"
            - notendswith: 结尾不是, 示例: file__notendswith="txt"
            - between: 在范围内, 示例: date__between=["2025-01-01","2025-01-31"]
            - notbetween: 不在范围内, 示例: age__notbetween=["0","18"]
        """
        # 去除空白字符
        expression = ''.join(expression.split())
        
        def parse(expression):
            # 辅助函数：解析表达式
            
            # 处理括号嵌套
            def find_matching_bracket(expr, start):
                # 找到匹配的右括号索引
                count = 1
                for i in range(start + 1, len(expr)):
                    if expr[i] == '(':
                        count += 1
                    elif expr[i] == ')':
                        count -= 1
                        if count == 0:
                            return i
                return -1
            
            # 如果表达式被括号包围，先解析括号内的内容
            if expression.startswith('(') and find_matching_bracket(expression, 0) == len(expression) - 1:
                return parse(expression[1:-1])
            
            # 查找最高级别的逻辑运算符（先||，后&&）
            bracket_level = 0
            or_pos = -1
            and_pos = -1
            
            for i, char in enumerate(expression):
                if char == '(':
                    bracket_level += 1
                elif char == ')':
                    bracket_level -= 1
                elif bracket_level == 0:
                    if char == '|' and i + 1 < len(expression) and expression[i + 1] == '|':
                        or_pos = i
                        break
                    elif char == '&' and i + 1 < len(expression) and expression[i + 1] == '&':
                        and_pos = i
            
            # 如果找到OR运算符
            if or_pos != -1:
                left = parse(expression[:or_pos])
                right = parse(expression[or_pos + 2:])
                return {
                    "type": "group",
                    "logic": "OR",
                    "children": [left, right]
                }
            
            # 如果找到AND运算符
            elif and_pos != -1:
                left = parse(expression[:and_pos])
                right = parse(expression[and_pos + 2:])
                return {
                    "type": "group",
                    "logic": "AND",
                    "children": [left, right]
                }
            
            # 否则，这是一个条件表达式
            else:
                # 处理 isempty 和 isnotempty 不带等号的情况
                if '__isempty' in expression:
                    field = expression.replace('__isempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isempty",
                        "value": []
                    }
                elif '__isnotempty' in expression:
                    field = expression.replace('__isnotempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isnotempty",
                        "value": []
                    }
                # 处理带等号的情况
                elif '=' in expression:
                    # 分割字段名（包含运算符）和值
                    field_op, value = expression.split('=', 1)
                    
                    # 分割字段名和运算符
                    if '__' in field_op:
                        field, op = field_op.split('__', 1)
                        operator = op
                    else:
                        return {}
                    
                    # 处理需要数组值的运算符
                    array_operators = ['in', 'notin', 'contains', 'notcontains', 'concurrent', 'belongsto', 'notbelongsto', 'between', 'notbetween']
                    
                    if operator in array_operators:
                        # 解析数组格式的值
                        if value.startswith('[') and value.endswith(']'):
                            import json
                            try:
                                array_value = json.loads(value)
                                if isinstance(array_value, list):
                                    return {
                                        "type": "condition",
                                        "field": field.strip(),
                                        "operator": operator,
                                        "value": array_value
                                    }
                            except:
                                pass
                    
                    # 处理普通运算符，去除字符串值的双引号
                    if operator not in array_operators:
                        # 移除字符串值的双引号
                        stripped_value = value.strip()
                        if stripped_value.startswith('"') and stripped_value.endswith('"'):
                            stripped_value = stripped_value[1:-1]
                        return {
                            "type": "condition",
                            "field": field.strip(),
                            "operator": operator,
                        "value": [stripped_value]
                    }
                return {}
        
        return parse(expression)


    @classmethod
    def _str_to_sort_list(cls, sorts: str) -> list:
        """将排序字符串转换为排序列表
        
        Args:
            sorts: 排序字符串，格式如 "-x,y"（负号表示降序，正号或无符号表示升序）
            
        Returns:
            list: 排序列表，格式如 [{"field":"x","isAsc":False},{"field":"y","isAsc":True}]
        """
        if not sorts:
            return []
        sort_fields = sorts.split(',')
        sort_list = []
        for field_str in sort_fields:
            field_str = field_str.strip()
            if not field_str:
                continue
            
            # 检查是否以负号开头
            if field_str.startswith('-'):
                field = field_str[1:].strip()
                is_asc = False
            else:
                # 移除可能的正号
                field = field_str.lstrip('+').strip()
                is_asc = True
            
            if field:
                sort_list.append({"field": field, "isAsc": is_asc})
        return sort_list

        

class HapWorksheetRow:
    """工作表行类，代表单行数据并提供操作方法"""
    def __init__(self, row_data: dict, row_id: str = None, worksheet: HapWorksheet = None, hap_conn: HapConnection = None, relation_origin_row: Optional['HapWorksheetRow'] = None, relation_field_name: Optional[str] = None):
        # 使用 HapUtils.process_choice_fields 处理选项字段
        processed_row_data = HapUtils.process_choice_fields(row_data)
        
        self.row_data = processed_row_data
        self.worksheet = worksheet
        self.row_id = row_id
        self.hap_conn = hap_conn
        self.relation_origin_row = relation_origin_row
        self.relation_field_name = relation_field_name
        self.relation_query: Dict[str, HapWorksheetRowSet] = {}
        self.refresh_stamp = datetime.now().timestamp()

        
    def exists(self) -> bool:
        """检查行是否存在
        
        Returns:
            bool: 如果行存在则返回True，否则返回False
        """
        return self.row_id is not None

        
    def update(self, data: Dict[str, Any], none_exist_then: Literal['error', 'ignore', 'create'] = 'error', exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> 'HapWorksheetRow':
        """更新行数据
        
        Args:
            data: 要更新的数据字典
            none_exist_then: 当行不存在时的处理方式，可选值为'error'（抛出异常）、'ignore'（无视跳过）、'create'（创建新行）
            
        Returns:
            HapWorksheetRow: 更新后的行对象
        """
        if not self.exists():
            if none_exist_then == 'error':
                raise Exception("Cannot update a non-existent row")
            elif none_exist_then == 'ignore':
                return self
            elif none_exist_then == 'create':
                # 使用 worksheet 对象创建新行
                return self.worksheet.create_rows([data])[0]
        
        # 构建更新请求
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/{self.row_id}"
        # self.refresh()

        update_fields = {}
        
        for k, v in data.items():
            if v is None and exclude_none:
                continue
            if k not in self.row_data:
                update_fields[k] = v
            elif when_value_equal_then == 'update' or not DataProcessor.is_equal(self.row_data[k], v):
                update_fields[k] = v

        payload = {
            "fields": self._data_dict_to_fields_list(data=update_fields, exclude_none=exclude_none),
            "triggerWorkflow": trigger_workflow
        }
        
        # 发送更新请求
        response = self.hap_conn._patch(endpoint=endpoint, payload=payload)
        
        # 更新本地数据
        if response.get('success'):
            self.row_data.update(data)
        
        return self
        

    def delete(self, trigger_workflow: bool = True, permanent: bool = False) -> bool:
        """删除行
        
        Args:
            trigger_workflow: 是否触发工作流
            permanent: 是否永久删除，默认False
        
        Returns:
            bool: 如果删除成功则返回True，否则返回False
        """
        if not self.exists():
            raise Exception("Cannot delete a non-existent row")
        
        # 构建删除请求
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/{self.row_id}"
        payload = {"permanent": permanent, "triggerWorkflow": trigger_workflow}
        response = self.hap_conn._delete(endpoint=endpoint, payload=payload)
        
        if response.get('success'):
            self.row_id = None
            self.row_data = {}
            return True
        return False


    # def append_relation_rows(self, child_rows: List['HapWorksheetRow'], child_fieldname: str, child_worksheet_id: str) -> 'HapWorksheetRow':
    #     """  追加关联表行
        
    #     Args:
    #         child_rows: 关联表行对象列表
    #         child_fieldname: 关联表字段名
    #         child_worksheet_id: 关联表工作表ID
        
    #     Returns:
    #         HapWorksheetRow: 更新后的行对象
    #     """
    #     child_rowids = [row.row_id for row in child_rows]
    #     self.update({child_fieldname: child_rowids})
    #     return self
        

    def to_dict(self) -> Dict[str, Any]:
        """将行数据转换为字典
        
        Returns:
            Dict[str, Any]: 行数据字典
        """
        return self.row_data.copy()
        

    def refresh(self) -> 'HapWorksheetRow':
        """从服务器刷新行数据
        
        Returns:
            HapWorksheetRow: 刷新后的行对象
        """
        if not self.exists():
            raise Exception("Cannot refresh a non-existent row")
        if datetime.now().timestamp() - self.refresh_stamp < REFRESH_INTERVAL_SECONDS:
            return self
        # 调用 worksheet.row() 会返回 HapWorksheetRow 对象
        row_obj = self.worksheet.row(row_id=self.row_id)
        self.row_data = row_obj.row_data
        self.refresh_stamp = datetime.now().timestamp()
        return self


    def relations(self, relation_fieldname: str, filter_expression: str = None) -> 'HapWorksheetRowSet':
        """获取关联表行集合
        relation_fieldname: 关联表在当前主表中的字段名
        filter_expression: 关联表行筛选表达式，注意不要太复杂，HAP 对筛选嵌套层数有限制
        """
        self.refresh()  # 先刷新一下，保证关联关系是最新的
        # 距离最新一次查询的秒数小于刷新间隔秒数，直接返回查询结果
        exist_query = self.relation_query.get(relation_fieldname)
        if exist_query:
            passed_seconds = datetime.now().timestamp() - exist_query.last_query_timestamp
            if passed_seconds <= REFRESH_INTERVAL_SECONDS:
                return exist_query
        related_worksheet_id = self.hap_conn.allowed_worksheets[self.worksheet.worksheet_id].related_sheets[relation_fieldname]
        related_worksheet = self.hap_conn.worksheet(related_worksheet_id)
        related_rowids = self.row_data[relation_fieldname]

        relation_rows_filter_exp = f"rowId__in={json.dumps(related_rowids)}"
        if filter_expression:
            filter_expression = f"{relation_rows_filter_exp} && ({filter_expression})"
        else:
            filter_expression = relation_rows_filter_exp
        related_row_query = related_worksheet.rows(filter_expression=filter_expression, relation_origin_row=self, relation_field_name=relation_fieldname)
        # related_row_query.relation_origin_row = self
        # related_row_query.relation_field_name = relation_fieldname

        self.relation_query[relation_fieldname] = related_row_query
        return related_row_query


    @classmethod
    def _data_dict_to_fields_list(cls, data: Dict[str, Any] | PydanticModel, exclude_none: bool = True, ignore_fields=[], field_map={}, remain_irrelevant_fields=True) -> List[Dict[str, Any]]:
        """
        将行数据字典转换为工作表API字段值list [{'id': ..., 'value': ...}, {'id': ..., 'value': ...}]
        exclude_none 是否排除值为None的字段
        ignore_fields 要忽略的字段列表
        field_map 将row_data_dict中的字段名称（键）映射规则 {'row_data_dict_key': 'worksheet_field_id'}
        remain_irrelevant_fields 是否保留 field_map 未提及的字段
        """
        return HapUtils.convert_data_to_fieldslist(data=data, exclude_none=exclude_none, ignore_fields=ignore_fields, field_map=field_map, remain_irrelevant_fields=remain_irrelevant_fields)    



class HapWorksheetRowSet:
    """HapWorksheetRow 集合类，用于管理多个行对象"""
    def __init__(self, rows: List['HapWorksheetRow'] | List[str], worksheet: 'HapWorksheet', hap_conn: 'HapConnection', relation_origin_row: Optional['HapWorksheetRow'] = None, relation_field_name: Optional[str] = None):
        """初始化 HapWorksheetRowSet
        
        Args:
            rows: HapWorksheetRow 对象的列表 或 行ID字符串列表
            worksheet: 关联的 HapWorksheet 对象
            hap_conn: 关联的 HapConnection 对象
            relation_origin_row: 父行对象，可选
        """
        # 处理字符串类型的 row_id
        if rows and isinstance(rows[0], str):
            self.row_ids = rows
            filter_expression = f"rowId__in={json.dumps(rows)}"
            self.rows: List['HapWorksheetRow'] = worksheet.rows(filter_expression=filter_expression, relation_origin_row=relation_origin_row, relation_field_name=relation_field_name).all()
        else:
            self.rows: List['HapWorksheetRow'] = rows
            for row in rows:
                row.relation_origin_row = relation_origin_row
                row.relation_field_name = relation_field_name
            self.row_ids = [row.row_id for row in rows]
        self.worksheet = worksheet
        self.hap_conn = hap_conn
        self.relation_origin_row: HapWorksheetRow = relation_origin_row
        self.relation_field_name: str = relation_field_name
        self.refresh_stamp = datetime.now().timestamp()


    def all(self) -> List['HapWorksheetRow']:
        return self.rows

    
    def first(self) -> Optional['HapWorksheetRow']:
        return self.rows[0] if self.rows else None


    def last(self) -> Optional['HapWorksheetRow']:
        return self.rows[-1] if self.rows else None

    
    def count(self) -> int:
        return len(self.rows)
    

    def update_all(self, data: Dict[str, Any], trigger_workflow: bool = True) -> List['HapWorksheetRow']:
        """批量更新所有行对象，不比对是否与当前行一致，都强制更新为 data参数 中对应字段的值
        未在data参数中提及的字段将保持不变。
        
        Args:
            data: 要更新的数据字典
            trigger_workflow: 是否触发工作流
            
        Returns:
            List[HapWorksheetRow]: 更新后的行对象列表
        """
        fields = HapWorksheetRow._data_dict_to_fields_list(data, exclude_none=True)
        
        # 分批处理，每批最多100条(根据HAP API限制)
        batch_size = 100
        total_rows = len(self.row_ids)
        
        import concurrent.futures
        
        # 定义批次更新函数
        def update_batch(batch_start, batch_end):
            batch_row_ids = self.row_ids[batch_start:batch_end]
            batch_rows = self.rows[batch_start:batch_end]
            
            # 发送API请求
            response = self.hap_conn._patch(
                endpoint=f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/batch",
                payload={
                    "rowIds": batch_row_ids,
                    "fields": fields,
                    "triggerWorkflow": trigger_workflow
                }
            )

            # 如果批次更新失败，抛出异常
            if not response.get('success'):
                raise Exception(f"Batch update failed at batch {batch_start//batch_size + 1}: {response.get('message', 'Unknown error')}")

            # 批次更新成功，更新对应的本地数据
            for row in batch_rows:
                row.row_data.update(data)
        
        # 使用线程池并发执行批次更新
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = []
            for i in range(0, total_rows, batch_size):
                batch_start = i
                batch_end = i + batch_size
                futures.append(executor.submit(update_batch, batch_start, batch_end))
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                future.result()  # 抛出可能的异常
        
        return self.rows
                
    
    def refresh_all(self) -> List['HapWorksheetRow']:
        """批量刷新所有行对象
        
        Returns:
            List[HapWorksheetRow]: 刷新后的行对象列表
        """
        if datetime.now().timestamp() - self.refresh_stamp < REFRESH_INTERVAL_SECONDS:
            return self.rows
        import concurrent.futures
        # 使用线程池并发执行刷新操作
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            # 提交所有刷新任务
            futures = [executor.submit(row.refresh) for row in self.rows]
            # 等待所有任务完成
            concurrent.futures.wait(futures)
        self.refresh_stamp = datetime.now().timestamp()
        return self.rows


    def delete_all(self, trigger_workflow: bool = True, permanent: bool = False) -> List[bool]:
        """批量删除所有行对象
        
        Args:
            trigger_workflow: 是否触发工作流
            permanent: 是否永久删除
            
        Returns:
            List[bool]: 删除结果列表，每个元素表示对应行的删除是否成功
        """
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/batch"
        
        # 初始化结果列表，默认所有行删除失败
        results = [False] * len(self.row_ids)
        
        # 分批处理，每批最多100条
        batch_size = 100
        total_rows = len(self.row_ids)
        
        import concurrent.futures
        
        # 定义批次删除函数
        def delete_batch(batch_start, batch_end):
            batch_row_ids = self.row_ids[batch_start:batch_end]
            
            # 发送API请求
            response = self.hap_conn._delete(
                endpoint=endpoint,
                payload={
                    "rowIds": batch_row_ids,
                    "triggerWorkflow": trigger_workflow,
                    "permanent": permanent
                }
            )

            # 检查批次删除是否成功
            if response.get('success'):
                # 由于 HAP 返回的 data 为空没有详细结果，标记该批次所有行为删除成功
                for j in range(batch_start, min(batch_end, total_rows)):
                    results[j] = True
        
        # 使用线程池并发执行批次删除
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = []
            for i in range(0, total_rows, batch_size):
                batch_start = i
                batch_end = i + batch_size
                futures.append(executor.submit(delete_batch, batch_start, batch_end))
            
            # 等待所有任务完成
            for future in concurrent.futures.as_completed(futures):
                future.result()  # 抛出可能的异常

        return results


    def upserlete(self, data_list: List[dict], conflict_fields: List[str] = None, delete_missing: bool = False):
        """
        逐行处理数据列表，根据 conflict_fields 策略处理重复行
        Args:
            data_list: 包含多个行数据的列表，每个元素为一个字典
            conflict_fields: 冲突字段列表，用于判断是否为重复行，默认使用工作表的冲突字段
            delete_missing: 是否删除不存在于 data_list 的行（遍历），默认False
        """
        passed_seconds = datetime.now().timestamp() - self.refresh_stamp
        if passed_seconds > REFRESH_INTERVAL_SECONDS:
            self.refresh_all()
        conflict_fields = conflict_fields or self.worksheet.conflict_fields

        if delete_missing:
            rows_to_delete = []
            for row in self.rows:
                # TODO 遍历 Worksheet row ，通过 conflict_fields 中的字段，判断是否存在于 data_list 中，若不存在，则添加到 rows_to_delete 中以备删除
                if not any(row.row_data.get(field, None) == data.get(field, None) for field in conflict_fields):
                    rows_to_delete.append(row)
            self.worksheet.delete_rows(rows_to_delete, trigger_workflow=False, permanent=False)

        rows_for_creation = []
        for data in data_list:
            # 检查是否为重复行
            is_conflict, existing_row = self.is_conflict_within(data, conflict_fields)
            if is_conflict:
                # 更新重复行
                existing_row.update(data)
            else:
                rows_for_creation.append(data)
        if rows_for_creation:
            new_rows_set = self.worksheet.create_rows(rows_for_creation)
            relation_origin_row = self.relation_origin_row
            if relation_origin_row:
                # TODO 如果当前行记录集是通过子表方式获取的，则需要将新增的行挂载至源头行记录的子表字段中
                new_rows_ids = new_rows_set.row_ids
                relation_origin_worksheet = relation_origin_row.worksheet
                relation_field_name = self.relation_field_name
                relation_origin_row.refresh()
                relation_origin_row.update({
                    relation_field_name: new_rows_ids + relation_origin_row.row_data.get(relation_field_name, [])
                })

        

    def is_conflict_within(self, data: dict, conflict_fields: List[str]) -> tuple[bool, 'HapWorksheetRow']:
        """检查数据是否在当前行数据集中有冲突
        
        Args:
            data: 要检查的行数据字典
            conflict_fields: 冲突字段列表，用于判断是否为重复行，默认使用工作表的冲突字段
        
        Returns:
            tuple: (是否为冲突行, 冲突行对象)
        """
        if set(conflict_fields) <= set(data.keys()):
            for row in self.rows:
                if all(row.row_data.get(field, None) == data.get(field, None) for field in conflict_fields):
                    return True, row
        return False, None



if __name__ == "__main__":
    """使用示例"""
    # 初始化连接
    hapconn = HapConnection(
        app_key="your_app_key",
        sign="your_sign",
        base_url="https://api.mingdao.com"
    )


    def example_basic_crud():
        """基本的增删改查示例"""
        print("=== 基本 CRUD 示例 ===")
        
        # 1. 获取工作表
        worksheet = hapconn.worksheet("t_material")
        
        # 2. 创建新行
        new_row_set = worksheet.create_rows([{
            "name": "测试用户",
            "age": 25,
            "email": "test@example.com"
        }])
        print(f"创建新行数量: {new_row_set.count()}")
        
        # 3. 查询行
        # 获取所有行
        all_rows_set: List['HapWorksheetRow'] = worksheet.rows().all()
        print(f"所有行数量: {all_rows_set.count()}")
        
        # 根据条件查询
        filtered_rows_set = worksheet.rows("name__eq=\"测试用户\" && age__gt=20").all()
        print(f"筛选行数量: {filtered_rows_set.count()}")
        
        # 获取第一条匹配的行
        query = worksheet.rows("name__eq=\"测试用户\"")
        print(f"查询表达式: name__eq=\"测试用户\"")
        first_row = query.first()
        if first_row:
            print(f"第一条行数据: {first_row.to_dict()}")
        
        # 4. 更新行
        if first_row:
            updated_row = first_row.update({
                "age": 26,
                "email": "updated@example.com"
            })
            print(f"更新后的数据: {updated_row.to_dict()}")
        
        # 5. 删除行
        if first_row:
            delete_result = first_row.delete()
            print(f"删除结果: {'成功' if delete_result else '失败'}")


    def example_chain_query():
        """链式查询示例"""
        print("\n=== 链式查询示例 ===")
        
        worksheet = hapconn.worksheet("worksheet_name")
        
        # 复杂查询示例
        rows = worksheet.rows("age__gt=18")\
            .sort("-age")\
            .set_limit(10)\
            .all()
        
        print(f"查询结果数量: {rows.count()}")
        for i, row in enumerate(rows.all()):
            print(f"行 {i+1}: {row.to_dict()}")


    def example_count_query():
        """计数查询示例"""
        print("\n=== 计数查询示例 ===")
        
        worksheet = hapconn.worksheet("worksheet_name")
        
        # 计算符合条件的行数
        total_count = worksheet.rows("status__eq=\"active\"").all().count()
        print(f"活跃用户数量: {total_count}")


    def example_row_operations():
        """行操作示例"""
        print("\n=== 行操作示例 ===")
        
        worksheet = hapconn.worksheet("worksheet_name")
        
        # 创建新行
        row_set = worksheet.create_rows([{
            "name": "操作测试",
            "status": "pending"
        }])
        row = row_set.first()
        
        # 检查行是否存在
        print(f"行是否存在: {row.exists()}")
        
        # 更新行
        row.update({"status": "processing"})
        print(f"更新后的状态: {row.to_dict().get('status')}")
        
        # 刷新行数据
        row.refresh()
        print(f"刷新后的数据: {row.to_dict()}")
        
        # 删除行
        row.delete()
        print(f"删除后行是否存在: {row.exists()}")
        
    # 注意：运行此示例需要有效的 HAP API 凭证
    # example_basic_crud()
    # example_chain_query()
    # example_count_query()
    # example_row_operations()
    print("请取消注释需要运行的示例函数")



