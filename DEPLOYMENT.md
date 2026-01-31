# MyAPS API 部署指南 - JYHDXS项目

本文档详细介绍了在新环境中部署MyAPS API项目，仅检出JYHDXS项目相关文件的完整步骤。

## 目录

- [环境要求](#环境要求)
- [部署步骤](#部署步骤)
  - [1. 环境准备](#1-环境准备)
  - [2. 克隆Git仓库](#2-克隆git仓库)
  - [3. 配置Git Sparse-Checkout](#3-配置git-sparse-checkout)
  - [4. 配置环境变量](#4-配置环境变量)
  - [5. 创建Python虚拟环境](#5-创建python虚拟环境)
  - [6. 安装项目依赖](#6-安装项目依赖)
  - [7. 数据库初始化](#7-数据库初始化)
  - [8. 启动服务](#8-启动服务)
  - [9. 验证部署](#9-验证部署)
- [常见问题](#常见问题)
- [维护操作](#维护操作)

## 环境要求

### 软件要求

- **Python**: 3.7 或更高版本
- **Git**: 2.25.0 或更高版本（支持sparse-checkout）
- **PostgreSQL**: 用于本API数据库
- **MySQL**: 用于MYAPS数据库（远程连接）

### 硬件要求

- **CPU**: 2核心及以上
- **内存**: 4GB及以上
- **磁盘空间**: 至少10GB可用空间

## 部署步骤

### 1. 环境准备

#### 1.1 检查Python版本

```bash
python --version
```

确保Python版本为3.7或更高。

#### 1.2 检查Git版本

```bash
git --version
```

确保Git版本为2.25.0或更高。

#### 1.3 检查PostgreSQL服务

确保PostgreSQL服务已启动并可以连接。

```bash
# Windows
net start postgresql-x64-14

# Linux
sudo systemctl start postgresql
```

### 2. 克隆Git仓库

#### 2.1 克隆仓库（稀疏克隆）

```bash
# 使用稀疏克隆模式克隆仓库
git clone --filter=blob:none --sparse <repository-url>
cd myaps_api
```

**说明**：
- `--filter=blob:none`: 只下载目录结构，不下载文件内容
- `--sparse`: 启用稀疏检出模式

#### 2.2 如果仓库已存在

如果仓库已经克隆，直接进入项目目录：

```bash
cd myaps_api
```

### 3. 配置Git Sparse-Checkout

#### 3.1 初始化Sparse-Checkout（非Cone模式）

```bash
git sparse-checkout init --no-cone
```

**说明**：
- `--no-cone`: 使用非cone模式，可以更精确地控制要检出的文件

#### 3.2 设置Sparse-Checkout路径

```bash
git sparse-checkout set \  
    apps/ \  
    config/ \  
    globalobjects/ \  
    migrations/ \  
    static/ \  
    /main.py \  
    /pyproject.toml \  
    /requirements.txt \  
    /run.bat \  
    /README.md \  
    /project_files/__init__.py \  
    /project_files/_base.py \  
    /project_files/_template.py \  
    project_files/JYHDXS/
```

**说明**：
- 目录路径不需要前导斜杠（如 `apps/`）
- 单个文件路径需要前导斜杠（如 `/main.py`）
- `project_files/JYHDXS/` 表示检出整个JYHDXS项目目录

#### 3.3 验证Sparse-Checkout配置

```bash
git sparse-checkout list
```

应该显示以下内容：
```
apps/
config/
globalobjects/
migrations/
static/
/main.py
/pyproject.toml
/requirements.txt
/run.bat
/README.md
/project_files/__init__.py
/project_files/_base.py
/project_files/_template.py
project_files/JYHDXS/
```

#### 3.4 检查检出状态

```bash
git status
```

应该显示类似以下内容：
```
On branch master
Your branch is up to date with 'origin/master'.

You are in a sparse checkout with X% of tracked files present.

nothing to commit, working tree clean
```

#### 3.5 验证文件结构

检查关键文件是否存在：

```bash
ls -la
ls project_files/JYHDXS/
```

应该能看到 `client.py` 和 `cache.json` 文件。

### 4. 配置环境变量

#### 4.1 创建.env文件

如果不存在.env文件，需要创建一个：

```bash
# 复制示例配置文件（如果存在）
cp .env.example .env

# 或者直接创建新文件
touch .env
```

#### 4.2 编辑.env文件

使用文本编辑器编辑.env文件，配置以下关键参数：

```ini
# 本API服务器配置
PROTOCOL=http://
HOST=localhost
PORT=8000

# 本API数据库配置<必须使用postgreSQL>
THIS_DB_HOST=localhost
THIS_DB_PORT=5432
THIS_DB_USER=postgres
THIS_DB_PASSWORD=your_password
THIS_DB_NAME=myaps_api

# MYAPS版本，P / L
MYAPS_VERSION=P
# MYAPS地址
MYAPS_ORIGIN_URL=http://your_myaps_server:8092
# MYAPS数据库配置<MySQL>
MYAPS_DB_HOST=your_mysql_host
MYAPS_DB_PORT=3333
MYAPS_DB_USER=root
MYAPS_DB_PASSWORD=your_mysql_password
MYAPS_DB_SET=haida1,dev_mes

# 连接器中定时任务生效的账套数据库
SCHEDULED_DBS=haida1,dev_mes

# 主账套
MYAPS_MAIN_DB=haida1

# 项目文件
PROJECT_FILE=pf_jyhdxs.py

# 项目目录（重要：设置为JYHDXS）
PROJECT_DIR=JYHDXS
```

**重要配置说明**：
- `PROJECT_DIR=JYHDXS`: 必须设置为JYHDXS，指定使用JYHDXS项目配置
- 数据库密码等敏感信息请根据实际情况修改
- 确保MYAPS数据库连接信息正确

### 5. 创建Python虚拟环境

#### 5.1 创建虚拟环境

```bash
# Windows
python -m venv venv

# Linux/macOS
python3 -m venv venv
```

#### 5.2 激活虚拟环境

```bash
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat

# Linux/macOS
source venv/bin/activate
```

激活成功后，命令行提示符应该显示 `(venv)` 前缀。

### 6. 安装项目依赖

#### 6.1 升级pip

```bash
pip install --upgrade pip
```

#### 6.2 安装依赖包

```bash
pip install -r requirements.txt
```

**主要依赖包**：
- fastapi>=0.110.0 - Web框架
- uvicorn>=0.29.0 - ASGI服务器
- tortoise-orm>=0.25.1 - ORM框架
- asyncpg>=0.29.0 - PostgreSQL异步驱动
- aiomysql>=0.2.0 - MySQL异步驱动
- apscheduler>=3.11.1 - 定时任务调度
- mysql_replication>=1.0.9 - MySQL Binlog复制

#### 6.3 验证安装

```bash
pip list
```

确保所有依赖包都已正确安装。

### 7. 数据库初始化

#### 7.1 创建PostgreSQL数据库

```sql
-- 连接到PostgreSQL
psql -U postgres

-- 创建数据库
CREATE DATABASE myaps_api;

-- 退出
\q
```

#### 7.2 初始化数据库迁移

```bash
# 初始化Aerich（如果尚未初始化）
aerich init -t config.settings.TORTOISE_ORM

# 创建迁移文件
aerich migrate --name init

# 应用迁移
aerich upgrade
```

**说明**：
- 如果项目中已有迁移文件，直接运行 `aerich upgrade` 即可
- 迁移文件位于 `migrations/` 目录下

#### 7.3 验证数据库表

连接到PostgreSQL数据库，检查表是否创建成功：

```sql
\c myaps_api
\dt
```

应该能看到项目相关的数据库表。

### 8. 启动服务

#### 8.1 方式一：使用uvicorn直接启动

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**参数说明**：
- `--host 0.0.0.0`: 监听所有网络接口
- `--port 8000`: 指定端口
- `--reload`: 开发模式，代码修改后自动重启

#### 8.2 方式二：使用run.bat启动（Windows）

```bash
run.bat
```

#### 8.3 方式三：使用systemd服务（Linux）

创建服务文件 `/etc/systemd/system/myaps_api.service`：

```ini
[Unit]
Description=MyAPS API Service
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/myaps_api
Environment="PATH=/path/to/myaps_api/venv/bin"
ExecStart=/path/to/myaps_api/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable myaps_api
sudo systemctl start myaps_api
sudo systemctl status myaps_api
```

### 9. 验证部署

#### 9.1 检查服务状态

访问以下URL验证服务是否正常运行：

- **根路径**: http://localhost:8000/
- **API文档**: http://localhost:8000/docs
- **ReDoc文档**: http://localhost:8000/redoc

#### 9.2 测试API端点

```bash
# 测试根路径
curl http://localhost:8000/

# 测试API信息
curl http://localhost:8000/api/info
```

#### 9.3 检查日志

查看应用日志，确保没有错误：

```bash
# 查看应用日志
tail -f logs/app.log

# 查看错误日志
tail -f logs/error.log
```

#### 9.4 验证JYHDXS项目配置

确认系统使用的是JYHDXS项目配置：

- 检查 `project_files/JYHDXS/client.py` 是否存在
- 检查 `project_files/JYHDXS/cache.json` 是否存在
- 验证 `.env` 文件中 `PROJECT_DIR=JYHDXS` 配置

## 常见问题

### Q1: Git sparse-checkout配置后文件没有检出？

**解决方案**：

```bash
# 重新应用sparse-checkout配置
git sparse-checkout reapply

# 如果仍然有问题，重新初始化
git sparse-checkout disable
git sparse-checkout init --no-cone
git sparse-checkout set apps/ config/ globalobjects/ migrations/ static/ /main.py /pyproject.toml /requirements.txt /run.bat /README.md /project_files/__init__.py /project_files/_base.py /project_files/_template.py project_files/JYHDXS/
```

### Q2: Python依赖安装失败？

**解决方案**：

```bash
# 升级pip和setuptools
pip install --upgrade pip setuptools wheel

# 使用国内镜像源安装
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q3: 数据库连接失败？

**解决方案**：

1. 检查PostgreSQL服务是否启动
2. 验证 `.env` 文件中的数据库配置
3. 确保数据库用户有足够的权限
4. 检查防火墙设置

### Q4: 服务启动后无法访问？

**解决方案**：

1. 检查端口是否被占用：`netstat -ano | findstr 8000`
2. 检查防火墙设置
3. 确认服务是否正常监听：`netstat -ano | findstr LISTENING`
4. 查看应用日志中的错误信息

### Q5: 如何更新代码？

**解决方案**：

```bash
# 拉取最新代码
git pull origin master

# 如果有新的sparse-checkout配置，重新应用
git sparse-checkout reapply

# 重启服务
# 如果使用uvicorn，按Ctrl+C停止后重新启动
# 如果使用systemd，执行：sudo systemctl restart myaps_api
```

## 维护操作

### 更新项目代码

```bash
# 拉取最新代码
git pull origin master

# 重新应用sparse-checkout配置
git sparse-checkout reapply

# 安装新的依赖（如果有）
pip install -r requirements.txt

# 应用数据库迁移（如果有）
aerich upgrade

# 重启服务
sudo systemctl restart myaps_api
```

### 查看服务日志

```bash
# 实时查看日志
tail -f logs/app.log

# 查看错误日志
tail -f logs/error.log

# 查看最近100行日志
tail -n 100 logs/app.log
```

### 备份数据库

```bash
# 备份PostgreSQL数据库
pg_dump -U postgres myaps_api > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
psql -U postgres myaps_api < backup_20240101_120000.sql
```

### 停止服务

```bash
# 如果使用uvicorn，按Ctrl+C停止

# 如果使用systemd
sudo systemctl stop myaps_api
```

### 重启服务

```bash
# 如果使用systemd
sudo systemctl restart myaps_api

# 查看服务状态
sudo systemctl status myaps_api
```

## 部署检查清单

部署完成后，请检查以下项目：

- [ ] Git sparse-checkout配置正确
- [ ] JYHDXS项目文件已检出
- [ ] Python虚拟环境已创建并激活
- [ ] 所有依赖包已安装
- [ ] .env文件配置正确，特别是PROJECT_DIR=JYHDXS
- [ ] PostgreSQL数据库已创建并初始化
- [ ] 数据库迁移已应用
- [ ] 服务已启动并正常运行
- [ ] API文档可以访问
- [ ] 日志文件正常生成
- [ ] JYHDXS项目配置生效

## 技术支持

如遇到问题，请查看：
1. 应用日志：`logs/app.log`
2. 错误日志：`logs/error.log`
3. API文档：http://localhost:8000/docs

---

**文档版本**: 1.0  
**最后更新**: 2026-01-31  
**适用项目**: MyAPS API - JYHDXS
