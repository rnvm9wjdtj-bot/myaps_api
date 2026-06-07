# 数据库连接池泄漏问题分析与改进方案

## 1. 问题概述

在项目运行过程中，日志频繁出现以下错误：

```
- "Cannot acquire connection after closing pool"
- "数据库连接健康检查超时"
- "连接池扩容: haida1 从 1 到 3, 使用率: 100%"
```

这些错误表明数据库连接池存在连接泄漏问题，导致连接资源持续紧张。

## 2. 问题根源分析

### 2.1 核心问题：连接刷新逻辑不完善

**涉及文件**: `globalobjects/db_manager.py`

#### 问题 1：连接移除后未完全清理

**代码位置**: `db_manager.py` 第 2200-2250 行 `refresh_connection` 方法

```python
# 第 2247 行
connections.discard(self.connection_name)
```

**问题描述**：
当调用 `connections.discard()` 时，虽然从连接字典中移除了连接引用，但旧的连接池对象本身可能没有被正确关闭。特别是：

1. 连接池对象可能仍然持有底层的网络连接
2. 未显式关闭数据库socket连接
3. 连接池中的实际连接未被释放回操作系统

**影响**：
- 每次刷新连接都会泄漏一个连接池对象
- 数据库服务器的连接数持续增长
- 最终导致连接资源耗尽

#### 问题 2：事件循环冲突时的连接泄漏

**代码位置**: `db_manager.py` 第 2216-2218 行

```python
if "bound to a different event loop" in str(close_error):
    logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
```

**问题描述**：
当检测到事件循环冲突时，直接**跳过了关闭操作**，导致旧连接继续存在且无法被正常清理。

**影响**：
- 旧连接对象持续占用内存
- 数据库连接资源泄漏
- 系统资源浪费

#### 问题 3：异常处理不完善

**代码位置**: `db_manager.py` 第 2236-2240 行

```python
except Exception as close_error:
    if "bound to a different event loop" in str(close_error):
        logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
    else:
        logger.warning(f"关闭旧连接时出错: {close_error}")
```

**问题描述**：
捕获异常后仅记录日志，没有后续的清理或补偿机制，导致资源泄漏。

**影响**：
- 无法追踪真正的错误原因
- 泄漏的连接继续占用资源
- 问题会累积并逐渐恶化

### 2.2 连接池使用模式问题

#### 问题 4：频繁的连接池重建

**代码位置**: `db_manager.py` 第 2246-2250 行

```python
try:
    connections.discard(self.connection_name)
    logger.info(f"已从连接存储中移除: {self.connection_name}")
except Exception as discard_error:
    logger.warning(f"移除连接时出错: {discard_error}")
```

**问题描述**：
每次健康检查失败或连接出现问题时，都会调用 `refresh_connection`，导致频繁的连接池重建。

**影响**：
- 频繁的连接建立和断开开销
- 每次重建都可能遗留旧的连接对象
- 性能下降和资源泄漏

#### 问题 5：缺少连接获取后的可靠性保证

**代码位置**: `db_manager.py` 第 894-904 行

```python
@asynccontextmanager
async def get_connection(self):
    """
    异步上下文管理器，用于安全地获取Tortoise ORM的数据库连接
    注意：Tortoise会自动管理连接的获取和释放，不需要手动关闭连接
    
    Yields:
        Tortoise数据库连接对象
    """
    connection = Tortoise.get_connection(self.connection_name)
    yield connection
```

**问题描述**：
虽然注释说"Tortoise会自动管理"，但在异常处理路径中（特别是重试和刷新逻辑中），连接可能没有被正确归还到连接池。

**影响**：
- 异常情况下连接无法正确释放
- 连接池状态不一致
- 长时间运行后连接耗尽

### 2.3 健康检查机制问题

#### 问题 6：健康检查触发刷新，刷新又依赖健康检查

**代码位置**: `db_manager.py` 第 2135-2175 行

```python
async def check_connection_health(self, timeout: int = 5, fast_mode: bool = False) -> bool:
    try:
        await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"数据库连接健康检查超时: {self.connection_name}")
        await self.refresh_connection(fast_mode=fast_mode)  # 这里调用刷新
        # 再次检查...
```

**问题描述**：
健康检查失败时会触发刷新连接，刷新过程本身又可能失败，形成死循环或级联故障。

**影响**：
- 刷新失败后健康检查返回 False
- 错误的连接状态被记录
- 可能触发更多的刷新操作

## 3. 现有检测机制

项目已经实现了 `ConnectionLeakDetector` 来检测连接泄漏（`core/database.py` 第 416-500 行），说明开发团队已经意识到这个问题。

### 3.1 检测逻辑

```python
class ConnectionLeakDetector:
    def detect_leak(self, db_name: str) -> Dict[str, Any]:
        # 检测条件：
        # 1. 平均使用率超过警告阈值
        # 2. 使用率持续高位（超过80%的数据点超过警告阈值）
        leak_detected = (
            avg_utilization > self._warning_threshold or 
            (high_usage_ratio > 0.8 and max_utilization > self._critical_threshold)
        )
```

### 3.2 智能连接池管理

```python
class SmartConnectionPoolManager:
    async def monitor_and_adjust(self):
        # 记录连接使用历史（用于泄漏检测）
        self._leak_detector.record_connection_usage(db_name, pool_status)
        
        # 检测连接泄漏
        leak_info = self._leak_detector.detect_leak(db_name)
        if leak_info.get('leak_detected'):
            # 尝试刷新连接
            await manager.refresh_connection(fast_mode=True)
```

## 4. 改进方案

### 4.1 方案一：完善连接清理机制（推荐）

#### 改进点 1：增强连接关闭逻辑

```python
async def refresh_connection(self, fast_mode: bool = False):
    """刷新数据库连接，确保连接有效"""
    # ... 省略前面的代码 ...
    
    # 1. 尝试获取并关闭当前连接
    try:
        conn = Tortoise.get_connection(self.connection_name)
        
        if conn and hasattr(conn, 'close'):
            # 检查是否是TransactionWrapper
            if hasattr(conn, '_pool'):
                try:
                    # 方案：使用更激进的清理策略
                    await self._force_close_connection(conn)
                except Exception as close_error:
                    logger.warning(f"关闭连接时出错: {close_error}")
                    # 即使出错也要尝试标记连接为不可用
                    await self._mark_connection_invalid(conn)
            else:
                # 对于TransactionWrapper
                if hasattr(conn, 'connection'):
                    inner_conn = conn.connection
                    if inner_conn and hasattr(inner_conn, 'close'):
                        await self._force_close_connection(inner_conn)
    except Exception as get_conn_error:
        logger.warning(f"获取当前连接时出错: {get_conn_error}")
    
    # 2. 从连接存储中移除
    connections.discard(self.connection_name)
    
    # 3. 方案：添加连接池状态标记，防止后续获取
    await self._mark_pool_as_closed()
    
    # 4. 等待连接完全关闭
    if fast_mode:
        wait_time = 0.5
    else:
        wait_time = 1.0
    await asyncio.sleep(wait_time)
    
    # 5. 尝试重新获取连接
    try:
        new_conn = connections.get(self.connection_name)
        await new_conn.execute_query("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"获取新连接失败: {e}")
        return False

async def _force_close_connection(self, conn):
    """
    强制关闭连接，处理各种异常情况
    """
    if conn is None:
        return
    
    try:
        # 尝试关闭连接池
        if hasattr(conn, '_pool') and conn._pool:
            pool = conn._pool
            # 关闭所有连接
            if hasattr(pool, 'close'):
                await pool.close()
            # 清理连接队列
            if hasattr(pool, '_connections'):
                pool._connections.clear()
            if hasattr(pool, '_used'):
                pool._used.clear()
            if hasattr(pool, '_idle'):
                pool._idle.clear()
    except RuntimeError as e:
        # 处理事件循环冲突
        if "bound to a different event loop" in str(e):
            logger.warning("检测到事件循环冲突，使用延迟清理策略")
            # 将连接标记为待清理
            self._pending_cleanup.append(conn)
        else:
            raise
    except Exception as e:
        logger.warning(f"强制关闭连接时出错: {e}")

async def _mark_connection_invalid(self, conn):
    """
    标记连接为无效状态，防止后续使用
    """
    try:
        # 标记连接属性
        conn._valid = False
        conn._closed = True
        # 标记连接池属性
        if hasattr(conn, '_pool') and conn._pool:
            conn._pool._closed = True
    except Exception as e:
        logger.warning(f"标记连接状态时出错: {e}")
```

#### 改进点 2：添加连接池状态管理

```python
class ConnectionPoolState:
    """
    连接池状态管理器，防止在连接池关闭后继续使用
    """
    _pool_states: Dict[str, bool] = {}  # connection_name -> is_closed
    
    @classmethod
    def mark_closed(cls, connection_name: str):
        """标记连接池为已关闭"""
        cls._pool_states[connection_name] = True
    
    @classmethod
    def mark_open(cls, connection_name: str):
        """标记连接池为打开状态"""
        cls._pool_states[connection_name] = False
    
    @classmethod
    def is_closed(cls, connection_name: str) -> bool:
        """检查连接池是否已关闭"""
        return cls._pool_states.get(connection_name, False)
    
    @classmethod
    def reset(cls, connection_name: str):
        """重置连接池状态"""
        cls._pool_states.pop(connection_name, None)
```

### 4.2 方案二：优化健康检查机制

#### 改进点 3：分离健康检查和刷新逻辑

```python
async def check_connection_health(self, timeout: int = 5) -> bool:
    """
    检查数据库连接健康状态（仅检查，不执行刷新）
    """
    try:
        import asyncio
        conn = Tortoise.get_connection(self.connection_name)
        
        # 检查连接池状态
        if ConnectionPoolState.is_closed(self.connection_name):
            logger.warning(f"连接池已标记为关闭: {self.connection_name}")
            return False
        
        await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(f"数据库连接健康检查超时: {self.connection_name}")
        return False
    except Exception as e:
        logger.warning(f"数据库连接健康检查失败: {e}")
        return False

async def refresh_connection_safe(self, fast_mode: bool = False):
    """
    安全刷新连接，包含完整的状态管理
    """
    # 标记即将刷新
    ConnectionPoolState.mark_closed(self.connection_name)
    
    try:
        await self.refresh_connection(fast_mode)
        
        # 验证新连接
        is_healthy = await self.check_connection_health(timeout=5)
        if is_healthy:
            # 标记刷新完成
            ConnectionPoolState.mark_open(self.connection_name)
            return True
        else:
            logger.error(f"刷新后连接仍不健康: {self.connection_name}")
            return False
    except Exception as e:
        logger.error(f"刷新连接失败: {e}")
        return False
```

### 4.3 方案三：实现定期清理机制

#### 改进点 4：添加后台清理任务

```python
class ConnectionCleanupManager:
    """
    连接清理管理器，定期清理可能泄漏的连接
    """
    _instance = None
    _cleanup_interval = 300  # 5分钟
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def start_cleanup_task(self):
        """启动定期清理任务"""
        while True:
            try:
                await self._cleanup_pending_connections()
                await self._cleanup_invalid_connections()
            except Exception as e:
                logger.error(f"连接清理任务异常: {e}")
            
            await asyncio.sleep(self._cleanup_interval)
    
    async def _cleanup_pending_connections(self):
        """清理待处理的连接"""
        # 清理标记为无效但未关闭的连接
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        
        for db_name, manager in db_managers.items():
            if hasattr(manager, '_pending_cleanup'):
                for conn in manager._pending_cleanup:
                    try:
                        await self._force_close_connection(conn)
                    except Exception as e:
                        logger.warning(f"清理待处理连接失败: {e}")
                manager._pending_cleanup.clear()
    
    async def _cleanup_invalid_connections(self):
        """清理无效的连接"""
        # 检查并清理陈旧的连接对象
        pass
```

### 4.4 方案四：增加连接泄漏监控告警

#### 改进点 5：增强监控告警

```python
async def check_connection_leak(self, db_name: str) -> Dict[str, Any]:
    """
    检查是否存在连接泄漏
    """
    result = {
        'leak_detected': False,
        'severity': 'normal',
        'details': {}
    }
    
    try:
        # 1. 检查连接池状态
        pool_status = await self.get_connection_pool_status()
        
        if pool_status.get('pool_available') is False:
            result['leak_detected'] = True
            result['severity'] = 'critical'
            result['details']['pool_unavailable'] = True
            return result
        
        # 2. 检查使用率趋势
        usage_rate = pool_status.get('usage_rate', 0)
        if usage_rate > 90:
            result['leak_detected'] = True
            result['severity'] = 'warning'
            result['details']['high_usage_rate'] = usage_rate
        
        # 3. 检查健康检查失败率
        # （需要额外的统计记录）
        
        # 4. 检查刷新操作失败率
        # （需要额外的统计记录）
        
        return result
    except Exception as e:
        logger.error(f"连接泄漏检查失败: {e}")
        result['leak_detected'] = True
        result['severity'] = 'critical'
        result['details']['check_failed'] = str(e)
        return result
```

## 5. 实施优先级建议

### 高优先级（立即实施）

1. **方案一：完善连接清理机制**
   - 影响范围：全局
   - 风险等级：低
   - 预期收益：高
   - 实施建议：重点实现 `_force_close_connection` 方法

2. **方案二：分离健康检查和刷新逻辑**
   - 影响范围：监控模块
   - 风险等级：低
   - 预期收益：中
   - 实施建议：避免刷新操作的级联失败

### 中优先级（近期实施）

3. **方案三：实现定期清理机制**
   - 影响范围：后台任务
   - 风险等级：中
   - 预期收益：中
   - 实施建议：作为兜底机制，处理边界情况

4. **方案四：增加连接泄漏监控告警**
   - 影响范围：监控告警
   - 风险等级：低
   - 预期收益：中
   - 实施建议：增强现有监控能力

## 6. 验证方案

### 6.1 单元测试

```python
import pytest

class TestConnectionLeakFix:
    """连接泄漏修复测试"""
    
    @pytest.mark.asyncio
    async def test_force_close_connection(self):
        """测试强制关闭连接"""
        manager = DbManager('test_db')
        conn = Tortoise.get_connection('test_db')
        
        await manager._force_close_connection(conn)
        
        # 验证连接已关闭
        assert conn._closed is True
    
    @pytest.mark.asyncio
    async def test_connection_pool_state(self):
        """测试连接池状态管理"""
        ConnectionPoolState.mark_closed('test_db')
        assert ConnectionPoolState.is_closed('test_db') is True
        
        ConnectionPoolState.mark_open('test_db')
        assert ConnectionPoolState.is_closed('test_db') is False
        
        ConnectionPoolState.reset('test_db')
    
    @pytest.mark.asyncio
    async def test_refresh_connection_safe(self):
        """测试安全的连接刷新"""
        manager = DbManager('test_db')
        result = await manager.refresh_connection_safe(fast_mode=True)
        
        assert isinstance(result, bool)
```

### 6.2 集成测试

```python
@pytest.mark.asyncio
async def test_connection_pool_stability():
    """
    测试连接池稳定性：模拟多次健康检查失败和刷新
    """
    # 1. 模拟多次健康检查失败
    # 2. 验证连接不会泄漏
    # 3. 验证连接池状态始终正确
    pass
```

### 6.3 性能测试

```python
@pytest.mark.asyncio
async def test_connection_pool_performance():
    """
    测试连接池性能：模拟高并发场景
    """
    # 1. 模拟100个并发请求
    # 2. 监控连接池使用情况
    # 3. 验证没有连接泄漏
    # 4. 测量平均响应时间
    pass
```

## 7. 风险评估

### 7.1 实施风险

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| 修改连接管理逻辑导致系统不稳定 | 中 | 高 | 先在测试环境充分验证 |
| 新增的状态管理增加内存开销 | 低 | 低 | 使用弱引用或限制状态数量 |
| 后台清理任务影响性能 | 低 | 中 | 使用异步非阻塞方式 |

### 7.2 兼容性考虑

- 保持现有的 API 接口不变
- 向后兼容现有的连接获取方式
- 渐进式引入新机制

## 8. 总结

连接池泄漏问题的主要根源在于：

1. **连接清理不彻底**：特别是遇到事件循环冲突时直接跳过清理
2. **缺少状态管理**：无法追踪连接池的真实状态
3. **健康检查和刷新逻辑耦合**：导致级联失败

通过实施上述改进方案，可以：

- ✅ 减少连接泄漏风险
- ✅ 提高系统稳定性
- ✅ 增强监控能力
- ✅ 改善性能表现

建议按照优先级逐步实施，并在每个阶段进行充分的测试验证。
