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
)

logger = log_config.get_logger(__name__)

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
        # (operation, connection) -> {count, total_time, max_time, slow, errors}
        self._stats: Dict[tuple, Dict[str, Any]] = {}

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
            record = {
                'timestamp': time.time(),
                'operation': operation,
                'connection': connection,
                'sql': self._truncate(sql, 2000),
                'params': self._truncate(str(params), 500),
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

            # 聚合统计
            key = (operation, connection)
            s = self._stats.setdefault(
                key, {'count': 0, 'total_time': 0.0, 'max_time': 0.0, 'slow': 0, 'errors': 0}
            )
            s['count'] += 1
            s['total_time'] += duration
            if duration > s['max_time']:
                s['max_time'] = duration
            if is_slow:
                s['slow'] += 1
            if not success:
                s['errors'] += 1

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
        """返回聚合统计"""
        return {
            'stats': [
                {
                    'operation': k[0],
                    'connection': k[1],
                    **v,
                    'avg_time': v['total_time'] / v['count'] if v['count'] else 0.0,
                }
                for k, v in self._stats.items()
            ],
            'history_size': len(self._history),
            'slow_threshold': DB_QUERY_SLOW_THRESHOLD,
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