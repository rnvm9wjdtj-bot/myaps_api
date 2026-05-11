# MyAPS API Docker 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose V2
- Python 3.12（镜像内置）

## 快速开始

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

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
```

## 环境配置

配置文件 `.env` 会被自动读取，以下变量会被容器环境覆盖：

| 变量 | 容器内值 | 说明 |
|-----|---------|------|
| `REDIS_HOST` | `redis` | 容器名访问 |
| `GUNICORN_BIND` | `0.0.0.0:8000` | 容器内监听 |
| `APP_ROOT` | `/app` | 容器工作目录 |

## PostgreSQL 自有数据库安装（可选）

项目支持自有 PostgreSQL 数据库（THIS_DB），以下为手动安装步骤。

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

# 6. 验证连接
psql -h localhost -U myaps_user -d myaps_db
```

### CentOS/RHEL 安装

```bash
# 1. 安装 PostgreSQL
sudo yum install -y postgresql-server postgresql-contrib
sudo postgresql-setup initdb

# 2. 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 3-6. 创建用户和配置（同Ubuntu）
```

### Docker 方式安装 PostgreSQL

```bash
# 启动 PostgreSQL 容器
docker run -d \
  --name myaps_postgres \
  -e POSTGRES_USER=myaps_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=myaps_db \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine

# 查看连接信息
docker inspect myaps_postgres | grep IPAddress
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

### 不使用自有数据库

如不需要自有数据库，保持 `.env` 中相关配置为空或注释即可：

```ini
# THIS_DB_HOST=
# THIS_DB_NAME=
```

应用会自动跳过自有数据库初始化。

## 数据持久化

以下目录已配置持久化挂载：

- `logs/` - 应用日志
- `project_files/` - 项目配置缓存
- `static/` - 静态文件
- `storage/` - 存储目录（SQLite、Binlog位置等）
- `apps/` - 应用代码（开发模式热更新）
- `core/` - 核心配置（开发模式热更新）
- `globalobjects/` - 全局对象（开发模式热更新）
- `scripts/` - 脚本文件（开发模式热更新）
- `redis_data` - Redis数据卷

> 注意：生产环境建议移除代码目录挂载，使用镜像内置代码以获得更好隔离性。

## 常用命令

```bash
# 查看应用日志
docker-compose logs -f app

# 进入容器
docker exec -it myaps_api bash

# 重新构建并启动
docker-compose up -d --build

# 停止并清理
docker-compose down

# 停止并清理卷
docker-compose down -v
```

## 版本更新

```bash
# 拉取最新代码
git pull

# 重新构建并启动（零停机）
docker-compose up -d --build

# 或使用脚本
./build.sh v2.0
docker-compose up -d
```

## 回滚操作

```bash
# 回滚到指定版本
docker tag myaps_api:v1.0 myaps_api:latest
docker-compose up -d
```

## 离线部署

```bash
# 导出镜像
./export_image.sh v1.0 /path/to/output

# 在目标机器导入
./import_image.sh /path/to/myaps_api_v1.0.tar

# 启动服务
./start.sh
```

## 健康检查

- 应用健康检查: `curl http://localhost:8000/docs`
- Redis健康检查: `docker exec myaps_redis redis-cli ping`
- 查看容器健康状态: `docker ps --format "table {{.Names}}\t{{.Status}}"`

## 镜像信息

| 项目 | 值 |
|-----|-----|
| 基础镜像 | python:3.12-slim |
| 镜像大小 | ~460MB |
| 多阶段构建 | 是 |
| 国内镜像源 | 已配置（腾讯云） |

## 故障排查

```bash
# 查看应用日志
docker-compose logs -f app

# 查看启动失败原因
docker logs myaps_api 2>&1 | head -50

# 进入容器调试
docker exec -it myaps_api bash

# 检查容器内文件
docker exec myaps_api ls -la /app/
```
