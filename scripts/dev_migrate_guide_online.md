# AI Agent 迁移指南

**适用**: CodeArts、Trae、GitHub Copilot、Cursor 等 AI 编程助手  
**版本**: 2.0 | **日期**: 2026-07-03

---

## 一、迁移前准备

### 1. 项目信息

**项目**: MyAPS API  
**技术栈**: FastAPI + Tortoise-ORM + Pydantic  
**Python**: 3.12.13  
**端口**: 8001 (开发) / 8000 (生产)

**依赖服务**：
- Redis 6.0+ (缓存、消息队列)
- PostgreSQL 14+ (数据清洗)
- MySQL 5.7+ (业务数据，可选)

### 2. 权限评估与密码索取

**评估 sudo 需求**：
- 安装系统包（Redis、PostgreSQL）→ 需要 sudo
- 启动系统服务 → 需要 sudo
- 安装 Python 包 → 不需要 sudo（使用虚拟环境）

**索取 sudo 密码**：
```
Agent: 检测到以下操作需要 sudo 权限：
       1. 安装 Redis、PostgreSQL
       2. 启动系统服务
       
       请提供 sudo 密码（仅用于必要操作，不存储不记录）

User: [密码]

Agent: ✓ 密码验证成功
```

**验证密码**：
```bash
echo 'password' | sudo -S whoami  # 期望输出: root
```

### 2. 系统环境检查
```bash
python3 --version  # 需要 3.10+
free -h            # 内存 ≥ 2GB
df -h /            # 磁盘 ≥ 5GB
```

---

## 二、迁移执行步骤

### Step 1: Python 3.12 安装
```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version  # 验证: 3.12.13
```

### Step 2: 虚拟环境创建
```bash
cd /opt/myaps_api
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -c "import fastapi; print('✓ OK')"
```

### Step 3: 基础服务安装
```bash
sudo apt install -y redis-server postgresql postgresql-contrib sqlite3 mysql-client
sudo systemctl start redis-server postgresql
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '123456';"
sudo -u postgres psql -c "CREATE DATABASE dev;"
redis-cli ping  # 验证: PONG
```

### Step 4: 项目配置

**4.1 创建 .env 文件**：
```bash
cp .env.example .env
```

**必须配置的项**：
```bash
PROJECT_DIR=YOUR_PROJECT_DIR          # 项目目录名
PORT=8001                             # 服务端口
THIS_DB_HOST=127.0.0.1                # PostgreSQL 主机
THIS_DB_PORT=5432                     # PostgreSQL 端口
THIS_DB_USER=postgres                 # PostgreSQL 用户
THIS_DB_PASSWORD=123456               # PostgreSQL 密码
THIS_DB_NAME=dev                      # PostgreSQL 数据库
REDIS_PORT=6379                       # Redis 端口
```

**4.2 创建 dev.json**：
```bash
mkdir -p project_files/{PROJECT_DIR}
```

**dev.json 模板**：
```json
{
    "env": {
        "MYAPS_DB_HOST": "MySQL主机",
        "MYAPS_DB_PORT": 3333,
        "MYAPS_DB_USER": "用户名",
        "MYAPS_DB_PASSWORD": "密码",
        "MYAPS_DB_SET": "db1,db2",
        "MYAPS_MAIN_DB": "db1"
    }
}
```

**4.3 创建 remind.py**（必填，client.py 的硬依赖）：
```python
from globalobjects.reminder import QqEmailReminder

ops_reminder = QqEmailReminder(
    smtp_user="",
    smtp_password="",
    email_from="",
    email_to="",
)

bus_reminder = QqEmailReminder(
    smtp_user="",
    smtp_password="",
    email_from="",
    email_to="",
)

if __name__ == "__main__":
    import sys
    sys.exit(ops_reminder.remind_by_shell())
```

> **注意**：`remind.py` 是 `client.py` 的硬依赖（通过 `from .remind import` 引入），必须存在。
> 模板中配置项硬编码为空字符串，实际使用时填入 QQ 邮箱及授权码即可启用消息推送。

### Step 5: 数据库初始化
```bash
./scripts/migrate/monitor/setup_monitor_tables.sh -l
./scripts/migrate/staging/setup_staging_tables.sh -d dev -l
sqlite3 storage/local_data.sqlite3 "SELECT * FROM schema_version;"
```

### Step 6: 启动服务
```bash
source venv/bin/activate
./scripts/dev_server.sh start
sleep 5
curl http://localhost:8001/docs  # 验证
```

---

## 三、验证检查清单

**环境准备**
- [ ] Python 3.12.13 已安装
- [ ] 虚拟环境已创建并激活
- [ ] 依赖已安装（28 个包）

**基础服务**
- [ ] Redis 运行中（端口 6379）
- [ ] PostgreSQL 运行中（端口 5432）
- [ ] 数据库 dev 已创建

**项目配置**
- [ ] .env 已配置
- [ ] dev.json 已创建
- [ ] remind.py 已创建（必填）

**数据库初始化**
- [ ] 监控表已创建（8 个表）
- [ ] 暂存表已创建（10 个表）

**服务验证**
- [ ] 应用已启动（端口 8001）
- [ ] API 文档可访问

---

## 四、最佳实践

### 1. 密码安全处理
- ✅ 仅在当前会话使用
- ✅ 使用管道传递（`echo 'pwd' | sudo -S`）
- ✅ 每次使用前告知用户
- ❌ 不存储、不记录、不写入文件

### 2. 透明操作原则
```
Agent: 正在执行：安装 Redis
       命令：sudo apt install -y redis-server
       
       [执行中...]
       
       ✓ Redis 安装完成
```

### 3. 错误处理流程
```
Agent: ✗ 操作失败
       错误：[具体错误信息]
       
       可能原因：
       1. [原因 1]
       2. [原因 2]
       
       解决方案：
       1. [方案 1]
       2. [方案 2]
```

### 4. 进度反馈
```
Agent: 迁移进度：
       [✓] 系统环境检查
       [✓] Python 安装
       [●] 依赖安装中... (3/6)
       [ ] 数据库初始化
       [ ] 启动服务
```

---

## 五、常见问题处理

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| sudo 密码验证失败 | 密码错误或无权限 | 重新输入或使用 Docker 替代方案 |
| MySQL 连接失败 | 用户权限不足 | 检查 dev.json 中的用户名密码 |
| 端口占用 | 进程未停止 | `lsof -i :8001 && kill -9 <PID>` |
| 依赖安装失败 | 网络超时 | 使用国内镜像源 |
| 数据库连接失败 | 服务未启动 | `systemctl start redis-server postgresql` |

**详细解决方案**：

```bash
# MySQL 连接验证
mysql -h <host> -P <port> -u <user> -p<password> -e "SELECT 1;"

# 使用国内镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 检查服务状态
systemctl status redis-server postgresql
```

---

## 六、无 sudo 替代方案

### 使用 Docker
```bash
# Redis
docker run -d --name myaps_redis --network host redis:7-alpine

# PostgreSQL
docker run -d --name myaps_postgres --network host \
  -e POSTGRES_PASSWORD=123456 -e POSTGRES_DB=dev \
  postgres:16-alpine
```

### 使用便携版本
```bash
# Redis（预编译）
wget http://download.redis.io/releases/redis-7.2.4.tar.gz
tar xzf redis-7.2.4.tar.gz && cd redis-7.2.4
make && make install PREFIX=$HOME/local
```

---

## 七、完成后操作

1. **提供访问地址**: http://localhost:8001/docs
2. **提供管理命令**: 
   ```bash
   ./scripts/dev_server.sh status|logs|restart|stop
   ```
3. **提示后续操作**:
   - 测试 API 接口
   - 配置生产环境
   - 设置开机自启

---

## 八、Agent 行为规范

### 必须遵守
- ✅ 开始前主动索取 sudo 密码
- ✅ 每次使用 sudo 前告知用户
- ✅ 提供实时进度反馈
- ✅ 错误时提供清晰信息和解决方案
- ✅ 记录所有执行的操作

### 禁止行为
- ❌ 直接执行 sudo 命令（未告知用户）
- ❌ 存储或记录密码
- ❌ 跳过验证步骤
- ❌ 隐藏错误信息

---

## 九、关键信息补充

### 1. 项目目录结构
```
/opt/myaps_api/
├── venv/                    # 虚拟环境
├── project_files/           # 租户配置
│   └── {PROJECT_DIR}/       # 项目目录
│       ├── dev.json         # 项目配置
│       └── remind.py        # 消息推送
├── scripts/                 # 脚本
│   ├── dev_server.sh        # 开发服务器
│   └── migrate/             # 数据库迁移
├── logs/                    # 日志目录
├── storage/                 # 数据存储
│   └── local_data.sqlite3   # SQLite 数据库
├── .env                     # 环境变量
└── requirements.txt         # Python 依赖
```

### 2. 关键文件说明

| 文件 | 用途 | 必须 |
|------|------|------|
| .env | 环境变量配置 | ✓ |
| project_files/{PROJECT_DIR}/dev.json | 项目配置 | ✓ |
| project_files/{PROJECT_DIR}/remind.py | 消息推送 | ✓ |
| requirements.txt | Python 依赖 | ✓ |

### 3. 重要配置项

**MySQL 连接**（dev.json）：
- MYAPS_DB_HOST: MySQL 主机地址
- MYAPS_DB_PORT: MySQL 端口（默认 3333）
- MYAPS_DB_USER: 用户名
- MYAPS_DB_PASSWORD: 密码
- MYAPS_DB_SET: 数据库列表（逗号分隔）
- MYAPS_MAIN_DB: 主数据库名

**PostgreSQL 连接**（.env）：
- THIS_DB_HOST: 主机地址（默认 127.0.0.1）
- THIS_DB_PORT: 端口（默认 5432）
- THIS_DB_USER: 用户名（默认 postgres）
- THIS_DB_PASSWORD: 密码
- THIS_DB_NAME: 数据库名（默认 dev）

### 4. 数据库说明

**SQLite** (监控数据):
- 位置: `storage/local_data.sqlite3`
- 表: api_requests, system_logs, binlog_positions 等
- 用途: 监控、日志、事件记录

**PostgreSQL** (数据清洗):
- 数据库: dev
- 表: t_material_staging, t_workcenter_staging 等
- 用途: 数据缓冲、清洗、验证

**MySQL** (业务数据):
- 多账套支持: hdtest, dev_mes 等
- 用途: 业务数据存储

### 5. 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| 应用服务 | 8001 | 开发环境 |
| 应用服务 | 8000 | 生产环境 |
| Redis | 6379 | 缓存服务 |
| PostgreSQL | 5432 | 数据库 |
| MySQL | 3333 | 业务数据库 |

---

## 十、文档说明

本文档为 MyAPS API 项目迁移的唯一指南文档，包含：

- ✅ 完整的迁移步骤（6 步骤）
- ✅ 所有关键配置模板
- ✅ 验证检查清单
- ✅ 最佳实践和行为规范
- ✅ 常见问题处理
- ✅ 项目结构和关键信息

**AI Agent 可仅凭此文档从零完成项目迁移**。

---

**文档版本**: 2.0 | **最后更新**: 2026-07-03