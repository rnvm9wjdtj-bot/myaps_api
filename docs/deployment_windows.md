# FastAPI 项目 Windows 部署文档

## 1. 项目依赖分析

根据 `requirements.txt`，项目已包含以下关键依赖：

| 类别 | 依赖包 | 版本 | 用途 |
|------|--------|------|------|
| 核心框架 | fastapi | >=0.110.0 | Web 框架 |
| 服务器 | uvicorn[standard] | >=0.29.0 | ASGI 服务器 |
| 数据库 | tortoise-orm | >=0.25.1 | ORM 框架 |
| 数据库 | aiomysql | >=0.2.0 | MySQL 异步驱动 |
| 数据库 | mysql_replication | >=1.0.9 | Binlog 监听 |
| HTTP 客户端 | requests | >=2.32.5 | 同步 HTTP 请求 |
| HTTP 客户端 | httpx | - | 异步 HTTP 客户端 |
| 缓存 | redis | >=7.0.0 | 分布式缓存 |
| 工具 | python-dotenv | >=1.0.0 | 环境变量管理 |
| 工具 | apscheduler | >=3.11.1 | 任务调度 |

**缺失依赖**：
- `gunicorn` - 进程管理器，用于多进程部署

## 2. 部署架构

采用 **Nginx + Gunicorn + Uvicorn** 架构：

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nginx     │────>│  Gunicorn   │────>│  Uvicorn    │
│ 反向代理    │     │ 进程管理器  │     │ ASGI服务器  │
└─────────────┘     └─────────────┘     └─────────────┘
                                          │
                                          ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Binlog监听  │<────│  应用代码   │<────│  业务逻辑   │
│ 单进程运行  │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
```

## 3. 详细部署步骤

### 3.1 环境准备

1. **安装 Python**
   - 下载并安装 Python 3.9+（推荐 3.10）
   - 确保添加 Python 到系统环境变量

2. **安装依赖**
   ```bash
   # 安装 gunicorn（缺失依赖）
   pip install gunicorn
   
   # 安装项目依赖
   pip install -r requirements.txt
   ```

3. **安装 Nginx**
   - 下载 Nginx for Windows
   - 解压到合适位置（如 `C:\nginx`）
   - 启动 Nginx 服务

### 3.2 配置文件准备

#### 3.2.1 Gunicorn 配置

创建 `gunicorn.conf.py` 文件：

```python
# gunicorn.conf.py
import os
import multiprocessing

# 进程数
workers = min(multiprocessing.cpu_count(), 4)
worker_class = "uvicorn.workers.UvicornWorker"
bind = "127.0.0.1:8000"
timeout = 30

# 日志配置
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# 确保日志目录存在
if not os.path.exists("logs"):
    os.makedirs("logs")
```

#### 3.2.2 Nginx 配置

修改 `nginx.conf` 文件：

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    server {
        listen 80;
        server_name localhost;
        
        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
}
```

#### 3.2.3 Binlog 监听器单进程控制

创建 `binlog_listener_service.py` 文件：

```python
# binlog_listener_service.py
import os
import sys
import time
import psutil

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apps.data_opt.utils.binlog_listener import binlog_listener

def is_process_running(process_name):
    """检查进程是否在运行"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if process_name in ' '.join(proc.info['cmdline']):
                return True
        except:
            pass
    return False

def main():
    # 检查是否已有监听器进程在运行
    if is_process_running("binlog_listener_service.py"):
        print("Binlog listener is already running.")
        return
    
    try:
        # 启动监听器
        print("Starting binlog listener...")
        binlog_listener.start()
    except KeyboardInterrupt:
        print("Stopping binlog listener...")
    except Exception as e:
        print(f"Error starting binlog listener: {e}")

if __name__ == "__main__":
    main()
```

### 3.3 启动脚本

#### 3.3.1 启动监听器

创建 `start_listener.bat` 文件：

```batch
@echo off
echo Starting binlog listener...
python binlog_listener_service.py
```

#### 3.3.2 启动应用

创建 `start_app.bat` 文件：

```batch
@echo off
echo Starting FastAPI application...
gunicorn -c gunicorn.conf.py main:app
```

#### 3.3.3 完整启动脚本

创建 `start_all.bat` 文件：

```batch
@echo off
echo Starting all services...

REM 启动 binlog 监听器
start /b python binlog_listener_service.py

REM 等待监听器启动
timeout /t 5

REM 启动应用
gunicorn -c gunicorn.conf.py main:app
```

### 3.4 配置环境变量

创建 `.env` 文件：

```dotenv
# 数据库配置
DATABASE_URL=mysql://username:password@localhost:3306/database

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# 应用配置
APP_NAME=MyAPS
APP_VERSION=1.0.0
DEBUG=False

# Binlog 监听配置
BINLOG_HOST=localhost
BINLOG_PORT=3306
BINLOG_USER=username
BINLOG_PASSWORD=password
```

## 4. 部署流程

### 4.1 首次部署

1. **准备环境**
   - 安装 Python、Nginx
   - 安装依赖包

2. **配置文件**
   - 创建 `gunicorn.conf.py`
   - 配置 `nginx.conf`
   - 创建 `binlog_listener_service.py`
   - 创建 `.env` 文件

3. **启动服务**
   - 启动 Nginx 服务
   - 运行 `start_all.bat` 脚本

4. **验证部署**
   - 访问 `http://localhost` 查看应用
   - 检查日志文件确认服务正常运行
   - 测试 binlog 监听是否正常

### 4.2 升级部署

1. **停止服务**
   - 停止 Nginx 服务
   - 停止应用进程
   - 停止 binlog 监听器

2. **更新代码**
   - 拉取最新代码
   - 更新依赖（如需要）

3. **重启服务**
   - 运行 `start_all.bat` 脚本
   - 启动 Nginx 服务

4. **验证升级**
   - 测试应用功能
   - 检查日志确认无错误

## 5. 故障排查

### 5.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| Binlog 监听器启动失败 | 数据库连接错误 | 检查数据库配置和 binlog 开启状态 |
| 应用启动失败 | 端口被占用 | 检查 8000 端口是否被占用 |
| 事件重复处理 | 监听器多进程运行 | 确保 `binlog_listener_service.py` 正常工作 |
| 性能问题 | 进程数不合理 | 调整 `gunicorn.conf.py` 中的 `workers` 参数 |
| 内存占用高 | 进程数过多 | 减少 `workers` 数量，增加服务器内存 |

### 5.2 日志检查

1. **应用日志**：`logs/access.log` 和 `logs/error.log`
2. **Nginx 日志**：`nginx/logs/access.log` 和 `nginx/logs/error.log`
3. **监听器日志**：检查应用日志中的监听器相关信息

### 5.3 调试命令

```bash
# 检查端口占用
netstat -ano | findstr :8000

# 查看进程
tasklist | findstr python

# 终止进程
taskkill /PID <进程ID> /F
```

## 6. 注意事项

1. **权限问题**
   - 确保脚本以管理员权限运行
   - 确保目录权限正确

2. **安全配置**
   - 生产环境中修改默认密码
   - 配置防火墙规则
   - 启用 HTTPS（可选）

3. **性能优化**
   - 根据服务器配置调整 `workers` 数量
   - 配置 Redis 缓存提高性能
   - 优化数据库连接池

4. **监控管理**
   - 定期检查日志文件
   - 监控服务器资源使用情况
   - 考虑使用监控工具（如 Prometheus）

5. **备份策略**
   - 定期备份数据库
   - 备份配置文件
   - 建立灾难恢复计划

## 7. 维护建议

1. **定期更新**
   - 定期更新依赖包
   - 关注安全漏洞补丁

2. **性能监控**
   - 监控响应时间
   - 监控数据库性能
   - 监控服务器资源使用

3. **故障演练**
   - 定期进行故障演练
   - 测试备份恢复流程
   - 确保高可用性

4. **文档更新**
   - 及时更新部署文档
   - 记录配置变更
   - 保持文档与实际部署一致