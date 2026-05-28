# MyAPS API Docker 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose V2
- Python 3.12（镜像内置）
- PostgreSQL 15+（服务自有数据库）
- Redis 7+（事件总线）

---

## 快速开始

```bash
# 1. 配置环境变量（编辑.env文件）
vim .env
# 确保以下变量已正确配置：
# - PROJECT_DIR=HACYXS        # 项目目录
# - PROJECT_JSON=dev          # 配置文件名
# - THIS_DB_*                 # 数据库连接信息（本地用localhost）
# - REDIS_HOST=localhost      # Redis连接信息

# 2. 部署服务（从Docker Hub拉取，统一使用host网络模式）
DOCKER_IMAGE=qsct/myaps-api:master docker-compose up -d

# 3. 验证部署
curl http://localhost:8000/
docker ps | grep myaps
```

---

## 部署方式

### 方式一：Docker Compose 部署（推荐）

#### 1. 配置 GitHub Secrets

在GitHub仓库中配置以下Secrets（Settings → Secrets and variables → Actions）：

| Secret名称 | 说明 | 示例值 |
|-----------|------|--------|
| `DOCKER_USERNAME` | Docker Hub用户名 | `qsct` |
| `DOCKER_PASSWORD` | Docker Hub访问令牌（非密码） | `dckr_pat_xxxx` |

**获取Docker Hub访问令牌：**
1. 登录 Docker Hub → Account Settings → Security → Personal access tokens
2. 点击 "Generate new token"
3. **权限必须勾选：Read, Write, Delete**
4. 复制生成的令牌（只显示一次）

#### 2. 触发 CI/CD 构建

```bash
# 推送代码到master分支触发自动构建
git push origin master

# 或在GitHub Actions页面手动触发
```

#### 3. 部署服务

```bash
# 从Docker Hub拉取并部署
DOCKER_IMAGE=qsct/myaps-api:master docker-compose up -d

# 或本地构建后部署
docker-compose up -d --build

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

**镜像选择说明：**
- 默认使用本地镜像 `myaps_api:latest`
- 通过 `DOCKER_IMAGE` 环境变量指定Docker Hub镜像
- 自动读取 `.env` 中的 `PROJECT_DIR`，挂载对应配置目录

#### 4. 使用 docker run 部署（可选）

```bash
# 拉取镜像
docker pull qsct/myaps-api:master

# 启动Redis（host网络模式）
docker run -d \
  --name myaps_redis \
  --network host \
  -v redis_data:/data \
  redis:7-alpine \
  redis-server --appendonly yes

# 启动App（host网络模式）
docker run -d \
  --name myaps-api \
  --network host \
  -v /opt/myaps_api/myaps_api/project_files/${PROJECT_DIR}:/app/project_files/${PROJECT_DIR} \
  -v /opt/myaps_api/myaps_api/logs:/app/logs \
  -v /opt/myaps_api/myaps_api/storage:/app/storage \
  -v /opt/myaps_api/myaps_api/static:/app/static \
  -e PORT=8000 \
  -e REDIS_HOST=localhost \
  --env-file /opt/myaps_api/myaps_api/.env \
  --entrypoint gunicorn \
  qsct/myaps-api:master \
  -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 main:app
```

#### 5. 验证部署

```bash
# 检查容器状态
docker ps | grep myaps-api

# 验证API可访问
curl http://localhost:8000/

# 访问API文档
# http://localhost:8000/docs
```

---

## 配置文件挂载

### 自动挂载机制

Docker Compose 自动根据 `.env` 中的 `PROJECT_DIR` 挂载配置目录：

```yaml
# docker-compose.yml
volumes:
  - ./project_files/${PROJECT_DIR}:/app/project_files/${PROJECT_DIR}
```

**示例：** 当 `PROJECT_DIR=HACYXS` 时，挂载：
- `project_files/HACYXS/` 整个目录

### 敏感文件说明

以下文件因包含敏感信息，已被 `.gitignore` 排除，需通过挂载注入：

```
project_files/{PROJECT_DIR}/
├── {PROJECT_JSON}.json    # 租户配置（数据库连接等）
└── remind.py              # 告警配置（SMTP密码）
```

**Git托管文件（覆盖无影响）：**
- `client.py` - 客户端代码
- 其他非敏感文件

### 环境变量配置

在 `.env` 中配置：

```ini
# 项目配置
PROJECT_DIR=HACYXS        # 项目目录名
PROJECT_JSON=dev          # 配置文件名（不含扩展名）

# 数据库配置
THIS_DB_HOST=localhost
THIS_DB_PORT=5432
THIS_DB_USER=myaps_user
THIS_DB_PASSWORD=your_password
THIS_DB_NAME=myaps_db

# Redis配置
REDIS_PORT=6379
REDIS_PASSWORD=
```

---

## 辅助脚本

```bash
cd scripts/deploy_docker

./build.sh              # 构建镜像 (默认 latest)
./build.sh v1.0         # 构建指定版本

./start.sh              # 启动服务
./stop.sh               # 停止服务
./restart.sh            # 重启服务
./status.sh             # 查看状态

./export_image.sh       # 导出镜像 (离线部署用)
./import_image.sh       # 导入镜像

./setup_kuma_monitors.sh    # 配置Uptime Kuma监控项
```

### 监控配置脚本

`setup_kuma_monitors.sh` 用于一键配置 Uptime Kuma 监控项，所有配置从 `.env` 文件读取。

**使用方法：**

```bash
# 查看帮助信息
./setup_kuma_monitors.sh --help

# 查看监控配置列表
./setup_kuma_monitors.sh --list

# 执行监控配置（幂等操作，可重复执行）
./setup_kuma_monitors.sh

# 模拟执行（不实际操作）
./setup_kuma_monitors.sh --dry-run

# 指定容器名称
./setup_kuma_monitors.sh --container my_uptime_kuma
```

**配置选项：**

| 选项 | 说明 |
|-----|------|
| `-h, --help` | 显示帮助信息 |
| `-l, --list` | 显示监控配置列表 |
| `-n, --dry-run` | 模拟执行，不实际操作 |
| `-c, --container` | 指定 Uptime Kuma 容器名称 |

**监控项列表（自动从 .env 读取配置）：**

| 监控项 | 类型 | 配置来源 |
|--------|------|---------|
| MyAPI服务 | HTTP | `PORT` |
| Redis | Port | `REDIS_PORT` |
| PostgreSQL | Port | `THIS_DB_PORT` |
| Portainer | HTTP | `PORTAINER_PORT` |
| Binlog监听器 | HTTP | `PORT` |
| Uptime Kuma | HTTP | `UPTIME_KUMA_PORT` |
| MyAPS数据库 | Port | `MYAPS_DB_HOST:MYAPS_DB_PORT` |

**环境变量配置：**

在 `.env` 文件中配置以下变量：

```ini
# 应用端口
PORT=8000

# 数据库端口
THIS_DB_PORT=5432
MYAPS_DB_HOST=1.13.184.21
MYAPS_DB_PORT=3333

# Redis端口
REDIS_PORT=6379

# 监控服务端口
UPTIME_KUMA_PORT=3001
PORTAINER_PORT=9000
PORTAINER_TUNNEL_PORT=9001
```

**执行示例：**

```bash
$ ./setup_kuma_monitors.sh
==============================================
  Uptime Kuma 监控配置一键安装脚本
==============================================

🔍 检查Uptime Kuma容器状态...
✅ 容器 myaps_uptime_kuma 运行正常

📝 生成SQL脚本...
✅ SQL脚本生成成功

📤 复制SQL脚本到容器...
✅ SQL脚本已复制到容器

⚙️  在容器内执行SQL导入...
本次执行添加 7 条监控记录
✅ SQL导入成功

🧹 清理临时文件...
✅ 清理完成

📊 检查监控配置...
✅ 当前监控数量: 7 个

==============================================
🎉 监控配置导入完成！
==============================================

💡 访问地址: http://localhost:3001
   查看已添加的7个监控项
```

> **注意**：脚本具有幂等性，重复执行不会产生重复监控项。

---

## 数据库配置
| `PROJECT_JSON` | 配置文件名（不含扩展名） | `dev` |

**需要挂载的文件列表：**

```
project_files/
└── {PROJECT_DIR}/              # 如 HACYXS/
    ├── {PROJECT_JSON}.json     # 如 dev.json（租户配置）
    └── remind.py               # 固定文件名（告警配置）
```

**示例：** 当 `PROJECT_DIR=HACYXS`，`PROJECT_JSON=dev` 时，需要挂载：
- `project_files/HACYXS/dev.json` - 租户配置文件
- `project_files/HACYXS/remind.py` - 告警邮件配置（SMTP密码等）

### 解决方案

**方案一：运行时挂载（推荐）**

将本地 `project_files` 目录挂载到容器中：

```bash
-v /opt/myaps_api/myaps_api/project_files:/app/project_files
```

**优点：**
- 敏感数据不进入镜像
- 不提交到GitHub仓库
- 可随时修改配置无需重新构建镜像

**方案二：环境变量注入**

修改代码，从环境变量读取敏感配置：

```python
# remind.py
import os

ops_reminder = QqEmailReminder(
    smtp_user=os.getenv("SMTP_USER"),
    smtp_password=os.getenv("SMTP_PASSWORD"),
    # ...
)
```

---

## 网络模式

当前配置统一使用 **Host模式**：

```yaml
services:
  redis:
    network_mode: host
    
  app:
    network_mode: host
```

### Host模式特点

| 特点 | 说明 |
|-----|------|
| **网络栈共享** | 容器直接使用宿主机网络 |
| **localhost访问** | 容器内localhost指向宿主机 |
| **性能最优** | 无NAT转换，网络延迟最低 |
| **配置简单** | 无需端口映射和容器名解析 |

### 访问路径

```
宿主机网络栈
├── Redis容器 → localhost:6379
├── App容器 → localhost:8000
└── PostgreSQL → localhost:5432
```

### 环境变量配置

```ini
# .env 配置示例
REDIS_HOST=localhost          # 本地Redis（默认）
THIS_DB_HOST=localhost        # 本地PostgreSQL

# 或使用远程服务
REDIS_HOST=192.168.1.100      # 远程Redis
THIS_DB_HOST=192.168.1.101    # 远程PostgreSQL
```

### 注意事项

- ⚠️ 端口冲突风险：确保8000、6379端口未被占用
- ⚠️ 单机单环境：不适合同一宿主机运行多套环境
- ✅ 访问本地服务：无需额外配置即可访问宿主机PostgreSQL/Redis

---

## 环境配置

配置文件 `.env` 会被自动读取，以下变量会被容器环境覆盖：

| 变量 | 容器内值 | 说明 |
|-----|---------|------|
| `REDIS_HOST` | `${REDIS_HOST:-localhost}` | 从.env读取，默认localhost |
| `GUNICORN_BIND` | `0.0.0.0:${PORT:-8000}` | 容器内监听 |
| `APP_ROOT` | `/app` | 容器工作目录 |
| `PORT` | `8000` | 服务端口 |

---

## PostgreSQL 自有数据库安装

### Docker 方式（推荐）

```bash
docker run -d \
  --name myaps_postgres \
  -e POSTGRES_USER=myaps_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=myaps_db \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine
```

### Ubuntu/Debian 安装

```bash
# 1. 安装 PostgreSQL
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# 2. 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 3. 创建数据库和用户
sudo -u postgres psql

# 在 psql 中执行
CREATE USER myaps_user WITH PASSWORD 'your_password';
CREATE DATABASE myaps_db OWNER myaps_user;
GRANT ALL PRIVILEGES ON DATABASE myaps_db TO myaps_user;
\q

# 4. 配置远程访问（如需要）
sudo vim /etc/postgresql/*/main/postgresql.conf
# 修改: listen_addresses = 'localhost' -> listen_addresses = '*'

sudo vim /etc/postgresql/*/main/pg_hba.conf
# 添加: host all all 0.0.0.0/0 md5

# 5. 重启服务
sudo systemctl restart postgresql
```

### 配置应用连接

编辑 `.env` 文件：

```ini
# 服务自有数据库配置
THIS_DB_HOST=localhost          # 或容器IP / 远程IP
THIS_DB_PORT=5432
THIS_DB_USER=myaps_user
THIS_DB_PASSWORD=your_password
THIS_DB_NAME=myaps_db
```

---

## 数据持久化

以下目录已配置持久化挂载：

| 目录 | 说明 | 是否必需 |
|-----|------|---------|
| `logs/` | 应用日志 | ✓ |
| `project_files/` | 项目配置（含敏感文件） | ✓ |
| `storage/` | 存储目录（SQLite、Binlog位置等） | ✓ |
| `redis_data` | Redis数据卷 | ✓ |

---

## 常用命令

```bash
# 查看容器状态
docker ps | grep myaps-api

# 查看应用日志
docker logs myaps-api -f

# 查看最近50行日志
docker logs myaps-api --tail 50

# 进入容器
docker exec -it myaps-api bash

# 重启容器
docker restart myaps-api

# 停止并删除容器
docker rm -f myaps-api

# 查看镜像信息
docker images qsct/myaps-api
```

---

## 版本更新

```bash
# 拉取最新镜像
docker pull qsct/myaps-api:master

# 使用docker-compose重启
docker-compose down
DOCKER_IMAGE=qsct/myaps-api:master docker-compose up -d
```

---

## 回滚操作

```bash
# 拉取指定版本的镜像
docker pull qsct/myaps-api:2c9ac38

# 或使用本地镜像标签
docker tag qsct/myaps-api:v1.0 qsct/myaps-api:master
```

---

## 离线部署

```bash
# 导出镜像
./export_image.sh v1.0 /path/to/output

# 在目标机器导入
./import_image.sh /path/to/myaps_api_v1.0.tar

# 启动服务
./start.sh
```

---

## 健康检查

```bash
# 应用健康检查
curl http://localhost:8000/docs

# Redis健康检查
docker exec myaps_redis redis-cli ping

# 查看容器健康状态
docker ps --format "table {{.Names}}\t{{.Status}}"

# 检查应用启动状态
curl -s http://localhost:8000/ | python3 -m json.tool
```

---

## 镜像信息

| 项目 | 值 |
|-----|-----|
| 镜像名称 | `qsct/myaps-api:master` |
| 基础镜像 | `python:3.12-slim` |
| 镜像大小 | ~405MB |
| 多阶段构建 | 是 |
| 镜像源 | 官方源（适配GitHub Actions） |

---

## 故障排查

### 常见问题

#### 1. 容器启动失败：ModuleNotFoundError

**现象：**
```
ModuleNotFoundError: No module named 'project_files.HACYXS.remind'
```

**原因：** 敏感配置文件未挂载

**解决：**
```bash
# 添加挂载参数
-v /opt/myaps_api/myaps_api/project_files:/app/project_files
```

---

#### 2. 容器无法连接Redis/PostgreSQL

**现象：**
```
Error 111 connecting to 127.0.0.1:6379. Connection refused.
```

**原因：** 容器内 `localhost` 指向容器自身

**解决：**
```bash
# 方案一：使用host网络模式
--network host

# 方案二：使用host.docker.internal（Docker Desktop）
-e REDIS_HOST=host.docker.internal
```

---

#### 3. 端口冲突

**现象：**
```
Bind for 0.0.0.0:8000 failed: port is already allocated
```

**解决：**
```bash
# 检查端口占用
ss -tlnp | grep :8000

# 使用其他端口
-e PORT=8002
# 并修改启动命令中的端口
-b 0.0.0.0:8002
```

---

#### 4. Docker镜像拉取超时

**现象：**
```
net/http: request canceled while waiting for connection
```

**原因：** 网络问题（国内访问Docker Hub慢）

**解决：**
```bash
# 配置镜像加速器
sudo vim /etc/docker/daemon.json
```

```json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn"
  ]
}
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

### 排查命令

```bash
# 查看容器退出原因
docker inspect myaps-api --format '{{.State.ExitCode}}'

# 查看完整启动日志
docker logs myaps-api 2>&1

# 进入容器调试
docker exec -it myaps-api bash

# 检查容器内文件
docker exec myaps-api ls -la /app/project_files/HACYXS/

# 测试应用能否加载
docker run --rm \
  -v /opt/myaps_api/myaps_api/project_files:/app/project_files \
  --env-file /opt/myaps_api/myaps_api/.env \
  qsct/myaps-api:master \
  python -c "from main import app; print('OK')"
```

---

## CI/CD 配置说明

### GitHub Actions 工作流程

1. **代码检查**：Black、isort、Ruff代码风格检查
2. **构建与测试**：运行单元测试和覆盖率检查
3. **安全扫描**：Bandit安全扫描、依赖漏洞检查
4. **构建交付物**：构建Docker镜像并推送到Docker Hub

### 修改记录

- **镜像源**：已从腾讯云源改为官方源（适配GitHub Actions环境）
- **镜像名称**：已修改为 `docker.io/${{ secrets.DOCKER_USERNAME }}/myaps-api`
- **Dockerfile**：移除腾讯云镜像源配置

### 注意事项

- CI环境使用官方源，国内部署建议配置镜像加速器
- 敏感文件不会进入镜像，需要运行时挂载
- 推送镜像需要Docker Hub Token具有Write权限

---

**最后更新**: 2026-05-26  
**维护者**: MyAPS开发团队
