# 数据库连接池泄漏修复 - 部署验证方案

## 1. 灰度部署方案

### 1.1 部署阶段

#### 阶段一：测试环境验证（第1-2天）

**目标**：在测试环境全面验证新功能

**步骤**：
1. 部署到测试环境
2. 启用增强连接池管理（`USE_ENHANCED_POOL=true`）
3. 执行功能测试套件
4. 执行性能测试套件
5. 运行压力测试（模拟高并发场景）
6. 监控7天，确认无资源泄漏

**验证指标**：
- 所有单元测试通过率 100%
- 所有集成测试通过率 100%
- 连接获取响应时间 < 100ms
- 健康检查响应时间 < 5s
- 连接刷新时间 < 10s
- 内存使用稳定，无持续增长
- 连接数稳定，无持续增长

**回滚条件**：
- 任何测试失败
- 性能指标未达标
- 出现资源泄漏

#### 阶段二：生产环境单租户试点（第3-5天）

**目标**：在生产环境选择单个租户试点

**步骤**：
1. 选择非关键业务租户（如测试账套）
2. 为该租户启用增强连接池管理
3. 密切监控该租户的连接池状态
4. 对比试点前后的性能指标
5. 收集告警信息，验证准确性

**监控指标**：
- 连接池使用率趋势
- 健康检查成功率
- 连接刷新次数
- 泄漏告警次数
- 业务响应时间
- 错误率

**回滚条件**：
- 连接获取失败率 > 5%
- 业务响应时间增加 > 20%
- 出现严重资源泄漏
- 出现严重异常或崩溃

#### 阶段三：逐步推广（第6-10天）

**目标**：逐步推广到所有租户

**步骤**：
1. 每天推广2-3个租户
2. 优先推广非关键业务租户
3. 最后推广关键业务租户
4. 持续监控所有租户状态
5. 及时处理告警

**推广顺序**：
1. 测试账套
2. 开发环境账套
3. 小流量业务账套
4. 中流量业务账套
5. 大流量业务账套
6. 核心业务账套

### 1.2 功能开关配置

**配置方式**：
```bash
# 启用增强连接池管理
USE_ENHANCED_POOL=true

# 禁用增强连接池管理（回滚）
USE_ENHANCED_POOL=false
```

**动态开关**（可选）：
```python
from globalobjects.db_pool import get_enhanced_db_manager

# 动态禁用
manager = get_enhanced_db_manager("my_connection")
manager._use_enhanced_pool = False

# 动态启用
manager._use_enhanced_pool = True
```

## 2. 验证和监控方案

### 2.1 功能验证清单

#### 连接获取验证
- [ ] 正常获取连接成功
- [ ] 连接池关闭时获取连接失败（符合预期）
- [ ] 连接池刷新时获取连接等待
- [ ] 异常情况下自动重试

#### 健康检查验证
- [ ] 正常连接健康检查通过
- [ ] 异常连接健康检查失败
- [ ] 超时连接健康检查失败
- [ ] 健康检查重试机制生效

#### 连接刷新验证
- [ ] 正常刷新成功
- [ ] 刷新后健康检查通过
- [ ] 事件循环冲突处理正确
- [ ] 快速模式和正常模式都正常

#### 泄漏检测验证
- [ ] 正常情况无告警
- [ ] 高使用率触发WARNING告警
- [ ] 超高使用率触发CRITICAL告警
- [ ] 连接池不可用触发EMERGENCY告警
- [ ] 趋势分析准确

#### 后台清理验证
- [ ] 清理任务正常启动
- [ ] 待清理队列处理正确
- [ ] 清理失败重试机制生效
- [ ] 清理任务停止正常

### 2.2 性能验证清单

#### 响应时间验证
- [ ] 连接获取响应时间 < 100ms
- [ ] 健康检查响应时间 < 5s
- [ ] 连接刷新时间 < 10s
- [ ] 清理任务执行时间 < 30s
- [ ] 状态标记操作时间 < 1ms

#### 并发性能验证
- [ ] 100并发请求稳定运行
- [ ] 500并发请求稳定运行
- [ ] 1000并发请求稳定运行
- [ ] 无死锁、无竞态条件

#### 资源使用验证
- [ ] 内存使用稳定，无持续增长
- [ ] CPU使用正常，无异常峰值
- [ ] 连接数稳定，无持续增长
- [ ] 文件描述符使用正常

### 2.3 稳定性验证清单

#### 长时间运行验证
- [ ] 连续运行24小时无异常
- [ ] 连续运行7天无资源泄漏
- [ ] 连接池状态始终正确
- [ ] 告警机制正常工作

#### 异常场景验证
- [ ] 数据库断开后自动恢复
- [ ] 网络抖动后自动恢复
- [ ] 事件循环冲突正确处理
- [ ] 内存压力下稳定运行

#### 压力测试验证
- [ ] 1000 QPS稳定运行1小时
- [ ] 5000 QPS稳定运行10分钟
- [ ] 峰值流量下无连接耗尽
- [ ] 压力解除后资源正常回收

### 2.4 监控指标

#### 实时监控指标
```python
# 连接池状态
- connection_pool_state: {connection_name}
- connection_pool_usage_rate: {connection_name}
- connection_pool_used_connections: {connection_name}
- connection_pool_total_connections: {connection_name}

# 健康检查
- health_check_success_rate: {connection_name}
- health_check_response_time: {connection_name}

# 刷新操作
- connection_refresh_count: {connection_name}
- connection_refresh_success_rate: {connection_name}

# 泄漏检测
- leak_detected: {connection_name}
- leak_severity: {connection_name}

# 清理任务
- cleanup_queue_size
- cleanup_count
- cleanup_success_rate
```

#### 告警规则
```yaml
# 连接池使用率告警
- alert: HighConnectionPoolUsage
  expr: connection_pool_usage_rate > 80
  for: 5m
  severity: warning
  
- alert: CriticalConnectionPoolUsage
  expr: connection_pool_usage_rate > 90
  for: 3m
  severity: critical

# 健康检查失败告警
- alert: HealthCheckFailure
  expr: health_check_success_rate < 0.5
  for: 5m
  severity: critical

# 连接泄漏告警
- alert: ConnectionLeakDetected
  expr: leak_detected == 1
  for: 1m
  severity: critical
```

### 2.5 监控看板

**Grafana看板配置**：
```json
{
  "dashboard": "数据库连接池监控",
  "panels": [
    {
      "title": "连接池使用率",
      "type": "graph",
      "metrics": ["connection_pool_usage_rate"]
    },
    {
      "title": "健康检查成功率",
      "type": "stat",
      "metrics": ["health_check_success_rate"]
    },
    {
      "title": "连接刷新次数",
      "type": "counter",
      "metrics": ["connection_refresh_count"]
    },
    {
      "title": "泄漏告警",
      "type": "alert",
      "metrics": ["leak_detected", "leak_severity"]
    }
  ]
}
```

## 3. 回滚方案

### 3.1 回滚触发条件

**自动回滚条件**：
- 连接获取失败率 > 5%
- 业务响应时间增加 > 20%
- 出现严重资源泄漏（连接数持续增长）
- 出现严重异常或崩溃
- 健康检查失败率 > 50%

**手动回滚条件**：
- 监控发现异常趋势
- 业务方反馈性能问题
- 出现未预期的告警
- 安全审计发现问题

### 3.2 回滚步骤

#### 快速回滚（配置开关）

**步骤**：
1. 修改环境变量：`USE_ENHANCED_POOL=false`
2. 重启应用（如果需要）
3. 验证回滚成功
4. 通知相关团队

**时间**：< 5分钟

**验证**：
```python
# 检查是否使用原有逻辑
manager = DbManager("my_connection")
assert manager._use_enhanced_pool == False
assert manager._enhanced_pool_manager is None
```

#### 完整回滚（代码回滚）

**步骤**：
1. 停止监控任务
2. 禁用功能开关
3. 回滚代码到上一版本
4. 清理新增文件和目录
5. 重启应用
6. 验证回滚成功
7. 通知相关团队

**时间**：< 30分钟

**验证**：
```bash
# 检查文件是否已清理
ls globalobjects/db_pool/  # 应该不存在

# 检查配置是否已回滚
grep "USE_ENHANCED_POOL" .env  # 应该不存在或为false

# 检查监控是否已停止
# 应该没有相关日志输出
```

### 3.3 回滚后验证

#### 功能验证
- [ ] 原有功能正常工作
- [ ] 连接获取正常
- [ ] 健康检查正常
- [ ] 连接刷新正常
- [ ] 业务功能正常

#### 性能验证
- [ ] 响应时间恢复正常
- [ ] 资源使用正常
- [ ] 无新增异常

#### 监控验证
- [ ] 原有监控正常
- [ ] 无新增告警
- [ ] 日志正常输出

### 3.4 回滚文档

**回滚记录模板**：
```markdown
## 回滚记录

**回滚时间**：YYYY-MM-DD HH:MM:SS
**回滚原因**：[描述回滚原因]
**回滚方式**：[配置开关/代码回滚]
**影响范围**：[受影响的租户/功能]
**回滚耗时**：XX分钟

**回滚步骤**：
1. [步骤1]
2. [步骤2]
3. [步骤3]

**验证结果**：
- [验证项1]：通过/失败
- [验证项2]：通过/失败

**后续计划**：
- [描述后续处理计划]
```

## 4. 应急预案

### 4.1 常见问题处理

#### 问题1：连接池不可用

**症状**：日志出现"连接池不可用"错误

**诊断**：
```python
from globalobjects.db_pool import get_enhanced_db_manager

manager = get_enhanced_db_manager("my_connection")
state_info = manager.get_state_info()
print(f"状态: {state_info.state}")
print(f"原因: {state_info.update_reason}")
```

**处理**：
1. 检查连接池状态
2. 如果是刷新中，等待刷新完成
3. 如果是已关闭，尝试重新打开
4. 如果无法恢复，执行回滚

#### 问题2：健康检查持续失败

**症状**：健康检查失败率持续高位

**诊断**：
```python
# 检查数据库连接
# 检查网络连接
# 检查数据库服务状态
```

**处理**：
1. 检查数据库服务是否正常
2. 检查网络连接是否稳定
3. 调整健康检查超时配置
4. 必要时重启数据库服务

#### 问题3：连接泄漏告警频繁

**症状**：频繁收到连接泄漏告警

**诊断**：
```python
from globalobjects.db_pool import EnhancedConnectionLeakDetector

detector = EnhancedConnectionLeakDetector()
result = detector.detect_leak("my_connection")
print(f"使用率: {result.usage_rate}")
print(f"趋势: {result.trend.trend_type}")
```

**处理**：
1. 分析泄漏检测结果
2. 检查业务代码是否有连接未释放
3. 调整告警阈值
4. 必要时增加连接池大小

#### 问题4：后台清理任务异常

**症状**：清理任务停止或异常

**诊断**：
```python
from globalobjects.db_pool import BackgroundCleanupTask

cleanup = BackgroundCleanupTask.get_instance()
status = cleanup.get_status()
print(f"运行状态: {status['is_running']}")
print(f"队列大小: {status['queue_size']}")
```

**处理**：
1. 检查清理任务状态
2. 重启清理任务
3. 检查待清理队列
4. 必要时手动清理

### 4.2 应急联系人

**技术负责人**：[姓名] - [电话] - [邮箱]
**运维负责人**：[姓名] - [电话] - [邮箱]
**业务负责人**：[姓名] - [电话] - [邮箱]

### 4.3 应急流程

1. **发现问题** → 记录问题详情
2. **初步诊断** → 确定问题类型和严重程度
3. **快速处理** → 尝试快速修复方案
4. **通知相关方** → 通知技术和业务负责人
5. **深入分析** → 分析根本原因
6. **彻底修复** → 实施彻底修复方案
7. **验证修复** → 验证问题已解决
8. **总结归档** → 记录问题和解决方案

## 5. 验收标准

### 5.1 功能验收

- [ ] 所有功能验证项通过
- [ ] 所有性能验证项通过
- [ ] 所有稳定性验证项通过
- [ ] 向后兼容性验证通过
- [ ] 无资源泄漏

### 5.2 监控验收

- [ ] 监控指标正常上报
- [ ] 告警规则正常触发
- [ ] 监控看板正常显示
- [ ] 日志正常输出

### 5.3 文档验收

- [ ] README文档完整
- [ ] 使用示例清晰
- [ ] 配置说明完整
- [ ] 故障排查指南有效

### 5.4 最终验收

- [ ] 灰度部署完成
- [ ] 所有租户正常运行
- [ ] 监控告警正常
- [ ] 性能指标达标
- [ ] 无资源泄漏
- [ ] 团队培训完成

---

**文档版本**：v1.0  
**创建时间**：2026-06-07  
**最后更新**：2026-06-07