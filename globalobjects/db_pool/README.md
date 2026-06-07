# 数据库连接池管理模块

本模块提供数据库连接池的增强管理功能，解决连接泄漏问题。

## 目录结构

```
globalobjects/db_pool/
├── __init__.py                    # 模块入口，导出所有公共接口
├── db_pool_models.py              # 数据模型定义
├── db_pool_exceptions.py          # 异常类定义
├── db_pool_state_manager.py       # 连接池状态管理器
├── db_health_checker.py           # 健康检查器
├── db_connection_refresher.py     # 安全连接刷新器
├── db_leak_detector.py            # 泄漏检测器
├── db_cleanup_task.py             # 后台清理任务
└── db_enhanced_manager.py         # 增强的数据库管理器
```

## 核心组件

### 1. ConnectionPoolStateManager（状态管理器）
- 管理连接池生命周期状态（OPEN/CLOSED/REFRESHING）
- 提供原子性状态标记
- 支持并发访问控制
- 支持状态等待机制

### 2. HealthChecker（健康检查器）
- 执行连接健康检查（SELECT 1）
- 支持超时控制（默认5秒）
- 支持重试机制
- 异常隔离，不向上抛出异常

### 3. SafeConnectionRefresher（安全刷新器）
- 刷新前标记状态为CLOSED
- 刷新后执行健康验证
- 处理事件循环冲突
- 支持快速模式和正常模式

### 4. EnhancedConnectionLeakDetector（泄漏检测器）
- 记录连接使用历史
- 分析使用率趋势（线性回归）
- 分级告警（WARNING/CRITICAL/EMERGENCY）
- 生成处理建议

### 5. BackgroundCleanupTask（后台清理任务）
- 定期清理待清理队列（默认5分钟）
- 处理事件循环冲突的连接
- 支持重试机制
- 容错处理

### 6. EnhancedDbManager（增强管理器）
- 统一管理入口
- 集成所有核心组件
- 提供便捷的使用接口

## 快速使用

### 基本使用

```python
from globalobjects.db_pool import get_enhanced_db_manager

# 获取增强管理器
manager = get_enhanced_db_manager("my_connection")

# 检查健康状态
health_result = await manager.check_health()
if health_result.is_healthy:
    print("连接健康")
else:
    print(f"连接不健康: {health_result.error_message}")

# 获取连接（自动检查状态）
async with manager.get_connection() as conn:
    result = await conn.execute_query("SELECT * FROM users")

# 刷新连接
success = await manager.refresh_connection(fast_mode=True)

# 获取连接池状态
status = await manager.get_connection_pool_status()
print(f"使用率: {status.usage_rate}%")
```

### 泄漏检测

```python
from globalobjects.db_pool import EnhancedConnectionLeakDetector, ConnectionPoolStatus

# 创建检测器
detector = EnhancedConnectionLeakDetector()

# 记录使用情况
pool_status = ConnectionPoolStatus(
    connection_name="my_connection",
    total_connections=10,
    used_connections=8,
    idle_connections=2,
    usage_rate=80.0
)
detector.record_usage("my_connection", pool_status, is_healthy=True)

# 检测泄漏
result = detector.detect_leak("my_connection")
if result.leak_detected:
    print(f"检测到泄漏: {result.severity.value}")
    alert = detector.generate_alert("my_connection", result)
    print(f"告警: {alert.message}")
```

### 后台清理任务

```python
from globalobjects.db_pool import BackgroundCleanupTask

# 获取清理任务实例
cleanup_task = BackgroundCleanupTask.get_instance()

# 启动清理任务
await cleanup_task.start()

# 添加待清理连接
await cleanup_task.add_to_cleanup_queue(
    connection=old_conn,
    connection_name="my_connection",
    reason="event_loop_conflict"
)

# 查看状态
status = cleanup_task.get_status()
print(f"队列大小: {status['queue_size']}")
print(f"已清理: {status['cleanup_count']}")

# 停止清理任务
await cleanup_task.stop()
```

## 配置参数

通过环境变量或PoolManagerConfig配置：

```python
from globalobjects.db_pool import PoolManagerConfig

config = PoolManagerConfig(
    health_check_timeout=5.0,           # 健康检查超时（秒）
    health_check_sql="SELECT 1",        # 健康检查SQL
    cleanup_interval=300,               # 清理间隔（秒）
    max_cleanup_time=30,                # 单次清理最大时间（秒）
    max_cleanup_queue_size=100,         # 清理队列最大大小
    leak_warning_threshold=80,          # 泄漏警告阈值（%）
    leak_critical_threshold=90,         # 泄漏严重阈值（%）
    leak_emergency_threshold=95,        # 泄漏紧急阈值（%）
    leak_history_size=100,              # 泄漏检测历史大小
    state_lock_timeout=10.0             # 状态锁超时（秒）
)
```

## 集成到现有代码

在 `globalobjects/db_manager.py` 中集成：

```python
from globalobjects.db_pool import get_enhanced_db_manager

class DbManager:
    def __init__(self, connection_name: str):
        self.connection_name = connection_name
        self._enhanced_manager = get_enhanced_db_manager(connection_name)
    
    async def refresh_connection(self, fast_mode: bool = False):
        # 使用增强的刷新方法
        return await self._enhanced_manager.refresh_connection(fast_mode)
    
    async def check_connection_health(self):
        # 使用增强的健康检查
        return await self._enhanced_manager.check_health()
```

## 测试

运行单元测试：

```bash
pytest tests/test_db_pool_state_manager.py -v
pytest tests/test_health_checker.py -v
pytest tests/test_leak_detector.py -v
```

## 注意事项

1. **向后兼容**：新功能不影响现有的DbManager，可以渐进式集成
2. **单例模式**：状态管理器和增强管理器使用单例模式，确保全局唯一
3. **异步安全**：所有操作都是异步的，使用asyncio.Lock保证并发安全
4. **异常隔离**：健康检查和清理任务不会抛出异常，避免影响业务
5. **配置默认值**：所有配置都有合理的默认值，无需修改即可使用

## 故障排查

### 连接池不可用
- 检查状态管理器状态：`manager.get_state_info()`
- 检查连接池是否正在刷新
- 查看日志中的状态变更记录

### 健康检查超时
- 检查数据库服务是否正常
- 检查网络连接
- 调整 `health_check_timeout` 配置

### 连接泄漏
- 查看泄漏检测结果：`detector.detect_leak()`
- 检查告警消息和处理建议
- 检查后台清理任务状态

### 事件循环冲突
- 查看待清理队列：`refresher.get_pending_cleanup_items()`
- 检查后台清理任务是否运行
- 查看清理日志