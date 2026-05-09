# MyAPS Docker 部署指南

## 项目说明

Docker 部署包含以下服务：

- **FastAPI 应用** - 主应用服务
- **Redis** - 缓存服务

> 项目当前使用远程 MySQL 数据库。

## 目录结构

```
scripts/deploy_docker/
├── docker-compose.yml     # 服务编排配置
├── docker-env.example    # 环境变量模板
├── build_image.bat       # 构建镜像（Windows开发机）
├── export_image.bat      # 导出镜像为tar文件（Windows）
├── import_image.sh       # 导入镜像（Ubuntu服务器）
└── start_service.sh      # 启动服务（含端口冲突处理）
```

**包含服务**：Redis 7、FastAPI App

## 配置国内镜像源（可选）

如果直接连接 Docker Hub 较慢，可以配置国内镜像源。

### 配置方法

1. 打开 **Docker Desktop**
2. 点击右上角 **设置**（齿轮图标）
3. 左侧选择 **Docker Engine**
4. 在编辑器中添加 `registry-mirrors` 配置：

```json
{
  "registry-mirrors": [
    "https://docker.mirrors.sjtug.sjtu.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://docker.m.daocloud.io"
  ]
}
```

1. 点击 **Apply & Restart**

### 常用国内镜像源（2026年可用）

| 镜像源      | 地址                                         | 状态 |
| -------- | ------------------------------------------ | -- |
| 上海交大     | `https://docker.mirrors.sjtug.sjtu.edu.cn` | 推荐 |
| 网易       | `https://hub-mirror.c.163.com`             | 可用 |
| DaoCloud | `https://docker.m.daocloud.io`             | 可用 |
| 阿里云      | （需登录阿里云容器镜像服务获取）                           | 稳定 |

> **注意**：部分旧镜像源（如中科大、百度云）已停止服务，请使用上表中的可用镜像源。

### 如果镜像源都无法使用

如果所有镜像源都无法连接，可以采用以下方案：

1. **在有外网的机器上** 使用 VPN/代理 拉取镜像
2. **导出镜像文件** 后拷贝到内网服务器
3. 在内网服务器上 **导入镜像文件** 使用

***

## 部署流程

### 阶段一：开发机准备（需要外网）

#### 1. 配置远程 MySQL

在 `.env` 文件中配置远程数据库连接：

```env
MYAPS_DB_HOST=your_mysql_host      # 远程 MySQL 地址
MYAPS_DB_PORT=3306                 # MySQL 端口
MYAPS_DB_USER=your_username        # 用户名
MYAPS_DB_PASSWORD=your_password    # 密码
MYAPS_MAIN_DB=your_database        # 主数据库名
MYAPS_DB_SET=aps1,aps2             # 数据库集合
```

#### 2. 构建镜像

```batch
cd d:\code\myaps_fastapi
.\scripts\deploy_docker\build_image.bat
```

#### 3. 导出镜像

```batch
.\scripts\deploy_docker\export_image.bat
```

导出的镜像文件位于：`d:\code\myaps_fastapi\docker_images\`

#### 4. 拷贝到内网服务器

将 `docker_images` 目录整体拷贝到内网Ubuntu服务器。

***

### 阶段二：内网服务器部署

#### 1. 安装Docker环境

```bash
# Ubuntu Server
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl start docker
sudo systemctl enable docker

# 当前用户加入docker组（可选）
sudo usermod -aG docker $USER
```

#### 2. 创建必要目录

```bash
cd /path/to/myaps_fastapi
mkdir -p storage logs
```

#### 3. 配置环境变量

```bash
cp scripts/deploy_docker/docker-env.example .env
# 编辑 .env 文件，配置远程 MySQL 和其他参数
```

**必须配置的项**：

```env
# 多租户项目配置
PROJECT_JSON=dev

# Redis 配置（Docker 内）
REDIS_HOST=redis
REDIS_PORT=6379

# 数据库配置
MYAPS_DB_HOST=your_mysql_host
MYAPS_DB_PORT=3306
MYAPS_DB_USER=your_username
MYAPS_DB_PASSWORD=your_password
MYAPS_DB_SET=aps1,aps2
MYAPS_MAIN_DB=aps1

# 其他配置
PORT=8000
LOG_LEVEL=INFO
TZ=Asia/Shanghai
```

> **说明**：
> - 数据库配置（MySQL 等）通过 `project_files/{项目名}/{PROJECT_JSON}.json` 文件动态加载
> - 确保 `project_files` 目录已拷贝到服务器
> - 多租户切换通过修改 `PROJECT_JSON` 环境变量实现

#### 4. 导入镜像

```bash
docker load -i docker_images/myaps_api_*.tar && \
docker load -i docker_images/redis_7-alpine_*.tar
```

#### 5. 启动服务

**推荐方式**（使用启动脚本，自动处理端口冲突）：

```bash
cd /path/to/myaps_fastapi
chmod +x scripts/deploy_docker/start_service.sh
./scripts/deploy_docker/start_service.sh
```

**脚本功能**：
- 自动检测 Redis 端口（6379）是否被占用
- 如果存在旧容器，自动清理
- 启动所有服务并显示状态

**手动方式**：

```bash
cd /path/to/myaps_fastapi
docker-compose -f scripts/deploy_docker/docker-compose.yml up -d
```

***

## 数据持久化

| 容器         | 持久化内容     | 位置                   |
| ---------- | --------- | -------------------- |
| Redis      | 缓存数据      | `redis_data` 卷       |
| App        | 上传文件      | `./storage` 目录       |
| App        | Binlog位置  | `./storage` 目录       |
| App        | 应用日志      | `./logs` 目录          |

> **注意**：远程 MySQL 数据存储在外部服务器。

## 服务管理

```bash
# 查看状态
docker-compose -f scripts/deploy_docker/docker-compose.yml ps

# 查看日志
docker-compose -f scripts/deploy_docker/docker-compose.yml logs -f

# 重启服务
docker-compose -f scripts/deploy_docker/docker-compose.yml restart

# 停止服务
docker-compose -f scripts/deploy_docker/docker-compose.yml down

# 更新部署（重新构建）
docker-compose -f scripts/deploy_docker/docker-compose.yml up -d --build
```

## 端口映射

| 服务         | 端口      | 说明            |
| ---------- | ------- | ------------- |
| FastAPI    | 8000    | API直连         |
| Redis      | 6379    | 缓存（如需外部访问）    |

> 远程 MySQL 端口 **不映射**，因为使用的是远程 MySQL。

## 健康检查

```bash
# 检查所有容器状态
docker-compose -f scripts/deploy_docker/docker-compose.yml ps

# 检查健康状态
docker inspect --format='{{.State.Health.Status}}' myaps_api
```

## 代码更新后重新部署

当项目代码更新后，需要重新构建镜像并部署：

### 完整重新部署流程

#### 阶段一：开发机（有外网）

```batch
# 1. 进入项目目录
cd d:\code\myaps_fastapi

# 2. 重新构建镜像（利用缓存，不会重复拉取基础镜像）
docker build -t myaps_api:latest .

# 3. 导出更新后的镜像
.\scripts\deploy_docker\export_image.bat

# 4. 拷贝 docker_images 目录到内网服务器
```

#### 阶段二：内网服务器

```bash
# 1. 进入项目目录
cd /path/to/myaps_fastapi

# 2. 导入更新后的镜像
docker load -i docker_images/myaps_api_*.tar

# 3. 重启服务（使用新镜像）
docker-compose -f scripts/deploy_docker/docker-compose.yml up -d

# 4. 验证服务状态
docker-compose -f scripts/deploy_docker/docker-compose.yml ps
```

### Docker 缓存说明

| 操作       | 是否拉取基础镜像 | 说明                                                                 |
| -------- | -------- | ------------------------------------------------------------------ |
| 首次构建     | 是        | 从镜像仓库拉取基础镜像                                                        |
| 后续构建     | **否**    | 使用本地缓存，构建速度更快                                                      |
| 强制更新基础镜像 | 是        | 添加 `--pull` 参数：`docker build --pull -t myaps_api:latest .`         |
| 强制不使用缓存  | 是        | 添加 `--no-cache` 参数：`docker build --no-cache -t myaps_api:latest .` |

### 快速重启（不重建镜像）

如果只是修改配置文件或重启服务，不需要重新构建镜像：

```bash
# 仅重启服务
docker-compose -f scripts/deploy_docker/docker-compose.yml restart

# 查看服务日志
docker-compose -f scripts/deploy_docker/docker-compose.yml logs -f
```

***

## 注意事项

1. **远程 MySQL**：确保内网服务器能访问远程 MySQL 数据库
2. **防火墙**：检查内网服务器的防火墙规则，允许访问远程 MySQL 端口
3. **Redis 数据**：`redis_data` 卷用于持久化缓存，不要删除
4. **定期备份**：建议定期备份 `./storage` 目录（上传文件）
5. **代码更新**：代码更新后必须重新构建镜像，因为代码已打包在镜像内部
