"""
数据库查询监测

通过 monkey-patch Tortoise ORM 各后端子类的 execute_query 拦截所有 SQL 执行，
记录语句/耗时/连接/调用栈，慢查询告警 + Prometheus 指标 + 内存队列。

patch 目标为 3 个具体子类（MySQLClient/AsyncpgDBClient/SqliteClient），
非基类 BaseDBAsyncClient（基类方法被子类覆盖，patch 基类不生效）。
"""
import time
import re
import random
import asyncio
import datetime
import traceback
from collections import deque
from typing import Optional, Dict, Any, List, Callable

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

from globalobjects import logger as log_config
from core.settings import (
    DB_QUERY_MONITOR_ENABLED,
    DB_QUERY_SLOW_THRESHOLD,
    DB_QUERY_LOG_ALL,
    DB_QUERY_HISTORY_SIZE,
    DB_QUERY_SAMPLE_RATE,
    MYAPS_DBSET_LIST,
    SQLITE_FILE,
)

logger = log_config.get_logger(__name__)

# ========== 全部连接名（用于前端筛选下拉框） ==========
# MySQL 账套 + SQLite 监控库，排除 default 别名，去空去重
# 不含 PostgreSQL staging 库（THIS_DB_NAME），清洗库查询不纳入业务筛选
_ALL_CONNECTION_NAMES: List[str] = []
_seen_conn = set()
for _c in [*MYAPS_DBSET_LIST, SQLITE_FILE]:
    if _c and _c != 'default' and _c not in _seen_conn:
        _ALL_CONNECTION_NAMES.append(_c)
        _seen_conn.add(_c)
del _seen_conn

# ========== SQL 分类 ==========
_SQL_PATTERN = re.compile(
    r'^\s*(SELECT|INSERT|UPDATE|DELETE|CALL|CREATE|ALTER|DROP|BEGIN|COMMIT|ROLLBACK|SET|SHOW|EXPLAIN)',
    re.IGNORECASE,
)

_HEALTH_CHECK_PATTERN = re.compile(r'^\s*SELECT\s+1\s*;?\s*$', re.IGNORECASE)


def classify_sql(sql: str) -> str:
    """识别 SQL 操作类型，返回小写类型名；无法识别返回 'other'"""
    if not sql:
        return 'other'
    m = _SQL_PATTERN.match(sql)
    return m.group(1).lower() if m else 'other'


def _is_health_check(query: str) -> bool:
    """判断是否为连接健康检查查询（如 SELECT 1），这类查询无业务价值应跳过记录"""
    return bool(query) and bool(_HEALTH_CHECK_PATTERN.match(query))


# ========== SQL 目标对象（表/视图/存储过程）提取 ==========
# 标识符字符：\w + 点号 + 反引号（支持 `db`.`t_material` 形式，反引号在 replace 阶段去除）
_IDENT = r'[\w.`]+'
# DML 目标对象：FROM/JOIN/INTO/UPDATE 后的表名
_DML_OBJECT_PATTERN = re.compile(
    rf'(?:\bFROM\b|\bJOIN\b|\bINTO\b|\bUPDATE\b)\s+({_IDENT})',
    re.IGNORECASE,
)
# DDL 目标对象：TABLE/VIEW 后的表名，跳过 IF [NOT] EXISTS / TEMPORARY / TEMP
_DDL_OBJECT_PATTERN = re.compile(
    rf'\b(?:TABLE|VIEW)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+|TEMPORARY\s+|TEMP\s+)?({_IDENT})',
    re.IGNORECASE,
)
_CALL_PATTERN = re.compile(rf'\bCALL\s+({_IDENT})', re.IGNORECASE)
# SQL 字符串字面量（单引号，支持 '' 转义）
_SQL_STRING_PATTERN = re.compile(r"'(?:[^']|'')*'")
# 非占位符的 % （即 % 后面不是 s 也不是 (name)s），需 escape 为 %% 避免 str.__mod__ 误解析
_NON_PLACEHOLDER_PERCENT = re.compile(r"%(?!s|\(\w+\)s)")


def extract_sql_object(sql: str) -> str:
    """从 SQL 语句提取目标表/视图/存储过程名，多个用逗号分隔。

    覆盖 DML（FROM/JOIN/INTO/UPDATE）、DDL（CREATE/ALTER/DROP TABLE/VIEW，跳过
    IF [NOT] EXISTS/TEMPORARY/TEMP）后的表名，以及 CALL 后的存储过程名。
    先剥离字符串字面量避免误匹配；去重保序，保留 schema 前缀（如 db.table）。
    """
    if not sql:
        return ''
    cleaned = _SQL_STRING_PATTERN.sub(' ', sql)
    m = _CALL_PATTERN.search(cleaned)
    if m:
        return m.group(1).replace('`', '')
    seen: set = set()
    result: List[str] = []
    for pattern in (_DML_OBJECT_PATTERN, _DDL_OBJECT_PATTERN):
        for name in pattern.findall(cleaned):
            name = name.replace('`', '')
            if name and name not in seen:
                seen.add(name)
                result.append(name)
    return ', '.join(result)


def _readable_value(v: Any) -> Any:
    """递归把 params 中的日期等对象转为可读字符串，其他原样。

    datetime/date/time → isoformat（T 替换为空格，保留时区信息）；
    list/tuple/dict 递归处理元素；其他类型原样返回。
    """
    if isinstance(v, datetime.datetime):
        return v.isoformat().replace('T', ' ')
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, datetime.time):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return type(v)(_readable_value(x) for x in v)
    if isinstance(v, dict):
        return {k: _readable_value(x) for k, x in v.items()}
    return v


def _sql_value_repr(v: Any) -> str:
    """参数值转 SQL 字面量表示，用于渲染可读 SQL。"""
    if v is None:
        return 'NULL'
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return "'" + v.isoformat().replace('T', ' ') + "'"
    return "'" + str(v).replace("'", "''") + "'"


def render_sql(sql: str, params: Any) -> str:
    """将参数整合进 SQL 模板，生成可读的完整 SQL。

    支持 %s、%(name)s、? 占位符；参数值按 SQL 字面量渲染（字符串加引号、None→NULL）。
    渲染失败（参数数量不匹配、含 % 字面量等）回退到原模板。
    """
    if not sql:
        return ''
    if not params:
        return sql
    try:
        if isinstance(params, dict) and '%(' in sql:
            safe = {k: _sql_value_repr(v) for k, v in params.items()}
            return _NON_PLACEHOLDER_PERCENT.sub('%%', sql) % safe
        if isinstance(params, (list, tuple)):
            if '%s' in sql:
                safe = tuple(_sql_value_repr(p) for p in params)
                return _NON_PLACEHOLDER_PERCENT.sub('%%', sql) % safe
            if '?' in sql:
                rendered = sql
                for p in params:
                    rendered = rendered.replace('?', _sql_value_repr(p), 1)
                return rendered
    except Exception:
        pass
    return sql


# ========== Prometheus 指标（独立 Registry，参考 binlog） ==========
_registry = CollectorRegistry()
db_query_total = Counter(
    'db_query_total', 'SQL 执行总次数', ['operation', 'connection'], registry=_registry
)
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds', 'SQL 耗时分布', ['operation', 'connection'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=_registry,
)
db_query_errors_total = Counter(
    'db_query_errors_total', 'SQL 错误次数', ['operation', 'connection', 'error_type'],
    registry=_registry,
)
db_slow_query_total = Counter(
    'db_slow_query_total', '慢查询次数', ['operation', 'connection'], registry=_registry
)
db_query_in_progress = Gauge(
    'db_query_in_progress', '执行中 SQL 数', ['connection'], registry=_registry
)


# ========== Collector 单例 ==========
class DBQueryCollector:
    """DB 查询收集器（单例，被 hook 引用）"""

    def __init__(self):
        self._history: deque = deque(maxlen=DB_QUERY_HISTORY_SIZE)
        # 累计计数器（从启动至今，不封顶），用于统计卡片
        self._total_count: int = 0
        self._slow_count: int = 0
        self._error_count: int = 0


    async def record(
        self,
        operation: str,
        connection: str,
        sql: str,
        params: Any,
        duration: float,
        success: bool,
        affected: int = 0,
        error: Optional[Exception] = None,
    ) -> None:
        """记录一条 SQL 执行（异步，不阻塞业务）。

        内部异常吞并不影响业务（记录逻辑自身容错）。
        """
        try:
            is_slow = duration >= DB_QUERY_SLOW_THRESHOLD
            self._total_count += 1
            if is_slow:
                self._slow_count += 1
            if not success:
                self._error_count += 1
            record = {
                'timestamp': time.time(),
                'operation': operation,
                'connection': connection,
                'object': extract_sql_object(sql),
                'sql': self._truncate(sql, 2000),
                'sql_rendered': self._truncate(render_sql(sql, params), 2000),
                'params': self._truncate(str(_readable_value(params)), 500),
                'duration': duration,
                'success': success,
                'affected': affected,
                'is_slow': is_slow,
                'stack': self._capture_stack() if is_slow else None,
            }

            if DB_QUERY_LOG_ALL:
                self._history.append(record)
            elif is_slow or not success:
                # 非全记录模式只留慢查询+错误
                self._history.append(record)


            # Prometheus
            db_query_total.labels(operation, connection).inc()
            db_query_duration_seconds.labels(operation, connection).observe(duration)
            if not success:
                db_query_errors_total.labels(
                    operation, connection, type(error).__name__
                ).inc()
            if is_slow:
                db_slow_query_total.labels(operation, connection).inc()

            # 慢查询不输出日志告警（避免淹没真正有价值的错误信息），
            # 仅通过 Prometheus 指标 + 内存队列 + /database/query/slow API 暴露
            if not success:
                logger.fail(
                    operation, f"@{connection}", f"{type(error).__name__}: {error}"
                )
        except Exception as e:
            # 记录逻辑自身异常吞并，绝不影响业务
            logger.warning(f"DB 查询记录逻辑异常（已吞并）: {e}")

    def get_recent(
        self,
        operation: Optional[str] = None,
        connection: Optional[str] = None,
        slow_only: bool = False,
        error_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """从内存队列过滤最近 SQL，按时间倒序返回"""
        results: List[Dict[str, Any]] = []
        for r in reversed(self._history):
            if operation and r['operation'] != operation:
                continue
            if connection and r['connection'] != connection:
                continue
            if slow_only and not r['is_slow']:
                continue
            if error_only and r.get('success', True):
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    def get_stats(self) -> Dict[str, Any]:
        """返回聚合统计。

        - total_count/slow_count/error_count：累计计数器（从启动至今，不封顶），用于统计卡片
        - stats：从内存队列 _history 重新聚合的操作分布（最近 N 条快照），用于操作分布表格
        - history_size：当前内存队列长度（<= maxlen）
        """
        db_order = {name: i for i, name in enumerate(MYAPS_DBSET_LIST)}
        fallback = len(db_order)
        stats_map: Dict[tuple, Dict[str, Any]] = {}
        for r in self._history:
            key = (r['operation'], r['connection'])
            s = stats_map.setdefault(
                key, {'count': 0, 'total_time': 0.0, 'max_time': 0.0, 'slow': 0, 'errors': 0}
            )
            s['count'] += 1
            s['total_time'] += r['duration']
            if r['duration'] > s['max_time']:
                s['max_time'] = r['duration']
            if r['is_slow']:
                s['slow'] += 1
            if not r.get('success', True):
                s['errors'] += 1
        raw = [
            {
                'operation': k[0],
                'connection': k[1],
                **v,
                'avg_time': v['total_time'] / v['count'] if v['count'] else 0.0,
            }
            for k, v in stats_map.items()
        ]
        raw.sort(key=lambda s: (db_order.get(s['connection'], fallback), -s.get('count', 0)))
        return {
            'stats': raw,
            'total_count': self._total_count,
            'slow_count': self._slow_count,
            'error_count': self._error_count,
            'history_size': len(self._history),
            'history_max': DB_QUERY_HISTORY_SIZE,
            'slow_threshold': DB_QUERY_SLOW_THRESHOLD,
            'connections': list(_ALL_CONNECTION_NAMES),
        }

    @staticmethod
    def _truncate(s: str, max_len: int) -> str:
        return s if len(s) <= max_len else s[:max_len] + '...[truncated]'

    @staticmethod
    def _capture_stack() -> str:
        """捕获调用栈前 5 帧（跳过 hook 自身帧）"""
        frames = traceback.extract_stack(limit=8)[:-3]  # 去掉 hook/record/_capture_stack
        return ''.join(traceback.format_list(frames[-5:]))


# 模块级单例
collector = DBQueryCollector()


# ========== Hook install/uninstall ==========
_originals: Dict[type, Callable] = {}


def _resolve_original(cls: type) -> Callable:
    """按 MRO 回退查找已 patch 的原始 execute_query。

    事务中 self 为 TransactionWrapper（继承 MySQLClient），type(self) 不在
    _originals 字典中，需沿 __mro__ 回退到已 patch 的基类。
    """
    for base in cls.__mro__:
        original = _originals.get(base)
        if original is not None:
            return original
    raise KeyError(cls)


async def _patched_execute_query(self, query: str, values: Optional[list] = None):
    """execute_query 的 patched 版本，记录 SQL 执行信息"""
    original = _resolve_original(type(self))
    if not DB_QUERY_MONITOR_ENABLED:
        return await original(self, query, values)
    if _is_health_check(query):
        return await original(self, query, values)
    if random.random() > DB_QUERY_SAMPLE_RATE:
        return await original(self, query, values)

    start = time.perf_counter()
    operation = classify_sql(query)
    connection = getattr(self, 'connection_name', 'unknown')

    db_query_in_progress.labels(connection).inc()
    try:
        result = await original(self, query, values)
        duration = time.perf_counter() - start
        affected = _extract_affected(result)
        asyncio.create_task(
            collector.record(
                operation, connection, query, values, duration, True, affected=affected
            )
        )
        return result
    except Exception as e:
        duration = time.perf_counter() - start
        asyncio.create_task(
            collector.record(
                operation, connection, query, values, duration, False, error=e
            )
        )
        raise
    finally:
        db_query_in_progress.labels(connection).dec()


def _extract_affected(result: Any) -> int:
    """从 execute_query 返回值提取影响行数。

    Tortoise 返回 tuple[int, Sequence[dict]]，影响行数在 result[0]。
    """
    try:
        if isinstance(result, (list, tuple)) and len(result) >= 1:
            return int(result[0]) if result[0] is not None else 0
    except Exception:
        pass
    return 0


def install_hook() -> None:
    """安装 hook（幂等）。

    patch 3 个具体子类（MySQLClient/AsyncpgDBClient/SqliteClient）。
    重复调用不覆盖原始引用。
    """
    if _originals:
        return
    try:
        from tortoise.backends.mysql.client import MySQLClient
        from tortoise.backends.asyncpg.client import AsyncpgDBClient
        from tortoise.backends.sqlite.client import SqliteClient
    except ImportError as e:
        raise ImportError(
            f"无法导入 Tortoise 后端子类，DB 查询监测 hook 安装失败: {e}"
        ) from e

    for cls in (MySQLClient, AsyncpgDBClient, SqliteClient):
        _originals[cls] = cls.execute_query
        cls.execute_query = _patched_execute_query
    logger.info("DB 查询监测 hook 已安装（patch 3 个后端子类）")


def uninstall_hook() -> None:
    """卸载 hook（幂等）。

    遍历恢复各子类 execute_query，清空 _originals。
    """
    if not _originals:
        return
    for cls, original in _originals.items():
        cls.execute_query = original
    _originals.clear()
    logger.info("DB 查询监测 hook 已卸载")