# 数据库连接池管理脚本

本目录包含数据库连接池管理的辅助工具脚本。

## 脚本列表

### 1. db_pool_manager.py - 连接池管理工具

**用途**：提供命令行界面来管理连接池监控

**使用方式**：
```bash
# 启动连接池监控
python scripts/db_pool/db_pool_manager.py start

# 停止连接池监控
python scripts/db_pool/db_pool_manager.py stop

# 查看监控状态
python scripts/db_pool/db_pool_manager.py status

# 检查指定连接的健康状态
python scripts/db_pool/db_pool_manager.py check db1

# 检测指定连接的泄漏情况
python scripts/db_pool/db_pool_manager.py leak db1
```

**功能说明**：

- `start`：启动连接池监控任务，自动监控所有配置的数据库连接
- `stop`：停止连接池监控任务
- `status`：显示当前监控状态，包括运行状态、监控间隔、队列大小等
- `check <connection_name>`：检查指定连接的健康状态和连接池状态
- `leak <connection_name>`：检测指定连接的泄漏情况和使用趋势

**应用场景**：
- 运维人员手动启动/停止监控
- 查看实时监控状态
- 快速检查连接健康
- 手动触发泄漏检测

### 2. verify_db_pool.py - 安装验证脚本

**用途**：验证连接池管理功能是否正确安装和配置

**使用方式**：
```bash
python scripts/db_pool/verify_db_pool.py
```

**检查项目**：

1. **文件完整性检查**
   - 检查12个核心文件是否存在
   - 包括：数据模型、异常类、核心组件、监控任务等

2. **模块导入检查**
   - 验证所有组件能否正常导入
   - 检查依赖是否满足

3. **配置检查**
   - 验证配置参数是否正确
   - 显示当前配置值

4. **集成检查**
   - 检查是否已集成到DbManager
   - 验证功能开关状态

5. **环境变量检查**
   - 检查环境变量是否设置
   - 显示未设置项的默认值

**输出示例**：
```
============================================================
数据库连接池管理验证
============================================================

检查文件...
✅ __init__.py
✅ README.md
✅ examples.py
...

检查导入...
✅ 数据模型导入成功
✅ 异常类导入成功
✅ 核心组件导入成功
...

============================================================
验证结果总结
============================================================
文件检查: ✅ 通过
导入检查: ✅ 通过
配置检查: ✅ 通过
集成检查: ✅ 通过
环境变量检查: ✅ 通过
============================================================

🎉 所有检查通过！连接池管理功能已正确安装。
```

**应用场景**：
- 部署后验证安装是否成功
- 故障排查时检查配置
- 升级后验证兼容性
- CI/CD流程中的自动化验证

## 快速开始

### 1. 验证安装

```bash
# 运行验证脚本
python scripts/db_pool/verify_db_pool.py
```

### 2. 启动监控

```bash
# 启动连接池监控
python scripts/db_pool/db_pool_manager.py start

# 查看监控状态
python scripts/db_pool/db_pool_manager.py status
```

### 3. 检查连接

```bash
# 检查指定连接的健康状态
python scripts/db_pool/db_pool_manager.py check db1

# 检测连接泄漏
python scripts/db_pool/db_pool_manager.py leak db1
```

## 注意事项

1. **运行环境**：
   - 确保在项目根目录运行脚本
   - 确保已安装所有依赖（pydantic、tortoise-orm等）

2. **权限要求**：
   - 需要有读取项目文件的权限
   - 需要有访问数据库的权限（用于健康检查）

3. **配置要求**：
   - 确保`.env`文件已正确配置
   - 确保`MYAPS_DBSET_LIST`已设置

4. **监控任务**：
   - 监控任务通常由应用启动时自动启动
   - 手动启动仅用于测试或特殊场景

## 故障排查

### 问题1：导入失败

**症状**：运行脚本时提示"No module named 'xxx'"

**解决**：
```bash
# 安装缺失的依赖
pip install pydantic tortoise-orm
```

### 问题2：找不到配置

**症状**：提示"未找到要监控的数据库连接"

**解决**：
```bash
# 检查.env配置
grep MYAPS_DBSET_LIST .env

# 如果未设置，添加配置
echo "MYAPS_DBSET_LIST=db1,db2,db3" >> .env
```

### 问题3：权限不足

**症状**：提示"Permission denied"

**解决**：
```bash
# 添加执行权限
chmod +x scripts/db_pool/db_pool_manager.py
chmod +x scripts/db_pool/verify_db_pool.py
```

## 相关文档

- 模块文档：`globalobjects/db_pool/README.md`
- 使用示例：`globalobjects/db_pool/examples.py`
- 部署指南：`docs/db_pool_deployment_guide.md`
- 实施总结：`docs/db_pool_implementation_summary.md`