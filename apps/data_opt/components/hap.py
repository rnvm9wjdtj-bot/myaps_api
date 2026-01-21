"""明道云 API v3 封装为 ORM """

import json
import re
from typing import List, Dict, Any, Optional, Union, Literal, Generator
from pydantic import BaseModel as PydanticModel
from decimal import Decimal

from ._base import get_session



# 自定义JSON编码器，用于处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)



# 工具类，包含通用方法
class HapUtils:
    """
    明道云工具类，包含通用方法
    """
    
    @staticmethod
    def convert_data_to_controls(data: Dict[str, Any] | PydanticModel, ignore_fields=[], controls_reflection={}, remain_irrelevant_fields=True) -> List[Dict[str, Any]]:
        """
        将单个数据字典转换为工作表API字段值list
        
        Args:
            data: 行数据字典或 PydanticModel
            ignore_fields: 忽略的字段列表
            controls_reflection: 字段名称映射到控件ID的字典
            remain_irrelevant_fields: 是否保留 controls_reflection 未提及的字段
            
        Returns:
            List[Dict[str, Any]]: 字段值列表
        """
        if isinstance(data, PydanticModel):
            data = data.model_dump(exclude_unset=True)
        
        controls = []
        for k, v in data.items():
            if k in ignore_fields: 
                continue
            try:
                control_id = controls_reflection[k]
            except:
                if remain_irrelevant_fields:
                    control_id = k
                else:
                    continue
            # control_id = controls_reflection.get(k, k)
            v_type = type(v)
            if v_type in (dict, list):
                controls.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False, cls=DecimalEncoder)})
            elif v_type in (int, float, Decimal):
                controls.append({'id': control_id, 'value': float(v), 'type': 2})
            elif v_type == str:
                controls.append({'id': control_id, 'value': v, 'type': 2})
            else:
                pass
        
        return controls
    

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
                        "value": [stripped_value]
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



hap_example_url = ('https://api.mingdao.com', 'http://127.0.0.1:8080/api')



def get_worksheet_config() -> dict:
    """获取工作表配置
    
    Args:
        worksheet_id: 工作表ID或名称
        
    Returns:
        dict: 工作表配置
    """
    from apps.io_api.utils.db_operation import process_model_or_tablename
    from globalobjects.db_manager import DbManager
    
    worksheet_ids = {'t_material', 't_workcenter', 't_mat_ver', 't_mat_wc', 't_mat_wc_bom', 't_mold', 't_mat_wc_mold'}

    worksheet_config = {}

    for mdl_name in worksheet_ids:
        mdl, table_name = process_model_or_tablename(mdl_name)
        worksheet_config[mdl_name] = {
            "conflict_fields": DbManager._get_conflict_fields(mdl),
            # "model": mdl
        }
    
    return worksheet_config
    

class HapConnection:
    def __init__(self, app_key: str, sign: str, base_url: str=hap_example_url[0], worksheet_config: callable=get_worksheet_config):
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
        self.worksheet_config = worksheet_config()
        self.headers = {
            'HAP-Appkey': app_key,
            'HAP-Sign': sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        
        # 初始化Session并配置性能参数
        self.session = get_session(
            retries=3,
            allowed_methods=["GET", "POST"],
            pool_connections=20,
            pool_maxsize=20,
            connect_timeout=3.0,
            read_timeout=30.0,
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
        return HapWorksheet(worksheet_id=worksheet_id, hap_conn=self)



class HapWorksheet:
    """工作表类，代表一个明道云工作表"""
    def __init__(self, worksheet_id: str, hap_conn: HapConnection):
        self.worksheet_id = worksheet_id
        try:
            self.conflict_fields = hap_conn.worksheet_config[worksheet_id]['conflict_fields']
        except KeyError:
            self.conflict_fields = None
        self.hap_conn = hap_conn
        

    def rows(self, filter_expression: Optional[str] = None, sort_str: Optional[str] = None) -> 'HapRowsQuery':
        """获取行查询对象
        
        Args:
            filter_expression: 过滤条件表达式，如 "name='test' && age>18"
            sort_str: 排序字符串，如 "name,-age"
            
        Returns:
            HapRowsQuery: 行查询对象，支持链式调用
        """
        return HapRowsQuery(worksheet=self, hap_conn=self.hap_conn, filter_expression=filter_expression, sort_str=sort_str)
        

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
            for k, v in data.items():
                # if k not in ('rowid', 'ctime', 'utime', 'caid', 'uaid', 'ownerid'):
                    if type(v) == list:
                        v = [item['value'] for item in v]
                        row_dict[k] = ','.join(v)
                    else:
                        row_dict[k] = v

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
        
        for i in range(0, total_rows, batch_size):
            # 获取当前批次的数据
            batch_start = i
            batch_end = i + batch_size
            batch_data = processed_data_list[batch_start:batch_end]
            
            # 构建创建请求
            endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/batch"
            # 转换数据为API要求的格式
            rows_data = []
            for data_dict in batch_data:
                row_controls = HapUtils.convert_data_to_controls(data_dict)
                rows_data.append({'fields': row_controls})
            payload = {
                "rows": rows_data,  
                "triggerWorkflow": trigger_workflow
            }
            response = self.hap_conn._post(endpoint, payload)
            
            # 获取当前批次的row_ids
            batch_row_ids = response.get('data', {}).get('rowIds', [])
            all_row_ids.extend(batch_row_ids)
            
            # 创建当前批次的行对象
            for j, row_id in enumerate(batch_row_ids):
                if batch_start + j < total_rows:
                    row = HapWorksheetRow(
                        row_data=processed_data_list[batch_start + j], 
                        row_id=row_id, 
                        worksheet=self, 
                        hap_conn=self.hap_conn
                    )
                    all_rows.append(row)
        
        worksheet_rowset = HapWorksheetRowSet(rows=all_rows, worksheet=self, hap_conn=self.hap_conn)
        if refresh_immediately:
            worksheet_rowset.refresh_all()
        return worksheet_rowset
    

    def upsert(self, data_list: List[Dict[str, Any] | PydanticModel], trigger_workflow: bool = True) -> 'HapWorksheetRowSet':
        """批量 upsert 操作
        
        Args:
            data_list: 行数据字典或 PydanticModel 列表
            trigger_workflow: 是否触发工作流
            
        Returns:
            HapWorksheetRowSet: 处理后的行对象集合
        """
        result_rows = []
        
        # 检查是否有冲突字段
        has_conflict_fields = bool(self.conflict_fields)
        
        for data in data_list:
            # 处理 PydanticModel
            if isinstance(data, PydanticModel):
                data_dict = data.model_dump()
            else:
                data_dict = data.copy()
            
            # 如果没有冲突字段，直接创建
            if not has_conflict_fields:
                created_rows = self.create_rows([data_dict], trigger_workflow=trigger_workflow)
                result_rows.extend(created_rows.all())
                continue
            
            # 构建查询条件
            filter_conditions = []
            for field in self.conflict_fields:
                if field in data_dict:
                    value = data_dict[field]
                    filter_conditions.append(f'{field}__eq=\"{value}\"')

            # 如果没有有效的冲突字段值，直接创建
            if not filter_conditions:
                created_rows = self.create_rows([data_dict], trigger_workflow=trigger_workflow)
                result_rows.extend(created_rows.all())
                continue
            
            # 执行查询
            filter_expression = " && ".join(filter_conditions)
            existing_rows = self.rows(filter_expression).all()
            
            # 如果存在，执行更新
            if existing_rows.count() > 0:
                # 更新第一条匹配的记录
                existing_row = existing_rows.first()
                updated_row = existing_row.update(data_dict, trigger_workflow=trigger_workflow)
                result_rows.append(updated_row)
            else:
                # 不存在，执行创建
                created_rows = self.create_rows([data_dict], trigger_workflow=trigger_workflow)
                result_rows.extend(created_rows.all())
        
        return HapWorksheetRowSet(rows=result_rows, worksheet=self, hap_conn=self.hap_conn)


    @classmethod
    def _rows_data_to_controls_list(cls, rows_data_list: list[dict | PydanticModel], ignore_fields=[], controls_reflection={}, remain_irrelevant_fields=True):
        """
        将行数据字典列表转换为工作表API字段值list
        controls_reflection 是一个可选参数，用于将row_data_dict中的字段名称（键）映射为目标工作表control_id
        remain_irrelevant_fields 是否保留 controls_reflection 未提及的字段
        """
        controls_list = []
        for data_dict in rows_data_list:
            row_controls = HapUtils.convert_data_to_controls(data_dict, ignore_fields, controls_reflection, remain_irrelevant_fields)
            controls_list.append({'fields': row_controls})
        return controls_list

    

class HapRowsQuery:
    """行查询类，支持链式查询操作"""
    def __init__(self, worksheet: HapWorksheet, hap_conn: HapConnection, filter_expression: str = None, sort_str: str = None, page_size: int = 1000):
        self.worksheet = worksheet
        self.hap_conn = hap_conn
        self.filter_expression = filter_expression
        self.filter_condition = HapUtils.expression_to_filter_condition(filter_expression)
        self.page_size = max(1, min(page_size, 1000))
        self.page_index = 1
        self.sort_str = sort_str
        self.sorts = HapUtils.str_to_sort_list(sort_str)
        self.limit = None
        

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
        
        # 处理响应
        rows = []
        if response.get('success'):
            for row_dict in response.get('data', {}).get('rows', []):
                rows.append(HapWorksheetRow(
                    row_data=row_dict,
                    row_id=row_dict.get('rowId'),
                    worksheet=self.worksheet,
                    hap_conn=self.hap_conn
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
                        hap_conn=self.hap_conn
                    ))
            
            # 应用 limit
            if self.limit and len(all_rows) >= self.limit:
                all_rows = all_rows[:self.limit]
                break
        
        return HapWorksheetRowSet(rows=all_rows, worksheet=self.worksheet, hap_conn=self.hap_conn)
    
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
                        hap_conn=self.hap_conn
                    )
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
    def __init__(self, row_data: dict, row_id: str = None, worksheet: HapWorksheet = None, hap_conn: HapConnection = None):
        self.row_data = row_data
        self.worksheet = worksheet
        self.row_id = row_id
        self.hap_conn = hap_conn
        
        
    def exists(self) -> bool:
        """检查行是否存在
        
        Returns:
            bool: 如果行存在则返回True，否则返回False
        """
        return self.row_id is not None

        
    def update(self, data: Dict[str, Any], none_exist_then: str = Literal['error', 'ignore', 'create'], trigger_workflow: bool = True) -> 'HapWorksheetRow':
        """更新行数据
        
        Args:
            data: 要更新的数据字典
            none_exist_then: 当行不存在时的处理方式，可选值为'error'（抛出异常）、'ignore'（忽略更新）、'create'（创建新行）
            
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
        
        # 更新本地数据
        self.row_data.update(data)
        
        # 构建更新请求
        endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/{self.row_id}"
        payload = {
            "fields": self._data_dict_to_controls_list(data),
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
        
        # 调用 worksheet.row() 会返回 HapWorksheetRow 对象
        row_obj = self.worksheet.row(row_id=self.row_id)
        self.row_data = row_obj.row_data
        return self


    @classmethod
    def _data_dict_to_controls_list(cls, data: Dict[str, Any] | PydanticModel, ignore_fields=[], controls_reflection={}, remain_irrelevant_fields=True) -> List[Dict[str, Any]]:
        """
        将行数据字典转换为工作表API字段值list [{'id': ..., 'value': ...}, {'id': ..., 'value': ...}]
        controls_reflection 是一个可选参数，用于将row_data_dict中的字段名称（键）映射为目标工作表control_id
        remain_irrelevant_fields 是否保留 controls_reflection 未提及的字段
        """
        return HapUtils.convert_data_to_controls(data, ignore_fields, controls_reflection, remain_irrelevant_fields)


class HapWorksheetRowSet:
    """HapWorksheetRow 集合类，用于管理多个行对象"""
    def __init__(self, rows: List['HapWorksheetRow'], worksheet: 'HapWorksheet', hap_conn: 'HapConnection'):
        """初始化 HapWorksheetRowSet
        
        Args:
            rows: HapWorksheetRow 对象的列表
            worksheet: 关联的 HapWorksheet 对象
            hap_conn: 关联的 HapConnection 对象
        """
        self.rows = rows
        self.row_ids = [row.row_id for row in rows]
        self.worksheet = worksheet
        self.hap_conn = hap_conn
    
    def all(self) -> List['HapWorksheetRow']:
        """获取所有行对象
        
        Returns:
            List[HapWorksheetRow]: 行对象列表
        """
        return self.rows
    
    def first(self) -> Optional['HapWorksheetRow']:
        """获取第一条行对象
        
        Returns:
            Optional[HapWorksheetRow]: 第一条行对象，如果列表为空则返回 None
        """
        return self.rows[0] if self.rows else None
    
    def count(self) -> int:
        """获取行对象数量
        
        Returns:
            int: 行对象数量
        """
        return len(self.rows)
    

    def update_all(self, data: Dict[str, Any], trigger_workflow: bool = True) -> List['HapWorksheetRow']:
        """批量更新所有行对象
        
        Args:
            data: 要更新的数据字典
            trigger_workflow: 是否触发工作流
            
        Returns:
            List[HapWorksheetRow]: 更新后的行对象列表
        """
        fields = HapWorksheetRow._data_dict_to_controls_list(data)
        
        # 分批处理，每批最多100条
        batch_size = 100
        total_rows = len(self.row_ids)
        
        for i in range(0, total_rows, batch_size):
            # 获取当前批次的row_ids和对应的本地行
            batch_start = i
            batch_end = i + batch_size
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
                raise Exception(f"Batch update failed at batch {i//batch_size + 1}: {response.get('message', 'Unknown error')}")

            # 批次更新成功，更新对应的本地数据
            for row in batch_rows:
                row.row_data.update(data)
            
        return self.rows
                
    
    def refresh_all(self) -> List['HapWorksheetRow']:
        """批量刷新所有行对象
        
        Returns:
            List[HapWorksheetRow]: 刷新后的行对象列表
        """
        # endpoint = f"/v3/app/worksheets/{self.worksheet.worksheet_id}/rows/list"
        # self.hap_conn.
        for row in self.rows:
            row.refresh()
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
        
        for i in range(0, total_rows, batch_size):
            # 获取当前批次的row_ids和对应的索引范围
            batch_start = i
            batch_end = i + batch_size
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
                # 检查响应中是否包含每个行的具体删除结果
                # 如果明道云API返回了详细的删除结果，使用它
                # 否则，假设批次中的所有行都删除成功
                if 'data' in response and isinstance(response['data'], dict):
                    # 假设data中包含每个rowId的删除结果
                    # 具体格式需要根据明道云API的实际响应来调整
                    for j, row_id in enumerate(batch_row_ids):
                        if row_id in response['data']:
                            results[batch_start + j] = response['data'][row_id]
                        else:
                            results[batch_start + j] = True
                else:
                    # 如果没有详细结果，标记该批次所有行为删除成功
                    for j in range(batch_start, min(batch_end, total_rows)):
                        results[j] = True

        return results

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
        all_rows_set = worksheet.rows().all()
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



