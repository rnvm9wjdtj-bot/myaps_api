from typing import List, Dict, Any, Tuple, Optional, Union, Literal, Callable
from contextlib import asynccontextmanager
from datetime import datetime
import time
import asyncio
import functools
import re

from tortoise import Tortoise
from tortoise.connection import connections
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError

from core.settings import MYAPS_DBSET_LIST
from globalobjects import logger as log_config
from apps.common.utils.redis_pool_manager import get_redis_client
import os
import uuid

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


def escape_sql_value(value: Any) -> str:
    """
    安全转义SQL值，防止SQL注入
    
    Args:
        value: 要转义的值
        
    Returns:
        转义后的安全字符串
    """
    if value is None:
        return "NULL"
    
    if isinstance(value, bool):
        return "1" if value else "0"
    
    if isinstance(value, (int, float)):
        return str(value)
    
    if isinstance(value, datetime):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    
    # 字符串处理：转义单引号
    str_value = str(value)
    # 将单引号转义为两个单引号（SQL标准）
    escaped = str_value.replace("'", "''")
    return f"'{escaped}'"


def validate_identifier(identifier: str) -> str:
    """
    验证并安全化SQL标识符（表名、字段名）
    
    Args:
        identifier: 标识符
        
    Returns:
        安全的标识符（用反引号包裹）
        
    Raises:
        ValueError: 如果标识符包含危险字符
    """
    # 移除首尾空格
    identifier = identifier.strip()
    
    # 检查危险字符
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', '\x00', '\n', '\r']
    for char in dangerous_chars:
        if char in identifier:
            raise ValueError(f"Invalid identifier: contains dangerous character '{char}'")
    
    # 用反引号包裹
    return f"`{identifier}`"


def build_safe_condition(field: str, operator: str, value: Any) -> str:
    """
    构建安全的SQL条件表达式
    
    Args:
        field: 字段名
        operator: 操作符 (=, !=, >, <, >=, <=, LIKE, IN)
        value: 值
        
    Returns:
        安全的SQL条件字符串
    """
    safe_field = validate_identifier(field)
    operator = operator.upper().strip()
    
    if operator == "IN":
        if not isinstance(value, (list, tuple)):
            raise ValueError("IN operator requires a list or tuple of values")
        escaped_values = [escape_sql_value(v) for v in value]
        return f"{safe_field} IN ({', '.join(escaped_values)})"
    
    if operator == "LIKE":
        return f"{safe_field} LIKE {escape_sql_value(value)}"
    
    # 标准比较操作符
    valid_operators = ['=', '!=', '<>', '>', '<', '>=', '<=', 'IS', 'IS NOT']
    if operator not in valid_operators:
        raise ValueError(f"Invalid operator: {operator}")
    
    if operator in ('IS', 'IS NOT'):
        if value is None:
            return f"{safe_field} {operator} NULL"
        raise ValueError(f"{operator} operator only accepts None value")
    
    return f"{safe_field} {operator} {escape_sql_value(value)}"


def build_safe_filter(conditions: List[Tuple[str, str, Any]], logic: str = "AND") -> str:
    """
    构建安全的WHERE条件字符串
    
    Args:
        conditions: 条件列表，每个条件为 (字段名, 操作符, 值) 元组
        logic: 逻辑连接符 (AND/OR)
        
    Returns:
        安全的WHERE条件字符串
    """
    if not conditions:
        return ""
    
    logic = logic.upper().strip()
    if logic not in ("AND", "OR"):
        raise ValueError(f"Invalid logic operator: {logic}")
    
    safe_conditions = [build_safe_condition(*cond) for cond in conditions]
    return f" {logic} ".join(safe_conditions)


def build_safe_order_by(fields: List[Tuple[str, str]]) -> str:
    """
    构建安全的ORDER BY子句
    
    Args:
        fields: 排序字段列表，每个元素为 (字段名, 方向) 元组
                方向为 'ASC' 或 'DESC'
                
    Returns:
        安全的ORDER BY字符串
    """
    if not fields:
        return ""
    
    order_parts = []
    for field, direction in fields:
        safe_field = validate_identifier(field)
        direction = direction.upper().strip()
        if direction not in ("ASC", "DESC"):
            raise ValueError(f"Invalid order direction: {direction}")
        order_parts.append(f"{safe_field} {direction}")
    
    return ", ".join(order_parts)


def build_safe_select(fields: List[str]) -> str:
    """
    构建安全的SELECT字段列表
    
    Args:
        fields: 字段名列表
        
    Returns:
        安全的SELECT字段字符串
    """
    if not fields:
        return "*"
    
    return ", ".join(validate_identifier(f) for f in fields)


class SafeQueryBuilder:
    """
    安全SQL查询构建器
    
    提供链式调用的SQL构建接口，自动处理转义和验证
    """
    
    def __init__(self, table_name: str):
        """
        初始化查询构建器
        
        Args:
            table_name: 表名
        """
        self._table = validate_identifier(table_name)
        self._select_fields = "*"
        self._conditions = []
        self._order_fields = []
        self._limit = None
        self._offset = None
    
    def select(self, *fields: str) -> 'SafeQueryBuilder':
        """设置SELECT字段"""
        if fields:
            self._select_fields = build_safe_select(list(fields))
        return self
    
    def where(self, field: str, operator: str, value: Any) -> 'SafeQueryBuilder':
        """添加WHERE条件"""
        self._conditions.append((field, operator, value))
        return self
    
    def where_in(self, field: str, values: List[Any]) -> 'SafeQueryBuilder':
        """添加IN条件"""
        self._conditions.append((field, "IN", values))
        return self
    
    def where_like(self, field: str, pattern: str) -> 'SafeQueryBuilder':
        """添加LIKE条件"""
        self._conditions.append((field, "LIKE", pattern))
        return self
    
    def where_between(self, field: str, start: Any, end: Any) -> 'SafeQueryBuilder':
        """添加BETWEEN条件"""
        safe_field = validate_identifier(field)
        self._conditions.append((f"{safe_field} >= {escape_sql_value(start)}", "=", True))
        self._conditions.append((f"{safe_field} <= {escape_sql_value(end)}", "=", True))
        return self
    
    def order_by(self, field: str, direction: str = "ASC") -> 'SafeQueryBuilder':
        """添加排序"""
        self._order_fields.append((field, direction))
        return self
    
    def limit(self, count: int) -> 'SafeQueryBuilder':
        """设置LIMIT"""
        if count > 0:
            self._limit = count
        return self
    
    def offset(self, count: int) -> 'SafeQueryBuilder':
        """设置OFFSET"""
        if count >= 0:
            self._offset = count
        return self
    
    def build_select_sql(self) -> str:
        """构建SELECT SQL语句"""
        sql = f"SELECT {self._select_fields} FROM {self._table}"
        
        if self._conditions:
            where_clause = build_safe_filter(self._conditions)
            sql += f" WHERE {where_clause}"
        
        if self._order_fields:
            order_clause = build_safe_order_by(self._order_fields)
            sql += f" ORDER BY {order_clause}"
        
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"
        
        return sql
    
    def build_count_sql(self) -> str:
        """构建COUNT SQL语句"""
        sql = f"SELECT COUNT(*) as total FROM {self._table}"
        
        if self._conditions:
            where_clause = build_safe_filter(self._conditions)
            sql += f" WHERE {where_clause}"
        
        return sql
    
    def build_delete_sql(self) -> str:
        """构建DELETE SQL语句"""
        if not self._conditions:
            raise ValueError("DELETE operation requires WHERE conditions for safety")
        
        where_clause = build_safe_filter(self._conditions)
        return f"DELETE FROM {self._table} WHERE {where_clause}"


def dict_to_lower_keys(d: dict) -> dict:
    """
    将字典的键转换为小写
    """
    return {k.lower(): v for k, v in d.items()}


class DbManagerError(Exception):
    """数据库管理错误基类"""
    def __init__(self, message, operation=None, table=None, connection=None):
        self.message = message
        self.operation = operation
        self.table = table
        self.connection = connection
        super().__init__(message)
    
    def to_dict(self):
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "operation": self.operation,
            "table": self.table,
            "connection": self.connection
        }


class DbConnectionError(DbManagerError):
    """数据库连接错误"""
    pass


class DbQueryError(DbManagerError):
    """数据库查询错误"""
    pass


class DbTransactionError(DbManagerError):
    """数据库事务错误"""
    pass


class DbDeadlockError(DbManagerError):
    """数据库死锁错误"""
    pass


class DbCircuitBreakerError(DbManagerError):
    """数据库熔断错误"""
    pass


class DeadlockCircuitBreaker:
    """
    死锁熔断保护类（使用Redis实现跨进程状态共享）
    
    实现基于时间窗口的熔断机制，当单位时间内死锁次数超过阈值时触发熔断，
    熔断期间所有请求直接失败，避免系统雪崩。
    
    状态机：
    CLOSED（闭合）-> 正常处理请求
    OPEN（打开）-> 熔断状态，拒绝请求
    HALF_OPEN（半开）-> 尝试恢复，允许部分请求通过
    """
    
    def __init__(
        self, 
        name: str = "default",
        threshold: int = 5, 
        window_seconds: int = 60, 
        cooldown_seconds: int = 30,
        half_open_attempts: int = 2
    ):
        """
        初始化熔断器
        
        Args:
            name: 熔断器名称，用于Redis键名
            threshold: 时间窗口内的最大死锁次数（超过此值触发熔断）
            window_seconds: 时间窗口大小（秒）
            cooldown_seconds: 熔断持续时间（秒）
            half_open_attempts: 半开状态下允许的尝试次数
        """
        self.name = name
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.half_open_attempts = half_open_attempts
        
        # 状态常量
        self.STATE_CLOSED = "closed"
        self.STATE_OPEN = "open"
        self.STATE_HALF_OPEN = "half_open"
        
        # Redis键名前缀
        self._redis_prefix = f"myaps:circuitbreaker:{name}"
    
    def _get_redis_state_key(self) -> str:
        """获取状态的Redis键名"""
        return f"{self._redis_prefix}:state"
    
    def _get_redis_deadlock_count_key(self) -> str:
        """获取死锁计数器的Redis键名"""
        return f"{self._redis_prefix}:deadlock_count"
    
    def _get_redis_window_start_key(self) -> str:
        """获取时间窗口开始时间的Redis键名"""
        return f"{self._redis_prefix}:window_start"
    
    def _get_redis_open_time_key(self) -> str:
        """获取熔断打开时间的Redis键名"""
        return f"{self._redis_prefix}:open_time"
    
    def _get_redis_half_open_success_key(self) -> str:
        """获取半开成功计数的Redis键名"""
        return f"{self._redis_prefix}:half_open_success"
    
    def _get_redis_half_open_failure_key(self) -> str:
        """获取半开失败计数的Redis键名"""
        return f"{self._redis_prefix}:half_open_failure"
    
    def _get_state(self) -> str:
        """从Redis获取当前状态"""
        client = get_redis_client()
        if client:
            try:
                state = client.get(self._get_redis_state_key())
                if state:
                    return state.decode('utf-8')
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取熔断状态失败: {e}"
                )
        return self.STATE_CLOSED
    
    def _set_state(self, state: str):
        """设置状态到Redis"""
        client = get_redis_client()
        if client:
            try:
                client.set(self._get_redis_state_key(), state)
                client.expire(self._get_redis_state_key(), self.window_seconds + self.cooldown_seconds + 60)
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置熔断状态失败: {e}"
                )
    
    def _get_deadlock_count(self) -> int:
        """从Redis获取死锁计数"""
        client = get_redis_client()
        if client:
            try:
                count = client.get(self._get_redis_deadlock_count_key())
                return int(count) if count else 0
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取死锁计数失败: {e}"
                )
        return 0
    
    def _set_deadlock_count(self, count: int):
        """设置死锁计数到Redis"""
        client = get_redis_client()
        if client:
            try:
                client.set(self._get_redis_deadlock_count_key(), count)
                client.expire(self._get_redis_deadlock_count_key(), self.window_seconds + 60)
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置死锁计数失败: {e}"
                )
    
    def _get_window_start_time(self) -> float:
        """从Redis获取时间窗口开始时间"""
        client = get_redis_client()
        if client:
            try:
                start_time = client.get(self._get_redis_window_start_key())
                return float(start_time) if start_time else time.time()
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取时间窗口开始时间失败: {e}"
                )
        return time.time()
    
    def _set_window_start_time(self, start_time: float):
        """设置时间窗口开始时间到Redis"""
        client = get_redis_client()
        if client:
            try:
                client.set(self._get_redis_window_start_key(), start_time)
                client.expire(self._get_redis_window_start_key(), self.window_seconds + 60)
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置时间窗口开始时间失败: {e}"
                )
    
    def _get_open_time(self) -> Optional[float]:
        """从Redis获取熔断打开时间"""
        client = get_redis_client()
        if client:
            try:
                open_time = client.get(self._get_redis_open_time_key())
                return float(open_time) if open_time else None
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取熔断打开时间失败: {e}"
                )
        return None
    
    def _set_open_time(self, open_time: Optional[float]):
        """设置熔断打开时间到Redis"""
        client = get_redis_client()
        if client:
            try:
                if open_time:
                    client.set(self._get_redis_open_time_key(), open_time)
                    client.expire(self._get_redis_open_time_key(), self.cooldown_seconds + 60)
                else:
                    client.delete(self._get_redis_open_time_key())
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置熔断打开时间失败: {e}"
                )
    
    def _get_half_open_success_count(self) -> int:
        """从Redis获取半开成功计数"""
        client = get_redis_client()
        if client:
            try:
                count = client.get(self._get_redis_half_open_success_key())
                return int(count) if count else 0
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取半开成功计数失败: {e}"
                )
        return 0
    
    def _set_half_open_success_count(self, count: int):
        """设置半开成功计数到Redis"""
        client = get_redis_client()
        if client:
            try:
                client.set(self._get_redis_half_open_success_key(), count)
                client.expire(self._get_redis_half_open_success_key(), self.cooldown_seconds + 60)
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置半开成功计数失败: {e}"
                )
    
    def _get_half_open_failure_count(self) -> int:
        """从Redis获取半开失败计数"""
        client = get_redis_client()
        if client:
            try:
                count = client.get(self._get_redis_half_open_failure_key())
                return int(count) if count else 0
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"读取半开失败计数失败: {e}"
                )
        return 0
    
    def _set_half_open_failure_count(self, count: int):
        """设置半开失败计数到Redis"""
        client = get_redis_client()
        if client:
            try:
                client.set(self._get_redis_half_open_failure_key(), count)
                client.expire(self._get_redis_half_open_failure_key(), self.cooldown_seconds + 60)
            except Exception as e:
                logger.warning(
                    "CircuitBreaker",
                    "REDIS_ERR",
                    f"设置半开失败计数失败: {e}"
                )
    
    @property
    def state(self):
        """获取当前熔断状态"""
        self._check_state_transition()
        return self._get_state()
    
    def _check_state_transition(self):
        """检查并执行状态转换"""
        now = time.time()
        current_state = self._get_state()
        
        # 如果是OPEN状态，检查是否需要转换到HALF_OPEN
        if current_state == self.STATE_OPEN:
            open_time = self._get_open_time()
            if open_time and now - open_time >= self.cooldown_seconds:
                self._transition_to_half_open()
        
        # 如果是CLOSED状态，检查时间窗口是否需要重置
        if current_state == self.STATE_CLOSED:
            window_start = self._get_window_start_time()
            if now - window_start >= self.window_seconds:
                self._reset_window()
    
    def _transition_to_open(self):
        """转换到OPEN状态（熔断）"""
        self._set_state(self.STATE_OPEN)
        self._set_open_time(time.time())
        self._set_deadlock_count(0)
        logger.warning(
            "CircuitBreaker",
            "TRIGGERED",
            f"死锁熔断已触发，将在 {self.cooldown_seconds} 秒后尝试恢复"
        )
    
    def _transition_to_half_open(self):
        """转换到HALF_OPEN状态（尝试恢复）"""
        self._set_state(self.STATE_HALF_OPEN)
        self._set_half_open_success_count(0)
        self._set_half_open_failure_count(0)
        logger.warning(
            "CircuitBreaker",
            "HALF_OPEN",
            "熔断进入半开状态，开始尝试恢复"
        )
    
    def _transition_to_closed(self):
        """转换到CLOSED状态（正常）"""
        self._set_state(self.STATE_CLOSED)
        self._set_deadlock_count(0)
        self._set_window_start_time(time.time())
        self._set_open_time(None)
        logger.info(
            "CircuitBreaker",
            "RESET",
            "熔断已恢复，系统正常运行"
        )
    
    def _reset_window(self):
        """重置时间窗口"""
        self._set_deadlock_count(0)
        self._set_window_start_time(time.time())
    
    def record_deadlock(self):
        """记录一次死锁（使用Redis INCR保证原子性）"""
        self._check_state_transition()
        current_state = self._get_state()
        
        if current_state == self.STATE_CLOSED:
            client = get_redis_client()
            if client:
                try:
                    new_count = client.incr(self._get_redis_deadlock_count_key())
                    client.expire(self._get_redis_deadlock_count_key(), self.window_seconds + 60)
                except Exception as e:
                    logger.warning(
                        "CircuitBreaker",
                        "REDIS_ERR",
                        f"死锁计数INCR失败，回退到内存模式: {e}"
                    )
                    new_count = self._get_deadlock_count() + 1
                    self._set_deadlock_count(new_count)
            else:
                new_count = self._get_deadlock_count() + 1
                self._set_deadlock_count(new_count)
            
            # 死锁预警：当达到阈值的80%时发出警告
            warning_threshold = int(self.threshold * 0.8)
            if new_count == warning_threshold:
                logger.warning(
                    "CircuitBreaker",
                    "WARNING",
                    f"死锁预警：当前死锁次数({new_count})已达到阈值({self.threshold})的80%，请关注系统状态"
                )
            
            # 检查是否超过阈值
            if new_count >= self.threshold:
                self._transition_to_open()
                return True  # 熔断已触发
        
        elif current_state == self.STATE_HALF_OPEN:
            # 半开状态下再次死锁，立即回到OPEN状态
            self._set_half_open_failure_count(self._get_half_open_failure_count() + 1)
            self._transition_to_open()
            return True
        
        return False  # 未触发熔断
    
    def record_success(self):
        """记录一次成功操作"""
        self._check_state_transition()
        current_state = self._get_state()
        
        if current_state == self.STATE_HALF_OPEN:
            client = get_redis_client()
            if client:
                try:
                    new_count = client.incr(self._get_redis_half_open_success_key())
                    client.expire(self._get_redis_half_open_success_key(), self.cooldown_seconds + 60)
                except Exception as e:
                    logger.warning(
                        "CircuitBreaker",
                        "REDIS_ERR",
                        f"半开成功计数INCR失败，回退到内存模式: {e}"
                    )
                    new_count = self._get_half_open_success_count() + 1
                    self._set_half_open_success_count(new_count)
            else:
                new_count = self._get_half_open_success_count() + 1
                self._set_half_open_success_count(new_count)
            
            # 检查是否达到恢复条件
            if new_count >= self.half_open_attempts:
                self._transition_to_closed()
    
    def is_available(self) -> bool:
        """检查是否可以执行操作"""
        self._check_state_transition()
        current_state = self._get_state()
        
        if current_state == self.STATE_OPEN:
            return False
        
        return True
    
    def get_wait_time(self) -> float:
        """获取距离熔断恢复的剩余时间（秒）"""
        current_state = self._get_state()
        if current_state != self.STATE_OPEN:
            return 0.0
        
        open_time = self._get_open_time()
        if not open_time:
            return 0.0
        
        elapsed = time.time() - open_time
        remaining = max(0.0, self.cooldown_seconds - elapsed)
        return remaining
    
    def get_stats(self) -> Dict[str, Any]:
        """获取熔断器统计信息"""
        self._check_state_transition()
        return {
            "state": self._get_state(),
            "deadlock_count": self._get_deadlock_count(),
            "threshold": self.threshold,
            "window_seconds": self.window_seconds,
            "cooldown_remaining": self.get_wait_time(),
            "half_open_success_count": self._get_half_open_success_count(),
            "half_open_failure_count": self._get_half_open_failure_count()
        }


def with_transaction(func):
    """
    事务装饰器，根据实例配置或方法参数决定是否使用事务
    
    Args:
        func: 要装饰的异步方法
        
    Returns:
        装饰后的方法
    """
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        # 检查是否有use_transaction参数，如果有则使用，否则使用实例默认值
        transaction_mode = kwargs.pop('use_transaction', self.use_transaction)
        
        try:
            if transaction_mode:
                # 使用事务
                async with in_transaction(self.connection_name):
                    return await func(self, *args, **kwargs)
            else:
                # 不使用事务
                return await func(self, *args, **kwargs)
        except Exception as e:
            # 特殊处理 bulk_upsert 方法在非事务模式下的错误
            if func.__name__ == 'bulk_upsert' and not transaction_mode:
                # 对于 bulk_upsert 方法，在非事务模式下返回错误信息
                db_table = None
                if 'model_class' in kwargs:
                    db_table = getattr(kwargs['model_class']._meta, 'db_table', None)
                logger.fail("批量upsert", f"{db_table}@{self.connection_name}", str(e))
                data_list = kwargs.get('data_list', [])
                return {
                    "success": False,
                    "error": str(e),
                    "total_records": len(data_list),
                    "inserted": 0,
                    "updated": 0
                }
            else:
                # 转换为自定义异常
                operation = func.__name__
                table = None
                
                # 尝试从参数中获取表名
                if 'table_name' in kwargs:
                    table = kwargs['table_name']
                elif 'model_class' in kwargs:
                    table = getattr(kwargs['model_class']._meta, 'db_table', None)
                
                error_str = str(e).upper()
                is_deadlock = 'DEADLOCK' in error_str or '1213' in str(e) or '死锁' in str(e)
                is_operational_error = "OperationalError" in str(type(e))
                is_connection_closed = "Cannot acquire connection after closing pool" in str(e)
                is_none_type_error = "NoneType" in str(e)
                is_connection_error = "Connection" in str(type(e))
                is_timeout_error = "Timeout" in str(type(e))
                is_network_error = "Network" in str(type(e)) or "网络" in str(e)
                is_pool_error = "Pool" in str(type(e))
                
                # 检查 OperationalError 是否为连接相关错误
                is_operational_connection_error = is_operational_error and (
                    'CONNECTION' in error_str or 
                    'CONNECT' in error_str or 
                    'POOL' in error_str or 
                    'TIMEOUT' in error_str or 
                    'NETWORK' in error_str or 
                    'HOST' in error_str or 
                    'PORT' in error_str or
                    'SERVER' in error_str
                )
                
                if is_deadlock:
                    logger.fail(operation, f"@{self.connection_name}", str(e))
                    raise DbDeadlockError(f"数据库死锁: {str(e)}", operation, table, self.connection_name)
                elif is_connection_error or is_operational_connection_error or is_connection_closed:
                    logger.fail(operation, f"@{self.connection_name}", str(e))
                    raise DbConnectionError(f"数据库连接错误: {str(e)}", operation, table, self.connection_name)
                else:
                    logger.fail(operation, f"@{self.connection_name}", str(e))
                    raise DbQueryError(f"数据库操作错误: {str(e)}", operation, table, self.connection_name)
    
    return wrapper


def handle_db_errors(max_retries: int = 3):
    """
    带重试机制和熔断保护的数据库错误处理装饰器
    
    Args:
        max_retries: 最大重试次数
        
    Returns:
        装饰后的方法
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            retry_count = 0
            last_exception = None
            
            while retry_count <= max_retries:
                # 检查熔断器状态
                circuit_breaker = getattr(self, 'circuit_breaker', None)
                if circuit_breaker and not circuit_breaker.is_available():
                    wait_time = circuit_breaker.get_wait_time()
                    logger.warning(
                        func.__name__,
                        f"@{self.connection_name}",
                        f"熔断器已触发，拒绝请求，剩余熔断时间: {wait_time:.1f}秒"
                    )
                    raise DbCircuitBreakerError(
                        f"数据库熔断中，剩余{wait_time:.1f}秒后恢复",
                        operation=func.__name__,
                        connection=self.connection_name
                    )
                
                try:
                    result = await func(self, *args, **kwargs)
                    
                    # 操作成功，通知熔断器（用于半开状态恢复）
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    
                    return result
                except Exception as e:
                    error_str = str(e).upper()
                    is_deadlock = 'DEADLOCK' in error_str or '1213' in str(e) or '死锁' in str(e)
                    is_operational_error = "OperationalError" in str(type(e))
                    is_connection_closed = "Cannot acquire connection after closing pool" in str(e)
                    is_none_type_error = "NoneType" in str(e)
                    is_connection_error = "Connection" in str(type(e))
                    is_timeout_error = "Timeout" in str(type(e))
                    is_network_error = "Network" in str(type(e)) or "网络" in str(e)
                    is_pool_error = "Pool" in str(type(e))
                    
                    # 检查 OperationalError 是否为连接相关错误
                    is_operational_connection_error = is_operational_error and (
                        'CONNECTION' in error_str or 
                        'CONNECT' in error_str or 
                        'POOL' in error_str or 
                        'TIMEOUT' in error_str or 
                        'NETWORK' in error_str or 
                        'HOST' in error_str or 
                        'PORT' in error_str or
                        'SERVER' in error_str
                    )
                    
                    is_retryable = (is_deadlock or is_operational_connection_error or is_connection_closed or 
                                  is_none_type_error or is_connection_error or is_timeout_error or 
                                  is_network_error or is_pool_error)
                    
                    # 死锁时记录到熔断器
                    if is_deadlock and circuit_breaker:
                        triggered = circuit_breaker.record_deadlock()
                        if triggered:
                            logger.warning(
                                func.__name__,
                                f"@{self.connection_name}",
                                "熔断器已触发，立即拒绝后续请求"
                            )
                    
                    if is_retryable and retry_count < max_retries:
                        retry_count += 1
                        
                        # 使用指数退避策略
                        if is_connection_closed:
                            base_delay = 3.0
                        elif is_deadlock:
                            base_delay = 5.0  # 增加死锁重试延迟，减少熔断器频繁触发
                        else:
                            base_delay = 1.0
                        
                        current_delay = base_delay * (2 ** (retry_count - 1))
                        current_delay = min(current_delay, 30.0)  # 最大延迟从20秒增加到30秒
                        
                        error_type = "连接错误"
                        if is_connection_closed:
                            error_type = "连接池关闭"
                        elif is_deadlock:
                            error_type = "死锁"
                        elif is_timeout_error:
                            error_type = "超时错误"
                        elif is_network_error:
                            error_type = "网络错误"
                        
                        logger.warning_msg(
                            func.__name__,
                            f"@{self.connection_name} 检测到{error_type}，第{retry_count}次重试中...",
                            f"等待{current_delay:.1f}秒后重试"
                        )
                        
                        # 尝试刷新连接
                        if not is_deadlock:
                            await self.refresh_connection(fast_mode=is_connection_closed)
                        
                        await asyncio.sleep(current_delay)
                        continue
                    else:
                        # 转换为自定义异常
                        operation = func.__name__
                        table = None
                        
                        # 尝试从参数中获取表名
                        if 'table_name' in kwargs:
                            table = kwargs['table_name']
                        elif 'model_class' in kwargs:
                            table = getattr(kwargs['model_class']._meta, 'db_table', None)
                        
                        if is_deadlock:
                            logger.fail(operation, f"@{self.connection_name}", str(e))
                            raise DbDeadlockError(f"数据库死锁: {str(e)}", operation, table, self.connection_name)
                        elif is_connection_error or is_operational_connection_error or is_connection_closed:
                            logger.fail(operation, f"@{self.connection_name}", str(e))
                            raise DbConnectionError(f"数据库连接错误: {str(e)}", operation, table, self.connection_name)
                        elif isinstance(e, IntegrityError):
                            logger.fail(operation, f"@{self.connection_name}", str(e))
                            raise DbTransactionError(f"数据完整性错误: {str(e)}", operation, table, self.connection_name)
                        else:
                            logger.fail(operation, f"@{self.connection_name}", str(e))
                            raise DbQueryError(f"数据库操作错误: {str(e)}", operation, table, self.connection_name)
            
            if last_exception:
                raise last_exception
        
        return wrapper
    
    return decorator


class DbManager:
    """数据库操作管理器"""
    
    # 类级别的熔断器，每个数据库连接共享一个熔断器
    _circuit_breakers: Dict[str, DeadlockCircuitBreaker] = {}
    
    # 类级别的并发执行跟踪器，用于检测同一存储过程的并发调用
    _active_procedures: Dict[str, int] = {}  # {procedure_name@connection: count}
    
    def __init__(self, connection_name: str, batch_size: int = 1000, use_transaction: bool = True):
        """
        初始化管理器
        
        Args:
            connection_name: 数据库连接名称
            batch_size: 批量大小，超过此数量会分批处理
            use_transaction: 是否使用事务
        """
        self.connection_name = connection_name
        self.batch_size = batch_size
        self.use_transaction = use_transaction
        self.stats = {
            'total_processed': 0,
            'batches_executed': 0,
            'last_execution_time': None
        }
        # 动态批量大小配置
        self.min_batch_size = 500
        self.max_batch_size = 5000
        self.optimal_batch_size = batch_size
        self.batch_size_history = []
        self.batch_size_adjustment_interval = 10  # 每10次操作调整一次
        
        # 获取或创建熔断器实例（每个连接共享）
        self._get_or_create_circuit_breaker()
        
        # 集成增强的连接池管理器（可选，默认启用）
        self._use_enhanced_pool = os.getenv("USE_ENHANCED_POOL", "true").lower() == "true"
        self._enhanced_pool_manager = None
        if self._use_enhanced_pool:
            try:
                from globalobjects.db_pool import get_enhanced_db_manager
                from globalobjects.db_pool.config import get_cached_config
                # 必须传入 get_cached_config()，否则会使用 PoolManagerConfig() 默认值，
                # 导致 .env 中的 DBPOOL_HEALTH_CHECK_TIMEOUT 等配置不生效
                self._enhanced_pool_manager = get_enhanced_db_manager(
                    connection_name,
                    get_cached_config()
                )
            except Exception as e:
                logger.warning(f"初始化增强连接池管理器失败: {e}，将使用原有逻辑")
    
    def _get_or_create_circuit_breaker(self):
        """获取或创建熔断器实例（使用连接名称作为熔断器名称，实现跨进程共享）"""
        if self.connection_name not in DbManager._circuit_breakers:
            DbManager._circuit_breakers[self.connection_name] = DeadlockCircuitBreaker(
                name=self.connection_name,
                threshold=10,        # 60秒内超过10次死锁触发熔断（从5增加到10）
                window_seconds=60,   # 时间窗口60秒
                cooldown_seconds=45, # 熔断持续45秒（从30增加到45）
                half_open_attempts=3 # 半开状态下成功3次恢复（从2增加到3）
            )
    
    @property
    def circuit_breaker(self) -> DeadlockCircuitBreaker:
        """获取熔断器实例"""
        return DbManager._circuit_breakers.get(self.connection_name)
    
    @property
    def enhanced_pool_manager(self):
        """获取增强连接池管理器实例"""
        return self._enhanced_pool_manager
    
    async def get_pool_status(self):
        """
        获取连接池状态（增强功能）
        
        Returns:
            ConnectionPoolStatus: 连接池状态信息
        """
        if self._enhanced_pool_manager:
            try:
                return await self._enhanced_pool_manager.get_connection_pool_status()
            except Exception as e:
                logger.warning(f"获取连接池状态失败: {e}")
        return None
    
    async def record_pool_usage(self):
        """
        记录连接池使用情况（增强功能）
        用于泄漏检测
        """
        if self._enhanced_pool_manager:
            try:
                await self._enhanced_pool_manager.record_usage()
            except Exception as e:
                logger.warning(f"记录连接池使用情况失败: {e}")
    
    async def detect_pool_leak(self):
        """
        检测连接池泄漏（增强功能）
        
        Returns:
            LeakDetectionResult: 泄漏检测结果
        """
        if self._enhanced_pool_manager:
            try:
                return await self._enhanced_pool_manager.detect_leak()
            except Exception as e:
                logger.warning(f"检测连接池泄漏失败: {e}")
        return None
    
    def _get_procedure_key(self, procedure_name: str) -> str:
        """获取存储过程的唯一标识键"""
        return f"{procedure_name}@{self.connection_name}"
    
    def _get_redis_key(self, procedure_name: str) -> str:
        """获取Redis中存储过程并发计数的键名"""
        return f"myaps:proc:concurrency:{self._get_procedure_key(procedure_name)}"
    
    def _try_acquire_procedure_slot(self, procedure_name: str, max_concurrent: int) -> bool:
        """
        原子性地尝试获取一个存储过程执行槽位（使用Redis INCR保证原子性）
        
        将"检查并发数"和"递增计数"合并为一次原子操作，消除TOCTOU竞态条件。
        
        Args:
            procedure_name: 存储过程名称
            max_concurrent: 最大并发数
        
        Returns:
            True: 成功获取槽位（调用方可直接执行，无需再调用 _increment_procedure_count）
            False: 超过并发限制，未获取到槽位
        """
        redis_key = self._get_redis_key(procedure_name)
        
        client = get_redis_client()
        if client:
            try:
                current = client.incr(redis_key)
                client.expire(redis_key, 300)
                if current <= max_concurrent:
                    return True  # 原子性地获取到槽位
                # 超过限制，回退
                client.decr(redis_key)
                return False
            except Exception as e:
                logger.warning(
                    "并发控制",
                    "REDIS_ERR",
                    f"原子获取执行槽位失败（将使用内存模式）: {e}"
                )
        
        # 无Redis时回退到内存模式
        key = self._get_procedure_key(procedure_name)
        current_count = DbManager._active_procedures.get(key, 0)
        if current_count < max_concurrent:
            DbManager._active_procedures[key] = current_count + 1
            return True
        return False
    
    def _increment_procedure_count(self, procedure_name: str):
        """增加存储过程执行计数（使用Redis实现跨进程同步）"""
        key = self._get_procedure_key(procedure_name)
        redis_key = self._get_redis_key(procedure_name)
        
        client = get_redis_client()
        if client:
            try:
                client.incr(redis_key)
                client.expire(redis_key, 300)
                return
            except Exception as e:
                logger.warning(
                    "并发控制",
                    "REDIS_ERR",
                    f"并发计数INCR失败（将使用内存模式）: {e}"
                )
        
        DbManager._active_procedures[key] = DbManager._active_procedures.get(key, 0) + 1
    
    def _decrement_procedure_count(self, procedure_name: str):
        """减少存储过程执行计数（使用Redis实现跨进程同步）"""
        key = self._get_procedure_key(procedure_name)
        redis_key = self._get_redis_key(procedure_name)
        
        client = get_redis_client()
        if client:
            try:
                current = client.decr(redis_key)
                if current <= 0:
                    client.delete(redis_key)
                return
            except Exception as e:
                logger.warning(
                    "并发控制",
                    "REDIS_ERR",
                    f"并发计数DECR失败（将使用内存模式）: {e}"
                )
        
        if key in DbManager._active_procedures:
            DbManager._active_procedures[key] -= 1
            if DbManager._active_procedures[key] <= 0:
                del DbManager._active_procedures[key]

    # ============ 数据库级别全局并发控制 ============
    
    def _get_db_concurrency_key(self) -> str:
        """获取数据库级别并发控制的Redis键名"""
        return f"myaps:db:concurrency:{self.connection_name}"
    
    def _try_acquire_db_slot(self, max_concurrent: int = 3) -> bool:
        """
        原子性地尝试获取一个数据库级别执行槽位（使用Redis INCR）
        
        限制所有Worker在同一个数据库上的总并发操作数，
        减少不同操作之间因锁竞争导致的死锁。
        
        Args:
            max_concurrent: 最大总并发数（默认3，跨所有Worker）
            
        Returns:
            True: 成功获取槽位
            False: 超过并发限制，未获取到槽位
        """
        redis_key = self._get_db_concurrency_key()
        
        client = get_redis_client()
        if client:
            try:
                current = client.incr(redis_key)
                client.expire(redis_key, 300)
                if current <= max_concurrent:
                    return True
                client.decr(redis_key)
                return False
            except Exception as e:
                logger.warning(
                    "数据库并发控制",
                    "REDIS_ERR",
                    f"获取DB执行槽位失败: {e}"
                )
        
        # Redis不可用时放行（不影响原有功能）
        return True
    
    def _release_db_slot(self):
        """释放数据库级别执行槽位"""
        redis_key = self._get_db_concurrency_key()
        
        client = get_redis_client()
        if client:
            try:
                current = client.decr(redis_key)
                if current <= 0:
                    client.delete(redis_key)
            except Exception as e:
                logger.warning(
                    "数据库并发控制",
                    "REDIS_ERR",
                    f"释放DB执行槽位失败: {e}"
                )
    
    async def _get_valid_connection(self):
        """
        获取并检查数据库连接的有效性
        
        Returns:
            有效的数据库连接对象
            
        Raises:
            DbConnectionError: 如果连接无效
        """
        import asyncio

        # 尝试获取连接，最多尝试3次
        for attempt in range(3):
            try:
                # Tortoise ORM已由lifespan初始化，禁止运行时重新初始化
                if not hasattr(Tortoise, '_inited') or not Tortoise._inited:
                    raise RuntimeError("Tortoise ORM未初始化，请等待应用启动完成")
                
                # 获取数据库连接
                conn = Tortoise.get_connection(self.connection_name)
                
                # 检查连接是否有效
                if conn is None:
                    logger.warning(f"连接为None，尝试刷新连接: {self.connection_name}")
                    await self.refresh_connection(fast_mode=True)
                    continue
                
                # 检查连接是否已关闭
                if hasattr(conn, 'closed') and conn.closed:
                    logger.warning(f"连接已关闭，尝试刷新连接: {self.connection_name}")
                    await self.refresh_connection(fast_mode=True)
                    continue
                
                # 检查连接是否有execute_query方法
                if not hasattr(conn, 'execute_query'):
                    logger.warning(f"连接不支持execute_query，尝试刷新连接: {self.connection_name}")
                    await self.refresh_connection(fast_mode=True)
                    continue
                
                # 检查连接是否有_execute_command方法（避免NoneType错误）
                if hasattr(conn, '_execute_command') and conn._execute_command is None:
                    logger.warning(f"连接的_execute_command为None，尝试刷新连接: {self.connection_name}")
                    await self.refresh_connection(fast_mode=True)
                    continue
                
                # 验证连接是否可以正常执行查询
                await conn.execute_query("SELECT 1")
                return conn
                
            except Exception as e:
                logger.warning(f"获取连接时出错 (尝试 {attempt+1}/3): {e}")
                if attempt < 2:
                    # 等待一段时间后重试
                    await asyncio.sleep(1)
                    # 尝试刷新连接
                    await self.refresh_connection(fast_mode=True)
                else:
                    raise DbConnectionError(f"获取数据库连接失败：{str(e)}")


    @asynccontextmanager
    async def get_connection(self):
        """
        异步上下文管理器，用于安全地获取Tortoise ORM的数据库连接
        注意：Tortoise会自动管理连接的获取和释放，不需要手动关闭连接
        
        增强功能：
        - 检查连接池状态，不可用时抛出异常
        - 记录连接使用情况（用于泄漏检测）
        
        Yields:
            Tortoise数据库连接对象
            
        Raises:
            ConnectionPoolUnavailableError: 连接池不可用
        """
        # 使用增强管理器检查连接池状态
        if self._enhanced_pool_manager:
            try:
                async with self._enhanced_pool_manager.get_connection() as conn:
                    # 记录使用情况
                    try:
                        await self._enhanced_pool_manager.record_usage()
                    except Exception:
                        pass  # 记录失败不影响业务
                    
                    yield conn
                    return
            except Exception as e:
                # 如果增强管理器失败，回退到原有逻辑
                if "ConnectionPoolUnavailableError" in str(type(e).__name__):
                    # 连接池不可用，向上抛出
                    raise
                logger.warning(f"增强管理器获取连接失败: {e}，使用原有逻辑")
        
        # 原有逻辑
        connection = Tortoise.get_connection(self.connection_name)
        yield connection


    @classmethod
    def _get_conflict_fields(cls, model_class, conflict_fields: Optional[Tuple[str, ...]]=None) -> Tuple[str, ...]:
        """
        获取冲突字段，如果未提供则自动确定
        
        Args:
            model_class: Tortoise 模型类
            conflict_fields: 冲突检测字段（可选）
            
        Returns:
            冲突检测字段元组
            
        Raises:
            ValueError: 如果模型没有定义主键或唯一约束
        """
        if conflict_fields is None:
            unique_together = getattr(model_class._meta, 'unique_together', [])
            if unique_together:
                conflict_fields = unique_together[0]
            else:
                pk_attr = getattr(model_class._meta, 'pk_attr', None)
                if pk_attr:
                    conflict_fields = (pk_attr,)
                else:
                    raise ValueError(f"模型 {model_class.__name__} 没有定义主键或唯一约束")
        return conflict_fields
    

    async def call_stored_procedure(
        self, 
        procedure_name: str, 
        params_list: List[List[Any]] = None, 
        use_transaction: Optional[bool] = None,
        max_concurrent: int = 1,
        wait_timeout: float = 15.0,
        use_queue: bool = None,
        use_distributed_lock: bool = False
    ) -> Dict[str, Any]:
        """
        调用数据库存储过程（支持死锁自动重试、并发控制、请求排队和分布式锁）
        
        Args:
            procedure_name: 存储过程名称
            params_list: 存储过程参数列表，每个元素是一个参数列表（可选，默认[[]]）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            max_concurrent: 最大并发数，超过此限制将等待或拒绝（默认1）
            wait_timeout: 等待并发资源的超时时间（默认15秒）
            use_queue: 是否使用队列执行（默认None，表示高风险存储过程自动使用队列）
            use_distributed_lock: 是否使用分布式锁（默认False）
            
        Returns:
            包含执行结果的字典，包括成功状态、执行时间、影响记录数等
            
        Raises:
            DbManagerError: 如果存储过程执行失败
        """
        if params_list is None:
            params_list = [[]]
        
        # 判断是否使用队列
        if use_queue is None:
            use_queue = is_high_risk_procedure(procedure_name)
        
        # 定义实际执行的内部函数
        async def _execute_with_lock():
            if use_queue:
                # 高风险存储过程使用队列串行化执行
                logger.debug(
                    "存储过程调用",
                    f"{procedure_name}@{self.connection_name}",
                    "使用队列串行化执行"
                )
                # 创建实际执行的回调函数
                async def _execute_procedure():
                    return await self._call_stored_procedure_inner(
                        procedure_name=procedure_name,
                        params_list=params_list,
                        use_transaction=use_transaction,
                        max_concurrent=max_concurrent,
                        wait_timeout=wait_timeout
                    )
                
                # 获取队列并执行
                queue = ProcedureQueueManager.get_queue(procedure_name)
                return await queue.enqueue(_execute_procedure)
            else:
                # 普通存储过程直接执行
                return await self._call_stored_procedure_inner(
                    procedure_name=procedure_name,
                    params_list=params_list,
                    use_transaction=use_transaction,
                    max_concurrent=max_concurrent,
                    wait_timeout=wait_timeout
                )
        
        # 如果启用分布式锁
        if use_distributed_lock:
            from apps.common.utils.distributed_lock import DistributedLock
            
            lock_key = f"{procedure_name}:{self.connection_name}"
            lock = DistributedLock(lock_key, timeout=30)
            
            async with lock.lock(max_wait=wait_timeout) as acquired:
                if not acquired:
                    raise DbManagerError(
                        f"无法获取分布式锁: {lock_key}，等待超时 {wait_timeout} 秒"
                    )
                
                logger.debug(
                    "存储过程调用",
                    f"{procedure_name}@{self.connection_name}",
                    "使用分布式锁执行"
                )
                
                return await _execute_with_lock()
        
        # 不使用分布式锁，直接执行
        return await _execute_with_lock()
    
    @with_transaction
    @handle_db_errors(max_retries=8)
    async def _call_stored_procedure_inner(
        self,
        procedure_name: str,
        params_list: List[List[Any]],
        use_transaction: Optional[bool] = None,
        max_concurrent: int = 1,
        wait_timeout: float = 15.0
    ) -> Dict[str, Any]:
        """
        存储过程调用的内部实现
        
        Args:
            procedure_name: 存储过程名称
            params_list: 存储过程参数列表
            use_transaction: 是否使用事务
            max_concurrent: 最大并发数
            wait_timeout: 等待并发资源的超时时间
            
        Returns:
            包含执行结果的字典
        """
        # 并发检测：使用原子操作获取执行槽位（消除TOCTOU竞态条件）
        start_wait = datetime.now()
        slot_acquired = False
        while not slot_acquired:
            slot_acquired = self._try_acquire_procedure_slot(procedure_name, max_concurrent)
            if slot_acquired:
                break
            wait_elapsed = (datetime.now() - start_wait).total_seconds()
            if wait_elapsed >= wait_timeout:
                logger.warning(
                    "存储过程调用",
                    f"{procedure_name}@{self.connection_name}",
                    f"等待并发槽位超时（{wait_timeout}秒）"
                )
                # 超时后使用内存计数继续执行（保持原有行为）
                self._increment_procedure_count(procedure_name)
                break
            await asyncio.sleep(0.5)
        
        try:
            start_time = datetime.now()
            
            # 优化：在获取连接前先检查连接池状态
            conn = await self._get_valid_connection()
            affect_count = 0
            results = []
            
            for params in params_list:
                result = await conn.execute_query(
                    f'CALL `{procedure_name}`({", ".join(["%s"] * len(params))})', 
                    params
                )
                count = result[0] if result else 0
                affect_count += count
                results.append(result)
        
            execution_time = (datetime.now() - start_time).total_seconds()
            
            self.stats['total_processed'] += len(params_list)
            self.stats['batches_executed'] += len(params_list)
            self.stats['last_execution_time'] = execution_time
            
            response = {
                "success": True,
                "procedure_name": procedure_name,
                "execution_time": execution_time,
                "total_calls": len(params_list),
                "affected_rows": affect_count,
                "results": results
            }
            
            logger.success("存储过程调用", f"{procedure_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒，影响记录数{affect_count}条")
            return response
        finally:
            # 确保无论成功还是失败都减少执行计数
            self._decrement_procedure_count(procedure_name)
    

    @handle_db_errors(max_retries=3)
    async def query_data(self, table_name: str, select_fields: str = '*', filter_string: str = '', order_string: str = '', page_size: int = 1000, page_index: int = 0) -> Dict[str, Any]:
        """
        查询数据库表数据，获取符合筛选条件的数据，支持重试机制
        
        Args:
            table_name: 表名
            select_fields: SELECT字段字符串（默认"*"，即查询所有字段）
            filter_string: WHERE条件字符串（可选）
            order_string: ORDER BY排序字符串（可选）
            page_size: 分页查询的页大小（最大/默认1000）
            page_index: 分页查询的页码（默认0，获取全部数据；若大于0则取对应页数据）
            
        Returns:
            包含查询结果的字典，包括成功状态、数据列表、总数、执行时间等
            
        Raises:
            DbManagerError: 如果查询失败
        """
        if page_size <= 0:
            page_size = 1000
            page_index = 0
        else:
            page_size = min(page_size, 1000)
        start_time = datetime.now()
        
        # 使用Tortoise的连接池机制，不需要手动关闭连接
        # Tortoise会自动管理连接的获取和释放
        conn = await self._get_valid_connection()
        
        # 构建WHERE和ORDER子句
        where = f" WHERE {filter_string}" if filter_string else ''
        order = f" ORDER BY {order_string}" if order_string else ''
        
        # 检查索引使用情况
        self._check_index_usage(table_name, filter_string, order_string)
        
        # 先获取数据总条数
        count_sql = f'SELECT COUNT(*) as total FROM `{table_name}` {where}'
        count_result = await conn.execute_query(count_sql)
        total = count_result[1][0].get('total', 0)
        
        # 查询数据
        all_data = []
        
        offset = max((page_index - 1) * page_size, 0)
        while offset < total:
            # 构建带LIMIT和OFFSET的分页查询SQL
            sql = f'SELECT {select_fields} FROM `{table_name}` {where} {order} LIMIT {page_size} OFFSET {offset}'
            _, batch_data = await conn.execute_query(sql)
            all_data.extend(batch_data)
            if page_index > 0:  # 若page_index大于0，说明需要查询指定页数据，查询当前页后直接退出
                break
            offset += page_size
            # 如果当前批次数据不足page_size，说明已经获取完所有数据
            if len(batch_data) < page_size:
                break
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # 更新统计信息
        self.stats['total_processed'] += total
        self.stats['batches_executed'] += (total + page_size - 1) // page_size
        self.stats['last_execution_time'] = execution_time
        
        # 记录查询性能
        self._record_query_performance(table_name, len(all_data), execution_time)
        
        response = {
            "success": True,
            "table_name": table_name,
            "filter": filter_string,
            "order": order_string,
            "execution_time": execution_time,
            "total": total,
            "page_size": page_size,
            "page_index": page_index,
            "data": [dict_to_lower_keys(item) for item in all_data],
            "performance_metrics": {
                "records_per_second": len(all_data) / execution_time if execution_time > 0 else 0,
                "query_type": "paginated" if page_index > 0 else "full"
            }
        }
        
        logger.success("数据查询", f"{table_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒，返回{len(all_data)}条记录")
        if execution_time > 1.0:
            logger.warning_console(f"数据查询 {table_name}@{self.connection_name} 查询执行时间较长: {execution_time:.3f}秒")
        logger.debug(f"数据查询完成：{response}")
        return response
    

    @handle_db_errors(max_retries=3)
    async def query_data_cursor(
        self,
        table_name: str,
        select_fields: str = '*',
        filter_string: str = '',
        order_fields: List[Tuple[str, str]] = None,
        page_size: int = 1000,
        cursor_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        游标分页查询（Keyset Pagination），避免 LIMIT/OFFSET 的幻读问题

        与 query_data 的 OFFSET 分页不同，游标分页使用排序字段的上次最大值作为游标，
        每次查询只追加 WHERE 条件而非使用 OFFSET，因此不受并发插入/删除影响。

        Args:
            table_name: 表名
            select_fields: SELECT字段字符串（默认"*"）
            filter_string: 基础 WHERE 条件字符串（不含游标条件）
            order_fields: 排序字段列表，每个元素为 (字段名, 'ASC'|'DESC')，
                          例如 [('MaterialNo', 'ASC'), ('DateStr', 'ASC')]
                          必须指定，用于构建游标条件和 ORDER BY 子句。
                          注意：排序字段必须是 NOT NULL 列且包含在 select_fields 中，
                          否则游标值为 NULL 时无法生成正确的游标条件，将抛出 ValueError。
            page_size: 每页大小（最大1000，默认1000）
            cursor_values: 游标值字典，键为排序字段名，值为上一页最后一条记录的对应字段值。
                           首页查询时传 None 或空字典。

        Returns:
            包含查询结果的字典：
            - success: 是否成功
            - data: 数据列表（字段名已转小写）
            - has_more: 是否还有更多数据（返回行数 == page_size 时为 True）
            - cursor_values: 本页最后一条记录的排序字段值，供下一页查询使用
            - execution_time: 执行耗时

        Raises:
            ValueError: order_fields 为空时抛出
            DbManagerError: 查询失败时抛出

        Example:
            # 首页
            result = await manager.query_data_cursor(
                table_name="v_supply",
                filter_string="`Type`='PR'",
                order_fields=[("MaterialNo", "ASC"), ("DateStr", "ASC")],
                page_size=1000,
                cursor_values=None,
            )
            # 下一页
            result = await manager.query_data_cursor(
                table_name="v_supply",
                filter_string="`Type`='PR'",
                order_fields=[("MaterialNo", "ASC"), ("DateStr", "ASC")],
                page_size=1000,
                cursor_values=result["cursor_values"],
            )
        """
        if not order_fields:
            raise ValueError("游标分页必须指定 order_fields，用于确定游标位置和排序方向")

        if page_size <= 0:
            page_size = 1000
        page_size = min(page_size, 1000)

        start_time = datetime.now()
        conn = await self._get_valid_connection()

        # 构建基础 WHERE 子句
        where_parts = []
        if filter_string:
            where_parts.append(filter_string)

        # 构建游标条件：基于排序字段的上次最大值
        # 对于 ASC 排序: (f1 > v1) OR (f1 = v1 AND f2 > v2) OR ...
        # 对于 DESC 排序: 将 > 改为 <
        if cursor_values:
            cursor_condition = self._build_cursor_condition(order_fields, cursor_values)
            if cursor_condition:
                where_parts.append(cursor_condition)

        where = f" WHERE {' AND '.join(where_parts)}" if where_parts else ''

        # 构建 ORDER BY 子句
        order_clause = ', '.join(f"`{field}` {direction}" for field, direction in order_fields)
        order = f" ORDER BY {order_clause}"

        # 无需 COUNT(*)，直接查询
        sql = f'SELECT {select_fields} FROM `{table_name}` {where} {order} LIMIT {page_size}'
        _, batch_data = await conn.execute_query(sql)

        execution_time = (datetime.now() - start_time).total_seconds()

        # 提取本页最后一条记录的游标值，供下一页使用
        next_cursor = None
        if batch_data:
            last_row = batch_data[-1]
            next_cursor = {field: last_row.get(field) for field, _ in order_fields}

        has_more = len(batch_data) == page_size

        self.stats['total_processed'] += len(batch_data)
        self.stats['batches_executed'] += 1
        self.stats['last_execution_time'] = execution_time
        self._record_query_performance(table_name, len(batch_data), execution_time)

        response = {
            "success": True,
            "table_name": table_name,
            "filter": filter_string,
            "order": order_clause,
            "execution_time": execution_time,
            "total": len(batch_data),
            "page_size": page_size,
            "has_more": has_more,
            "cursor_values": next_cursor,
            "data": [dict_to_lower_keys(item) for item in batch_data],
        }

        logger.success("游标分页查询", f"{table_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒，返回{len(batch_data)}条记录，{'还有更多' if has_more else '已到末页'}")
        if execution_time > 1.0:
            logger.warning_console(f"游标分页查询 {table_name}@{self.connection_name} 查询执行时间较长: {execution_time:.3f}秒")

        return response

    @staticmethod
    def _build_cursor_condition(
        order_fields: List[Tuple[str, str]],
        cursor_values: Dict[str, Any],
    ) -> str:
        """
        根据排序字段和游标值构建游标过滤条件

        对于组合排序键 (f1 ASC, f2 ASC, f3 ASC) 和游标值 (v1, v2, v3)，
        生成条件:
          (`f1` > 'v1' OR (`f1` = 'v1' AND `f2` > 'v2') OR (`f1` = 'v1' AND `f2` = 'v2' AND `f3` > 'v3'))

        DESC 排序字段使用 < 替代 >。

        Args:
            order_fields: 排序字段列表 [(field, 'ASC'|'DESC'), ...]
            cursor_values: 游标值字典 {field_name: value}

        Returns:
            游标条件的 SQL 字符串（不含 WHERE 关键字）
        """
        if not cursor_values:
            return ''

        def _sql_value(val: Any) -> str:
            if val is None:
                return 'NULL'
            if isinstance(val, (int, float)):
                return str(val)
            return f"'{str(val).replace(chr(39), chr(39)+chr(39))}'"

        or_parts = []
        for i in range(len(order_fields)):
            field, direction = order_fields[i]
            op = '>' if direction.upper() == 'ASC' else '<'
            val = cursor_values.get(field)
            if val is None:
                raise ValueError(
                    f"游标分页失败：排序字段 {field} 的游标值为 NULL 或缺失（cursor_values={cursor_values}）。"
                    f"游标分页要求排序字段为 NOT NULL 列且包含在 select 字段中，"
                    f"请确认 {field} 满足条件，或改用 db_query 分页。"
                )

            eq_chain = []
            for j in range(i):
                prev_field, _ = order_fields[j]
                prev_val = cursor_values.get(prev_field)
                eq_chain.append(f"`{prev_field}` = {_sql_value(prev_val)}")

            condition = f"`{field}` {op} {_sql_value(val)}"
            if eq_chain:
                condition = ' AND '.join(eq_chain) + f' AND {condition}'
            or_parts.append(f'({condition})')

        return ' OR '.join(or_parts) if or_parts else ''


    @with_transaction
    @handle_db_errors(max_retries=3)
    async def delete_data(self, table_name: str, filter_string: str = '', use_transaction: Optional[bool] = None) -> Dict[str, Any]:
        """
        删除数据库表数据
        
        Args:
            table_name: 表名
            filter_string: WHERE条件字符串（可选）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            包含删除结果的字典，包括成功状态、删除记录数、执行时间等
            
        Raises:
            DbManagerError: 如果删除失败
        """
        start_time = datetime.now()
        
        # 使用Tortoise的连接池机制，不需要手动关闭连接
        # Tortoise会自动管理连接的获取和释放
        conn = await self._get_valid_connection()
        
        # 构建WHERE子句
        where = f" WHERE {filter_string}" if filter_string else ''
        
        # 构建DELETE SQL语句
        delete_sql = f'DELETE FROM `{table_name}` {where}'
        
        # 执行删除操作
        affected_rows, data = await conn.execute_query(delete_sql)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # 更新统计信息
        self.stats['total_processed'] += affected_rows
        self.stats['batches_executed'] += 1
        self.stats['last_execution_time'] = execution_time
        
        response = {
            "success": True,
            "table_name": table_name,
            "filter": filter_string,
            "execution_time": execution_time,
            "affected_rows": affected_rows,
            "connection_name": self.connection_name
        }
        
        logger.success("数据删除", f"{table_name}@{self.connection_name}", f"影响{affected_rows}行")
        return response
    

    @handle_db_errors(max_retries=5)
    async def _execute_native_sql(self, sql: str, params: List[Any], description: str = "") -> tuple:
        """
        执行原生 SQL 查询
        
        Args:
            sql: SQL语句
            params: SQL参数列表
            description: 操作描述（可选）
            
        Returns:
            包含影响行数和数据列表的元组
            
        Raises:
            DbManagerError: 如果执行失败
        """
        # 数据库级别并发控制（限制定期任务等批量操作的总并发数）
        db_slot_acquired = self._try_acquire_db_slot(max_concurrent=4)
        
        start_time = datetime.now()
        try:
            # 使用Tortoise的连接池机制，不需要手动关闭连接
            # Tortoise会自动管理连接的获取和释放
            conn = await self._get_valid_connection()
            
            # 检查SQL语句是否为空
            if not sql.strip():
                raise DbQueryError("SQL语句为空")
            
            count, data_list = await conn.execute_query(sql, params)
            if data_list:
                data_list = [dict_to_lower_keys(row) for row in data_list]
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if description:
                logger.debug(f"{description} - 执行时间：{execution_time:.3f}秒")
            
            return (count if count else 0, data_list)
        finally:
            if db_slot_acquired:
                self._release_db_slot()
    

    async def _bulk_upsert_native_sql(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None
    ) -> Dict[str, Any]:
        """
        使用原生 SQL 执行批量 upsert
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据列表（不能为空）
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
        """
        
        # 获取冲突字段
        conflict_fields = self._get_conflict_fields(model_class, conflict_fields)

        # 如果未提供exclude_fields，则初始化为空列表
        # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
        if exclude_fields is None:
            exclude_fields = []

        # 获取表名
        table_name = model_class._meta.db_table
        
        # 收集所有记录中的所有字段，排除指定字段
        all_fields_set = set()
        for data in data_list:
            all_fields_set.update(data.keys())
        all_fields = [field for field in all_fields_set if field not in exclude_fields]
        
        # 获取数据库表的实际字段列表
        db = await self._get_valid_connection()
        # 使用SHOW COLUMNS获取表的实际字段
        columns_result = await db.execute_query(f"SHOW COLUMNS FROM `{table_name}`", [])
        db_field_names = set()
        for column in columns_result[1]:
            # 字段名可能是大写或小写，统一转换为小写
            field_name = column.get('Field', column.get('field', '')).lower()
            if field_name:
                db_field_names.add(field_name)
        
        # 检测并记录数据字段与数据库表字段的差异
        original_fields_set = set(all_fields)
        filtered_fields_set = set([field for field in all_fields if field.lower() in db_field_names])
        missing_fields = original_fields_set - filtered_fields_set
        if missing_fields:
            logger.warning(f"批量upsert检测到数据字段与数据库表字段存在差异: 表={table_name}, 数据中存在但表中不存在的字段={missing_fields}, 这些字段将被忽略")
        
        # 过滤掉数据库表中不存在的字段
        all_fields = [field for field in all_fields if field.lower() in db_field_names]
        
        if not all_fields:
            raise ValueError("没有可插入的字段")
        
        # 验证字段
        # 只验证冲突字段，update_fields可能为空
        for field in conflict_fields:
            # 检查字段是否是自增主键
            is_auto_increment_pk = False
            if hasattr(model_class._meta, 'pk_attr') and field == model_class._meta.pk_attr:
                pk_field = model_class._meta.fields_map.get(field)
                if pk_field and pk_field.generated:
                    is_auto_increment_pk = True
            # 跳过自增主键的验证
            if not is_auto_increment_pk and field not in all_fields:
                raise ValueError(f"字段 {field} 不在数据字段中")
        
        # 注意：不再验证update_fields是否在all_fields中，因为不同批次可能包含不同的字段
        # update_fields是从所有数据中收集的，而all_fields是从当前批次中收集的
        
        # 构建字段字符串，使用反引号包裹字段名
        fields_str = ', '.join([f"`{field}`" for field in all_fields])
        total_inserted = 0
        total_updated = 0
        failed_batches = []
        
        # 动态调整批量大小，避免锁等待超时
        # 对于批量upsert操作，使用较小的批量大小
        batch_size = min(self.batch_size, 500)  # 减小批量大小，降低锁竞争
        
        # 分批处理
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            
            # 构建 VALUES 占位符和参数
            placeholders = []
            values = []
            for data in batch:
                # 只包含需要的字段，对于不存在的字段使用None
                row_values = [data.get(field) for field in all_fields]
                placeholders.append('(' + ', '.join(['%s'] * len(all_fields)) + ')')
                values.extend(row_values)
            
            # 检查是否有数据要插入
            if not placeholders:
                logger.warning(f"批次 {i//batch_size + 1} 没有数据要插入，跳过执行")
                continue
            
            # 构建 SQL
            if update_fields:
                # 如果有update_fields，构建完整的UPSERT语句
                # 获取当前批次中实际存在的字段
                batch_fields_set = set()
                for data in batch:
                    batch_fields_set.update(data.keys())
                # 只更新在当前批次中实际存在且数据库表中存在的字段
                batch_update_fields = [field for field in update_fields if field in batch_fields_set and field.lower() in db_field_names]
                
                if batch_update_fields:
                    # 构建 ON DUPLICATE KEY UPDATE 部分
                    update_parts = [f"`{field}` = VALUES(`{field}`)" for field in batch_update_fields]
                    update_str = ', '.join(update_parts)
                    
                    sql = f"""
                    INSERT INTO `{table_name}` ({fields_str}) 
                    VALUES {', '.join(placeholders)}
                    ON DUPLICATE KEY UPDATE
                    {update_str}
                    """
                else:
                    # 如果当前批次中没有需要更新的字段，使用INSERT IGNORE
                    sql = f"INSERT IGNORE INTO `{table_name}` ({fields_str}) VALUES {', '.join(placeholders)}"
            else:
                # 如果没有update_fields，只执行INSERT IGNORE
                sql = f"INSERT IGNORE INTO `{table_name}` ({fields_str}) VALUES {', '.join(placeholders)}"
            
            # 执行 SQL
            try:
                affected, result_data = await self._execute_native_sql(
                    sql, 
                    values,
                    description=f"批量 upsert 批次 {i//batch_size + 1}"
                )
                
                # 计算新增和更新数量
                if update_fields:
                    # 对于 INSERT INTO ... ON DUPLICATE KEY UPDATE:
                    # - 新增行：影响行数 = 1
                    # - 更新行：影响行数 = 2
                    # - 未改变：影响行数 = 0
                    # 使用实际处理的数据行数（len(batch)）代替batch_size，因为可能有重复数据
                    actual_size = len(batch)
                    affected = affected or 0
                    updated = max(0, affected - actual_size)
                    inserted = affected - 2 * updated
                    # 确保插入数量为非负数
                    inserted = max(0, inserted)
                else:
                    # 对于 INSERT IGNORE:
                    # - 成功插入：影响行数 = 1
                    # - 忽略冲突：影响行数 = 0
                    inserted = affected or 0
                    updated = 0
                
                logger.info(f"批量upsert执行成功: 表={table_name}, 批次={i//batch_size + 1}, 影响行数={affected}, 插入={inserted}, 更新={updated}")
                
                total_inserted = (total_inserted or 0) + inserted
                total_updated = (total_updated or 0) + updated
                
                self.stats['batches_executed'] += 1
                
                # 每处理完一个批次，短暂休眠，避免过度占用数据库资源
                await asyncio.sleep(0.1)
            except Exception as e:
                # 记录错误并继续处理下一批次
                # 注意：底层的 _execute_native_sql 已经通过 @handle_db_errors 装饰器记录了错误日志
                # 这里只记录 SQL 语句以便调试，避免重复记录错误信息
                logger.error(f"执行批量upsert批次失败，SQL语句: {sql}")
                # 累计失败批次信息，供上层感知写库失败（避免静默丢失数据）
                failed_batches.append({
                    "batch": i // batch_size + 1,
                    "error": str(e)
                })
                # 跳过当前批次，继续处理下一批次
                continue
        
        return {
            'inserted': total_inserted or 0,
            'updated': total_updated or 0,
            'total': (total_inserted or 0) + (total_updated or 0),
            'errors': failed_batches
        }
    
    
    @handle_db_errors(max_retries=3)
    async def _bulk_upsert_orm(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None
    ) -> Dict[str, int]:
        """
        使用 ORM 的 bulk_create 执行批量 upsert
        适合小批量数据
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据列表（不能为空）
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段
            exclude_fields: 排除的字段列表（必须显式提供）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
            
        Raises:
            DbManagerError: 如果执行失败
        """        
        # 获取冲突字段
        # 获取数据库连接对象
        db = await self._get_valid_connection()
        conflict_fields = conflict_fields if conflict_fields is not None else self._get_conflict_fields(model_class)
        
        # 获取模型的主键字段
        pk_field = getattr(model_class._meta, 'pk_attr', None)

        # 如果未提供exclude_fields，则初始化为空列表
        # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
        if exclude_fields is None:
            exclude_fields = []
        
        # 注意：不要将冲突字段（包括主键）从数据中排除，它们是标识记录所必需的
        # 只需要在后续更新操作中确保不更新主键字段即可

        # 过滤排除字段
        filtered_data = []
        for data in data_list:
            filtered_data.append({k: v for k, v in data.items() 
                               if k not in exclude_fields})
        
        # 查询已存在的记录
        existing_records = []
        if conflict_fields:
            # 构建查询条件
            conditions = []
            for data in filtered_data:
                condition = {}  # 将条件改为字典类型
                for field in conflict_fields:
                    if field in data:
                        condition[field] = data[field]
                if condition:
                    conditions.append(condition)
            
            # 查询所有满足冲突条件的记录
            # 使用 Q 对象构建 OR 查询
            if conditions:
                # 第一个条件作为基础
                query = Q(**conditions[0])
                # 为每个条件创建 Q 对象并使用 OR 连接
                for condition in conditions[1:]:
                    query |= Q(**condition)
                
                existing_records = await model_class.filter(query).only(*conflict_fields).using_db(db).all()
            else:
                existing_records = []
        
        # 创建模型实例
        instances = [model_class(**data) for data in filtered_data]
        
        # 使用 bulk_create
        # 如果没有update_fields，不执行更新操作（仅插入）
        if existing_records:# update_fields:
            # 使用指定的数据库连接执行bulk_create
            if len(filtered_data) == 1:
                await existing_records[0].update_from_dict(filtered_data[0])
                # 获取需要更新的字段列表，确保不包含主键字段
                update_fields_list = [field for field in filtered_data[0].keys() if field != pk_field]
                await existing_records[0].save(update_fields=update_fields_list)
                # await model_class.filter(query).only(*conflict_fields).using_db(db).all().update_from_dict(filtered_data[0])
            else:
                # 确保update_fields不包含主键字段
                filtered_update_fields = None
                if update_fields:
                    filtered_update_fields = [field for field in update_fields if field != pk_field]
                await model_class.bulk_create(instances, on_conflict=conflict_fields, update_fields=filtered_update_fields, using_db=db)
            
        else:
            # 只执行插入操作，忽略冲突
            await model_class.bulk_create(instances, ignore_conflicts=True, using_db=db)
        
        # 计算新增和更新数量
        # 创建现有记录的冲突字段值的集合，用于快速查找
        existing_keys = set()
        for record in existing_records:
            key = tuple(getattr(record, field) for field in conflict_fields)
            existing_keys.add(key)
        
        # 计算新增和更新数量
        updated_count = 0
        inserted_count = 0
        
        for data in filtered_data:
            key = tuple(data.get(field) for field in conflict_fields)
            if key in existing_keys:
                updated_count += 1
            else:
                inserted_count += 1
        
        return {
            'inserted': inserted_count or 0,
            'updated': updated_count or 0,
            'total': (inserted_count or 0) + (updated_count or 0)
        }
    

    @with_transaction
    @handle_db_errors(max_retries=3)
    async def bulk_upsert(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None,
        use_orm_or_sql: Literal["orm", "sql", "auto"] = "sql",
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        批量 upsert 主方法
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据字典列表（不能为空）
            conflict_fields: 冲突检测字段（必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段列表（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 要排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            use_orm_or_sql: 显式指定使用 ORM 或 SQL 执行批量 upsert，默认使用 SQL 执行 （auto时根据数据量自动选择）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
        Returns:
            执行统计信息
            
        Raises:
            DbManagerError: 如果执行失败且使用事务
        """
        start_time = datetime.now()
        db_table = model_class._meta.db_table
        
        # 获取冲突字段（需要在计算默认update_fields之前获取）
        if conflict_fields is None:
            conflict_fields = self._get_conflict_fields(model_class, conflict_fields)
        
        # 如果未提供exclude_fields，则初始化为空列表
        # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
        if exclude_fields is None:
            exclude_fields = []
        
        # 如果未提供update_fields，则自动使用所有非冲突非排除字段作为默认更新字段
        if update_fields is None and data_list:
            # 收集所有记录中的所有字段
            all_fields = set()
            for data in data_list:
                all_fields.update(data.keys())
            # 获取冲突字段和排除字段的集合
            # 注意：即使exclude_fields为空，也需要排除冲突字段，因为它们不应该被更新
            excluded_set = set(conflict_fields) | set(exclude_fields)
            # 计算默认更新字段：所有非冲突非排除字段
            update_fields = list(all_fields - excluded_set)
        
        # 选择执行策略
        if use_orm_or_sql == "orm" or (use_orm_or_sql == "auto" and len(data_list) < 100):
            method = "orm"
            result = await self._bulk_upsert_orm(
                model_class, data_list, update_fields,
                exclude_fields, conflict_fields
            )
        else:
            method = "native_sql"
            result = await self._bulk_upsert_native_sql(
                model_class, data_list, update_fields, 
                exclude_fields, conflict_fields
            )

        execution_time = (datetime.now() - start_time).total_seconds()
        
        # 更新统计
        self.stats['total_processed'] += len(data_list)
        self.stats['last_execution_time'] = execution_time
        
        # 记录批量操作性能，用于动态调整批量大小
        self._record_batch_performance(len(data_list), execution_time)
        
        batch_errors = result.get('errors', [])
        response = {
            "success": not batch_errors,
            "method": method,
            "total_records": len(data_list),
            "affected_rows": result['total'],
            "inserted": result['inserted'],
            "updated": result['updated'],
            "errors": batch_errors,
            "execution_time": execution_time,
            "batch_size": len(data_list),
            "optimal_batch_size": self.optimal_batch_size,
            "conflict_fields": conflict_fields,
            "update_fields": update_fields
        }
        
        logger.success("批量upsert", f"{db_table}@{self.connection_name}", f"插入{result['inserted']}条，更新{result['updated']}条，执行时间{execution_time:.3f}秒")
        return response


    @with_transaction
    @handle_db_errors(max_retries=3)
    async def single_upsert(
        self,
        model_class,
        data: Dict[str, Any],
        conflict_fields: Optional[Tuple[str, ...]] = None,
        # update_fields: Optional[List[str]] = None,
        # exclude_fields: Optional[List[str]] = None,
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        单条记录 upsert 操作
        
        Args:
            model_class: Tortoise 模型类
            data: 单条数据字典
            conflict_fields: 冲突检测字段（必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段列表（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 要排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            执行结果字典，包含操作类型、影响行数等信息
            
        Raises:
            ValueError: 如果存在多个与冲突字段匹配的记录
            DbManagerError: 如果执行失败
        """
        # 获取冲突字段
        if conflict_fields is None:
            conflict_fields = conflict_fields or self._get_conflict_fields(model_class)
            # 取字段交集：只保留既在 data 中也在 conflict_fields 里的键，为什么要这样做？
            conflict_fields = tuple(set(conflict_fields) & set(data.keys()))
            # 因为如果 data 中包含了不在 conflict_fields 里的字段，那么在 upsert 时就会报错
            # 具体应用场景：t_supply 联合主键（默认冲突字段）是 supplyno + materialno
            # 而 patch supply 时（单条），前端可能不传入 materialno
            # 此时若按联合主键索引，一则可能 raise materialno 不存在；其次，就算不报错，因为缺少 materialno，也无法索引出目标记录
        else:
            # 检查数据中是否包含所有冲突字段
            missing_fields = [field for field in conflict_fields if field not in data]
            if missing_fields:
                raise ValueError(f"数据中缺少必要的冲突字段: {', '.join(missing_fields)}")
        
        # 构建查询条件
        query_conditions = {field: data[field] for field in conflict_fields}
        
        # 查询是否存在记录
        conn = await self._get_valid_connection()
        conflict_check_sql = f"""
        SELECT COUNT(*) as count FROM `{model_class._meta.db_table}`
        WHERE {' AND '.join([f'`{field}` = %s' for field in conflict_fields])}
        """
        
        # 执行查询
        result = await conn.execute_query(conflict_check_sql, list(query_conditions.values()))
        count = result[1][0]['count']
        
        # 如果存在多条冲突记录，抛出错误
        if count > 1:
            raise ValueError(f"检测到多个 {', '.join(conflict_fields)} 匹配的记录，无法执行单条 upsert 操作")
        
        # 计算更新字段
        update_fields = tuple(set(data.keys()) - set(conflict_fields))
        
        # 根据记录是否存在，决定执行INSERT还是UPDATE
        conn = await self._get_valid_connection()
        
        if count == 0:
            # 执行INSERT操作
            fields = list(data.keys())
            placeholders = ['%s'] * len(fields)
            values = list(data.values())
            
            insert_sql = f"""
            INSERT INTO `{model_class._meta.db_table}` ({', '.join([f'`{k}`' for k in fields])})
            VALUES ({', '.join(placeholders)})
            """
            
            result = await conn.execute_query(insert_sql, values)
            affected_rows = result[0]
            operation_type = 'inserted'
        else:
            # 执行UPDATE操作
            if not update_fields:
                # 没有需要更新的字段
                affected_rows = 0
                operation_type = 'no_change'
            else:
                update_parts = [f'`{field}` = %s' for field in update_fields]
                where_parts = [f'`{field}` = %s' for field in conflict_fields]
                
                update_sql = f"""
                UPDATE `{model_class._meta.db_table}`
                SET {', '.join(update_parts)}
                WHERE {' AND '.join(where_parts)}
                """
                
                # 构建参数列表：先更新字段的值，再冲突字段的值
                update_values = [data[field] for field in update_fields]
                conflict_values = [data[field] for field in conflict_fields]
                all_values = update_values + conflict_values
                
                result = await conn.execute_query(update_sql, all_values)
                affected_rows = result[0]
                operation_type = 'updated'
        
        return {
            'success': True,
            'operation_type': operation_type,
            'affected_rows': affected_rows,
            'conflict_fields': conflict_fields,
            'update_fields': update_fields,
            'inserted': 1 if operation_type == 'inserted' else 0,
            'updated': 1 if operation_type == 'updated' else 0
        }


    @with_transaction
    @handle_db_errors(max_retries=3)
    async def conditional_bulk_upsert(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_rules: Dict[str, str],
        condition_field: str,
        condition_value: Any,
        conflict_fields: Optional[Tuple[str, ...]] = None,
        use_transaction: Optional[bool] = None
    ) -> Dict[str, int]:
        """
        条件批量 upsert
        支持更复杂的更新逻辑
        
        Args:
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_rules: 更新规则字典，key为字段名，value为SQL表达式
                注意：所有表达式必须包含VALUES
                例如: {'quantity': 'quantity + VALUES(quantity)', 'price': 'VALUES(price)'}
            condition_field: 条件字段（必需）
            condition_value: 条件值（必需）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
            
        Raises:
            DbManagerError: 如果执行失败
        """
        # 获取冲突字段
        conflict_fields = self._get_conflict_fields(model_class, conflict_fields)

        table_name = model_class._meta.db_table
        all_fields = list(data_list[0].keys())
        fields_str = ', '.join([f"`{field}`" for field in all_fields])
        
        total_inserted = 0
        total_updated = 0
        
        async def execute_batch():
            nonlocal total_inserted, total_updated
            for i in range(0, len(data_list), self.batch_size):
                batch = data_list[i:i + self.batch_size]
                batch_size = len(batch)
                
                # 构建 VALUES
                placeholders = []
                values = []
                for data in batch:
                    row_values = [data[field] for field in all_fields]
                    placeholders.append('(' + ', '.join(['%s'] * len(all_fields)) + ')')
                    values.extend(row_values)
                
                # 构建条件更新
                update_parts = []
                for field, expression in update_rules.items():
                    if 'VALUES' not in expression:
                        raise ValueError(f"更新规则表达式必须包含VALUES: {field} = {expression}")
                    update_parts.append(f"`{field}` = {expression}")
                
                # 添加条件
                where_clause = f"WHERE `{condition_field}` = %s"
                values.append(condition_value)
                
                # 为冲突字段字符串添加反引号包裹
                conflict_fields_str = ', '.join([f"`{field}`" for field in conflict_fields])
                update_str = ', '.join(update_parts)
                
                # 构建 SQL 语句
                sql = f"""
                INSERT INTO `{table_name}` ({fields_str}) 
                VALUES {', '.join(placeholders)}
                ON DUPLICATE KEY UPDATE
                {update_str}
                {where_clause}
                """
                
                affected, data_list = await self._execute_native_sql(
                    sql, values, f"条件批量 upsert 批次 {i//self.batch_size + 1}"
                )
                
                # 计算新增和更新数量
                # 对于条件更新，我们需要预查询来获取更准确的计数
                # 先查询已存在的记录
                existing_records = []
                if conflict_fields:
                    # 构建查询条件
                    conditions = []
                    for data in batch:
                        condition = {}
                        for field in conflict_fields:
                            condition[field] = data[field]
                        conditions.append(condition)
                    
                    # 查询所有满足冲突条件的记录
                    # 使用 Q 对象构建 OR 查询
                    if conditions:
                        # 第一个条件作为基础
                        query = Q(**conditions[0])
                        # 为每个条件创建 Q 对象并使用 OR 连接
                        for condition in conditions[1:]:
                            query |= Q(**condition)
                        
                        existing_records = await model_class.filter(
                            query
                        ).using_db(self.connection_name).all()
                    else:
                        existing_records = []
                
                # 计算新增数量
                inserted = batch_size - len(existing_records)
                
                # 计算更新数量
                # 对于条件更新，影响行数可能不等于更新行数
                # 影响行数 = 新增行数 + 更新成功的行数
                updated = max(0, affected - inserted)
                
                total_inserted = (total_inserted or 0) + inserted
                total_updated = (total_updated or 0) + updated
        
        # 移除事务分支，直接执行批次处理
        await execute_batch()
        
        return {
            'inserted': total_inserted or 0,
            'updated': total_updated or 0,
            'total': (total_inserted or 0) + (total_updated or 0)
        }
    

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_processed': 0,
            'batches_executed': 0,
            'last_execution_time': None
        }
    
    def _record_batch_performance(self, batch_size: int, execution_time: float):
        """
        记录批量操作性能，用于动态调整批量大小
        
        Args:
            batch_size: 批量大小
            execution_time: 执行时间（秒）
        """
        if execution_time > 0:
            # 计算每秒处理记录数
            records_per_second = batch_size / execution_time
            self.batch_size_history.append({
                'batch_size': batch_size,
                'execution_time': execution_time,
                'records_per_second': records_per_second
            })
            
            # 限制历史记录数量
            if len(self.batch_size_history) > 50:
                self.batch_size_history = self.batch_size_history[-50:]
            
            # 每10次操作调整一次批量大小
            if len(self.batch_size_history) % self.batch_size_adjustment_interval == 0:
                self._adjust_batch_size()
    
    def _adjust_batch_size(self):
        """
        根据历史性能数据调整批量大小
        """
        if len(self.batch_size_history) < 5:
            return
        
        # 分析最近的性能数据
        recent_history = self.batch_size_history[-10:]
        
        # 计算不同批量大小的平均性能
        batch_performance = {}
        for record in recent_history:
            batch_size = record['batch_size']
            if batch_size not in batch_performance:
                batch_performance[batch_size] = []
            batch_performance[batch_size].append(record['records_per_second'])
        
        # 计算每个批量大小的平均性能
        avg_performance = {}
        for batch_size, performances in batch_performance.items():
            avg_performance[batch_size] = sum(performances) / len(performances)
        
        # 找出性能最好的批量大小
        best_batch_size = max(avg_performance, key=avg_performance.get)
        best_performance = avg_performance[best_batch_size]
        
        # 计算当前批量大小的性能
        current_performance = avg_performance.get(self.batch_size, 0)
        
        # 如果最佳批量大小的性能比当前高20%以上，则调整
        if best_performance > current_performance * 1.2:
            # 调整批量大小，在最佳批量大小基础上进行微调
            new_batch_size = int(best_batch_size * 1.1)  # 稍微增加一点
            new_batch_size = max(self.min_batch_size, min(self.max_batch_size, new_batch_size))
            
            if new_batch_size != self.batch_size:
                # 避免除以零的错误
                if current_performance > 0:
                    performance_improvement = ((best_performance / current_performance) - 1) * 100
                    logger.info(f"调整批量大小: {self.batch_size} -> {new_batch_size}, 性能提升: {performance_improvement:.1f}%")
                else:
                    logger.info(f"调整批量大小: {self.batch_size} -> {new_batch_size}")
                self.batch_size = new_batch_size
                self.optimal_batch_size = new_batch_size
    
    def _check_index_usage(self, table_name: str, filter_string: str, order_string: str):
        """
        检查索引使用情况，提供索引优化建议
        
        Args:
            table_name: 表名
            filter_string: WHERE条件字符串
            order_string: ORDER BY排序字符串
        """
        # 简单的索引使用检查
        # 实际项目中可以根据数据库类型执行EXPLAIN查询来分析索引使用情况
        if filter_string:
            # 检查是否使用了索引字段
            # 这里只是简单的检查，实际项目中可以根据具体表结构和索引进行更详细的分析
            pass
        
        if order_string:
            # 检查排序字段是否有索引
            pass
    
    def _record_query_performance(self, table_name: str, record_count: int, execution_time: float):
        """
        记录查询性能，用于监控和优化
        
        Args:
            table_name: 表名
            record_count: 返回记录数
            execution_time: 执行时间（秒）
        """
        # 记录查询性能数据
        if execution_time > 0:
            records_per_second = record_count / execution_time
            # 可以将性能数据存储到监控系统中
            logger.debug(f"查询性能: {table_name} - {records_per_second:.2f} 条/秒, 执行时间: {execution_time:.3f}秒")
    

    def switch_connection(self, connection_name: str):
        """
        切换数据库连接
        
        Args:
            connection_name: 新的数据库连接名称
        """
        self.connection_name = connection_name
        logger.info(f"已切换数据库连接至：{connection_name}")
    
    async def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态（增强版）
        
        增强功能：
        - 优先使用增强管理器的状态信息
        - 包含连接池生命周期状态
        - 包含泄漏检测结果
        
        Returns:
            连接池状态信息
        """
        # 优先使用增强管理器
        if self._enhanced_pool_manager:
            try:
                pool_status = await self._enhanced_pool_manager.get_connection_pool_status()
                state_info = self._enhanced_pool_manager.get_state_info()
                
                status = {
                    'connection_name': self.connection_name,
                    'pool_available': pool_status.pool_available,
                    'total_connections': pool_status.total_connections,
                    'used_connections': pool_status.used_connections,
                    'idle_connections': pool_status.idle_connections,
                    'usage_rate': pool_status.usage_rate,
                    'timestamp': time.time(),
                    'warnings': [],
                    'alerts': [],
                    # 增强信息
                    'enhanced': {
                        'state': state_info.state.value,
                        'is_available': state_info.is_available,
                        'update_reason': state_info.update_reason,
                        'last_update_time': state_info.last_update_time.isoformat() if state_info.last_update_time else None
                    }
                }
                
                # 使用率预警
                if status['usage_rate'] >= 90:
                    status['alerts'].append(f"连接池使用率过高: {status['usage_rate']:.1f}%")
                elif status['usage_rate'] >= 80:
                    status['warnings'].append(f"连接池使用率较高: {status['usage_rate']:.1f}%")
                
                # 空闲连接预警
                if status['idle_connections'] == 0:
                    status['warnings'].append("连接池没有空闲连接")
                
                # 状态预警
                if not state_info.is_available:
                    status['alerts'].append(f"连接池不可用: {state_info.state.value}")
                
                return status
            except Exception as e:
                logger.warning(f"增强管理器获取连接池状态失败: {e}，使用原有逻辑")
        
        # 原有逻辑作为后备
        try:
            conn = Tortoise.get_connection(self.connection_name)
            pool = conn._pool if hasattr(conn, '_pool') else None
            
            status = {
                'connection_name': self.connection_name,
                'pool_available': pool is not None,
                'timestamp': time.time(),
                'warnings': [],
                'alerts': []
            }
            
            if pool:
                # 不同数据库后端的连接池属性可能不同
                # 尝试多种可能的属性名称
                # 当前连接数
                if hasattr(pool, '_size'):
                    status['current_size'] = pool._size
                elif hasattr(pool, 'size'):
                    status['current_size'] = pool.size
                elif hasattr(pool, 'current_size'):
                    status['current_size'] = pool.current_size
                elif hasattr(pool, '_connections'):
                    status['current_size'] = len(pool._connections)
                elif hasattr(pool, 'connections'):
                    status['current_size'] = len(pool.connections)
                else:
                    status['current_size'] = 10  # 默认值
                
                # 最大连接数
                if hasattr(pool, '_maxsize'):
                    status['max_size'] = pool._maxsize
                elif hasattr(pool, 'maxsize'):
                    status['max_size'] = pool.maxsize
                elif hasattr(pool, 'max_size'):
                    status['max_size'] = pool.max_size
                elif hasattr(pool, 'maximum_size'):
                    status['max_size'] = pool.maximum_size
                else:
                    status['max_size'] = 30  # 默认值
                
                # 最小连接数
                if hasattr(pool, '_minsize'):
                    status['min_size'] = pool._minsize
                elif hasattr(pool, 'minsize'):
                    status['min_size'] = pool.minsize
                elif hasattr(pool, 'min_size'):
                    status['min_size'] = pool.min_size
                elif hasattr(pool, 'minimum_size'):
                    status['min_size'] = pool.minimum_size
                else:
                    status['min_size'] = 10  # 默认值
                
                # 空闲连接数
                if hasattr(pool, '_idle'):
                    status['idle_connections'] = len(pool._idle)
                elif hasattr(pool, 'idle'):
                    status['idle_connections'] = len(pool.idle)
                elif hasattr(pool, 'idle_connections'):
                    status['idle_connections'] = pool.idle_connections
                elif hasattr(pool, 'free'):
                    status['idle_connections'] = len(pool.free)
                elif hasattr(pool, 'free_connections'):
                    status['idle_connections'] = pool.free_connections
                elif hasattr(pool, '_free'):
                    status['idle_connections'] = len(pool._free)
                else:
                    status['idle_connections'] = status.get('current_size', 10)  # 默认值
                
                # 使用中连接数
                if hasattr(pool, '_used'):
                    status['used_connections'] = len(pool._used)
                elif hasattr(pool, 'used'):
                    status['used_connections'] = len(pool.used)
                elif hasattr(pool, 'used_connections'):
                    status['used_connections'] = pool.used_connections
                elif hasattr(pool, 'in_use'):
                    status['used_connections'] = len(pool.in_use)
                elif hasattr(pool, 'busy'):
                    status['used_connections'] = len(pool.busy)
                elif hasattr(pool, 'busy_connections'):
                    status['used_connections'] = pool.busy_connections
                elif hasattr(pool, '_busy'):
                    status['used_connections'] = len(pool._busy)
                # 如果无法直接获取使用中连接数，尝试计算
                elif 'current_size' in status and 'idle_connections' in status:
                    status['used_connections'] = status['current_size'] - status['idle_connections']
                # 直接设置默认值
                else:
                    status['used_connections'] = 0  # 默认值
                
                # 计算使用率和预警
                if status.get('max_size', 0) > 0:
                    status['usage_rate'] = status['used_connections'] / status['max_size'] * 100
                    
                    # 使用率预警
                    if status['usage_rate'] >= 90:
                        status['alerts'].append(f"连接池使用率过高: {status['usage_rate']:.1f}%")
                    elif status['usage_rate'] >= 80:
                        status['warnings'].append(f"连接池使用率较高: {status['usage_rate']:.1f}%")
                    
                    # 空闲连接预警
                    if status['idle_connections'] == 0:
                        status['warnings'].append("连接池没有空闲连接")
            
            return status
        except Exception as e:
            logger.error(f"获取连接池状态失败: {e}")
            return {
                'connection_name': self.connection_name,
                'pool_available': False,
                'error': str(e),
                'timestamp': time.time()
            }
    
    async def check_connection_health(self, timeout: int = 5, fast_mode: bool = False) -> bool:
        """
        检查数据库连接健康状态
        
        Args:
            timeout: 查询超时时间（秒）
            fast_mode: 是否使用快速模式，快速模式下刷新连接时使用较少的重试次数
            
        Returns:
            bool: 连接是否健康
        """
        # 优先使用增强管理器
        if self._enhanced_pool_manager:
            try:
                result = await self._enhanced_pool_manager.check_health(timeout=timeout)
                if not result.is_healthy and fast_mode:
                    await self.refresh_connection(fast_mode=True)
                    result = await self._enhanced_pool_manager.check_health(timeout=timeout)
                return result.is_healthy
            except Exception as e:
                logger.warning(f"增强管理器健康检查失败: {e}，使用原有逻辑")
        
        # 原有逻辑作为后备
        try:
            import asyncio
            conn = Tortoise.get_connection(self.connection_name)
            # 执行一个简单的查询来检查连接是否有效，添加超时设置
            await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"数据库连接健康检查超时: {self.connection_name}")
            # 尝试刷新连接
            await self.refresh_connection(fast_mode=fast_mode)
            # 再次检查连接
            try:
                conn = Tortoise.get_connection(self.connection_name)
                await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
                return True
            except Exception as e:
                logger.warning(f"刷新连接后健康检查仍失败: {e}")
                return False
        except Exception as e:
            logger.warning(f"数据库连接健康检查失败: {e}")
            # 尝试刷新连接
            await self.refresh_connection(fast_mode=fast_mode)
            # 再次检查连接
            try:
                conn = Tortoise.get_connection(self.connection_name)
                await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
                return True
            except Exception as e:
                logger.warning(f"刷新连接后健康检查仍失败: {e}")
                return False
    
    async def refresh_connection(self, fast_mode: bool = False):
        """
        刷新数据库连接，确保连接有效
        当出现数据包序列号错误等协议层问题时，会强制重新创建连接
        
        Args:
            fast_mode: 是否使用快速模式，快速模式下使用较少的重试次数和较短的等待时间
        """
        # 优先使用增强管理器
        if self._enhanced_pool_manager:
            try:
                success = await self._enhanced_pool_manager.refresh_connection(fast_mode=fast_mode)
                if success:
                    return
                logger.warning("增强管理器刷新失败，使用原有逻辑")
            except Exception as e:
                logger.warning(f"增强管理器刷新异常: {e}，使用原有逻辑")
        
        # 原有逻辑作为后备
        import asyncio
        import time
        from tortoise.connection import connections
        # 根据模式设置不同的重试参数
        if fast_mode:
            retry_count = 3  # 快速模式下减少重试次数
            retry_delay = 1.0  # 快速模式下减少初始延迟
        else:
            retry_count = 5  # 正常模式下增加重试次数
            retry_delay = 2.0  # 正常模式下增加初始延迟
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                logger.info(f"尝试刷新连接 {self.connection_name} (尝试 {attempt + 1}/{retry_count})")
                
                # 1. 尝试获取并关闭当前连接
                try:
                    conn = Tortoise.get_connection(self.connection_name)
                    
                    # 关闭当前连接（如果存在且可关闭）
                    if conn and hasattr(conn, 'close'):
                        try:
                            # 检查是否是TransactionWrapper（通过检查是否有_pool属性）
                            if hasattr(conn, '_pool'):
                                # 尝试关闭连接，但如果出现事件循环冲突，就跳过
                                try:
                                    await conn.close()
                                    logger.info(f"已关闭旧连接: {self.connection_name}")
                                except Exception as close_error:
                                    # 如果是事件循环冲突，就跳过关闭操作
                                    if "bound to a different event loop" in str(close_error):
                                        logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                                    else:
                                        logger.warning(f"关闭旧连接时出错: {close_error}")
                            else:
                                # 对于TransactionWrapper，尝试获取内部连接并关闭
                                if hasattr(conn, 'connection'):
                                    inner_conn = conn.connection
                                    if inner_conn and hasattr(inner_conn, 'close'):
                                        try:
                                            await inner_conn.close()
                                            logger.info(f"已关闭TransactionWrapper内部连接: {self.connection_name}")
                                        except Exception as inner_close_error:
                                            # 如果是事件循环冲突，就跳过关闭操作
                                            if "bound to a different event loop" in str(inner_close_error):
                                                logger.warning(f"关闭TransactionWrapper内部连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                                            else:
                                                logger.warning(f"关闭TransactionWrapper内部连接时出错: {inner_close_error}")
                                logger.info(f"处理TransactionWrapper连接: {self.connection_name}")
                        except Exception as close_error:
                            # 如果是事件循环冲突，就跳过关闭操作
                            if "bound to a different event loop" in str(close_error):
                                logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                            else:
                                logger.warning(f"关闭旧连接时出错: {close_error}")
                except Exception as get_conn_error:
                    logger.warning(f"获取当前连接时出错: {get_conn_error}")
                
                # 2. 从 Tortoise ORM 的连接存储中移除损坏的连接
                # 这样下次调用 connections.get() 时会自动创建新的连接
                try:
                    connections.discard(self.connection_name)
                    logger.info(f"已从连接存储中移除: {self.connection_name}")
                except Exception as discard_error:
                    logger.warning(f"移除连接时出错: {discard_error}")
                
                # 3. Tortoise ORM已由lifespan初始化，禁止运行时重新初始化
                # 运行时重新初始化会破坏TortoiseContext导致所有请求失败
                if not hasattr(Tortoise, '_inited') or not Tortoise._inited:
                    logger.error(f"Tortoise未初始化，无法刷新连接。请等待应用启动完成")
                    raise RuntimeError("Tortoise ORM未初始化，请等待应用启动完成")
                
                # 3. 等待一段时间，确保连接完全关闭
                if fast_mode:
                    wait_time = 0.5 + attempt * 0.5  # 快速模式下使用较短的等待时间
                else:
                    wait_time = 1.0 + attempt * 1.0  # 正常模式下使用较长的等待时间
                logger.info(f"等待 {wait_time:.1f} 秒，确保连接完全关闭...")
                await asyncio.sleep(wait_time)
                
                # 4. 尝试重新获取连接（会自动创建新的连接）
                try:
                    logger.info(f"尝试创建新连接: {self.connection_name}")
                    new_conn = connections.get(self.connection_name)
                    
                    # 5. 检查新连接是否有效
                    if new_conn:
                        # 执行一个简单的查询来验证连接
                        logger.info(f"验证新连接: {self.connection_name}")
                        await new_conn.execute_query("SELECT 1")
                        elapsed_time = time.time() - start_time
                        logger.info(f"数据库连接已刷新并验证: {self.connection_name} (耗时: {elapsed_time:.2f}秒)")
                        return True
                    else:
                        logger.error(f"刷新数据库连接失败: 无法获取新连接")
                        if attempt < retry_count - 1:
                            logger.info(f"将在 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 1.5  # 指数退避
                        continue
                except Exception as get_conn_error:
                    logger.error(f"获取新连接时出错: {get_conn_error}")
                    # 针对 Packet sequence number 错误进行特殊处理
                    if "Packet sequence number wrong" in str(get_conn_error):
                        logger.error(f"检测到数据包序列号错误，这是 MySQL 协议层问题")
                        logger.error(f"将进行更彻底的连接重置...")
                        # 额外等待一段时间
                        if fast_mode:
                            await asyncio.sleep(1.0)  # 快速模式下使用较短的等待时间
                        else:
                            await asyncio.sleep(2.0)  # 正常模式下使用较长的等待时间
                    if attempt < retry_count - 1:
                        logger.info(f"将在 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # 指数退避
                    continue
            except Exception as e:
                logger.error(f"刷新数据库连接失败: {e}")
                if attempt < retry_count - 1:
                    logger.info(f"将在 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # 指数退避
                continue
        
        # 所有尝试都失败
        logger.error(f"所有尝试都失败: 无法刷新数据库连接 {self.connection_name}")
        return False


    @with_transaction
    @handle_db_errors(max_retries=3)
    async def update_by_index(
        self,
        model_class,
        index_dict: Dict[str, Any],
        new_values_dict: Dict[str, Any],
        not_found_behavior: Literal["insert", "error", "skip"] = "error",
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        基于索引更新记录，支持更新联合主键字段
        
        Args:
            model_class: Tortoise 模型类
            index_dict: 用于索引记录的字典，包含旧的键值
            new_values_dict: 新值构成的字典，可包含联合主键字段
            not_found_behavior: 找不到记录时的行为："insert" 新增，"error" 报错，"skip" 略过
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            执行结果字典，包含操作类型、影响行数等信息
            
        Raises:
            ValueError: 当 not_found_behavior 为 "error" 且找不到记录时
            DbQueryError: 当数据库操作失败时
            DbConnectionError: 当数据库连接失败时
        """
        start_time = datetime.now()
        
        # 先检查连接是否健康，如果不健康就刷新连接
        is_healthy = await self.check_connection_health(fast_mode=True)
        if not is_healthy:
            logger.warning(f"数据库连接不健康，将刷新连接: {self.connection_name}")
            await self.refresh_connection(fast_mode=True)
        
        table_name = model_class._meta.db_table
        conn = await self._get_valid_connection()
        
        # 构建 WHERE 子句（使用旧值）
        where_parts = []
        where_values = []
        for field, value in index_dict.items():
            where_parts.append(f"`{field}` = %s")
            where_values.append(value)
        
        where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        # 检查记录是否存在
        check_sql = f"SELECT COUNT(*) as count FROM `{table_name}`{where_clause}"
        result = await conn.execute_query(check_sql, where_values)
        count = result[1][0]['count']
        
        if count == 0:
            if not_found_behavior == "error":
                raise ValueError(f"未找到匹配记录: {index_dict}")
            elif not_found_behavior == "insert":
                # 执行插入操作
                all_fields = list(index_dict.keys()) + list(new_values_dict.keys())
                all_fields = list(set(all_fields))  # 去重
                
                fields_str = ', '.join([f"`{field}`" for field in all_fields])
                placeholders = ', '.join(['%s'] * len(all_fields))
                
                values = []
                for field in all_fields:
                    if field in new_values_dict:
                        values.append(new_values_dict[field])
                    elif field in index_dict:
                        values.append(index_dict[field])
                
                insert_sql = f"INSERT INTO `{table_name}` ({fields_str}) VALUES ({placeholders})"
                affected_rows, data_list = await self._execute_native_sql(
                    insert_sql, 
                    values,
                    description="基于索引更新 - 新增记录"
                )
                
                operation_type = 'inserted'
            else:  # skip
                affected_rows = 0
                operation_type = 'skipped'
        else:
            # 执行更新操作
            # 构建 SET 子句（使用新值）
            set_parts = []
            set_values = []
            for field, value in new_values_dict.items():
                set_parts.append(f"`{field}` = %s")
                set_values.append(value)
            
            if not set_parts:
                affected_rows = 0
                operation_type = 'no_change'
            else:
                set_clause = " SET " + ", ".join(set_parts)
                update_sql = f"UPDATE `{table_name}`{set_clause}{where_clause}"
                
                affected_rows, data_list = await self._execute_native_sql(
                    update_sql, 
                    set_values + where_values,
                    description="基于索引更新 - 更新记录"
                )
                
                operation_type = 'updated'
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # 更新统计信息
        self.stats['total_processed'] += 1
        self.stats['batches_executed'] += 1
        self.stats['last_execution_time'] = execution_time
        
        response = {
            "success": True,
            "operation_type": operation_type,
            "affected_rows": affected_rows,
            "index_dict": index_dict,
            "updated_fields": list(new_values_dict.keys()),
            "execution_time": execution_time
        }
        
        logger.success("索引更新", f"{table_name}@{self.connection_name}", f"影响{affected_rows}行")
        return response


# 延迟初始化 db_managers
_db_managers = None

def get_db_managers():
    """
    获取数据库管理器实例字典
    返回同一个实例字典，确保统计信息的持久化
    """
    global _db_managers
    if _db_managers is None:
        _db_managers = {}
        for db in MYAPS_DBSET_LIST:
            _db_managers[db] = DbManager(db)
    return _db_managers

# 为了保持向后兼容，提供一个模块级别的变量
# 但在实际使用中，建议使用 get_db_managers() 函数来获取
def db_managers():
    """
    获取数据库管理器实例字典
    每次调用都会返回最新的实例字典，确保使用当前事件循环的连接
    """
    return get_db_managers()


# ==================== 存储过程请求队列管理器 ====================

class ProcedureQueueManager:
    """
    存储过程请求队列管理器
    
    为高风险存储过程提供串行化执行能力，同一存储过程的请求会按顺序执行，
    不同存储过程可以并行执行。
    """
    
    # 类级别队列存储
    _queues: Dict[str, 'ProcedureQueue'] = {}
    
    @classmethod
    def get_queue(cls, procedure_name: str) -> 'ProcedureQueue':
        """
        获取指定存储过程的执行队列
        
        Args:
            procedure_name: 存储过程名称
            
        Returns:
            对应的执行队列实例
        """
        if procedure_name not in cls._queues:
            cls._queues[procedure_name] = ProcedureQueue(procedure_name)
        return cls._queues[procedure_name]
    
    @classmethod
    def get_all_queues(cls) -> List[Tuple[str, 'ProcedureQueue']]:
        """获取所有队列信息"""
        return list(cls._queues.items())
    
    @classmethod
    def get_queue_stats(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有队列的统计信息"""
        stats = {}
        for name, queue in cls._queues.items():
            stats[name] = queue.get_stats()
        return stats


class ProcedureQueue:
    """
    单个存储过程的执行队列
    
    使用FIFO队列保证请求顺序执行，避免并发导致的死锁。
    """
    
    def __init__(self, procedure_name: str):
        """
        初始化队列
        
        Args:
            procedure_name: 存储过程名称
        """
        self.procedure_name = procedure_name
        self._queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        
        # 统计信息
        self._total_requests = 0
        self._completed_requests = 0
        self._failed_requests = 0
        self._avg_wait_time = 0.0
        self._avg_exec_time = 0.0
        self._wait_time_history: List[float] = []
        self._exec_time_history: List[float] = []
    
    def _start_consumer(self):
        """启动队列消费者任务"""
        if self._task is None or self._task.done():
            self._is_running = True
            self._task = asyncio.create_task(self._consume())
    
    async def _consume(self):
        """队列消费者主循环"""
        while self._is_running:
            try:
                # 获取队列中的请求（无超时，持续等待）
                request = await self._queue.get()
                
                request_id = request['request_id']
                callback = request['callback']
                args = request['args']
                kwargs = request['kwargs']
                start_wait_time = request['start_time']
                
                # 计算等待时间
                wait_time = (datetime.now() - start_wait_time).total_seconds()
                self._wait_time_history.append(wait_time)
                if len(self._wait_time_history) > 100:
                    self._wait_time_history.pop(0)
                
                try:
                    # 执行回调函数
                    exec_start = datetime.now()
                    result = await callback(*args, **kwargs)
                    exec_time = (datetime.now() - exec_start).total_seconds()
                    
                    self._exec_time_history.append(exec_time)
                    if len(self._exec_time_history) > 100:
                        self._exec_time_history.pop(0)
                    
                    # 设置成功结果
                    request['future'].set_result(result)
                    self._completed_requests += 1
                    logger.debug(
                        "QueueConsumer",
                        f"{self.procedure_name}",
                        f"请求{request_id}执行成功，等待{wait_time:.2f}秒，执行{exec_time:.2f}秒"
                    )
                except Exception as e:
                    # 设置异常结果
                    request['future'].set_exception(e)
                    self._failed_requests += 1
                    logger.error(
                        "QueueConsumer",
                        f"{self.procedure_name}",
                        f"请求{request_id}执行失败: {str(e)}"
                    )
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("QueueConsumer", f"{self.procedure_name}", "消费者任务已取消")
                break
            except Exception as e:
                logger.error("QueueConsumer", f"{self.procedure_name}", f"消费者异常: {str(e)}")
        
        self._is_running = False
    
    async def enqueue(self, callback: Callable, *args, **kwargs) -> Any:
        """
        将请求加入队列并等待执行结果
        
        Args:
            callback: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            回调函数的执行结果
        """
        # 创建唯一请求ID
        request_id = str(uuid.uuid4())[:8]
        start_time = datetime.now()
        
        # 创建Future用于获取结果
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        # 构建请求对象
        request = {
            'request_id': request_id,
            'callback': callback,
            'args': args,
            'kwargs': kwargs,
            'future': future,
            'start_time': start_time
        }
        
        # 加入队列
        await self._queue.put(request)
        self._total_requests += 1
        
        # 确保消费者运行
        self._start_consumer()
        
        # 记录入队日志
        logger.debug(
            "QueueEnqueue",
            f"{self.procedure_name}",
            f"请求{request_id}已入队，当前队列长度: {self._queue.qsize()}"
        )
        
        # 等待执行结果（带超时保护）
        try:
            return await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            # 超时后取消 future，避免消费者最终返回时悬空
            if not future.done():
                future.cancel()
            raise DbDeadlockError(
                f"存储过程 {self.procedure_name} 排队超时（300秒）",
                operation="call_stored_procedure",
                connection="queue"
            ) from None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        wait_times = self._wait_time_history
        exec_times = self._exec_time_history
        
        return {
            'procedure_name': self.procedure_name,
            'queue_size': self._queue.qsize(),
            'is_running': self._is_running,
            'total_requests': self._total_requests,
            'completed_requests': self._completed_requests,
            'failed_requests': self._failed_requests,
            'avg_wait_time': sum(wait_times) / len(wait_times) if wait_times else 0.0,
            'max_wait_time': max(wait_times) if wait_times else 0.0,
            'avg_exec_time': sum(exec_times) / len(exec_times) if exec_times else 0.0,
            'max_exec_time': max(exec_times) if exec_times else 0.0
        }
    
    async def close(self):
        """关闭队列，停止消费者"""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


# 高风险存储过程列表（需要串行化执行的存储过程）
HIGH_RISK_PROCEDURES = {
    'SupplyConvertMOByE2A',
    'UpdateConfirmQtyToOrderWC',
}


def is_high_risk_procedure(procedure_name: str) -> bool:
    """
    判断存储过程是否为高风险（需要串行化执行）
    
    Args:
        procedure_name: 存储过程名称
        
    Returns:
        True: 高风险，需要串行化
        False: 普通存储过程，可以并行执行
    """
    return procedure_name in HIGH_RISK_PROCEDURES


def add_high_risk_procedure(procedure_name: str):
    """
    将存储过程标记为高风险
    
    Args:
        procedure_name: 存储过程名称
    """
    HIGH_RISK_PROCEDURES.add(procedure_name)
    logger.info("RiskProcedure", "ADD", f"已将{procedure_name}标记为高风险存储过程")


def remove_high_risk_procedure(procedure_name: str):
    """
    移除存储过程的高风险标记
    
    Args:
        procedure_name: 存储过程名称
    """
    HIGH_RISK_PROCEDURES.discard(procedure_name)
    logger.info("RiskProcedure", "REMOVE", f"已移除{procedure_name}的高风险标记")


def get_high_risk_procedures() -> list:
    """获取所有高风险存储过程列表"""
    return list(HIGH_RISK_PROCEDURES)