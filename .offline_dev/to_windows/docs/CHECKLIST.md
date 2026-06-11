# MyAPS API - 离线迁移检查清单

> 在迁移的各个阶段使用此清单确认每一步是否完成。

---

## 第一阶段：外网机器准备（有外网环境）

### 环境检查

- [ ] 外网机器可正常访问互联网
- [ ] Python 3.11 或 3.12 已安装
- [ ] pip 已更新到最新版本 (`python -m pip install --upgrade pip`)
- [ ] 磁盘空间 >= 2GB

### 下载离线包

- [ ] 项目代码完整（包含 `requirements.txt` 和 `.env.example`）
- [ ] 执行下载脚本成功：
  - Linux/macOS: `bash .offline_dev/scripts/download_packages.sh`
  - Windows: `powershell .offline_dev/scripts/download_packages.ps1`
- [ ] `.offline_dev/packages/` 目录生成
- [ ] 包清单文件 `MANIFEST.txt` 已生成
- [ ] 下载日志 `download.log` 无严重错误
- [ ] 关键包已下载（检查是否存在）：
  - [ ] fastapi
  - [ ] uvicorn
  - [ ] tortoise-orm
  - [ ] pydantic
  - [ ] pandas
  - [ ] redis
  - [ ] aiomysql
  - [ ] asyncpg

### 打包传输

- [ ] 整个 `myaps_api/` 项目目录已打包
- [ ] 打包文件大小合理（通常 200MB-1GB）
- [ ] 通过安全方式传输到内网（U盘/光盘/网闸）
- [ ] 内网机器已收到完整文件
- [ ] 文件完整性校验通过（如有校验和）

---

## 第二阶段：内网机器部署（无外网环境）

### 环境准备

- [ ] Windows 10/11 或 Windows Server 2019+
- [ ] Python 3.11 或 3.12 已安装（版本与外网一致）
- [ ] Python 已添加到系统 PATH
- [ ] 验证：`python --version` 显示正确版本
- [ ] 验证：`pip --version` 正常工作
- [ ] 磁盘空间 >= 5GB

### 数据库服务

- [ ] MySQL 服务已安装并运行
- [ ] MySQL 数据库已创建（根据 `MYAPS_DB_SET` 配置）
- [ ] MySQL 用户已创建并授权
- [ ] PostgreSQL 服务已安装并运行（如使用 Staging 功能）
- [ ] PostgreSQL 数据库已创建
- [ ] Redis 服务已安装并运行
- [ ] 防火墙已放行相关端口

### 项目部署

- [ ] 项目文件解压到目标目录（如 `D:\myaps_api`）
- [ ] 目录结构完整，无文件缺失
- [ ] 执行安装脚本：`.offline_dev\scripts\install_packages.bat`
- [ ] 虚拟环境 `venv` 创建成功
- [ ] pip 升级成功
- [ ] 所有依赖安装成功（无 ERROR）
- [ ] 关键包验证通过：
  - [ ] fastapi
  - [ ] uvicorn
  - [ ] tortoise-orm
  - [ ] pydantic
  - [ ] pandas
  - [ ] redis

### 环境配置

- [ ] `.env` 文件已创建（从 `.env.example` 复制）
- [ ] `MYAPS_DB_HOST` 配置为内网 MySQL 地址
- [ ] `MYAPS_DB_PORT` 配置正确
- [ ] `MYAPS_DB_USER` 配置正确
- [ ] `MYAPS_DB_PASSWORD` 配置正确
- [ ] `MYAPS_DB_SET` 配置为实际数据库列表
- [ ] `MYAPS_MAIN_DB` 配置正确
- [ ] `THIS_DB_HOST` 配置为内网 PostgreSQL 地址（如使用）
- [ ] `REDIS_HOST` 配置为内网 Redis 地址
- [ ] `PROJECT_DIR` 配置为实际租户目录
- [ ] `PROJECT_JSON` 配置正确

### 服务启动

- [ ] 端口 8000 未被占用（或已配置其他端口）
- [ ] 执行启动命令成功：
  - [ ] `scripts\dev_server.bat start` 或
  - [ ] `venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000`
- [ ] 控制台无严重错误输出
- [ ] 进程在任务管理器中可见

### 功能验证

- [ ] API 文档可访问：http://localhost:8000/docs
- [ ] API 文档可访问：http://localhost:8000/redoc
- [ ] 健康检查接口正常（如有配置）
- [ ] 日志文件正常生成（`logs/` 目录）
- [ ] 数据库连接正常（无连接错误日志）
- [ ] Redis 连接正常
- [ ] 前端静态资源可访问

### 测试验证（可选）

- [ ] 运行单元测试：`venv\Scripts\python.exe -m pytest tests/ -v`
- [ ] 测试通过率 > 90%
- [ ] 核心功能测试通过

---

## 第三阶段：生产部署（可选）

### Windows 服务

- [ ] 以管理员身份运行部署脚本
- [ ] NSSM 工具可用（`scripts\nssm.exe`）
- [ ] 服务安装成功：`scripts\deploy\simple_deploy.bat`
- [ ] 服务可在服务管理器中查看
- [ ] 服务可正常启动
- [ ] 服务可正常停止
- [ ] 服务异常时可自动重启
- [ ] 服务日志正常输出

### 性能检查

- [ ] 内存占用正常（< 2GB）
- [ ] CPU 占用正常（空闲时 < 10%）
- [ ] 响应时间正常（< 200ms）

---

## 问题记录

| 序号 | 问题描述 | 发生阶段 | 解决方案 | 状态 |
|------|----------|----------|----------|------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

---

## 迁移完成确认

- [ ] 所有检查项已完成
- [ ] 问题记录已填写（如有）
- [ ] 迁移文档已归档
- [ ] 相关人员已通知

**迁移负责人签名**: _______________  **日期**: _______________

**验证人签名**: _______________  **日期**: _______________
