# MyAPS Ubuntu 部署指南（完全离线版）

## 📁 目录结构

```
scripts/deploy_ubuntu/
├── deploy.sh          # 主部署脚本（完全离线）
├── start.sh           # 启动服务
├── stop.sh            # 停止服务
├── restart.sh         # 重启服务
├── status.sh          # 查看状态
├── prepare_offline.sh # 打包离线依赖（开发机用）
└── nginx.conf         # Nginx 配置模板
```

## 🚀 部署步骤

### 前提条件

目标服务器为 **完全无外网环境**，所有依赖已提前下载。

### 1. 在有外网的开发机准备离线包

```bash
# 在开发机执行（需要外网）
cd /path/to/myaps_fastapi

# 方式一：使用已下载的 Ubuntu 离线包
# 确认 offline_packages/ubuntu/ 目录下有所有依赖

# 方式二：重新下载（需外网）
./scripts/deploy_ubuntu/prepare_offline.sh
```

### 2. 打包整个项目

推荐使用 PowerShell 脚本打包，确保排除目录生效：

```powershell
# 在项目根目录运行
cd D:\code\myaps_fastapi
.\scripts\deploy_ubuntu\package_for_deploy.ps1
```

**打包结果**：
- 输出文件：`D:\code\myaps_fastapi_YYYYMMDD.tar.gz`（YYYYMMDD 为日期）
- 自动排除以下目录：

| 目录 | 说明 |
|------|------|
| `venv` | Python 虚拟环境（服务器上重新创建） |
| `offline_packages` | 离线依赖包（太大，需单独拷贝） |
| `logs` | 日志目录（无需迁移） |
| `test` | 测试代码（无需部署） |
| `storage` | 本地存储（无需迁移） |
| `backups` | 备份目录（无需迁移） |
| `.git` | Git 仓库 |
| `__pycache__` / `*.pyc` | Python 编译文件 |

### 手动打包命令（Git Bash）

如果需要手动打包，可使用以下命令：

```bash
# 进入项目上级目录
cd /d/code/

# 创建临时目录
mkdir myaps_fastapi_temp

# 复制文件（排除目录）
rsync -av --exclude='venv' --exclude='offline_packages' --exclude='logs' \
      --exclude='test' --exclude='storage' --exclude='backups' --exclude='.git' \
      --exclude='__pycache__' --exclude='*.pyc' myaps_fastapi/ myaps_fastapi_temp/

# 打包
tar -czvf myaps_fastapi.tar.gz myaps_fastapi_temp/

# 清理临时目录
rm -rf myaps_fastapi_temp
```

### 单独打包离线依赖包

```bash
# 打包项目代码（不含离线包）
.\scripts\deploy_ubuntu\package_for_deploy.ps1

# 单独打包离线依赖包
cd D:\code\
tar -czvf offline_packages.tar.gz myaps_fastapi/offline_packages/
```

### 3. 传输到离线服务器

```bash
# 方法一：使用 U 盘/移动硬盘拷贝
# 将 myaps_fastapi.tar.gz 拷贝到服务器

# 方法二：内网 SCP（如果有内网网络）
scp myaps_fastapi.tar.gz root@your-server:/opt/
```

### 4. 在离线服务器解压

```bash
# 在目标服务器执行
cd /opt
tar -xzvf myaps_fastapi.tar.gz
mv myaps_fastapi_temp myaps_api
cd /opt/myaps_api
```

### 5. 配置 .env

编辑 `/opt/myaps_api/.env`，确保以下参数正确：

```ini
# 项目配置
PROJECT_DIR=JYHDXS        # 租户目录（CHANGDE/JYHDXS/HACYXS）
PROJECT_JSON=dev          # dev/prod

# 部署配置
WORKERS=4                 # 工作进程数（建议为 CPU 核数）
GUNICORN_BIND=127.0.0.1:8000
GUNICORN_TIMEOUT=30
APP_USER=www-data
APP_ROOT=/opt/myaps_api/myaps_api  # 注意：项目实际目录结构为 /opt/myaps_api/myaps_api

# 数据库配置（根据实际环境修改）
MYAPS_DB_HOST=127.0.0.1
MYAPS_DB_PORT=3306
MYAPS_DB_USER=username
MYAPS_DB_PASSWORD=password
MYAPS_DB_SET=database_name
MYAPS_MAIN_DB=database_name

# Redis 配置
REDIS_PORT=6379
REDIS_PASSWORD=
```

### 6. 安装系统依赖（离线方式）

#### 6.1 安装基础依赖

```bash
# 如果服务器从未安装过以下依赖，需要提前准备 deb 包

# 安装 Python 3.12（必须）
# 方法：在有外网的 Ubuntu 机器上下载 deb 包
# apt download python3.12 python3.12-venv python3.12-dev
# 然后拷贝到离线服务器安装

# 安装编译依赖（某些 Python 包需要）
# apt download build-essential libssl-dev libffi-dev

# 安装 MySQL 客户端库
# apt download libmysqlclient-dev

# 安装完成后执行
apt install ./python3.12*.deb ./build-essential*.deb ./libssl-dev*.deb ./libffi-dev*.deb
```

#### 6.2 安装 Redis 数据库（离线方式）

```bash
# 方法一：使用 deb 包完整安装（推荐，最可靠）
# 1. 在有外网的 Ubuntu 机器上下载 Redis 及其所有依赖
mkdir -p /tmp/redis_packages
cd /tmp/redis_packages

# 自动获取并下载所有依赖包（最完整的方式）
apt download $(apt-cache depends redis-server redis-tools | grep -E "Depends|Recommends" | cut -d: -f2 | tr -d '<> ')

# 或者手动下载已知的关键依赖（备选方案）
# apt download redis-server redis-tools libjemalloc2 libhiredis0.14 liblzf1

# 查看下载的文件
ls -la *.deb

# 2. 将所有 deb 包拷贝到离线服务器
# 使用 U 盘/移动硬盘或 scp 命令
# 拷贝到离线服务器的 /opt/redis_packages/ 目录

# 3. 在离线服务器上安装
cd /opt/redis_packages
# 方法 A：使用 dpkg 安装所有包
apt --fix-broken install -y

# 方法 B：如果有部分依赖问题，使用 apt 本地安装（推荐）
# apt install ./*.deb

# 方法二：源码编译安装（适用于无 deb 包的情况）
# 1. 下载 Redis 源码（在有外网的机器上）
# wget https://download.redis.io/releases/redis-7.4.0.tar.gz

# 2. 拷贝到离线服务器并解压
# tar -xzvf redis-7.4.0.tar.gz
# cd redis-7.4.0

# 3. 编译安装（需要先安装 build-essential）
# apt install ./build-essential*.deb
# make
# make install

# 4. 创建配置文件和服务
# mkdir -p /etc/redis /var/lib/redis
# cp redis.conf /etc/redis/
# useradd -r -s /bin/false redis
# chown redis:redis /var/lib/redis

# 5. 创建 systemd 服务文件
# cat > /etc/systemd/system/redis.service << 'EOF'
# [Unit]
# Description=Redis In-Memory Data Store
# After=network.target

# [Service]
# User=redis
# Group=redis
# ExecStart=/usr/local/bin/redis-server /etc/redis/redis.conf
# ExecStop=/usr/local/bin/redis-cli shutdown
# Restart=always

# [Install]
# WantedBy=multi-user.target
# EOF

# 启动 Redis 服务（两种方法都需要）
systemctl daemon-reload
systemctl start redis-server
systemctl enable redis-server

# 验证安装
redis-cli ping
# 输出: PONG
```

#### 常见问题与解决

**问题：安装时提示缺少依赖包**

解决方法：确保使用了上面的方法一，使用 `apt-cache depends` 自动获取所有依赖。

**问题：dpkg 安装后仍有未配置的包**

解决方法：
```bash
# 强制修复配置
apt-get -f install
# 或者再次执行 dpkg 配置
dpkg --configure -a
```

**问题：如何检查已下载的依赖是否完整**

```bash
# 在有外网的机器上模拟安装，检查是否还有缺失
mkdir -p /tmp/test_install
cd /tmp/test_install
cp /tmp/redis_packages/*.deb .
# 使用 apt 模拟安装（不会真正安装）
apt install --dry-run ./*.deb
```

### 7. 执行离线部署

```bash
cd /opt/myaps_api
chmod +x ./scripts/deploy_ubuntu/*.sh

# 首次部署（包含数据库迁移）
./scripts/deploy_ubuntu/deploy.sh -d

# 增量更新（跳过数据库迁移，避免破坏数据）
./scripts/deploy_ubuntu/deploy.sh -d -s
```

**部署选项说明：**

| 选项 | 说明 |
|------|------|
| `-d` | 执行部署 |
| `-s` | 跳过数据库迁移（用于增量更新） |
| `-t <租户>` | 指定租户（如 CHANGDE、JYHDXS、HACYXS） |

**示例：**
```bash
# 首次部署，指定租户
./scripts/deploy_ubuntu/deploy.sh -d -t CHANGDE

# 增量更新，跳过迁移
./scripts/deploy_ubuntu/deploy.sh -d -s

# 指定租户且跳过迁移
./scripts/deploy_ubuntu/deploy.sh -d -t CHANGDE -s
```

### 8. 配置 Nginx（可选）

```bash
# 安装 Nginx（提前准备 deb 包）
# apt download nginx
# dpkg -i nginx*.deb

# 复制配置
cp ./scripts/deploy_ubuntu/nginx.conf /etc/nginx/nginx.conf

# 测试配置
nginx -t

# 重启 Nginx
systemctl restart nginx
systemctl enable nginx
```

## 📝 常用命令

```bash
# 启动服务
./scripts/deploy_ubuntu/start.sh

# 停止服务
./scripts/deploy_ubuntu/stop.sh

# 重启服务
./scripts/deploy_ubuntu/restart.sh

# 查看状态
./scripts/deploy_ubuntu/status.sh

# 查看日志
journalctl -u MyAPS_API -f

# 切换租户（修改 .env 后重启）
sed -i 's/PROJECT_DIR=JYHDXS/PROJECT_DIR=CHANGDE/' .env
./scripts/deploy_ubuntu/restart.sh
```

## 📦 离线依赖包说明

### 依赖包位置

```
/opt/myaps_api/offline_packages/ubuntu/python_pkg/
├── fastapi-0.136.1-py3-none-any.whl
├── uvicorn-0.46.0-py3-none-any.whl
├── gunicorn-26.0.0-py3-none-any.whl
├── pandas-3.0.2-cp312-cp312-manylinux_*.whl
├── numpy-2.4.4-cp312-cp312-manylinux_*.whl
└── ... (共 56 个依赖包)
```

### 离线包兼容性

| 类型 | 特征 | 说明 |
|------|------|------|
| `py3-none-any.whl` | 纯 Python 代码 | 跨平台通用 |
| `manylinux_*.whl` | 编译后的二进制 | Ubuntu x86_64 专用 |

## ⚠️ 注意事项

1. **完全离线**：确保服务器无任何外网访问，所有依赖已提前准备
2. **Python 版本**：必须使用 Python 3.12（依赖包为 cp312 版本）
3. **权限问题**：建议使用 `www-data` 用户运行，而非 `root`
4. **数据库连接**：确保 `.env` 中数据库配置正确且可达
5. **防火墙**：确保端口 80/443/8000 已开放
6. **系统依赖**：提前准备 `python3.12`, `build-essential`, `libssl-dev` 等 deb 包
7. **APP_ROOT 配置**：确保 `APP_ROOT=/opt/myaps_api/myaps_api`（项目实际在二级目录）
8. **只读文件系统**：如果 `/opt/myaps_api` 是只读挂载点，脚本会自动使用用户级别 Systemd 服务

## 🔧 故障排查

| 问题 | 解决方法 |
|------|---------|
| 服务启动失败 | `systemctl status MyAPS_API` |
| 日志查看 | `journalctl -u MyAPS_API -f` |
| 端口占用 | `lsof -i :8000` |
| Nginx 配置错误 | `nginx -t` |
| Python 版本不匹配 | 确认安装 Python 3.12 |
| 依赖安装失败 | 检查 offline_packages/ubuntu/ 目录是否完整 |
| 只读文件系统错误 | 检查 `/opt/myaps_api` 挂载状态，使用 `mount` 命令确认 |
| Systemd 服务创建失败 | 脚本会自动回退到用户级别服务，使用 `systemctl --user` 命令 |

## 📋 部署检查清单

- [ ] 项目代码已拷贝到 `/opt/myaps_api/`
- [ ] `.env` 配置文件已正确设置（`APP_ROOT=/opt/myaps_api/myaps_api`）
- [ ] 离线依赖包存在于 `offline_packages/ubuntu/python_pkg/`
- [ ] Python 3.12 已安装
- [ ] 数据库服务已启动且可连接
- [ ] Redis 服务已启动且可连接
- [ ] 执行 `deploy.sh -d` 部署成功（首次部署）
- [ ] 执行 `deploy.sh -d -s` 部署成功（增量更新）
- [ ] 服务状态正常（`systemctl --user status MyAPS_API` 或 `systemctl status MyAPS_API`）

## 🔄 无外网环境代码同步指南

### 首次获取代码：使用 Git Bundle 传输（推荐）

#### 步骤1：在外网机器上打包
```bash
# 从远程仓库拉取最新代码
git clone 远程仓库地址 myaps_api
cd myaps_api

# 打包成完整的 bundle 文件（包含所有分支和历史）
git bundle create myaps_api.bundle --all
```

#### 步骤2：传输到内网机器
使用 U 盘、移动硬盘或其他物理介质将 `myaps_api.bundle` 传输到内网服务器。

#### 步骤3：在内网机器上从 bundle 创建仓库
```bash
# 从 bundle 文件克隆仓库
git clone myaps_api.bundle myaps_api
cd myaps_api

# 验证仓库状态
git log --oneline -10
```

---

### 更新代码：方法1 - 使用 Git Bundle 增量更新（推荐）

#### 步骤1：在外网机器上准备
```bash
# 进入外网仓库目录
cd myaps_api

# 拉取最新代码
git pull origin master

# 记录上次同步的 commit（或使用标签）
# 假设上次同步的 commit 是 abc1234
git bundle create update.bundle abc1234..HEAD

# 或者打包所有分支
git bundle create update.bundle --all
```

#### 步骤2：传输到内网机器
将 `update.bundle` 传输到内网服务器。

#### 步骤3：在内网机器上更新
```bash
cd /opt/myaps_api/myaps_api

# 从 bundle 获取更新
git fetch /path/to/update.bundle

# 合并到本地分支
git merge FETCH_HEAD

# 或者直接 pull
git pull /path/to/update.bundle master
```

---

### 更新代码：方法2 - 使用补丁文件 (Patch)

适合小范围更新，文件体积小。

#### 步骤1：在外网机器上生成补丁
```bash
cd myaps_api
git pull origin master

# 生成从某个 commit 到最新的补丁
# 方法A：生成单个补丁文件
git format-patch start_commit..HEAD --stdout > updates.patch

# 方法B：生成多个独立补丁文件
git format-patch -n start_commit..HEAD
```

#### 步骤2：传输补丁文件
将 `updates.patch` 或多个 `.patch` 文件传输到内网服务器。

#### 步骤3：在内网机器上应用补丁
```bash
cd /opt/myaps_api/myaps_api

# 方法A：应用单个补丁文件
git apply updates.patch

# 方法B：使用 git am 应用（会保留提交信息）
git am *.patch

# 如果有冲突，解决后继续
git am --continue
```

---

### 推荐工作流程

1. **在外网机器**：
   - 定期从远程仓库拉取代码
   - 使用 Git Bundle 打包（首次用完整 bundle，后续用增量 bundle）

2. **物理传输**：
   - 通过 U 盘/移动硬盘传输 bundle 文件到内网

3. **在内网机器**：
   - 从 bundle 更新本地仓库
   - 执行增量部署：`./scripts/deploy_ubuntu/deploy.sh -d -s`

---

### 实用技巧

#### 使用标签记录同步点
```bash
# 在外网机器：每次打包前打标签
git tag -a sync_20260510 -m "Sync point 2026-05-10"
git push origin sync_20260510

# 下次打包时使用标签
git bundle create update.bundle sync_20260510..HEAD
```

#### 验证 bundle 完整性
```bash
# 验证 bundle 文件是否有效
git bundle verify myaps_api.bundle

# 查看 bundle 中包含的引用
git bundle list-heads myaps_api.bundle
```