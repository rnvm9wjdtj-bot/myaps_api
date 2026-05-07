# 部署脚本使用说明

## 1. 环境准备

1. **安装 Python 3.9+**
2. **安装 Nginx**（可选）：
   - 下载 Nginx for Windows
   - 解压到合适位置（如 `C:\nginx`）
3. **准备 NSSM**：
   - 确保 `nssm.exe` 位于项目根目录（与 `scripts` 同级）

## 2. 部署方式

### 2.1 傻瓜式部署（推荐）

#### 2.1.1 使用方法
1. **运行部署工具**：
   - 右键点击 `simple_deploy.bat`
   - 选择 "以管理员身份运行"
   - 按照界面提示进行操作

#### 2.1.2 主要功能
- **1. 安装服务**：自动检查环境、安装依赖、配置服务
- **2. 启动服务**：启动已安装的服务
- **3. 停止服务**：停止正在运行的服务
- **4. 重启服务**：重启服务
- **5. 卸载服务**：从系统中移除服务
- **6. 查看状态**：检查服务运行状态和配置
- **7. 检查环境**：检查系统环境和依赖
- **8. 清理日志**：清理旧的日志文件
- **9. 查看帮助**：显示使用说明
- **A. 健康检查**：执行 HTTP 健康检查，验证服务响应
- **B. 滚动更新**：优雅重启，最小化更新过程中的停机时间

### 2.2 传统部署方式

#### 2.2.1 安装依赖
```bash
# 安装项目依赖
pip install -r requirements.txt
```

#### 2.2.2 启动脚本
- **启动监听器**：`start_listener.bat`
- **启动应用**：`start_app.bat`
- **启动所有服务**：`start_all.bat`

## 3. 配置文件

### 3.1 Gunicorn 配置
- `gunicorn.conf.py`：Gunicorn 进程管理器配置
- `gunicorn_multiprocess.conf.py`：多进程模式配置（推荐）

### 3.2 Binlog 监听器
- `binlog_listener_service.py`：Binlog 监听器单进程控制

### 3.3 环境变量
- `.env.example`：环境变量配置示例
  - 复制为 `.env` 并填写实际配置
  - **关键配置项**：
    - `SERVICE_NAME`：Windows 服务名称
    - `PROTOCOL`：访问协议（http:// 或 https://）
    - `PORT`：服务端口
    - `PYTHON_VENV_DIR`：Python 虚拟环境目录
    - `LOG_RETENTION`：日志保留天数

### 3.4 健康检查脚本
- `check_health.bat`：HTTP 健康检查脚本
  - 自动检测服务状态
  - 多次重试验证服务响应
  - 异常时自动重启服务

### 3.5 滚动更新脚本
- `rolling_update.bat`：优雅重启脚本
  - 平滑停止服务，等待现有请求完成
  - 自动重启服务
  - 验证服务健康状态

### 3.6 服务守护脚本
- `service_daemon.ps1`：PowerShell 服务守护脚本（位于 `scripts` 目录）
  - 监控 Windows 服务状态
  - 检查日志文件健康
  - 自动重启异常服务
  - 支持邮件和系统通知

#### 3.6.1 功能说明

| 功能 | 说明 |
|------|------|
| 服务状态监控 | 检查服务是否正在运行 |
| 日志健康检查 | 检查 nssm_stderr.log 中的错误 |
| 自动重启 | 服务异常时自动尝试重启 |
| 邮件通知 | SMTP 配置后发送邮件告警 |
| 系统通知 | Windows 气泡通知提醒 |

#### 3.6.2 配置参数

在 `.env` 文件中配置以下参数：

```ini
# 服务配置
SERVICE_NAME=MyAPS_API           # Windows 服务名称
SERVICE_LOG_DIR=logs              # 日志目录

# 邮件通知配置
SERVICE_DAEMON_EMAIL_ENABLED=false       # 启用邮件通知
SERVICE_DAEMON_EMAIL_TO=admin@example.com  # 收件人（多个用逗号分隔）
SERVICE_DAEMON_EMAIL_FROM=noreply@example.com  # 发件人
SERVICE_DAEMON_SMTP_SERVER=smtp.example.com   # SMTP 服务器
SERVICE_DAEMON_SMTP_PORT=587            # SMTP 端口
SERVICE_DAEMON_SMTP_USER=user           # SMTP 用户名
SERVICE_DAEMON_SMTP_PASSWORD=password   # SMTP 密码

# 通知配置
SERVICE_DAEMON_SYSTEM_NOTIFICATION=true # 启用系统通知
SERVICE_DAEMON_AUTO_RESTART=true        # 自动重启异常服务
```

#### 3.6.3 使用方法

**方法一：手动运行测试**
```powershell
# 进入脚本目录
cd d:\code\myaps_fastapi\scripts

# 运行守护脚本
powershell.exe -ExecutionPolicy Bypass -File service_daemon.ps1

# 查看日志
Get-Content d:\code\myaps_fastapi\logs\service_daemon.log -Tail 20
```

**方法二：通过任务计划定期执行**

1. 打开"任务计划程序"
2. 创建基本任务：
   - 名称：`MyAPS_API_Daemon`
   - 触发器：每 5 分钟
3. 操作：启动程序
   - 程序：`powershell.exe`
   - 参数：`-ExecutionPolicy Bypass -NoProfile -File "d:\code\myaps_fastapi\scripts\service_daemon.ps1"`
4. 完成创建

#### 3.6.4 注意事项

- 邮件通知需要正确配置 SMTP 服务器和凭证
- 系统通知需要在有桌面交互的环境下运行
- 自动重启功能会在服务失败后尝试重启
- 建议配合 Windows 任务计划定期执行（建议每 5-10 分钟）

## 4. 部署流程

### 4.1 首次部署（使用傻瓜式工具）
1. 运行 `simple_deploy.bat`
2. 选择选项 1 "安装服务 (多进程模式)"
3. 等待脚本自动完成环境检查和依赖安装
4. 选择选项 2 "启动服务"
5. 选择选项 A "健康检查" 验证部署
6. 访问 `http://localhost:8000` 验证部署

### 4.2 首次部署（传统方式）
1. 准备环境（安装 Python、Nginx、依赖）
2. 配置 `.env` 文件
3. 启动 Nginx 服务（可选）
4. 运行 `start_all.bat` 脚本
5. 访问 `http://localhost` 验证部署

### 4.3 升级部署
1. 运行 `simple_deploy.bat`
2. 选择选项 3 "停止服务"（或选项 B "滚动更新"）
3. 更新代码
4. 选择选项 4 "重启服务"（或等待滚动更新完成）
5. 选择选项 A "健康检查" 验证升级

## 5. 技术特性

### 5.1 多进程部署
- **优势**：充分利用 CPU 资源，提高并发处理能力
- **配置**：自动根据 CPU 核心数调整进程数
- **默认**：`min(CPU核心数 * 2 + 1, 8)`

### 5.2 Binlog 监听器
- **单进程运行**：避免事件重复触发
- **自动重连**：连接断开后自动重试
- **位置持久化**：重启后从断点续传

### 5.3 服务管理
- **Windows 系统服务**：开机自启动
- **自动重启**：服务异常时自动重启
- **日志管理**：详细的日志记录和自动清理
- **健康检查**：HTTP 端点验证服务可用性
- **滚动更新**：优雅重启，最小化停机时间

### 5.4 动态配置
- **统一配置源**：所有脚本从 `.env` 读取配置
- **服务名称**：通过 `SERVICE_NAME` 配置
- **端口协议**：通过 `PROTOCOL` 和 `PORT` 动态拼接健康检查 URL

## 6. 注意事项

- 确保脚本以管理员权限运行
- 生产环境中修改默认密码
- 根据服务器配置调整 `gunicorn_multiprocess.conf.py` 中的 `workers` 参数
- 定期检查日志文件
- 首次运行会自动安装必要的依赖
- 所有配置修改后建议使用选项 A 进行健康检查

## 7. 故障排查

- **检查端口占用**：`netstat -ano | findstr :8000`
- **查看进程**：`tasklist | findstr python`
- **终止进程**：`taskkill /PID <进程ID> /F`
- **查看日志**：`logs/access.log` 和 `logs/error.log`
- **使用部署工具**：选择选项 7 "检查系统环境" 进行全面检查
- **健康检查失败**：运行选项 A "健康检查" 自动诊断和重启
- **服务异常**：检查 `logs/nssm_stdout.log` 和 `logs/nssm_stderr.log`

## 8. 部署方式对比

| 特性 | 傻瓜式部署 | 传统部署 |
|------|-----------|----------|
| 操作难度 | 低（图形界面） | 中（命令行） |
| 自动化程度 | 高（自动检查和安装） | 中（需要手动操作） |
| 多进程支持 | ✅ 内置支持 | ✅ 需要手动配置 |
| 服务管理 | ✅ 完整的服务生命周期管理 | ⚠️ 基本的启动停止 |
| 环境检查 | ✅ 自动检查 | ❌ 需要手动检查 |
| 健康检查 | ✅ 内置 HTTP 检查 | ❌ 无 |
| 滚动更新 | ✅ 优雅重启支持 | ❌ 无 |
| 适合人群 | 无IT基础用户 | 有一定技术基础用户 |

## 9. 系统要求

- **操作系统**：Windows 7+ / Windows Server 2008 R2+
- **Python**：3.9 或更高版本
- **内存**：至少 2GB（推荐 4GB+）
- **CPU**：至少 2 核心（推荐 4 核心+）
- **磁盘空间**：至少 500MB 可用空间
- **PowerShell**：5.0 或更高版本（用于服务守护脚本）

## 10. 无人值守建议

为确保服务稳定运行，建议：

1. **配置 Windows 任务计划**：
   - 定期运行 `check_health.bat`（建议每 5-10 分钟）
   - 定期运行 `simple_deploy.bat` 选项 8 清理日志（建议每天）

2. **启用服务守护脚本**：
   - 配置 `.env` 中的邮件通知设置
   - 通过任务计划定期运行 `service_daemon.ps1`

3. **监控系统资源**：
   - 定期检查 CPU、内存、磁盘使用情况
   - 确保有足够的可用资源