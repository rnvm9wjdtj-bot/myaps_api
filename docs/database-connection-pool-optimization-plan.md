# 数据库连接池优化实施方案

## 文档信息
- **版本**: v1.0
- **创建日期**: 2026-06-08
- **适用范围**: myaps_api 项目数据库连接池管理
- **优先级**: 高

---

## 一、问题概述

根据连接池泄漏分析报告，当前数据库连接池存在以下核心问题：

| 问题ID | 问题描述 | 严重程度 | 影响 |
|--------|---------|---------|------|
| P01 | 连接移除后未完全清理，底层socket未关闭 | **高** | 连接资源持续占用，最终耗尽 |
| P02 | 事件循环冲突时跳过关闭操作 | **高** | 旧连接泄漏，无法回收 |
| P03 | 异常处理不完善，无清理补偿机制 | **中** | 问题累积恶化 |
| P04 | 健康检查与刷新逻辑耦合 | **中** | 级联故障风险 |

---

## 二、优化方案

### 方案一：完善连接清理机制（高优先级）

#### 2.1 增强连接关闭逻辑

**目标**: 在移除连接前确保底层资源完全释放

**修改文件**: `globalobjects/db_manager.py`

**实现代码**:

```python
async def refresh_connection(self, fast_mode: bool = False):
    """刷新数据库连接，确保连接有效"""
    
    # 1. 尝试获取并关闭当前连接
    try:
        conn = Tortoise.get_connection(self.connection_name)
        
        if conn and hasattr(conn, 'close'):
            if hasattr(conn, '_pool'):
                try:
                    await self._force_close_connection(conn)
                except Exception as close_error:
                    logger.warning(f"关闭连接时出错: {close_error}")
                    await self._mark_connection_invalid(conn)
            else:
                # 处理 TransactionWrapper
                if hasattr(conn, 'connection'):
                    inner_conn = conn.connection
                    if inner_conn and hasattr(inner_conn, 'close'):
                        await self._force_close_connection(inner_conn)
    except Exception as get_conn_error:
        logger.warning(f"获取当前连接时出错: {get_conn_error}")
    
    # 2. 从连接存储中移除
    connections.discard(self.connection_name)
    
    # 3. 标记连接池为关闭状态
    await self._mark_pool_as_closed()
    
    # 4. 等待连接完全关闭
    await asyncio.sleep(0.5 if fast_mode else 1.0)
    
    # 5. 验证新连接
    try:
        new_conn = connections.get(self.connection_name)
        await new_conn.execute_query("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"获取新连接失败: {e}")
        return False
```

#### 2.2 添加强制关闭方法

```python
async def _force_close_connection(self, conn):
    """强制关闭连接，处理各种异常情况"""
    if conn is None:
        return
    
    try:
        if hasattr(conn, '_pool') and conn._pool:
            pool = conn._pool
            # 关闭连接池
            if hasattr(pool, 'close'):
                await pool.close()
            # 清理连接队列
            for attr in ['_connections', '_used', '_idle']:
                if hasattr(pool, attr):
                    getattr(pool, attr).clear()
    except RuntimeError as e:
        if "bound to a different event loop" in str(e):
            logger.warning("检测到事件循环冲突，使用延迟清理策略")
            if not hasattr(self, '_pending_cleanup'):
                self._pending_cleanup = []
            self._pending_cleanup.append(conn)
        else:
            raise
    except Exception as e:
        logger.warning(f"强制关闭连接时出错: {e}")
```

#### 2.3 添加连接标记方法

```python
async def _mark_connection_invalid(self, conn):
    """标记连接为无效状态，防止后续使用"""
    try:
        conn._valid = False
        conn._closed = True
        if hasattr(conn, '_pool') and conn._pool:
            conn._pool._closed = True
    except Exception as e:
        logger.warning(f"标记连接状态时出错: {e}")
```

---

### 方案二：连接池状态管理（高优先级）

#### 2.4 新增连接池状态管理器

**目标**: 追踪连接池状态，防止使用已关闭的连接池

**新增文件**: `globalobjects/connection_pool_state.py`

```python
from typing import Dict

class ConnectionPoolState:
    """连接池状态管理器"""
    
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
    
    @classmethod
    def get_all_states(cls) -> Dict[str, bool]:
        """获取所有连接池状态"""
        return cls._pool_states.copy()
```

---

### 方案三：优化健康检查机制（高优先级）

#### 2.5 分离健康检查与刷新逻辑

**目标**: 避免健康检查失败触发级联刷新

**修改文件**: `globalobjects/db_manager.py`

```python
async def check_connection_health(self, timeout: int = 5) -> bool:
    """检查数据库连接健康状态（仅检查，不执行刷新）"""
    from globalobjects.connection_pool_state import ConnectionPoolState
    
    try:
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
    """安全刷新连接，包含完整的状态管理"""
    from globalobjects.connection_pool_state import ConnectionPoolState
    
    # 标记即将刷新
    ConnectionPoolState.mark_closed(self.connection_name)
    
    try:
        await self.refresh_connection(fast_mode)
        
        # 验证新连接
        is_healthy = await self.check_connection_health(timeout=5)
        if is_healthy:
            ConnectionPoolState.mark_open(self.connection_name)
            return True
        else:
            logger.error(f"刷新后连接仍不健康: {self.connection_name}")
            return False
    except Exception as e:
        logger.error(f"刷新连接失败: {e}")
        return False
```

---

### 方案四：定期清理机制（中优先级）

#### 2.6 新增连接清理管理器

**目标**: 定期清理泄漏的连接

**新增文件**: `globalobjects/connection_cleanup_manager.py`

```python
import asyncio
from typing import List

class ConnectionCleanupManager:
    """连接清理管理器，定期清理可能泄漏的连接"""
    
    _instance = None
    _cleanup_interval = 300  # 5分钟
    _pending_cleanup: List = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def start_cleanup_task(self):
        """启动定期清理任务"""
        logger.info("启动连接清理任务，清理间隔: {}秒".format(self._cleanup_interval))
        
        while True:
            try:
                await self._cleanup_pending_connections()
                await self._cleanup_invalid_connections()
            except Exception as e:
                logger.error(f"连接清理任务异常: {e}")
            
            await asyncio.sleep(self._cleanup_interval)
    
    async def _cleanup_pending_connections(self):
        """清理待处理的连接"""
        if not self._pending_cleanup:
            return
        
        from globalobjects.db_manager import get_db_managers
        
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            if hasattr(manager, '_pending_cleanup') and manager._pending_cleanup:
                for conn in manager._pending_cleanup:
                    try:
                        await manager._force_close_connection(conn)
                    except Exception as e:
                        logger.warning(f"清理待处理连接失败: {e}")
                manager._pending_cleanup.clear()
    
    async def _cleanup_invalid_connections(self):
        """清理无效的连接（可选扩展）"""
        # 可扩展：检查并清理长时间空闲的连接
        pass
    
    def add_pending_connection(self, conn):
        """添加待清理的连接"""
        self._pending_cleanup.append(conn)
```

---

### 方案五：增强监控告警（中优先级）

#### 2.7 连接泄漏检测增强

**修改文件**: `core/database.py`

```python
async def check_connection_leak(self, db_name: str) -> dict:
    """检查是否存在连接泄漏"""
    result = {
        'leak_detected': False,
        'severity': 'normal',
        'details': {},
        'timestamp': time.time()
    }
    
    try:
        pool_status = await self.get_connection_pool_status()
        
        if pool_status.get('pool_available') is False:
            result.update({
                'leak_detected': True,
                'severity': 'critical',
                'details': {'pool_unavailable': True}
            })
            return result
        
        usage_rate = pool_status.get('usage_rate', 0)
        if usage_rate > 90:
            result.update({
                'leak_detected': True,
                'severity': 'warning',
                'details': {'high_usage_rate': usage_rate}
            })
        
        return result
    except Exception as e:
        logger.error(f"连接泄漏检查失败: {e}")
        result.update({
            'leak_detected': True,
            'severity': 'critical',
            'details': {'check_failed': str(e)}
        })
        return result
```

---

## 三、实施步骤

### 阶段一：基础优化（立即实施）

| 步骤 | 任务 | 负责人 | 预计时间 |
|------|------|--------|---------|
| 1 | 添加 `ConnectionPoolState` 类 | 开发 | 0.5天 |
| 2 | 实现 `_force_close_connection` 方法 | 开发 | 1天 |
| 3 | 实现 `_mark_connection_invalid` 方法 | 开发 | 0.5天 |
| 4 | 修改 `refresh_connection` 方法 | 开发 | 1天 |

### 阶段二：逻辑优化（1周内）

| 步骤 | 任务 | 负责人 | 预计时间 |
|------|------|--------|---------|
| 5 | 分离健康检查与刷新逻辑 | 开发 | 1天 |
| 6 | 实现 `refresh_connection_safe` 方法 | 开发 | 0.5天 |
| 7 | 集成连接池状态检查 | 开发 | 0.5天 |

### 阶段三：进阶优化（2周内）

| 步骤 | 任务 | 负责人 | 预计时间 |
|------|------|--------|---------|
| 8 | 实现 `ConnectionCleanupManager` | 开发 | 1天 |
| 9 | 启动后台清理任务 | 开发 | 0.5天 |
| 10 | 增强连接泄漏检测 | 开发 | 1天 |

---

## 四、测试验证方案

### 4.1 单元测试

```python
import pytest

class TestConnectionPoolOptimization:
    """连接池优化测试"""
    
    @pytest.mark.asyncio
    async def test_force_close_connection(self):
        """测试强制关闭连接"""
        manager = DbManager('test_db')
        conn = Tortoise.get_connection('test_db')
        
        await manager._force_close_connection(conn)
        
        assert hasattr(conn, '_closed') and conn._closed is True
    
    @pytest.mark.asyncio
    async def test_connection_pool_state(self):
        """测试连接池状态管理"""
        from globalobjects.connection_pool_state import ConnectionPoolState
        
        ConnectionPoolState.mark_closed('test_db')
        assert ConnectionPoolState.is_closed('test_db') is True
        
        ConnectionPoolState.mark_open('test_db')
        assert ConnectionPoolState.is_closed('test_db') is False
    
    @pytest.mark.asyncio
    async def test_refresh_connection_safe(self):
        """测试安全的连接刷新"""
        manager = DbManager('test_db')
        result = await manager.refresh_connection_safe(fast_mode=True)
        
        assert isinstance(result, bool)
```

### 4.2 集成测试

```python
@pytest.mark.asyncio
async def test_connection_pool_stability():
    """测试连接池稳定性：模拟多次健康检查失败和刷新"""
    # 1. 模拟多次健康检查失败
    # 2. 验证连接不会泄漏
    # 3. 验证连接池状态始终正确
    pass
```

---

## 五、风险评估

| 风险项 | 可能性 | 影响程度 | 缓解措施 |
|--------|--------|----------|----------|
| 修改连接管理逻辑导致系统不稳定 | 中 | 高 | 先在测试环境充分验证 |
| 新增状态管理增加内存开销 | 低 | 低 | 使用弱引用或限制状态数量 |
| 后台清理任务影响性能 | 低 | 中 | 使用异步非阻塞方式 |
| 事件循环冲突处理不当 | 低 | 中 | 添加延迟清理队列 |

---

## 六、预期收益

| 指标 | 预期改善 |
|------|---------|
| 连接泄漏率 | 降低至接近0 |
| 系统稳定性 | 显著提升 |
| 资源利用率 | 优化连接池使用效率 |
| 可观测性 | 增强监控告警能力 |

---

## 七、兼容性考虑

- ✅ 保持现有 API 接口不变
- ✅ 向后兼容现有连接获取方式
- ✅ 渐进式引入新机制，不影响现有功能

---

## 八、版本记录

| 版本 | 修改日期 | 修改内容 | 作者 |
|------|---------|---------|------|
| v1.0 | 2026-06-08 | 初始版本 | 系统自动生成 |
