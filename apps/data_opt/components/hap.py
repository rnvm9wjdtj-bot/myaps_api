"""明道云 API v3 封装为 ORM """

import json
import re
from typing import List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel as PydanticModel
from decimal import Decimal



# 自定义JSON编码器，用于处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)



from ._base import get_session


hap_example_url = ('https://api.mingdao.com', 'http://127.0.0.1:8080/api')



class HapConnection:
    def __init__(self, app_key: str, sign: str, base_url: str=hap_example_url[0]):
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
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


    def _delete(self, endpoint: str, params: dict=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.delete(url, headers=self.headers, params=params)
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
        self.hap_conn = hap_conn
        

    def rows(self, filter_condition: Optional[str] = None, sorts: Optional[str] = None) -> 'HapRowsQuery':
        """获取行查询对象
        
        Args:
            filter_condition: 过滤条件表达式，如 "name='test' && age>18"
            
        Returns:
            HapRowsQuery: 行查询对象，支持链式调用
        """
        return HapRowsQuery(worksheet_id=self.worksheet_id, hap_conn=self.hap_conn, filter_condition=filter_condition, sorts=sorts)
        

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
                if k not in ('rowid', 'ctime', 'utime', 'caid', 'uaid', 'ownerid'):
                    if type(v) == list:
                        v = [item['value'] for item in v]
                        row_dict[k] = ','.join(v)
                    else:
                        row_dict[k] = v

            if exclude_unamed_fields:
                row_dict = self._exclude_unamed_fields(row_dict)
            if exclude_sys_fields:
                row_dict = self._exclude_sys_fields(row_dict)
        
        return HapWorksheetRow(
            row_data=row_dict, 
            row_id=row_id, 
            worksheet_id=self.worksheet_id, 
            hap_conn=self.hap_conn
        )



    def create_rows(self, data_list: List[Dict[str, Any]], trigger_workflow: bool = True) -> List['HapWorksheetRow']:
        """创建新行
        
        Args:
            data_list: 行数据字典列表
            
        Returns:
            List[HapWorksheetRow]: 新创建的行对象列表
        """
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/batch"
        payload = {
            "rows": self._rows_data_to_controls_list(data_list),
            "triggerWorkflow": trigger_workflow
        }
        response = self.hap_conn._post(endpoint, payload)
        
        row_ids = response.get('data', {}).get('rowIds', [])
        return [
            HapWorksheetRow(
                row_data=data, 
                row_id=row_id, 
                worksheet_id=self.worksheet_id, 
                hap_conn=self.hap_conn
            )
            for data, row_id in zip(data_list, row_ids)
        ]


    @classmethod
    def _rows_data_to_controls_list(cls, rows_data_list: list[dict | PydanticModel], ignore_fields=[], controls_reflection={}, remain_irrelevant_fields=True):
        """
        将行数据字典转换为工作表API字段值list
        controls_reflection 是一个可选参数，用于将row_data_dict中的字段名称（键）映射为目标工作表control_id
        remain_irrelevant_fields 是否保留 controls_reflection 未提及的字段
        """
        controls_list = []
        for data_dict in rows_data_list:
            row_controls_list = []
            controls_list.append({'fields': row_controls_list})
            if isinstance(data_dict, PydanticModel):
                data_dict = data_dict.model_dump(exclude_unset=True)
            for k, v in data_dict.items():
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
                    row_controls_list.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False, cls=DecimalEncoder)})
                elif v_type in (int, float, Decimal):
                    row_controls_list.append({'id': control_id, 'value': float(v), 'type': 2})
                elif v_type == str:
                    row_controls_list.append({'id': control_id, 'value': v, 'type': 2})
                else:
                    pass
        return controls_list

    

class HapRowsQuery:
    """行查询类，支持链式查询操作"""
    def __init__(self, worksheet_id: str, hap_conn: HapConnection, filter_condition: str = None, sorts: str = None):
        self.worksheet_id = worksheet_id
        self.hap_conn = hap_conn
        self.filter_condition = filter_condition
        self.page_size = 1000
        self.page_index = 1
        self.sorts = sorts
        self.limit = None
        

    def filter(self, filter_condition: str) -> 'HapRowsQuery':
        """添加过滤条件
        
        Args:
            filter_condition: 过滤条件表达式
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.filter_condition = filter_condition
        return self
        

    def sort(self, sorts: str) -> 'HapRowsQuery':
        """添加排序条件
        
        Args:
            sorts: 排序字符串，格式如 "x,-y"，其中 "-" 表示降序
            
        Returns:
            HapRowsQuery: 自身，支持链式调用
        """
        self.sorts = sorts
        return self

        
    def limit(self, limit: int) -> 'HapRowsQuery':
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

        
    def _execute_query(self, page_size: int, include_total: bool = True) -> List['HapWorksheetRow']:
        """执行查询并返回结果
        
        Args:
            page_size: 查询的每页记录数
            include_total: 是否包含总记录数
            
        Returns:
            List[HapWorksheetRow]: 行对象列表
        """
        # 构建查询参数
        payload = {
            "pageSize": page_size,
            "pageIndex": self.page_index,
            "includeTotalCount": include_total,
        }
        
        # 添加过滤条件
        if self.filter_condition:
            filter_condtion = self._expression_to_filter_condtion(self.filter_condition)
            payload["filter"] = filter_condtion
        
        # 添加排序条件
        if self.sorts:
            payload['sorts'] = self._str_to_sort_list(self.sorts)
        
        # 发送请求
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/list"
        response = self.hap_conn._post(endpoint=endpoint, payload=payload)
        
        # 处理响应
        rows = []
        if response.get('success'):
            for row_dict in response.get('data', {}).get('rows', []):
                rows.append(HapWorksheetRow(
                    row_data=row_dict,
                    row_id=row_dict.get('rowId'),
                    worksheet_id=self.worksheet_id,
                    hap_conn=self.hap_conn
                ))
        
        return rows

    def first(self) -> Optional['HapWorksheetRow']:
        """获取第一条记录
        
        Returns:
            Optional[HapWorksheetRow]: 行对象，如果没有记录则返回None
        """
        # 只获取一条记录，不包含总数
        rows = self._execute_query(page_size=1, include_total=False)
        return rows[0] if rows else None

        
    def all(self) -> List['HapWorksheetRow']:
        """获取所有匹配的记录
        
        Returns:
            List[HapWorksheetRow]: 行对象列表
        """
        # 获取指定页大小的记录，包含总数
        page_size = min(self.limit, self.page_size) if self.limit else self.page_size
        rows = self._execute_query(page_size=page_size, include_total=True)
        
        # 应用limit
        if self.limit:
            rows = rows[:self.limit]
        
        return rows



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
    #         filter_condtion = self.hap_conn._expression_to_filter_condtion(self.filter_condition)
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
    def _expression_to_filter_condtion(cls, expression: str) -> dict:
        """
        将逻辑表达式字符串转换为筛选条件JSON结构
        
        参数:
            expression: 逻辑表达式字符串，格式如 "(a=1 && b=2) || c=3 || (d=4 && (e=5 || f=6))"
            
        返回:
            符合明道云API要求的筛选条件JSON结构
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
                # 分割字段名和值
                if '=' in expression:
                    field, value = expression.split('=', 1)
                    return {
                        "type": "condition",
                        "field": field,
                        "operator": "eq",
                        "value": [value]
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
    def __init__(self, row_data: dict, row_id: str = None, worksheet_id: str = None, hap_conn: HapConnection = None):
        self.row_data = row_data
        self.worksheet_id = worksheet_id
        self.row_id = row_id
        self.hap_conn = hap_conn
        self.worksheet = HapWorksheet(worksheet_id=self.worksheet_id, hap_conn=self.hap_conn)
        
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
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/{self.row_id}"
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
        
        endpoint = f"/v3/app/worksheets/{self.worksheet_id}/rows/{self.row_id}"
        params = {"permanent": permanent, "triggerWorkflow": trigger_workflow}
        response = self.hap_conn._delete(endpoint=endpoint, params=params)
        
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
        new_row = worksheet.create_rows([{
            "name": "测试用户",
            "age": 25,
            "email": "test@example.com"
        }])
        print(f"创建新行: {new_row}")
        
        # 3. 查询行
        # 获取所有行
        all_rows = worksheet.rows().all()
        print(f"所有行数量: {len(all_rows)}")
        
        # 根据条件查询
        filtered_rows = worksheet.rows("name='测试用户' && age>20").all()
        print(f"筛选行数量: {len(filtered_rows)}")
        
        # 获取第一条匹配的行
        first_row = worksheet.rows("name='测试用户'").first()
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
        rows = worksheet.rows("age>18")\
            .order("age", "desc")\
            .limit(10)\
            .all()
        
        print(f"查询结果数量: {len(rows)}")
        for i, row in enumerate(rows):
            print(f"行 {i+1}: {row.to_dict()}")


    def example_count_query():
        """计数查询示例"""
        print("\n=== 计数查询示例 ===")
        
        worksheet = hapconn.worksheet("worksheet_name")
        
        # 计算符合条件的行数
        total_count = worksheet.rows("status='active'").count()
        print(f"活跃用户数量: {total_count}")


    def example_row_operations():
        """行操作示例"""
        print("\n=== 行操作示例 ===")
        
        worksheet = hapconn.worksheet("worksheet_name")
        
        # 创建新行
        row = worksheet.create_rows([{
            "name": "操作测试",
            "status": "pending"
        }])[0]
        
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



