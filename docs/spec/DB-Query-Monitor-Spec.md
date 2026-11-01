# 数据库交互监测方案 Spec

> 状态：待审核  
> 日期：2026-11-01  
> 作者：CodeArts  
> 关联：`apps/common/monitor/` 监控模块

## 1. 背景与目标

项目通过 Tortoise ORM（aiomysql + asyncpg）与 MySQL/PostgreSQL 交互，全项目约 162 处数据库交互点（裸 ORM 调用 ~81 处 + `execute_query` ~81 处），分散在 `db_manager.py`、`staging_routers.py`、`storage.py`、`components/` 等多处。

**目标**：记录每次数据库读写的 SQL 语句、耗时、连接、调用栈，识别低效数据库交互逻辑（慢查询、N+1、重复查询、异常 SQL）。

**非目标**：不做 SQL 审计合规、不做数据库性能调优建议自动生成、不做前端展示页（本次仅后端 + API，前端页后续可选）。

## 2. 方案概览

**Hook 层**：monkey-patch `tortoise.connections.Connection.execute_query`（async 方法）。Tortoise ORM 的所有 CRUD（filter/all/get/save/create/bulk_create）和原生 SQL 最终都走此方法，**单点覆盖全部 ~162 处交互点**。

**记录策略**（用户已确认）：
- 慢查询阈值：**1.0 秒**
- 记录范围：**全记录**（每条 SQL 入内存队列 deque maxlen=2000 + Prometheus 计数），慢查询额外告警日志
- SQL 脱敏：**完整记录含参数**（便于复现问题，用户已接受敏感数据入监控日志）

**复用现有基础设施**：
- `HTTPCollector` / `http_metrics_collector` 单例模式（`apps/common/monitor/middleware.py`）→ DB 监测类比实现
- `prometheus-client`（已在 `requirements.txt`）→ Prometheus 指标
- `globalobjects/logger`（`logger.warning_msg` / `logger.fail`）→ 慢查询告警与错误日志
- Histogram 桶配置（复用 `binlog/prometheus_metrics.py` 的 `[0.001...10.0]`）

## 3. 目录与文件变更清单

### 3.1 新增文件（仅 1 个）

| 文件 | 职责 |
|---|---|
| `apps/common/monitor/db_query_hook.py` | DB 查询监测核心模块：collector 单例 + Prometheus 指标 + monkey-patch install/uninstall + SQL 分类 + 内存队列 |

**精简理由**：collector 单例需被 hook 引用，hook 需引用 metrics，三者强耦合，合并单文件避免循环导入与过度拆分。SQL 分类是几行正则，不值得独立文件。

### 3.2 修改现有文件（7 个）

| 文件 | 改动 | 说明 |
|---|---|---|
| `apps/common/monitor/collectors/db_collector.py` | `DatabaseCollector` 类新增 3 个方法 | 委托给 `db_query_hook` 模块单例，与现有 `get_connection_status`/`get_pool_status` 并列 |
| `apps/common/monitor/routers.py` | 新增 3 个 API 端点 | 复用现有 `router = APIRouter(prefix="/monitor/api")`，放在 `/database/pool-leak-detection`（L505）附近 |
| `core/settings.py` | 新增 5 个配置项 | 见 §5 |
| `core/lifespan.py` | startup 调 `install_hook()`，shutdown 调 `uninstall_hook()` | startup 在 L670（db_check_task 启动）之前；shutdown 在 L1091 之前 |
| `.env.example` | 新增 5 行配置示例 | 注释说明 |
| `static/monitor/index.html` | MySQL 卡片新增 SQL 监控统计区 | 在现有 `db-detail-table`（L206-225）下方追加统计指标区 + 慢查询列表区，见 §14 |
| `static/monitor/js/monitor.js` | `updateDatabaseDetailDisplay` 后追加 SQL 监控渲染 | 在 L2162 `fetchDatabaseDetail` 末尾追加 `fetchDbQueryStats()` 调用，见 §14 |

### 3.3 新增依赖

**无**。全部复用现有：`prometheus-client`、`globalobjects/logger`、标准库 `time`/`traceback`/`re`/`collections.deque`/`asyncio`/`random`。

## 4. 模块详细设计

### 4.1 `apps/common/monitor/db_query_hook.py`（新增）

#### 4.1.1 模块结构

```python
"""
数据库查询监测

通过 monkey-patch Connection.execute_query 拦截所有 SQL 执行，
记录语句/耗时/连接/调用栈，慢查询告警 + Prometheus 指标 + 内存队列。
"""
import time
import re
import random
import asyncio
import traceback
from collections import deque
from typing import Optional, Dict, Any, List
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

def classify_sql(sql: str) -> str:
    """识别 SQL 操作类型"""
    if not sql:
        return 'other'
    m = _SQL_PATTERN.match(sql)
    return m.group(1).lower() if m else 'other'

# ========== Prometheus 指标（独立 Registry，参考 binlog） ==========
_registry = CollectorRegistry()
db_query_total = Counter('db_query_total', 'SQL 执行总次数', ['operation', 'connection'], registry=_registry)
db_query_duration_seconds = Histogram('db_query_duration_seconds', 'SQL 耗时分布', ['operation', 'connection'], buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0], registry=_registry)
db_query_errors_total = Counter('db_query_errors_total', 'SQL 错误次数', ['operation', 'connection', 'error_type'], registry=_registry)
db_slow_query_total = Counter('db_slow_query_total', '慢查询次数', ['operation', 'connection'], registry=_registry)
db_query_in_progress = Gauge('db_query_in_progress', '执行中 SQL 数', ['connection'], registry=_registry)

# ========== Collector 单例 ==========
class DBQueryCollector:
    """DB 查询收集器（单例，被 hook 引用）"""
    def __init__(self):
        self._history: deque = deque(maxlen=DB_QUERY_HISTORY_SIZE)
        self._stats: Dict[tuple, Dict] = {}  # (operation, connection) -> {count, total_time, max_time, slow, errors}

    async def record(self, operation, connection, sql, params, duration, success, affected=0, error=None):
        """记录一条 SQL 执行（异步，不阻塞业务）"""
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
        elif is_slow or not success:  # 非全记录模式只留慢查询+错误
            self._history.append(record)

        # 聚合统计
        key = (operation, connection)
        s = self._stats.setdefault(key, {'count': 0, 'total_time': 0.0, 'max_time': 0.0, 'slow': 0, 'errors': 0})
        s['count'] += 1
        s['total_time'] += duration
        s['max_time'] = max(s['max_time'], duration)
        if is_slow: s['slow'] += 1
        if not success: s['errors'] += 1

        # Prometheus
        db_query_total.labels(operation, connection).inc()
        db_query_duration_seconds.labels(operation, connection).observe(duration)
        if not success:
            db_query_errors_total.labels(operation, connection, type(error).__name__).inc()
        if is_slow:
            db_slow_query_total.labels(operation, connection).inc()

        # 慢查询告警日志
        if is_slow:
            logger.warning_msg(
                f"慢SQL {operation}@{connection}",
                f"耗时 {duration:.3f}s, SQL: {record['sql'][:200]}"
            )
        if not success:
            logger.fail(operation, f"@{connection}", f"{type(error).__name__}: {error}")

    def get_recent(self, operation=None, connection=None, slow_only=False, limit=100) -> List[Dict]:
        """从内存队列过滤最近 SQL"""
        results = []
        for r in reversed(self._history):
            if operation and r['operation'] != operation: continue
            if connection and r['connection'] != connection: continue
            if slow_only and not r['is_slow']: continue
            results.append(r)
            if len(results) >= limit: break
        return results

    def get_stats(self) -> Dict[str, Any]:
        """返回聚合统计"""
        return {
            'stats': [
                {'operation': k[0], 'connection': k[1], **v,
                 'avg_time': v['total_time'] / v['count'] if v['count'] else 0}
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
        """捕获调用栈前 5 帧（跳过 hook 自身）"""
        frames = traceback.extract_stack(limit=8)[:-3]  # 去掉 hook/record/_capture_stack
        return ''.join(traceback.format_list(frames[-5:]))

# 模块级单例
collector = DBQueryCollector()

# ========== Hook install/uninstall ==========
_original_execute_query = None

async def _patched_execute_query(self, query, *args, **kwargs):
    if not DB_QUERY_MONITOR_ENABLED:
        return await _original_execute_query(self, query, *args, **kwargs)
    if random.random() > DB_QUERY_SAMPLE_RATE:
        return await _original_execute_query(self, query, *args, **kwargs)

    start = time.perf_counter()
    operation = classify_sql(query)
    connection = getattr(self, 'connection_name', 'unknown')

    db_query_in_progress.labels(connection).inc()
    try:
        result = await _original_execute_query(self, query, *args, **kwargs)
        duration = time.perf_counter() - start
        affected = _extract_affected(result)
        asyncio.create_task(collector.record(
            operation, connection, query, args, duration, True, affected=affected
        ))
        return result
    except Exception as e:
        duration = time.perf_counter() - start
        asyncio.create_task(collector.record(
            operation, connection, query, args, duration, False, error=e
        ))
        raise
    finally:
        db_query_in_progress.labels(connection).dec()

def _extract_affected(result) -> int:
    """从 execute_query 返回值提取影响行数（Tortoise 返回 (rows, affected_count) 或类似）"""
    try:
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            return int(result[1]) if result[1] is not None else 0
    except Exception:
        pass
    return 0

def install_hook():
    """安装 hook（幂等）"""
    global _original_execute_query
    if _original_execute_query is not None:
        return
    from tortoise.connections import Connection
    _original_execute_query = Connection.execute_query
    Connection.execute_query = _patched_execute_query
    logger.info("DB 查询监测 hook 已安装")

def uninstall_hook():
    """卸载 hook（幂等）"""
    global _original_execute_query
    if _original_execute_query is not None:
        from tortoise.connections import Connection
        Connection.execute_query = _original_execute_query
        _original_execute_query = None
        logger.info("DB 查询监测 hook 已卸载")
```

#### 4.1.2 关键设计点

| 点 | 说明 |
|---|---|
| `execute_query` 是 async | patch 必须用 `async def`，内部 `await _original_execute_query(...)` |
| `asyncio.create_task` 非阻塞 | 记录逻辑异步化，不增加业务 SQL 耗时 |
| `time.perf_counter()` | 单调递增、高精度，适合耗时测量（非 `time.time()`） |
| 调用栈仅慢查询捕获 | `duration >= threshold` 时才抓栈，正常 SQL 无栈捕获开销 |
| SQL 截断 | SQL 截到 2000 字符，参数截到 500 字符，避免超长撑爆队列 |
| 采样率 | `random.random() > sample_rate` 时跳过记录，高频场景可降到 0.1 |
| 幂等 install/uninstall | 重复 install 不覆盖，uninstall 恢复原始引用 |
| Tortoise Connection 路径 | `tortoise.connections.Connection`，实现时需核实（可能是 `tortoise.connection.Connection` 单数） |

### 4.2 `apps/common/monitor/collectors/db_collector.py`（修改）

在 `DatabaseCollector` 类中新增 3 个方法，委托给 `db_query_hook.collector` 单例（类比 `HTTPCollector` 委托给 `http_metrics_collector`）：

```python
# 在 DatabaseCollector 类中新增

async def get_query_metrics(self) -> Dict[str, Any]:
    """获取 SQL 查询监测聚合统计"""
    from ..db_query_hook import collector
    return collector.get_stats()

async def get_recent_queries(self, operation=None, connection=None,
                             slow_only=False, limit=100) -> List[Dict[str, Any]]:
    """获取最近 SQL 列表"""
    from ..db_query_hook import collector
    return collector.get_recent(operation, connection, slow_only, limit)

async def get_slow_queries(self, limit=20) -> List[Dict[str, Any]]:
    """获取慢查询列表"""
    from ..db_query_hook import collector
    slow = collector.get_recent(slow_only=True, limit=limit)
    await remind_manager.trigger_remind(RemindType.DB_SLOW_QUERY, slow)  # 若 RemindType 有此类型
    return slow
```

**注意**：`RemindType.DB_SLOW_QUERY` 需确认是否存在，若无则跳过 `trigger_remind` 或新增枚举值（实现时核实 `globalobjects` 的 `RemindType` 定义）。

### 4.3 `apps/common/monitor/routers.py`（修改）

在 `/database/pool-leak-detection`（L505）附近新增 3 个端点：

```python
@router.get("/database/query/stats")
async def get_db_query_stats():
    """获取 SQL 查询监测聚合统计"""
    collector = DatabaseCollector()
    return await collector.get_query_metrics()

@router.get("/database/query/recent")
async def get_db_query_recent(
    operation: Optional[str] = None,
    connection: Optional[str] = None,
    slow: bool = False,
    limit: int = 100,
):
    """获取最近 SQL 列表"""
    collector = DatabaseCollector()
    return await collector.get_recent_queries(operation, connection, slow, limit)

@router.get("/database/query/slow")
async def get_db_query_slow(limit: int = 20):
    """获取慢查询列表"""
    collector = DatabaseCollector()
    return await collector.get_slow_queries(limit)
```

**端点路径**：`/monitor/api/database/query/{stats|recent|slow}`，与现有 `/monitor/api/database/*` 对齐。

### 4.4 `core/lifespan.py`（修改）

**Startup**（在 L670 db_check_task 启动之前插入）：

```python
# 安装 DB 查询监测 hook
if DB_QUERY_MONITOR_ENABLED:
    from apps.common.monitor.db_query_hook import install_hook
    install_hook()
    log_config.info("DB 查询监测已启用")
```

**Shutdown**（在 L1091 之前插入）：

```python
# 卸载 DB 查询监测 hook
from apps.common.monitor.db_query_hook import uninstall_hook
uninstall_hook()
```

**跨平台影响**（按 memory `feedback-cross-platform-impact-check`）：lifespan 改动对 Linux Docker/Gunicorn 部署无特殊影响，hook 是纯 Python monkey-patch，不涉及文件锁或平台特定 API。

### 4.5 `core/settings.py`（修改）

新增 5 个配置项（放在时区配置附近或 DB 配置区块）：

```python
# DB 查询监测
DB_QUERY_MONITOR_ENABLED = os.getenv("DB_QUERY_MONITOR_ENABLED", "true").lower() == "true"
DB_QUERY_SLOW_THRESHOLD = float(os.getenv("DB_QUERY_SLOW_THRESHOLD", "1.0"))
DB_QUERY_LOG_ALL = os.getenv("DB_QUERY_LOG_ALL", "true").lower() == "true"
DB_QUERY_HISTORY_SIZE = int(os.getenv("DB_QUERY_HISTORY_SIZE", "2000"))
DB_QUERY_SAMPLE_RATE = float(os.getenv("DB_QUERY_SAMPLE_RATE", "1.0"))
```

## 5. 配置项（.env）

| 环境变量 | 默认值 | 范围 | 说明 |
|---|---|---|---|
| `DB_QUERY_MONITOR_ENABLED` | `true` | true/false | 监测总开关 |
| `DB_QUERY_SLOW_THRESHOLD` | `1.0` | >0 | 慢查询阈值（秒） |
| `DB_QUERY_LOG_ALL` | `true` | true/false | true=全记录入队；false=仅慢查询+错误入队 |
| `DB_QUERY_HISTORY_SIZE` | `2000` | 100-10000 | 内存队列容量 |
| `DB_QUERY_SAMPLE_RATE` | `1.0` | 0.0-1.0 | 采样率（高频场景可降到 0.1） |

**.env.example 新增**：

```bash
# DB 查询监测
DB_QUERY_MONITOR_ENABLED=true       # 监测开关
DB_QUERY_SLOW_THRESHOLD=1.0         # 慢查询阈值（秒）
DB_QUERY_LOG_ALL=true               # true=全记录，false=仅慢查询+错误
DB_QUERY_HISTORY_SIZE=2000          # 内存队列容量
DB_QUERY_SAMPLE_RATE=1.0            # 采样率 0.0-1.0
```

**纯字符串配置**（按 memory `feedback-env-config-plain-string-not-json`）：均为简单标量，无 JSON。

## 6. API 端点

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/monitor/api/database/query/stats` | 无 | 聚合统计（按 operation/connection 分组的次数/平均/最大耗时/慢查询数/错误数） |
| GET | `/monitor/api/database/query/recent` | `operation`, `connection`, `slow`, `limit` | 最近 SQL 列表（可过滤） |
| GET | `/monitor/api/database/query/slow` | `limit` | 慢查询列表 |

**响应示例**（`/recent`）：

```json
[
  {
    "timestamp": 1730419200.123,
    "operation": "select",
    "connection": "mingluo",
    "sql": "SELECT * FROM t_supply WHERE SupplyNo = 'MO001'",
    "params": "()",
    "duration": 0.023,
    "success": true,
    "affected": 1,
    "is_slow": false,
    "stack": null
  }
]
```

**慢查询响应**（含调用栈）：

```json
{
  "timestamp": 1730419200.456,
  "operation": "call",
  "connection": "mingluo",
  "sql": "CALL `SupplyConvertMOByE2A`(...)",
  "duration": 1.234,
  "is_slow": true,
  "stack": "  File \"apps/data_opt/components/__init__.py\", line 380, in refresh\n    await db_manager.call_stored_procedure(...)\n  ..."
}
```

## 7. Prometheus 指标

暴露于现有 `/metrics` 端点（`apps/data_opt/routers.py` L93），独立 `CollectorRegistry` 避免污染全局。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `db_query_total` | Counter | `operation, connection` | SQL 执行总次数 |
| `db_query_duration_seconds` | Histogram | `operation, connection` | SQL 耗时分布 |
| `db_query_errors_total` | Counter | `operation, connection, error_type` | 错误次数 |
| `db_slow_query_total` | Counter | `operation, connection` | 慢查询次数 |
| `db_query_in_progress` | Gauge | `connection` | 当前执行中 SQL 数 |

**命名约定**：`db_` 前缀（类比现有 `binlog_` 前缀），与 binlog 指标隔离。

## 8. 性能考量

| 操作 | 开销 | 频率 |
|---|---|---|
| `time.perf_counter()` × 2 | ~0.1μs | 每条 SQL |
| `classify_sql` 正则 | ~1μs | 每条 SQL |
| `deque.append` | ~0.1μs | 每条 SQL（全记录模式） |
| Prometheus 指标更新 | ~0.5μs | 每条 SQL |
| `asyncio.create_task` | ~5μs | 每条 SQL |
| 调用栈捕获 | ~10μs | 仅慢查询 |
| 慢查询日志 | ~50μs | 仅慢查询 |

**总开销**：正常 SQL ~7μs/条，慢查询 ~70μs/条。对毫秒级 SQL 查询的开销占比 <0.1%。

### 8.1 内存压力详评

**单条记录内存占用**（`DBQueryCollector.record` 中的 dict）：

| 字段 | 类型 | 占用 | 说明 |
|---|---|---|---|
| `timestamp` | float | 8B | |
| `operation` | str | ~10B | select/insert/update/delete/call/other |
| `connection` | str | ~20B | 账套名 |
| `sql` | str | 200-500B（平均）/ 2000B（截断上限） | 截断到 2000 字符 |
| `params` | str | 100-500B | `str(args)` 截断到 500 字符 |
| `duration` | float | 8B | |
| `success` | bool | 1B | |
| `affected` | int | 8B | |
| `is_slow` | bool | 1B | |
| `stack` | str/None | 0B（正常）/ ~500B（慢查询） | 仅慢查询捕获前 5 帧 |
| dict 对象开销 | - | ~200B | Python dict 元数据 |

- **正常 SQL 记录**：~700-900B
- **慢查询记录**（含 stack）：~1200-1500B
- **平均估算**：~800B/条

**内存上限**：

| 配置 | 计算 | 上限 |
|---|---|---|
| 默认 `HISTORY_SIZE=2000` | 2000 × 800B | **~1.6MB** |
| `HISTORY_SIZE=10000` | 10000 × 800B | ~8MB |
| 极端全慢查询 `HISTORY_SIZE=2000` | 2000 × 1500B | ~3MB |

**`_stats` 聚合字典**：键为 `(operation, connection)` 组合，约 5 operations × 3 connections = 15 条 × ~100B ≈ 1.5KB，可忽略。

**Prometheus 指标内存**：
- Counter/Histogram 按标签组合数线性增长
- 5 operations × 3 connections = 15 组合
- Histogram 12 桶 × 15 = 180 桶
- 总计 < 10KB，可忽略

**结论**：默认配置下总内存 **< 2MB**，相对 Python 进程（数百 MB）占比 <1%，**内存压力可忽略**。`deque(maxlen=N)` 自动丢弃最旧记录，无 OOM 风险。若部署在内存敏感环境，`HISTORY_SIZE=500` 即可降到 ~0.4MB。

**降级**：`DB_QUERY_SAMPLE_RATE=0.1` 时只采 10%，开销降 10 倍。`DB_QUERY_MONITOR_ENABLED=false` 完全关闭（hook 直接调原始方法，仅多一次 bool 判断）。

**高频小查询噪音**：`SELECT 1`（健康检查）、`SET` 等可在 `classify_sql` 加白名单跳过（实现时评估是否需要）。

## 9. 风险与回滚

| 风险 | 等级 | 缓解 |
|---|---|---|
| monkey-patch Tortoise 内部方法，升级 Tortoise 可能破坏 | 中 | `_original_execute_query` 保存原始引用，`uninstall_hook()` 可恢复；升级 Tortoise 时需回归测试 |
| `asyncio.create_task` 在事件循环关闭时报警告 | 低 | shutdown 时先 `uninstall_hook()` 再关循环 |
| 完整记录 SQL 含参数，敏感数据入监控日志 | 中 | 用户已确认接受；后续可加 `DB_QUERY_MASK_PARAMS` 开关 |
| 高频小查询产生噪音 | 低 | 采样率 + 白名单跳过 `SELECT 1`/`SET` |
| Tortoise `Connection` 类路径变更 | 低 | `install_hook` 时 `from tortoise.connections import Connection` 失败会抛明确异常，启动即可发现 |

**回滚**：`.env` 设 `DB_QUERY_MONITOR_ENABLED=false` 重启即可，无需改代码。紧急回滚也可 `uninstall_hook()` 运行时卸载。

## 10. 实施步骤

1. 新建 `apps/common/monitor/db_query_hook.py`（核心模块）
2. 修改 `core/settings.py` 新增 5 个配置项
3. 修改 `core/lifespan.py` startup 安装 hook + shutdown 卸载
4. 修改 `apps/common/monitor/collectors/db_collector.py` 新增 3 个委托方法
5. 修改 `apps/common/monitor/routers.py` 新增 3 个端点
6. 修改 `.env.example` 新增配置示例
7. 修改 `static/monitor/index.html` MySQL 卡片追加 SQL 监控统计区 + 慢查询列表区
8. 修改 `static/monitor/js/monitor.js` 新增 `fetchDbQueryStats`/`fetchDbSlowQueries`/`updateSqlMonitorSummary`/`updateSqlSlowList` 函数
9. 补充 i18n 资源文件（`static/lib/i18n/`）新增 key 翻译
10. 重启服务验证

## 11. 验证方案

| 项 | 方法 |
|---|---|
| hook 生效 | 触发任意 API（如 `GET /monitor/api/health`），调 `GET /monitor/api/database/query/recent` 应有记录 |
| 慢查询识别 | 临时设 `DB_QUERY_SLOW_THRESHOLD=0.001`，触发查询，`/slow` 端点应返回结果且日志有慢 SQL 告警 |
| 错误记录 | 构造一个会失败的 SQL（如查不存在表），`/recent?limit=1` 应见 `success=false` |
| Prometheus 指标 | `GET /metrics` 应包含 `db_query_total`/`db_query_duration_seconds` 等 |
| 开关关闭 | `DB_QUERY_MONITOR_ENABLED=false` 重启，`/recent` 应返回空，业务正常 |
| 卸载 | shutdown 日志应见 "DB 查询监测 hook 已卸载" |
| 性能 | 对比开关前后 API 响应耗时，应无显著差异（<0.1%） |
| Tortoise Connection 路径 | 启动日志应见 "DB 查询监测 hook 已安装"，若路径错误启动即报错 |

## 12. 前端集成

在 `static/monitor/index.html` 的"数据库"页签 MySQL 卡片中增加 SQL 监控统计信息，复用现有 `monitor.js` 数据加载框架。

### 12.1 `static/monitor/index.html`（修改）

在 MySQL 卡片（L198-228 `<section class="card full-width">`）的 `db-detail-table`（L206-225）下方追加两个区：

```html
<!-- 在 </div> <!-- db-detail-table-container --> 之后、</div> <!-- card-body --> 之前插入 -->

<!-- SQL 监控统计指标区 -->
<div class="sql-monitor-summary" id="sql-monitor-summary" style="margin-top:16px;">
    <h3 data-i18n="monitor.card.sql_monitor">SQL 监控</h3>
    <div class="sql-metrics-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;">
        <div class="metric-item">
            <div class="metric-label" data-i18n="monitor.metric.total_queries">总查询数</div>
            <div class="metric-value" id="sql-total-count">0</div>
        </div>
        <div class="metric-item">
            <div class="metric-label" data-i18n="monitor.metric.slow_queries">慢查询数</div>
            <div class="metric-value" id="sql-slow-count" style="color:#ef4444;">0</div>
        </div>
        <div class="metric-item">
            <div class="metric-label" data-i18n="monitor.metric.query_errors">错误数</div>
            <div class="metric-value" id="sql-error-count" style="color:#ef4444;">0</div>
        </div>
        <div class="metric-item">
            <div class="metric-label" data-i18n="monitor.metric.slow_threshold">慢查询阈值</div>
            <div class="metric-value" id="sql-slow-threshold">1.0s</div>
        </div>
    </div>
    <!-- 按 operation 分组的小表格 -->
    <table class="db-detail-table" id="sql-operation-stats" style="margin-top:12px;">
        <thead>
            <tr>
                <th data-i18n="monitor.col.operation">操作</th>
                <th data-i18n="monitor.col.connection">连接</th>
                <th data-i18n="monitor.col.count">次数</th>
                <th data-i18n="monitor.col.avg_duration">平均耗时</th>
                <th data-i18n="monitor.col.max_duration">最大耗时</th>
                <th data-i18n="monitor.col.slow_count">慢查询</th>
                <th data-i18n="monitor.col.error_count">错误</th>
            </tr>
        </thead>
        <tbody id="sql-operation-tbody"></tbody>
    </table>
</div>

<!-- 慢查询 TOP 列表区 -->
<div class="sql-slow-list" id="sql-slow-list" style="margin-top:16px;">
    <h3 data-i18n="monitor.card.slow_queries">慢查询列表</h3>
    <table class="db-detail-table" id="sql-slow-table">
        <thead>
            <tr>
                <th data-i18n="monitor.col.timestamp">时间</th>
                <th data-i18n="monitor.col.connection">连接</th>
                <th data-i18n="monitor.col.operation">操作</th>
                <th data-i18n="monitor.col.duration">耗时</th>
                <th data-i18n="monitor.col.sql">SQL</th>
            </tr>
        </thead>
        <tbody id="sql-slow-tbody"></tbody>
    </table>
</div>
```

**i18n key 命名**：全部用点分英文路径（如 `monitor.metric.total_queries`），不嵌入中文，与现有 key 约定一致。需在 i18n 资源文件补充对应翻译（中/英/德）。

### 12.2 `static/monitor/js/monitor.js`（修改）

在 `fetchDatabaseDetail()`（L2156 附近）末尾追加 SQL 监控数据加载，新增两个渲染函数：

```javascript
// 在 fetchDatabaseDetail() 的 try 块末尾追加
await fetchDbQueryStats();
await fetchDbSlowQueries();

// 新增函数
async function fetchDbQueryStats() {
    try {
        const response = await fetch(`${API_BASE}/database/query/stats`);
        const data = await response.json();
        updateSqlMonitorSummary(data);
    } catch (error) {
        console.error('获取 SQL 监控统计失败:', error);
    }
}

async function fetchDbSlowQueries() {
    try {
        const response = await fetch(`${API_BASE}/database/query/slow?limit=10`);
        const data = await response.json();
        updateSqlSlowList(data);
    } catch (error) {
        console.error('获取慢查询列表失败:', error);
    }
}

function updateSqlMonitorSummary(data) {
    const stats = data.stats || [];
    let totalCount = 0, slowCount = 0, errorCount = 0;
    stats.forEach(s => {
        totalCount += s.count;
        slowCount += s.slow;
        errorCount += s.errors;
    });
    document.getElementById('sql-total-count').textContent = totalCount;
    document.getElementById('sql-slow-count').textContent = slowCount;
    document.getElementById('sql-error-count').textContent = errorCount;
    document.getElementById('sql-slow-threshold').textContent = (data.slow_threshold || 1.0) + 's';

    // 按 operation 分组的表格
    const tbody = document.getElementById('sql-operation-tbody');
    tbody.innerHTML = stats.map(s => `<tr>
        <td>${s.operation}</td>
        <td>${s.connection}</td>
        <td>${s.count}</td>
        <td>${(s.avg_time * 1000).toFixed(1)}ms</td>
        <td>${(s.max_time * 1000).toFixed(1)}ms</td>
        <td style="color:${s.slow > 0 ? '#ef4444' : ''}">${s.slow}</td>
        <td style="color:${s.errors > 0 ? '#ef4444' : ''}">${s.errors}</td>
    </tr>`).join('') || `<tr><td colspan="7" class="empty-state">${i18n.t('monitor.status.no_data')}</td></tr>`;
}

function updateSqlSlowList(data) {
    const tbody = document.getElementById('sql-slow-tbody');
    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${i18n.t('monitor.status.no_slow_queries')}</td></tr>`;
        return;
    }
    tbody.innerHTML = data.map(r => `<tr>
        <td>${new Date(r.timestamp * 1000).toLocaleString()}</td>
        <td>${r.connection}</td>
        <td>${r.operation}</td>
        <td style="color:#ef4444;font-weight:bold;">${(r.duration * 1000).toFixed(0)}ms</td>
        <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(r.sql)}">${escapeHtml(r.sql.substring(0, 100))}</td>
    </tr>`).join('');
}
```

**集成点**：
- `fetchDatabaseDetail()` 位于 `monitor.js` L2143 附近，已通过 `fetch(${API_BASE}/database)` 加载连接池数据
- 在其 try 块末尾追加两个 `await` 调用，与现有数据库详情同步加载
- 复用现有 `API_BASE`、`i18n`、`escapeHtml`（若不存在则新增简单实现）

### 12.3 刷新频率

SQL 监控统计随数据库页签刷新（现有 `fetchDatabaseDetail` 的调用频率，通常随页面轮询或手动刷新）。无需独立轮询，避免额外请求。慢查询列表 `limit=10` 控制单次返回量。

### 12.4 跨平台影响（按 memory feedback-cross-platform-impact-check）

前端改动为纯 HTML/JS，无 lifespan/文件锁/启动分支变更，对 Linux 部署环境无影响。i18n key 需在 `static/lib/i18n/` 资源文件补充，缺失时回退显示默认中文文案（HTML 内联文本）。

## 13. 后续可选（不在本次范围）

- SQL 指纹聚合（用 sqlparse 归并相同模板的 SQL，统计 N+1/重复查询）——需新增 `sqlparse` 依赖
- `DB_QUERY_MASK_PARAMS` 开关（用 `[REDACTED]` 替换参数值）
- 白名单配置（`DB_QUERY_SKIP_PATTERNS=SELECT 1,SET` 跳过指定 SQL）
- 持久化到 SQLite（类比 `APIRequest` 模型，跨重启保留历史）
- 独立 SQL 监控详情页（类比 `history-logs.html`，支持时间范围查询/过滤/分页/导出）

## 14. 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| Hook 层次 | 驱动层 `execute_query` 单点 | 封装层只覆盖 16 处，驱动层覆盖全部 162 处 |
| 新增文件数 | 1 个（`db_query_hook.py`） | collector/metrics/hook 强耦合，合并避免循环导入；collector 方法复用 `db_collector.py` |
| API 端点位置 | `routers.py` | 复用现有 router，与 `/database/*` 端点对齐 |
| Prometheus Registry | 独立 `CollectorRegistry` | 参考 binlog 模式，避免全局污染 |
| 记录方式 | `asyncio.create_task` 异步 | 不阻塞业务，记录逻辑与 SQL 执行解耦 |
| 耗时测量 | `time.perf_counter()` | 单调递增、高精度，优于 `time.time()` |
| 依赖 | 0 新增 | 全部复用 prometheus-client/logger/标准库 |
| 持久化 | 不新增 model，仅内存队列 | SQL 频率高全持久化 IO 压力大 + 递归风险；三层存储（内存队列/logger/Prometheus）已覆盖实时/告警/趋势场景 |
| 前端集成位置 | `index.html` MySQL 卡片内 | 用户要求；复用现有数据库页签数据加载框架，无需独立页面 |
| 前端 i18n key | 英文点分路径 | 与现有 key 约定一致，不嵌入中文 |