# 数据库初始化优化 TODO List

> 生成时间: 2026-05-20
> 目标: 解决 Tortoise ORM 初始化问题，确保数据库连接稳定

---

## P0 - 紧急 (导致所有数据库操作失败)

### TODO-001: Tortoise ORM 初始化未完成

**问题描述**:
- 错误: `RuntimeError: No TortoiseContext is currently active`
- 影响: 所有数据库操作失败

**问题位置**:
- `main.py:81` → `core/database.py:310-314`

**排查步骤**:
1. 检查 `register_tortoise()` 是否正确执行
2. 验证 `TORTOISE_ORM_CONFIG` 配置是否完整
3. 确认异步上下文是否正确

**解决方案**:
- [ ] 添加初始化日志，确认 `register_tortoise()` 执行时机
- [ ] 检查 FastAPI lifespan 与 Tortoise 的集成方式
- [ ] 考虑使用 `register_tortoise()` 的回调模式确保初始化完成

**验证方法**:
```python
# 在 register_database 后添加测试
from tortoise import Tortoise
assert Tortoise._inited, "Tortoise 未初始化"
```

---

## P1 - 高优先级

### TODO-002: 环境变量 THIS_DB_NAME 可能未正确加载

**问题描述**:
- 如果 `THIS_DB_NAME` 为空，PostgreSQL 连接不会被添加到配置中
- 导致 `Tortoise.get_connection(THIS_DB_NAME)` 失败

**问题位置**:
- `core/settings.py:170`
- `core/database.py:89`

**排查步骤**:
1. 检查 `.env` 文件中 `THIS_DB_NAME` 是否设置
2. 验证环境变量加载顺序
3. 添加默认值或错误提示

**解决方案**:
- [ ] 在 `core/database.py:89` 添加日志输出 `THIS_DB_NAME` 的值
- [ ] 如果为空，抛出明确的配置错误
- [ ] 考虑添加配置验证函数

**代码改进**:
```python
if not THIS_DB_NAME:
    raise ValueError("THIS_DB_NAME 环境变量未设置，请检查 .env 配置")
```

---

### TODO-003: register_tortoise 缺少关键参数

**问题描述**:
- `register_tortoise()` 调用时缺少可选参数
- 可能导致初始化不完整

**问题位置**:
- `core/database.py:310-314`

**当前代码**:
```python
register_tortoise(
    app=app,
    config=TORTOISE_ORM_CONFIG,
)
```

**解决方案**:
- [ ] 添加 `generate_schemas=False` (明确不自动生成表结构)
- [ ] 添加 `add_exception_handlers=True` (添加异常处理器)
- [ ] 添加 `_create_db=False` (不自动创建数据库)

**改进代码**:
```python
register_tortoise(
    app=app,
    config=TORTOISE_ORM_CONFIG,
    generate_schemas=False,
    add_exception_handlers=True,
)
```

---

### TODO-004: 数据库模型注册验证

**问题描述**:
- 模型路径或连接名称可能配置错误
- 导致模型无法正确映射到数据库连接

**问题位置**:
- `core/database.py:104-107`

**当前配置**:
```python
TORTOISE_ORM_CONFIG["apps"]["data_opt_models"] = {
    "models": ["apps.data_opt.mds.staging_models"],
    "default_connection": THIS_DB_NAME,
}
```

**排查步骤**:
1. 验证模型路径是否正确
2. 确认 `THIS_DB_NAME` 与 `connections` 字典中的键匹配
3. 检查模型是否能正确导入

**解决方案**:
- [ ] 添加模型导入验证
- [ ] 添加连接名称匹配验证
- [ ] 输出完整的 TORTOISE_ORM_CONFIG 供调试

---

## P2 - 中优先级

### TODO-005: PostgreSQL 连接缺少超时配置

**问题描述**:
- PostgreSQL 连接配置缺少 `connect_timeout`
- 可能导致连接建立缓慢或挂起

**问题位置**:
- `core/database.py:89-103`

**当前配置**:
```python
connections[THIS_DB_NAME] = {
    "engine": "tortoise.backends.asyncpg",
    "credentials": {
        "host": THIS_DB_HOST,
        "port": THIS_DB_PORT,
        "user": THIS_DB_USER,
        "password": THIS_DB_PASSWORD,
        "database": THIS_DB_NAME,
        "server_settings": {"TimeZone": TIMEZONE_NAME},
    },
    "min_size": 3,
    "max_size": 10,
    "use_tz": True,
}
```

**解决方案**:
- [ ] 添加 `connect_timeout` 参数 (建议 30 秒)
- [ ] 添加 `command_timeout` 参数 (建议 60 秒)

**改进代码**:
```python
connections[THIS_DB_NAME] = {
    "engine": "tortoise.backends.asyncpg",
    "credentials": {
        "host": THIS_DB_HOST,
        "port": THIS_DB_PORT,
        "user": THIS_DB_USER,
        "password": THIS_DB_PASSWORD,
        "database": THIS_DB_NAME,
        "server_settings": {"TimeZone": TIMEZONE_NAME},
        "command_timeout": 60,
    },
    "min_size": 3,
    "max_size": 10,
    "use_tz": True,
}
# 注意: asyncpg 的 timeout 在 credentials 中
```

---

### TODO-006: 数据库操作缺少异常处理

**问题描述**:
- 获取数据库连接时无异常处理
- 一旦 Tortoise 未初始化直接崩溃

**问题位置**:
- `apps/data_opt/mds/staging_routers.py:728-729`

**当前代码**:
```python
conn = Tortoise.get_connection(THIS_DB_NAME)
```

**解决方案**:
- [ ] 添加 try-catch 保护
- [ ] 提供友好的错误提示
- [ ] 记录详细的错误日志

**改进代码**:
```python
try:
    conn = Tortoise.get_connection(THIS_DB_NAME)
except Exception as e:
    logger.error(f"获取数据库连接失败: {e}")
    raise HTTPException(
        status_code=500,
        detail="数据库连接失败，请检查服务配置或稍后重试"
    )
```

---

### TODO-007: lifespan 与 register_tortoise 的交互问题

**问题描述**:
- `lifespan` 在 `register_database` 之前就关联到 app
- 可能导致初始化时序问题

**问题位置**:
- `main.py:31` (create_app)
- `main.py:81` (register_database)

**当前顺序**:
```python
app = create_app(lifespan=lifespan)  # 第31行
# ... 其他初始化 ...
register_database(app)               # 第81行
```

**排查步骤**:
1. 理解 `register_tortoise` 的初始化时机
2. 确认 lifespan 启动时数据库是否已就绪
3. 检查是否有竞态条件

**解决方案**:
- [ ] 考虑将 `register_database` 移到 `create_app` 内部
- [ ] 或在 lifespan 的 startup 阶段添加数据库就绪检查
- [ ] 添加初始化状态标志

---

## P3 - 低优先级

### TODO-008: MySQL 数据库连接超时 (非阻塞)

**问题描述**:
- MySQL 数据库 `hacy_p` 连接失败
- 但这是警告，不影响 PostgreSQL 连接

**日志信息**:
```
数据库连接健康检查超时: hacy_p
连接预热超时: hacy_p，跳过预热
```

**解决方案**:
- [ ] 检查 MySQL 数据库配置是否正确
- [ ] 添加更友好的警告提示
- [ ] 考虑是否需要 MySQL 连接 (如果不使用可禁用)

---

### TODO-009: 添加数据库连接状态检查端点

**问题描述**:
- 缺少专门的数据库健康检查 API
- 难以快速判断数据库连接状态

**解决方案**:
- [ ] 添加 `/health/database` 端点
- [ ] 返回所有数据库连接状态
- [ ] 包含连接池使用情况

**示例代码**:
```python
@router.get("/health/database")
async def check_database_health():
    from tortoise import Tortoise
    results = {}
    for db_name in Tortoise._connections:
        try:
            conn = Tortoise.get_connection(db_name)
            await conn.execute_query("SELECT 1")
            results[db_name] = {"status": "healthy"}
        except Exception as e:
            results[db_name] = {"status": "unhealthy", "error": str(e)}
    return results
```

---

### TODO-010: 添加配置验证函数

**问题描述**:
- 数据库配置分散在多处
- 缺少统一的验证机制

**解决方案**:
- [ ] 创建 `validate_database_config()` 函数
- [ ] 在应用启动时调用
- [ ] 输出配置摘要供调试

**示例代码**:
```python
def validate_database_config():
    """验证数据库配置"""
    issues = []
    
    if not THIS_DB_NAME:
        issues.append("THIS_DB_NAME 未设置")
    
    if THIS_DB_NAME and THIS_DB_NAME not in connections:
        issues.append(f"{THIS_DB_NAME} 未在 connections 中配置")
    
    if issues:
        raise ValueError("数据库配置错误:\n" + "\n".join(issues))
    
    logger.info("数据库配置验证通过")
```

---

## 执行计划

### 阶段1: 紧急修复 (立即执行)
1. [ ] TODO-001: Tortoise 初始化问题
2. [ ] TODO-002: 环境变量验证
3. [ ] TODO-003: register_tortoise 参数

### 阶段2: 稳定性优化 (本周内)
4. [ ] TODO-004: 模型注册验证
5. [ ] TODO-005: PostgreSQL 超时配置
6. [ ] TODO-006: 异常处理

### 阶段3: 架构优化 (下周)
7. [ ] TODO-007: lifespan 集成
8. [ ] TODO-008: MySQL 连接处理
9. [ ] TODO-009: 健康检查端点
10. [ ] TODO-010: 配置验证

---

## 调试命令

### 检查环境变量
```bash
cat .env | grep -E "THIS_DB_|MYAPS_DB"
```

### 测试数据库连接
```bash
# PostgreSQL
PGPASSWORD=123456 psql -h 129.211.172.205 -p 5432 -U n8n -d appsmith -c "SELECT 1"

# MySQL (如果使用)
mysql -h <host> -P <port> -u <user> -p<password> -e "SELECT 1"
```

### 检查 Tortoise 初始化
```python
# 在应用启动后执行
from tortoise import Tortoise
print(f"Tortoise initialized: {Tortoise._inited}")
print(f"Connections: {list(Tortoise._connections.keys())}")
```

---

## 参考资料

- [Tortoise ORM 官方文档](https://tortoise.github.io/tortoise-orm/)
- [FastAPI 生命周期事件](https://fastapi.tiangolo.com/advanced/events/)
- [asyncpg 连接参数](https://magicstack.github.io/asyncpg/current/api/index.html#connection)

---

## 变更记录

| 日期 | 操作 | 说明 |
|------|------|------|
| 2026-05-20 | 创建 | 初始化数据库优化 TODO List |
