# 数据库连接池智能恢复系统完整指南

## 📖 文档概述

本文档是数据库连接池智能恢复系统的完整指南，包含：

1. **快速开始** - 3分钟快速上手
2. **功能介绍** - 主动恢复引擎的核心功能
3. **配置说明** - 完整的环境变量配置列表
4. **使用方法** - 详细的使用示例和场景
5. **最佳实践** - 生产环境的推荐配置
6. **监控告警** - 监控方法和告警说明
7. **故障排查** - 常见问题和解决方案

---

## 🚀 快速开始

### 1. 启动监控（自动启用智能恢复）

主动恢复引擎已自动集成到连接池监控系统中，**无需额外配置**：

```python
from globalobjects.db_pool import start_pool_monitoring

# 启动监控（自动启动主动恢复引擎）
await start_pool_monitoring(["db1", "db2", "db3"])
```

### 2. 查看监控状态

```python
from globalobjects.db_pool import get_pool_monitor_status

status = get_pool_monitor_status()
print(status)
```

### 3. 配置参数（可选）

**所有参数都有默认值，无需配置即可运行。** 如需调整：

```bash
# .env 文件
DBPOOL_CLEANUP_INTERVAL=300         # 清理任务间隔（秒）
DBPOOL_LEAK_WARNING_THRESHOLD=80    # 泄漏警告阈值（%）
DBPOOL_LEAK_CRITICAL_THRESHOLD=90   # 泄漏严重阈值（%）
DBPOOL_LEAK_EMERGENCY_THRESHOLD=95  # 泄漏紧急阈值（%）
```

### 4. 验证配置

```python
from globalobjects.db_pool import get_pool_config

config = get_pool_config()
print(f"清理间隔: {config.cleanup_interval}秒")
print(f"警告阈值: {config.leak_warning_threshold}%")
```

**💡 提示：默认配置适用于大多数生产环境，建议先观察运行情况再调整。**

---

## 🎯 功能概述

### 核心功能

主动连接恢复引擎（ActiveConnectionRecovery）是一个智能的数据库连接池恢复系统，提供：

#### ✅ 主动扫描僵尸连接
- 定期扫描连接池中长时间未使用的连接（默认300秒）
- 自动识别并回收僵尸连接
- 避免连接泄漏导致连接池耗尽

#### ✅ 智能恢复策略（4级分级）

| 优先级 | 策略 | 等待时间 | 适用场景 |
|--------|------|----------|----------|
| LOW | FAST_REFRESH | 0.5秒 | 轻微异常 |
| MEDIUM | FULL_REFRESH | 1秒 | 僵尸连接 |
| HIGH | REBUILD_POOL | 2秒 | 连接池不可用 |
| CRITICAL | GRACEFUL_RESTART | 多次重试 | 使用率>95% |

#### ✅ 指数退避机制
- 恢复失败后，退避时间指数增长：5s → 10s → 20s → 40s → ... → 300s
- 恢复成功后，退避时间重置为 5s
- 高优先级任务减少退避时间，低优先级任务增加退避时间
- **避免频繁恢复尝试，减少系统开销**

#### ✅ 分级告警
- 区分健康检查失败和真实连接泄漏
- 不同级别使用不同日志级别
- 包含详细的诊断信息

#### ✅ 完整恢复统计
- 记录总尝试次数、成功次数、失败次数
- 计算恢复成功率
- 保存最近100次恢复历史
- 支持监控和优化

---

## ⚙️ 配置说明

### 环境变量完整列表

**所有参数都有默认值，无需配置即可运行，按需调整即可。**

### 基础配置

```bash
# 是否启用增强的连接池管理（默认：true）
DBPOOL_USE_ENHANCED=true

# 健康检查配置
DBPOOL_HEALTH_CHECK_TIMEOUT=5.0          # 健康检查超时时间（秒）
DBPOOL_HEALTH_CHECK_SQL="SELECT 1"       # 健康检查SQL语句

# 连接池状态管理
DBPOOL_STATE_LOCK_TIMEOUT=10.0           # 状态锁超时时间（秒）
```

### 清理任务配置

```bash
DBPOOL_CLEANUP_INTERVAL=300              # 后台清理任务间隔（秒）
DBPOOL_MAX_CLEANUP_TIME=30               # 单次清理最大时间（秒）
DBPOOL_MAX_CLEANUP_QUEUE_SIZE=100        # 清理队列最大大小
```

### 泄漏检测配置

```bash
DBPOOL_LEAK_WARNING_THRESHOLD=80         # 泄漏警告阈值（%）
DBPOOL_LEAK_CRITICAL_THRESHOLD=90        # 泄漏严重阈值（%）
DBPOOL_LEAK_EMERGENCY_THRESHOLD=95       # 泄漏紧急阈值（%）
DBPOOL_LEAK_HISTORY_SIZE=100             # 泄漏检测历史数据大小
DBPOOL_LEAK_ANALYSIS_WINDOW=300          # 泄漏检测分析窗口（秒）
```

### 告警配置

```bash
DBPOOL_ALERT_COOLDOWN=300                # 告警冷却时间（秒）
```

### 主动恢复配置

```bash
DBPOOL_CONNECTION_TIMEOUT=300            # 连接超时时间（秒）- 僵尸连接判定阈值
DBPOOL_MAX_RECOVERY_ATTEMPTS=5           # 最大恢复尝试次数
DBPOOL_BASE_BACKOFF=5.0                  # 基础退避时间（秒）
DBPOOL_MAX_BACKOFF=300.0                 # 最大退避时间（秒）
```

### 参数说明表

#### 核心参数

| 参数 | 默认值 | 说明 | 推荐范围 |
|------|--------|------|----------|
| `DBPOOL_USE_ENHANCED` | true | 是否启用增强连接池管理 | true/false |
| `DBPOOL_HEALTH_CHECK_TIMEOUT` | 5.0 | 健康检查超时（秒） | 3.0-10.0 |
| `DBPOOL_CLEANUP_INTERVAL` | 300 | 清理任务间隔（秒） | 60-600 |

#### 泄漏检测参数

| 参数 | 默认值 | 说明 | 推荐范围 |
|------|--------|------|----------|
| `DBPOOL_LEAK_WARNING_THRESHOLD` | 80 | 警告阈值（%） | 70-85 |
| `DBPOOL_LEAK_CRITICAL_THRESHOLD` | 90 | 严重阈值（%） | 85-95 |
| `DBPOOL_LEAK_EMERGENCY_THRESHOLD` | 95 | 紧急阈值（%） | 90-98 |

#### 告警参数

| 参数 | 默认值 | 说明 | 推荐范围 |
|------|--------|------|----------|
| `DBPOOL_ALERT_COOLDOWN` | 300 | 告警冷却时间（秒） | 60-600 |

---

## 🚀 使用方法

### 1. 基本使用（自动集成）

主动恢复引擎已自动集成到连接池监控系统中，无需手动配置：

```python
from globalobjects.db_pool import start_pool_monitoring

# 启动监控（自动启动主动恢复引擎）
await start_pool_monitoring(["db1", "db2", "db3"])
```

### 2. 手动控制

如需手动控制主动恢复引擎：

```python
from globalobjects.db_pool import ActiveConnectionRecovery

# 获取实例
recovery = ActiveConnectionRecovery.get_instance()

# 注册连接
recovery.register_connection("my_db")

# 启动引擎
await recovery.start()

# 停止引擎
await recovery.stop()
```

### 3. 查看恢复统计

```python
from globalobjects.db_pool import get_pool_monitor_status

# 获取监控状态（包含恢复统计）
status = get_pool_monitor_status()

print(status["active_recovery_status"])
# 输出示例：
# {
#   "is_running": True,
#   "registered_connections": ["db1", "db2"],
#   "connection_stats": {
#     "db1": {
#       "total_attempts": 10,
#       "successful_recoveries": 8,
#       "failed_recoveries": 2,
#       "success_rate": 0.8,
#       "current_backoff": 10.0
#     }
#   }
# }
```

### 4. 查看单个连接的恢复统计

```python
from globalobjects.db_pool import ActiveConnectionRecovery

recovery = ActiveConnectionRecovery.get_instance()
stats = recovery.get_recovery_stats("db1")

print(f"恢复成功率: {stats['success_rate']:.1%}")
print(f"总尝试次数: {stats['total_attempts']}")
print(f"当前退避时间: {stats['current_backoff']:.1f}秒")
```

### 5. 代码配置方式

```python
from globalobjects.db_pool import PoolManagerConfig, ActiveConnectionRecovery

config = PoolManagerConfig(
    cleanup_interval=300,  # 扫描间隔
    leak_emergency_threshold=95,  # 紧急阈值
    leak_critical_threshold=90,   # 严重阈值
    leak_warning_threshold=80     # 警告阈值
)

recovery = ActiveConnectionRecovery.get_instance(config)
```

---

## 📋 配置场景示例

### 场景1：默认配置（推荐）

适用于大多数生产环境，无需任何配置：

```bash
# 无需配置，使用默认值即可
```

**适用场景**：
- 标准生产环境
- 中等负载应用
- 数据库服务稳定

### 场景2：高负载环境

连接使用频繁，需要更严格的监控：

```bash
DBPOOL_LEAK_WARNING_THRESHOLD=70         # 降低警告阈值
DBPOOL_LEAK_CRITICAL_THRESHOLD=85        # 降低严重阈值
DBPOOL_LEAK_EMERGENCY_THRESHOLD=90       # 降低紧急阈值
DBPOOL_CLEANUP_INTERVAL=180              # 缩短扫描间隔（3分钟）
DBPOOL_ALERT_COOLDOWN=180                # 缩短告警冷却（3分钟）
```

**适用场景**：
- 高并发应用
- 连接使用率常>70%
- 需要快速响应故障

### 场景3：低性能环境

服务器资源有限，减少监控开销：

```bash
DBPOOL_CLEANUP_INTERVAL=600              # 延长扫描间隔（10分钟）
DBPOOL_HEALTH_CHECK_TIMEOUT=10.0         # 增加健康检查超时
DBPOOL_LEAK_HISTORY_SIZE=50              # 减少历史数据大小
```

**适用场景**：
- 低配服务器
- 资源受限环境
- 非关键业务

### 场景4：高可用环境

要求快速恢复，减少故障时间：

```bash
DBPOOL_HEALTH_CHECK_TIMEOUT=3.0          # 缩短健康检查超时
DBPOOL_CLEANUP_INTERVAL=120              # 缩短扫描间隔（2分钟）
DBPOOL_ALERT_COOLDOWN=120                # 缩短告警冷却（2分钟）
DBPOOL_STATE_LOCK_TIMEOUT=5.0            # 缩短状态锁超时
DBPOOL_BASE_BACKOFF=2.0                  # 缩短基础退避时间
```

**适用场景**：
- 关键业务系统
- 要求高可用性
- 故障恢复时间要求<1分钟

### 场景5：开发/测试环境

减少告警干扰：

```bash
DBPOOL_LEAK_WARNING_THRESHOLD=90         # 提高警告阈值
DBPOOL_LEAK_CRITICAL_THRESHOLD=95        # 提高严重阈值
DBPOOL_ALERT_COOLDOWN=600                # 延长告警冷却（10分钟）
```

**适用场景**：
- 开发环境
- 测试环境
- 调试阶段

---

## 🔄 恢复流程示例

### 场景1：数据库服务宕机后自动恢复

```
时间轴：
08:41:34 ❌ 健康检查失败，触发 EMERGENCY 告警
08:42:34 🔄 尝试直接连接数据库 → 失败
08:43:34 🔄 尝试直接连接数据库 → 失败
08:44:34 ✅ 数据库已恢复，执行 REBUILD_POOL 策略
08:44:36 ✅ 连接池重建成功，服务恢复
```

**恢复策略**：REBUILD_POOL（重建连接池）

### 场景2：僵尸连接自动回收

```
时间轴：
10:00:00 🔍 扫描发现3个僵尸连接（空闲>300秒）
10:00:00 🔄 执行 FULL_REFRESH 策略
10:00:01 ✅ 僵尸连接已清理，连接池刷新成功
```

**恢复策略**：FULL_REFRESH（完整刷新）

### 场景3：高负载自动恢复

```
时间轴：
14:30:00 ⚠️ 检测到连接使用率=96%
14:30:00 🔄 执行 GRACEFUL_RESTART 策略（多次重试）
14:30:02 ❌ 第1次重建失败
14:30:07 ❌ 第2次重建失败
14:30:12 ✅ 第3次重建成功，服务恢复
```

**恢复策略**：GRACEFUL_RESTART（优雅重启）

---

## 📊 监控和告警

### 1. 查看实时状态

#### API方式

```bash
curl http://localhost:8000/api/pool-monitor/status
```

#### 命令行方式

```bash
tail -f /opt/myaps_api/logs/dev_server.log | grep -E "(ActiveRecovery|PoolMonitor)"
```

### 2. 关键日志

```log
# 恢复开始
INFO - ActiveRecovery @db1 - 开始恢复: 策略=rebuild_pool, 优先级=high, 原因=连接池不可用

# 恢复成功
INFO - ActiveRecovery @db1 - 恢复成功: 策略=rebuild_pool, 耗时=2.35秒

# 恢复失败
WARNING - ActiveRecovery @db1 - 恢复失败: 策略=rebuild_pool, 耗时=1.20秒

# 退避调整
DEBUG - ActiveRecovery @db1 - 退避时间增加: 10.0秒 -> 20.0秒

# 僵尸连接发现
WARNING - ActiveRecovery @db1 - 发现僵尸连接: ID=12345, 空闲时间=350.5秒
```

### 3. 告警级别

| 告警类型 | 日志级别 | 说明 |
|---------|---------|------|
| 健康检查失败 | ERROR | 数据库连接不可用 |
| 连接泄漏 | WARNING | 使用率>=80% |
| 连接池异常 | WARNING | 其他异常情况 |
| 恢复失败 | WARNING | 自动恢复失败 |
| 恢复成功 | INFO | 自动恢复成功 |

### 4. 配置验证

配置完成后，可以通过以下方式验证：

#### 查看当前配置

```python
from globalobjects.db_pool import get_pool_config

config = get_pool_config()
print(f"清理间隔: {config.cleanup_interval}秒")
print(f"警告阈值: {config.leak_warning_threshold}%")
print(f"严重阈值: {config.leak_critical_threshold}%")
print(f"紧急阈值: {config.leak_emergency_threshold}%")
```

#### 查看监控状态

```python
from globalobjects.db_pool import get_pool_monitor_status

status = get_pool_monitor_status()
print(status)
```

---

## 💡 最佳实践

### 1. 生产环境推荐配置

```bash
# .env 文件
DBPOOL_USE_ENHANCED=true
DBPOOL_CLEANUP_INTERVAL=300           # 5分钟扫描一次
DBPOOL_LEAK_EMERGENCY_THRESHOLD=95    # 95%触发紧急恢复
DBPOOL_LEAK_CRITICAL_THRESHOLD=90     # 90%触发严重恢复
DBPOOL_LEAK_WARNING_THRESHOLD=80      # 80%触发警告
DBPOOL_ALERT_COOLDOWN=300             # 5分钟告警冷却
```

### 2. 监控建议

- **短期监控**：关注恢复成功率和退避时间
- **中期监控**：分析恢复历史，优化恢复策略
- **长期监控**：统计故障频率，改进系统稳定性

### 3. 故障排查

如果频繁触发自动恢复：

1. 检查数据库服务稳定性
2. 检查网络连接质量
3. 检查连接池配置（最大连接数、超时时间）
4. 检查应用代码是否存在连接泄漏

### 4. 性能优化

- **调整扫描间隔**：根据业务负载调整 `DBPOOL_CLEANUP_INTERVAL`
- **调整阈值**：根据实际情况调整泄漏阈值
- **优化退避**：根据恢复成功率调整退避参数

---

## ❓ 常见问题

### Q1: 主动恢复会影响性能吗？

**A**: 影响很小。扫描任务在后台异步执行，不阻塞业务线程。默认5分钟扫描一次，开销可忽略。

### Q2: 如果数据库一直不可用怎么办？

**A**: 指数退避机制会逐渐增加重试间隔（5s → 300s），避免频繁尝试。同时会持续记录告警，提醒人工介入。

### Q3: 如何判断恢复是否有效？

**A**: 查看恢复统计中的 `success_rate`。如果成功率<50%，说明恢复效果不佳，需要排查根本原因。

### Q4: 可以禁用主动恢复吗？

**A**: 可以，但不推荐。如果确实需要禁用：

```python
# 方式1：不启动监控
# await start_pool_monitoring(...)  # 注释掉

# 方式2：只停止主动恢复引擎
from globalobjects.db_pool import ActiveConnectionRecovery
recovery = ActiveConnectionRecovery.get_instance()
await recovery.stop()
```

### Q5: 如何自定义恢复策略？

**A**: 可以继承 `ActiveConnectionRecovery` 并重写 `_select_recovery_strategy` 方法：

```python
class CustomRecovery(ActiveConnectionRecovery):
    def _select_recovery_strategy(self, priority):
        # 自定义策略选择逻辑
        if priority == RecoveryPriority.HIGH:
            return RecoveryStrategy.FULL_REFRESH  # 改用完整刷新
        return super()._select_recovery_strategy(priority)
```

### Q6: 这些参数如果不在 .env 文件中声明，是否有默认值？

**A**: 是的，**所有参数都有默认值**，无需配置即可运行。默认值适用于大多数生产环境。

### Q7: 如何从旧配置迁移到新配置？

**A**: 更新 `.env` 文件中的环境变量名称：

```bash
# 旧配置（已废弃）
USE_ENHANCED_POOL=true
HEALTH_CHECK_TIMEOUT=5.0

# 新配置（推荐）
DBPOOL_USE_ENHANCED=true
DBPOOL_HEALTH_CHECK_TIMEOUT=5.0
```

---

## 🔍 故障排查指南

### 配置问题

如果配置后出现问题：

1. **检查参数格式**：确保数值类型正确（整数/浮点数）
2. **检查阈值关系**：确保 `WARNING < CRITICAL < EMERGENCY`
3. **检查单位**：注意时间单位是秒，阈值单位是百分比
4. **查看日志**：检查启动日志是否有配置错误提示

### 恢复失败

如果自动恢复频繁失败：

1. **检查数据库连接**：确认数据库服务正常运行
2. **检查网络连通性**：测试数据库网络连接
3. **检查连接配置**：验证连接参数是否正确
4. **查看详细日志**：分析失败原因

### 性能问题

如果监控影响性能：

1. **增加扫描间隔**：调大 `DBPOOL_CLEANUP_INTERVAL`
2. **减少历史数据**：调小 `DBPOOL_LEAK_HISTORY_SIZE`
3. **提高告警阈值**：减少不必要的告警

---

## 📈 对比：优化前 vs 优化后

| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| **恢复检测** | 被动（60-300秒） | ✅ 主动（定期扫描） |
| **恢复策略** | 单一（刷新连接池） | ✅ 分级（4种策略） |
| **退避机制** | ❌ 无 | ✅ 指数退避（5s-300s） |
| **告警分类** | ❌ 混淆 | ✅ 清晰区分 |
| **僵尸连接** | ❌ 不处理 | ✅ 主动回收 |
| **恢复统计** | ❌ 无 | ✅ 完整统计 |
| **自适应** | ❌ 无 | ✅ 自适应调整 |
| **成功率** | 未知 | ✅ 可监控 |
| **配置命名** | ❌ 不统一 | ✅ 统一前缀 |

---

## 🎯 总结

### 核心优势

通过智能自动恢复系统，服务现在具备**完整的自动恢复能力**：

1. ✅ **主动监控**：定期扫描连接池状态
2. ✅ **智能恢复**：分级策略 + 指数退避
3. ✅ **清晰告警**：区分不同故障类型
4. ✅ **完整统计**：支持监控和优化
5. ✅ **统一配置**：所有参数统一前缀管理

### 使用建议

- **生产环境**：保持默认配置，让系统自动处理大部分故障
- **高负载环境**：降低阈值，缩短扫描间隔
- **低性能环境**：延长扫描间隔，减少监控开销
- **高可用环境**：缩短超时时间，快速恢复

### 关键要点

1. **所有参数都有默认值**，无需配置即可运行
2. **环境变量统一前缀** `DBPOOL_`，便于管理
3. **分级恢复策略**，根据故障严重程度自动选择
4. **指数退避机制**，避免频繁恢复尝试
5. **完整恢复统计**，支持监控和优化

**现在可以放心地让系统自动处理大部分故障场景！**

---

## 📚 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 本文档 | `globalobjects/db_pool/DBPOOL_GUIDE.md` | 完整使用指南 |
| 模块文档 | `globalobjects/db_pool/README.md` | 模块概述 |
| 使用示例 | `globalobjects/db_pool/examples.py` | 代码示例 |
| 开发指南 | `AGENTS.md` | 项目开发规范 |

---

**最后更新**: 2026-07-29  
**版本**: 2.0.0  
**维护者**: MyAPS 开发团队