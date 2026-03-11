"""
工具类集合
"""

import re
import json
import time
import threading
import requests
from typing import Dict, Any, Optional, List, Union, Literal, Generator, Type, Callable
from decimal import Decimal


from ._base import console_log, _MAX_CONCURRENCY, _DEFAULT_BUFFER_SIZE, _ADAPTIVE_MIN_BUFFER_SIZE, _ADAPTIVE_SCALE_UP_FAST, _ADAPTIVE_SCALE_UP_SLOW, _ADAPTIVE_SCALE_DOWN, _ADAPTIVE_SCALE_DOWN_FAST, _DEFAULT_MAX_RETRIES, _DEFAULT_RETRY_DELAY


# 预编译正则表达式，提升性能
_UUID_PATTERN = re.compile(r'^[0-9a-f]{18,24}$', re.IGNORECASE)


# 自适应超时管理器
class AdaptiveTimeout:
    """自适应超时管理器，根据网络状况动态调整超时时间"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, base_connect: float = 5.0, base_read: float = 60.0):
        if not hasattr(self, '_initialized'):
            self.base_connect_timeout = base_connect
            self.base_read_timeout = base_read
            self.current_connect_timeout = base_connect
            self.current_read_timeout = base_read
            self.success_count = 0
            self.failure_count = 0
            self.total_response_time = 0.0
            self._stats_lock = threading.Lock()
            self._initialized = True
    
    def record_success(self, response_time: float):
        """记录成功请求"""
        with self._stats_lock:
            self.success_count += 1
            self.total_response_time += response_time
            if self.success_count >= 10:
                avg_response_time = self.total_response_time / self.success_count
                self.current_read_timeout = max(
                    self.base_read_timeout,
                    min(120.0, avg_response_time * 3)
                )
                self.current_connect_timeout = min(15.0, self.base_connect_timeout * 1.5)
                self.success_count = 0
                self.total_response_time = 0.0
    
    def record_failure(self):
        """记录失败请求"""
        with self._stats_lock:
            self.failure_count += 1
            if self.failure_count >= 3:
                self.current_connect_timeout = min(20.0, self.current_connect_timeout * 1.5)
                self.current_read_timeout = min(120.0, self.current_read_timeout * 1.3)
                self.failure_count = 0
    
    def get_timeout(self) -> tuple:
        """获取当前超时设置"""
        return (self.current_connect_timeout, self.current_read_timeout)
    
    def reset(self):
        """重置为默认超时"""
        with self._stats_lock:
            self.current_connect_timeout = self.base_connect_timeout
            self.current_read_timeout = self.base_read_timeout
            self.success_count = 0
            self.failure_count = 0
            self.total_response_time = 0.0



# 增强的重试策略类
class EnhancedRetryStrategy:
    """增强的重试策略，支持指数退避和抖动"""
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: float = 0.1
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        import random
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)
    
    def should_retry(self, attempt: int, status_code: int = None, exception: Exception = None) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        
        if status_code and status_code in (429, 500, 502, 503, 504):
            return True
        
        if exception:
            retryable_exceptions = (
                ConnectionError,
                TimeoutError,
                ConnectionResetError,
                ConnectionAbortedError
            )
            if isinstance(exception, retryable_exceptions):
                return True
        
        return False



# 令牌桶算法实现，用于控制QPS
class TokenBucket:
    """令牌桶算法实现，用于控制QPS"""
    def __init__(self, capacity: int, refill_rate: float):
        """
        初始化令牌桶
        :param capacity: 令牌桶容量
        :param refill_rate: 令牌生成速率（每秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill_time = time.time()
        self.lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        尝试消费令牌
        :param tokens: 需要消费的令牌数
        :return: 是否成功消费
        """
        with self.lock:
            # 先补充令牌
            now = time.time()
            time_passed = now - self.last_refill_time
            new_tokens = time_passed * self.refill_rate
            
            if new_tokens > 0:
                self.tokens = min(self.capacity, self.tokens + new_tokens)
                self.last_refill_time = now
            
            # 尝试消费令牌
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False
    
    def wait_for_token(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        等待直到获取到令牌
        :param tokens: 需要消费的令牌数
        :param timeout: 超时时间（秒）
        :return: 是否成功获取令牌
        """
        start_time = time.time()
        while True:
            if self.consume(tokens):
                return True
            
            if timeout is not None and time.time() - start_time > timeout:
                return False
            
            # 短暂睡眠，避免CPU占用过高
            time.sleep(min(0.1, max(0.001, tokens * 0.01)))



# 自定义JSON编码器，用于处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)



# 字符串intern池，减少重复字符串的内存占用
class StringInternPool:
    """字符串intern池，用于减少重复字符串的内存占用"""
    _instance = None
    _pool: Dict[str, str] = {}
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def intern(self, s: str) -> str:
        """Intern一个字符串，如果池中已存在则返回池中的版本"""
        if s in self._pool:
            return self._pool[s]
        with self._lock:
            if s not in self._pool:
                self._pool[s] = s
            return self._pool[s]



# 数据处理方法已合并到 HapUtils 类中



# 轻量级数据容器 - 使用__slots__减少内存占用
class LightweightRow:
    """轻量级行数据容器，使用__slots__减少内存占用"""
    __slots__ = ('_data', 'row_id')
    
    def __init__(self, data: dict = None):
        self._data = data or {}
        self.row_id = self._data.get('rowid') or self._data.get('rowId')
    
    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value
    
    def to_dict(self) -> dict:
        return self._data.copy()
    
    def get(self, key, default=None):
        return self._data.get(key, default)



# 对象池管理器
class ObjectPool:
    """通用对象池，用于复用对象减少内存分配"""
    
    def __init__(self, factory, max_size: int = 1000):
        self._factory = factory
        self._max_size = max_size
        self._pool: List = []
        self._lock = threading.Lock()
    
    def acquire(self):
        """获取一个对象"""
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self._factory()
    
    def release(self, obj):
        """归还一个对象"""
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)
    
    def clear(self):
        """清空对象池"""
        with self._lock:
            self._pool.clear()



class HapUtils:
    """
    明道云工具类，包含通用方法
    """
    
    @staticmethod
    def normalize_field_name(model, field_identifier: str) -> str:
        """
        将属性名或 field_name 标准化为 field_name
        
        Args:
            model: 模型类
            field_identifier: 属性名或 field_name
            
        Returns:
            str: 标准化后的 field_name
        """
        if not model:
            return field_identifier
        
        # 检查是否已经是 field_name
        try:
            reverse_map = model._get_reverse_field_map()
            if field_identifier in reverse_map:
                return field_identifier
        except Exception:
            pass
        
        # 检查是否是属性名
        try:
            field_map = model._get_field_map()
            if field_identifier in field_map:
                return field_map[field_identifier]
        except Exception:
            pass
        
        # 如果都不是，返回原标识符
        return field_identifier
    
    @staticmethod
    def normalize_data_fields(model, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据字典的字段名，将属性名转换为 field_name
        
        Args:
            model: 模型类
            data: 数据字典
            
        Returns:
            Dict[str, Any]: 标准化后的字段名
        """
        if not model or not data:
            return data
        
        normalized_data = {}
        for key, value in data.items():
            normalized_key = HapUtils.normalize_field_name(model, key)
            normalized_data[normalized_key] = value
        return normalized_data
    
    @staticmethod
    def map_api_fields_to_model_attrs(model, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 API 字段名映射到模型属性名
        
        Args:
            model: 模型类
            data: 数据字典，键为 API 字段名
            
        Returns:
            Dict[str, Any]: 映射后的数据字典，键为模型属性名
        """
        if not model or not data:
            return data
        
        mapped_data = {}
        reverse_field_map = model._get_reverse_field_map()
        
        for api_field, value in data.items():
            # 尝试将 API 字段名映射到模型属性名
            if api_field in reverse_field_map:
                model_attr = reverse_field_map[api_field]
                mapped_data[model_attr] = value
            else:
                # 如果无法映射，保留原字段名
                mapped_data[api_field] = value
        
        return mapped_data
    
    @staticmethod
    def convert_data_to_fieldslist(data: Dict[str, Any], exclude_none: bool = True, ignore_fields=[], field_map={}, remain_irrelevant_fields=True, model=None) -> List[Dict[str, Any]]:
        """
        将单个数据字典转换为工作表API字段值list
        
        Args:
            data: 行数据字典
            exclude_none: 是否排除值为None的字段
            ignore_fields: 忽略的字段列表
            field_map: 字段名称映射规则，将row_data_dict中的字段名称（键）映射为目标工作表control_id
            remain_irrelevant_fields: 是否保留 field_map 未提及的字段
            model: 当前的模型类，用于判断字段类型
            
        Returns:
            List[Dict[str, Any]]: 字段值列表
        """
        
        if exclude_none:
            # 删除值为None的键
            keys_to_delete = [k for k, v in data.items() if v is None]
            for k in keys_to_delete:
                del data[k]
        
        fieldlist = []
        for k, v in data.items():
            if k in ignore_fields: 
                continue
            
            # 标准化字段名，将属性名或field_name转换为field_name
            normalized_key = HapUtils.normalize_field_name(model, k)
            
            try:
                control_id = field_map.get(k, normalized_key)
            except:
                if remain_irrelevant_fields:
                    control_id = normalized_key
                else:
                    continue

            v_type = type(v)
            if v_type in (dict, list):
                # 检查是否需要 json.dumps
                need_json_dumps = True
                if model:
                    # 获取反向字段映射（field_name 到属性名）
                    reverse_field_map = model._get_reverse_field_map()
                    # 获取字段名（属性名）
                    field_name = reverse_field_map.get(control_id, k)
                    # 获取字段对象
                    field_obj = getattr(model, field_name, None)
                    # 检查字段类型
                    if hasattr(field_obj, '__class__'):
                        field_class_name = field_obj.__class__.__name__
                        # 如果不是文本字段，保留原格式
                        if field_class_name not in ['TextField']:
                            need_json_dumps = False
                
                if need_json_dumps:
                    fieldlist.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False, cls=DecimalEncoder)})
                else:
                    fieldlist.append({'id': control_id, 'value': v})
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
    def expression_to_filter_condition(expression, field_map: Optional[Dict[str, str]] = None):
        """
        将逻辑表达式字符串转换为筛选条件JSON结构

        参数:
            expression: 逻辑表达式字符串，格式如 "(age__gt=18 && status__in=[\"active\",\"pending\"]) || name__isempty"
            field_map: 属性名到 field_name 的映射字典，用于将属性名转换为字段名
            
        返回:
            符合明道云API要求的筛选条件JSON结构
        """
        # 处理None值
        if expression is None:
            return {}
        
        # 去除空白字符
        expression = ''.join(expression.split())
        
        def convert_field_name(field: str) -> str:
            """将属性名转换为 field_name"""
            if field_map and field in field_map:
                return field_map[field]
            return field
        
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
                        "field": convert_field_name(field.strip()),
                        "operator": "isempty",
                        "value": []
                    }
                elif '__isnotempty' in expression:
                    field = expression.replace('__isnotempty', '')
                    return {
                        "type": "condition",
                        "field": convert_field_name(field.strip()),
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
                    
                    # 转换字段名
                    field = convert_field_name(field.strip())
                    
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
                                        "field": field,
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
                            "field": field,
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
    
    @staticmethod
    def process_row_data(data: dict) -> dict:
        """
        一次性处理行数据，合并多个处理步骤
        包含：处理选项字段、排除未命名字段、排除系统字段
        
        Args:
            data: 原始数据字典
            
        Returns:
            dict: 处理后的数据字典
        """
        if not data:
            return {}
        
        processed = {}
        for k, v in data.items():
            if k.startswith('_'):
                continue
            
            if _UUID_PATTERN.match(k.lower()):
                continue
            
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'key' in v[0] and 'value' in v[0]:
                picked_options = [item['value'] for item in v]
                v = ','.join(picked_options)
            
            processed[k] = v
        
        return processed
    
    @staticmethod
    def process_batch(data_list: List[dict]) -> List[dict]:
        """批量处理数据字典列表"""
        return [HapUtils.process_row_data(data) for data in data_list]


# 连接池预热器
class ConnectionPoolWarmer:
    """连接池预热器
    
    预先建立连接，减少首次请求延迟。
    支持预热多个目标地址，提高并发性能。
    """
    
    def __init__(self, session: requests.Session, max_warm_connections: int = 5):
        """
        初始化连接池预热器
        
        Args:
            session: requests.Session 实例
            max_warm_connections: 最大预热连接数
        """
        self._session = session
        self._max_warm_connections = max_warm_connections
        self._warmed_urls = set()
        self._lock = threading.Lock()
    
    def warm_up(self, base_url: str, headers: dict = None, timeout: float = 5.0) -> bool:
        """
        预热连接池
        
        Args:
            base_url: 基础 URL
            headers: 请求头
            timeout: 超时时间
            
        Returns:
            bool: 是否成功预热
        """
        with self._lock:
            if base_url in self._warmed_urls:
                return True
            
            try:
                # 发送预热请求（HEAD 请求开销小）
                for i in range(self._max_warm_connections):
                    try:
                        response = self._session.head(
                            base_url,
                            headers=headers,
                            timeout=timeout
                        )
                        if response.status_code < 500:
                            console_log.info(f"连接池预热成功 [{i+1}/{self._max_warm_connections}]: {base_url}")
                        else:
                            console_log.warning(f"连接池预热返回状态码 {response.status_code}: {base_url}")
                    except Exception as e:
                        console_log.warning(f"连接池预热请求失败: {e}")
                        # 继续尝试其他连接
                
                self._warmed_urls.add(base_url)
                console_log.info(f"连接池预热完成: {base_url}")
                return True
                
            except Exception as e:
                console_log.error(f"连接池预热失败: {e}")
                return False
    
    def is_warmed(self, base_url: str) -> bool:
        """检查是否已预热"""
        with self._lock:
            return base_url in self._warmed_urls



# 智能批处理大小计算器
class SmartBatchSizeCalculator:
    """智能批处理大小计算器
    
    根据数据特征动态计算最优批次大小，提高处理效率。
    """
    
    def __init__(
        self,
        base_size: int = 200,
        min_size: int = 50,
        max_size: int = 500,
        field_threshold: int = 20,
        complexity_threshold: float = 1.0
    ):
        """
        初始化智能批处理大小计算器
        
        Args:
            base_size: 基础批次大小
            min_size: 最小批次大小
            max_size: 最大批次大小
            field_threshold: 字段数阈值
            complexity_threshold: 复杂度阈值
        """
        self.base_size = base_size
        self.min_size = min_size
        self.max_size = max_size
        self.field_threshold = field_threshold
        self.complexity_threshold = complexity_threshold
        self._history = []
    
    def calculate(
        self,
        data_size: int,
        field_count: int,
        complexity_score: float = 1.0,
        network_latency: float = 0.0
    ) -> int:
        """
        计算最优批次大小
        
        Args:
            data_size: 数据总量
            field_count: 字段数量
            complexity_score: 复杂度评分（1.0为基准）
            network_latency: 网络延迟（毫秒）
            
        Returns:
            int: 最优批次大小
        """
        # 基础大小
        optimal = self.base_size
        
        # 根据数据量调整
        if data_size > 10000:
            size_factor = 1.5  # 大数据量，增大批次
        elif data_size > 1000:
            size_factor = 1.2
        elif data_size < 100:
            size_factor = 0.8  # 小数据量，减小批次
        else:
            size_factor = 1.0
        
        # 根据字段数调整
        if field_count > self.field_threshold * 2:
            field_factor = 0.7  # 字段多，减小批次
        elif field_count > self.field_threshold:
            field_factor = 0.85
        elif field_count < 5:
            field_factor = 1.3  # 字段少，增大批次
        else:
            field_factor = 1.0
        
        # 根据复杂度调整
        if complexity_score > self.complexity_threshold * 2:
            complexity_factor = 0.6
        elif complexity_score > self.complexity_threshold:
            complexity_factor = 0.8
        elif complexity_score < 0.5:
            complexity_factor = 1.2
        else:
            complexity_factor = 1.0
        
        # 根据网络延迟调整
        if network_latency > 500:
            latency_factor = 1.4  # 高延迟，增大批次减少请求数
        elif network_latency > 200:
            latency_factor = 1.2
        elif network_latency < 50:
            latency_factor = 0.9  # 低延迟，可以减小批次
        else:
            latency_factor = 1.0
        
        # 计算最终批次大小
        optimal = int(
            self.base_size * 
            size_factor * 
            field_factor * 
            complexity_factor * 
            latency_factor
        )
        
        # 限制在合理范围内
        optimal = max(self.min_size, min(self.max_size, optimal))
        
        # 记录历史
        self._history.append({
            'data_size': data_size,
            'field_count': field_count,
            'complexity': complexity_score,
            'latency': network_latency,
            'batch_size': optimal
        })
        
        return optimal
    
    def get_average_batch_size(self, last_n: int = 10) -> float:
        """获取最近 N 次的平均批次大小"""
        if not self._history:
            return self.base_size
        recent = self._history[-last_n:]
        return sum(h['batch_size'] for h in recent) / len(recent)
    
    def get_recommendation(self) -> dict:
        """获取优化建议"""
        if len(self._history) < 5:
            return {'message': '数据不足，无法提供建议'}
        
        avg_size = self.get_average_batch_size()
        recent = self._history[-10:]
        
        # 分析趋势
        if len(recent) >= 5:
            first_half = sum(h['batch_size'] for h in recent[:5]) / 5
            second_half = sum(h['batch_size'] for h in recent[5:]) / 5
            trend = 'increasing' if second_half > first_half * 1.1 else \
                    'decreasing' if second_half < first_half * 0.9 else 'stable'
        else:
            trend = 'unknown'
        
        return {
            'average_batch_size': avg_size,
            'trend': trend,
            'recommendation': '考虑调整基础批次大小' if trend != 'stable' else '当前配置良好',
            'history_count': len(self._history)
        }



# 自适应速率控制器
class AdaptiveRateController:
    """自适应速率控制器
    
    根据网络状况和 QPS 动态调整 buffer_size 和 max_concurrency。
    
    核心机制：
    1. 监控请求成功率和响应时间
    2. 根据成功率动态调整并发数
    3. 根据响应时间动态调整缓冲区大小
    4. 遇到错误时自动降速
    """
    
    def __init__(
        self,
        initial_buffer_size: int = None,
        initial_concurrency: int = None,
        min_buffer_size: int = None,
        max_buffer_size: int = None,
        min_concurrency: int = 1,
        max_concurrency: int = None,
        target_qps: float = 10.0,
        adjustment_interval: int = 5,
    ):
        """
        初始化自适应速率控制器
        
        Args:
            initial_buffer_size: 初始缓冲区大小，None 时根据 QPS 自动计算
            initial_concurrency: 初始并发数，None 时根据 QPS 自动计算
            min_buffer_size: 最小缓冲区大小，None 时使用配置默认值
            max_buffer_size: 最大缓冲区大小，None 时根据 QPS 自动计算
            min_concurrency: 最小并发数
            max_concurrency: 最大并发数，None 时根据 QPS 自动计算
            target_qps: 目标 QPS（每秒请求数）
            adjustment_interval: 调整间隔（每 N 个请求调整一次）
        """
        # 使用配置的默认值
        if min_buffer_size is None:
            min_buffer_size = _ADAPTIVE_MIN_BUFFER_SIZE
        
        # 根据 QPS 自动计算参数
        if initial_buffer_size is None:
            initial_buffer_size = min(500, max(100, int(target_qps * 5)))
        if initial_concurrency is None:
            initial_concurrency = min(10, max(_MAX_CONCURRENCY, int(target_qps / 10)))
        if max_buffer_size is None:
            max_buffer_size = min(1000, max(300, int(target_qps * 10)))
        if max_concurrency is None:
            max_concurrency = min(20, max(_MAX_CONCURRENCY, int(target_qps / 5)))
        
        self.buffer_size = initial_buffer_size
        self.concurrency = initial_concurrency
        
        self.min_buffer_size = min_buffer_size
        self.max_buffer_size = max_buffer_size
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.target_qps = target_qps
        self.adjustment_interval = adjustment_interval
        
        # 统计数据
        self.request_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_response_time = 0.0
        self.recent_response_times = []
        self.recent_failures = []
        self._lock = threading.Lock()
    
    def record_request(self, success: bool, response_time: float):
        """记录请求结果"""
        with self._lock:
            self.request_count += 1
            if success:
                self.success_count += 1
                self.total_response_time += response_time
                self.recent_response_times.append(response_time)
                # 保留最近 20 次响应时间
                if len(self.recent_response_times) > 20:
                    self.recent_response_times.pop(0)
            else:
                self.failure_count += 1
                self.recent_failures.append(response_time)
                # 保留最近 10 次失败
                if len(self.recent_failures) > 10:
                    self.recent_failures.pop(0)
    
    def adjust(self) -> tuple:
        """根据统计数据调整参数
        
        Returns:
            tuple: (new_buffer_size, new_concurrency)
        """
        with self._lock:
            # 每隔一定请求数才调整
            if self.request_count % self.adjustment_interval != 0:
                return self.buffer_size, self.concurrency
            
            # 计算成功率
            total = self.success_count + self.failure_count
            success_rate = self.success_count / total if total > 0 else 1.0
            
            # 计算平均响应时间
            avg_response_time = (
                sum(self.recent_response_times) / len(self.recent_response_times)
                if self.recent_response_times else 1.0
            )
            
            # 计算当前 QPS
            current_qps = 1.0 / avg_response_time if avg_response_time > 0 else 1.0
            
            # 调整策略
            new_buffer_size = self.buffer_size
            new_concurrency = self.concurrency
            
            # 成功率高且 QPS 低于目标 -> 激进提速
            if success_rate > 0.90 and current_qps < self.target_qps:
                # 大幅增加缓冲区（减少请求次数）
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_UP_FAST))
                # 大幅增加并发（提高吞吐量）
                new_concurrency = min(self.max_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_UP_FAST))
            
            # 成功率一般但 QPS 远低于目标 -> 温和提速
            elif success_rate > 0.85 and current_qps < self.target_qps * 0.5:
                # 增加缓冲区
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_UP_SLOW))
                # 增加并发
                new_concurrency = min(self.max_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_UP_SLOW))
            
            # 成功率低或响应时间过长 -> 降速
            elif success_rate < 0.75 or avg_response_time > 10.0:
                # 减小缓冲区（更频繁但更小的请求）
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_DOWN))
                # 减少并发（降低服务器压力）
                new_concurrency = max(self.min_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_DOWN))
            
            # 连续失败 -> 大幅降速
            elif len(self.recent_failures) >= 3:
                # 大幅减小缓冲区（更多失败时）
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_DOWN_FAST))
                # 大幅减少并发（失败时降低服务器压力）
                new_concurrency = max(self.min_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_DOWN_FAST))
            
            # 更新参数
            self.buffer_size = new_buffer_size
            self.concurrency = new_concurrency
            
            return new_buffer_size, new_concurrency
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        with self._lock:
            total = self.success_count + self.failure_count
            return {
                "request_count": self.request_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "success_rate": self.success_count / total if total > 0 else 1.0,
                "buffer_size": self.buffer_size,
                "concurrency": self.concurrency,
                "avg_response_time": (
                    sum(self.recent_response_times) / len(self.recent_response_times)
                    if self.recent_response_times else 0
                ),
            }



# HAP API 请求监控器
class HapApiMonitor:
    """HAP API 请求监控器
    
    记录所有向 HAP 发起的 API 请求，包括：
    - 请求时间、方法、URL
    - 请求参数、响应时间
    - 成功/失败状态
    - 错误信息
    """
    
    def __init__(self):
        """初始化监控器"""
        self._lock = threading.Lock()
        self._requests = []
        self._max_records = 1000  # 最多保留 1000 条记录
    
    def record_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None,
        response_time: float = 0.0,
        success: bool = True,
        status_code: int = None,
        error: str = None
    ):
        """记录 API 请求
        
        Args:
            method: HTTP 方法（GET, POST, PATCH, DELETE）
            endpoint: API 端点
            params: 请求参数
            data: 请求体数据
            response_time: 响应时间（秒）
            success: 是否成功
            status_code: HTTP 状态码
            error: 错误信息
        """
        import time
        
        record = {
            "timestamp": time.time(),
            "method": method,
            "endpoint": endpoint,
            "params": params,
            "data": data,
            "response_time": response_time,
            "success": success,
            "status_code": status_code,
            "error": error
        }
        
        with self._lock:
            self._requests.append(record)
            # 限制记录数量
            if len(self._requests) > self._max_records:
                self._requests = self._requests[-self._max_records:]
    
    def get_stats(self, last_n: int = 100) -> dict:
        """获取统计数据
        
        Args:
            last_n: 统计最近 N 条记录
            
        Returns:
            dict: 统计信息
        """
        with self._lock:
            records = self._requests[-last_n:] if last_n else self._requests
            
            if not records:
                return {
                    "total": 0,
                    "success": 0,
                    "failure": 0,
                    "success_rate": 0.0,
                    "avg_response_time": 0.0,
                    "requests": []
                }
            
            total = len(records)
            success = sum(1 for r in records if r["success"])
            failure = total - success
            avg_response_time = sum(r["response_time"] for r in records) / total
            
            # 按端点统计
            endpoint_stats = {}
            for r in records:
                endpoint = r["endpoint"]
                if endpoint not in endpoint_stats:
                    endpoint_stats[endpoint] = {
                        "count": 0,
                        "success": 0,
                        "avg_response_time": 0.0
                    }
                endpoint_stats[endpoint]["count"] += 1
                if r["success"]:
                    endpoint_stats[endpoint]["success"] += 1
                endpoint_stats[endpoint]["avg_response_time"] += r["response_time"]
            
            # 计算每个端点的平均响应时间
            for stats in endpoint_stats.values():
                stats["success_rate"] = stats["success"] / stats["count"] if stats["count"] > 0 else 0
                stats["avg_response_time"] /= stats["count"]
            
            return {
                "total": total,
                "success": success,
                "failure": failure,
                "success_rate": success / total if total > 0 else 0,
                "avg_response_time": avg_response_time,
                "endpoint_stats": endpoint_stats,
                "requests": records[-10:]  # 最近 10 条记录
            }
    
    def get_recent_errors(self, limit: int = 10) -> list:
        """获取最近的错误记录
        
        Args:
            limit: 返回的记录数
            
        Returns:
            list: 错误记录列表
        """
        with self._lock:
            errors = [r for r in self._requests if not r["success"]]
            return errors[-limit:]
    
    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._requests.clear()



# 统计 HAP 异步操作执行时间的装饰器
def hap_async_timer(func: Callable = None, *, operation_name: str = None):
    """统计 HAP 异步操作执行时间的装饰器
    
    用于装饰 async 函数，记录其执行时间、操作名称、数据条数等信息。
    
    Args:
        func: 被装饰的函数
        operation_name: 操作名称，默认使用函数名
    
    Returns:
        装饰后的函数
    
    Example:
        >>> @hap_async_timer()
        >>> async def my_operation():
        >>>     pass
        >>>
        >>> @hap_async_timer(operation_name="自定义操作")
        >>> async def my_operation():
        >>>     pass
    """
    def decorator(fn: Callable) -> Callable:
        import time
        import logging
        import functools
        
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or fn.__name__
            start_time = time.time()
            result = None
            error = None
            data_count = 0
            
            try:
                result = await fn(*args, **kwargs)
                
                if hasattr(result, 'count'):
                    data_count = result.count()
                elif hasattr(result, '__len__'):
                    data_count = len(result)
                elif isinstance(result, int):
                    data_count = result
                
                return result
            except Exception as e:
                error = e
                raise
            finally:
                elapsed_time = time.time() - start_time
                
                log_info = {
                    "operation": op_name,
                    "elapsed_time": f"{elapsed_time:.3f}s",
                    "data_count": data_count,
                }
                
                if elapsed_time > 0:
                    data_rate_per_second = data_count / elapsed_time
                    log_info["data_rate_per_second"] = f"{data_rate_per_second:.2f}条/秒"
                else:
                    log_info["data_rate_per_second"] = "N/A"
                
                if error:
                    log_info["status"] = "FAILED"
                    log_info["error"] = str(error)
                    console_log.warning(f"HAP异步操作统计 | {log_info}")
                else:
                    log_info["status"] = "SUCCESS"
                    console_log.info(f"HAP异步操作统计 | {log_info}")
        
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)


