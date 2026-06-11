# MyAPS API - 完全离线环境迁移手册 (Linux版)

> **版本**: 2.0  
> **适用场景**: 无外网访问的内网 Linux 开发环境  
> **最后更新**: 2026-06-11

---

## 🎉 新增功能：可视化 GUI 工具

本项目现在提供一个基于 Python tkinter 的可视化界面工具，让离线迁移更加简单直观！

| 方式 | 推荐人群 | 说明 |
|------|----------|------|
| **GUI 工具** | 所有用户 | 可视化操作，推荐优先使用 |
| **命令行脚本** | 高级用户/CI | 保留原有的命令行方式 |

### 快速启动 GUI

**Linux/macOS**:
```bash
bash .offline_dev/to_linux/gui/run_gui.sh
```

---

## 目录

1. [迁移概述](#一迁移概述)
2. [前置准备](#二前置准备)
3. [第一阶段：外网机器准备离线包](#三第一阶段外网机器准备离线包)
4. [第二阶段：内网机器部署](#四第二阶段内网机器部署)
5. [常见问题排查](#五常见问题排查)
6. [附录](#六附录)

---

## 一、迁移概述

### 1.1 迁移目标

将 MyAPS API 项目从当前开发环境（macOS/Linux，有外网）迁移到**完全无外网访问**的内网 Linux 环境继续开发。

### 1.2 迁移流程概览

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   外网机器       │     │   文件传输       │     │   内网Linux     │
│  (准备离线包)    │────▶│  (U盘/光盘/网闸) │────▶│  (部署运行)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 1.3 需要迁移的内容

| 类别 | 内容 | 说明 |
|------|------|------|
| 源代码 | `myaps_api/` 整个项目目录 | 包含所有 Python 代码、前端资源、配置文件 |
| 依赖包 | `.offline_dev/to_linux/packages/` 目录 | 所有 Python 第三方库的离线安装包 |
| 数据库 | MySQL / PostgreSQL / Redis | 需在内网单独部署或已有 |
| 环境配置 | `.env` 文件 | 内网数据库连接等配置 |

---

## 二、前置准备

### 2.1 外网机器要求

- **操作系统**: Linux / macOS（有外网访问）
- **Python**: 3.11 或 3.12（**必须与内网目标机器版本一致**）
- **pip**: 最新版本
- **磁盘空间**: 至少 2GB 可用空间（用于下载依赖包）

### 2.2 内网 Linux 机器要求

- **操作系统**: CentOS 7+ / Ubuntu 18.04+ / Debian 10+ 或其他主流发行版
- **Python**: 3.11 或 3.12（**必须与外网打包机器版本一致**）
- **内存**: 至少 4GB RAM
- **磁盘空间**: 至少 5GB 可用空间
- **编译工具**:
  - gcc / g++ / make
  - python3-devel (或 python3-dev)
  - postgresql-devel (如使用 PostgreSQL)
- **数据库服务**:
  - MySQL 5.7+（业务数据库，多账套）
  - PostgreSQL 12+（Staging 清洗数据库，可选）
  - Redis 6.0+（缓存服务）

### 2.3 文件传输方式

选择以下任一方式将文件从外网传输到内网：

- **U盘/移动硬盘**（推荐）
- **光盘刻录**
- **安全网闸/摆渡机**
- **内网文件服务器**

---

## 三、第一阶段：外网机器准备离线包

> **执行环境**: 有外网访问的机器  
> **执行人员**: 运维/开发人员  
> **预计耗时**: 10-30 分钟（取决于网络速度）

### 3.1 获取项目代码

确保项目代码完整，包含以下关键文件：

```
myaps_api/
├── apps/                    # 应用模块
├── core/                    # 核心组件
├── globalobjects/           # 全局对象
├── project_files/           # 租户配置
├── scripts/                 # 脚本目录
├── static/                  # 前端静态资源
├── tests/                   # 测试文件
├── main.py                  # 应用入口
├── requirements.txt         # Python依赖清单 [重要]
├── .env.example             # 环境变量模板 [重要]
└── .offline_dev/            # 本手册所在目录
    └── to_linux/            # Linux迁移工具
        ├── README.md        # 本手册
        ├── scripts/         # 辅助脚本
        │   ├── download_packages.sh      # 下载脚本
        │   ├── install_packages.sh       # 内网安装脚本
        │   └── setup_env.sh              # 环境配置向导
        └── packages/        # 离线包存放目录（自动生成）
```

### 3.2 下载 Python 依赖包

```bash
# 进入项目目录
cd /path/to/myaps_api

# 执行下载脚本
bash .offline_dev/to_linux/scripts/download_packages.sh

# 使用国内镜像加速（推荐）
INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  bash .offline_dev/to_linux/scripts/download_packages.sh
```

### 3.3 验证下载结果

下载完成后，检查 `.offline_dev/to_linux/packages/` 目录：

```bash
# 查看下载的包数量
ls .offline_dev/to_linux/packages/*.whl .offline_dev/to_linux/packages/*.tar.gz | wc -l

# 查看清单文件
cat .offline_dev/to_linux/packages/MANIFEST.txt
```

### 3.4 打包待传输文件

将整个项目目录打包，准备传输到内网：

```bash
# 打包整个项目
tar -czf myaps_api_offline_linux.tar.gz myaps_api/
```

---

## 四、第二阶段：内网机器部署

> **执行环境**: 无外网访问的内网 Linux 机器  
> **执行人员**: 内网运维/开发人员  
> **预计耗时**: 15-30 分钟

### 4.1 安装 Python

**如果内网机器已安装 Python 3.11+，请跳过此步骤。**

1. 准备 Python 源码包（在外网下载）：
   - 官网: https://www.python.org/downloads/source/
   - 下载: `Python-3.12.x.tar.xz`

2. 在内网机器编译安装：
   ```bash
   # 解压
   tar -xJf Python-3.12.x.tar.xz
   cd Python-3.12.x
   
   # 配置
   ./configure --prefix=/usr/local/python3.12 --enable-optimizations
   
   # 编译（使用多核加速）
   make -j$(nproc)
   
   # 安装
   sudo make install
   
   # 创建软链接
   sudo ln -sf /usr/local/python3.12/bin/python3.12 /usr/bin/python3
   sudo ln -sf /usr/local/python3.12/bin/pip3.12 /usr/bin/pip3
   ```

3. 验证安装：
   ```bash
   python3 --version
   pip3 --version
   ```

### 4.2 安装编译依赖

某些 Python 包需要编译环境：

```bash
# CentOS/RHEL
sudo yum install -y gcc make cmake \
  python3-devel postgresql-devel mysql-devel \
  libffi-devel openssl-devel

# Ubuntu/Debian
sudo apt-get install -y build-essential \
  python3-dev libpq-dev libmysqlclient-dev \
  libffi-dev libssl-dev
```

### 4.3 解压项目文件

将传输过来的项目文件解压到目标目录，例如：

```bash
tar -xzf myaps_api_offline_linux.tar.gz -C /opt/
cd /opt/myaps_api
```

### 4.4 安装离线依赖

#### 方式 A：使用自动安装脚本（推荐）

```bash
# 进入项目目录
cd /opt/myaps_api

# 运行安装脚本
bash .offline_dev/to_linux/scripts/install_packages.sh
```

脚本会自动完成：
- 检查 Python 环境
- 创建虚拟环境 (`venv`)
- 从离线包安装所有依赖
- 验证关键包安装状态

#### 方式 B：手动安装

如果脚本执行失败，可手动执行：

```bash
# 1. 创建虚拟环境
cd /opt/myaps_api
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 升级 pip
pip install --upgrade pip --no-index \
  --find-links=.offline_dev/to_linux/packages

# 4. 安装依赖
pip install --no-index \
  --find-links=.offline_dev/to_linux/packages \
  -r requirements.txt
```

### 4.5 配置环境变量

#### 方式 A：使用配置向导（推荐）

```bash
cd /opt/myaps_api
bash .offline_dev/to_linux/scripts/setup_env.sh
```

按提示输入内网数据库连接信息。

#### 方式 B：手动配置

1. 复制环境模板：
   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件：
   ```ini
   # 应用配置
   PORT=8000
   HOST=0.0.0.0

   # MySQL 数据库（内网地址）
   MYAPS_DB_HOST=192.168.1.100
   MYAPS_DB_PORT=3306
   MYAPS_DB_USER=root
   MYAPS_DB_PASSWORD=your_password
   MYAPS_DB_SET=db1,db2
   MYAPS_MAIN_DB=db1

   # PostgreSQL（可选）
   THIS_DB_HOST=192.168.1.100
   THIS_DB_PORT=5432
   THIS_DB_USER=postgres
   THIS_DB_PASSWORD=your_password
   THIS_DB_NAME=appsmith

   # Redis
   REDIS_HOST=192.168.1.100
   REDIS_PORT=6379

   # 项目配置
   PROJECT_DIR=HACYXS
   PROJECT_JSON=dev
   ```

### 4.6 启动服务

#### 开发模式

```bash
cd /opt/myaps_api

# 方式1：使用 uvicorn 直接启动
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 方式2：使用项目自带的脚本
./scripts/dev_server.sh start
```

#### 生产模式（Systemd 服务）

创建 systemd 服务文件：

```bash
sudo tee /etc/systemd/system/myaps-api.service > /dev/null <<EOF
[Unit]
Description=MyAPS API Service
After=network.target

[Service]
Type=simple
User=myaps
WorkingDirectory=/opt/myaps_api
Environment="PATH=/opt/myaps_api/venv/bin"
ExecStart=/opt/myaps_api/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动服务
sudo systemctl daemon-reload
sudo systemctl enable myaps-api
sudo systemctl start myaps-api
```

### 4.7 验证部署

1. **访问 API 文档**：
   - 打开浏览器访问: http://localhost:8000/docs
   - 或: http://localhost:8000/redoc

2. **检查服务状态**：
   ```bash
   ./scripts/dev_server.sh status
   # 或
   sudo systemctl status myaps-api
   ```

3. **查看日志**：
   ```bash
   ./scripts/dev_server.sh logs
   # 或查看 logs/ 目录下的日志文件
   tail -f logs/app.log
   ```

---

## 五、常见问题排查

### 5.1 依赖安装失败

**现象**: `pip install` 报错，提示找不到某些包或编译失败

**解决步骤**:

1. 检查离线包是否完整：
   ```bash
   ls .offline_dev/to_linux/packages/*.whl | wc -l
   ```

2. 确认 Python 版本与打包时一致：
   ```bash
   python3 --version
   ```

3. 安装编译依赖：
   ```bash
   # CentOS/RHEL
   sudo yum install -y gcc make python3-devel postgresql-devel
   
   # Ubuntu/Debian
   sudo apt-get install -y build-essential python3-dev libpq-dev
   ```

4. 手动安装缺失的包：
   ```bash
   pip install --no-index \
     --find-links=.offline_dev/to_linux/packages \
     包名
   ```

### 5.2 数据库连接失败

**现象**: 启动时报错 `Connection refused` 或 `Access denied`

**检查清单**:

- [ ] MySQL/PostgreSQL/Redis 服务是否已启动
- [ ] `.env` 中的数据库地址、端口是否正确
- [ ] 防火墙是否放行了数据库端口
- [ ] 数据库用户是否有相应权限
- [ ] 数据库是否已创建（首次部署需要手动建库）

### 5.3 端口被占用

**现象**: `Address already in use`

```bash
# 查看端口占用
lsof -i :8000
netstat -tunlp | grep 8000

# 结束占用进程
kill -9 <PID>
```

### 5.4 权限问题

**现象**: 日志或存储目录写入失败

**解决**:

```bash
# 确保目录可写
chmod -R 755 logs/ storage/
chown -R $(whoami) logs/ storage/
```

### 5.5 虚拟环境激活失败

**现象**: `source venv/bin/activate` 执行无反应

**解决**:

```bash
# 使用完整路径调用
/opt/myaps_api/venv/bin/python -m uvicorn main:app

# 或手动设置 PATH
export PATH=/opt/myaps_api/venv/bin:$PATH
```

---

## 六、附录

### 附录 A：项目目录结构

```
myaps_api/
├── apps/                           # 应用模块
│   ├── common/                     # 通用模块（监控、帮助）
│   ├── data_opt/                   # 数据操作模块
│   └── io_api/                     # I/O API 模块
├── core/                           # 核心组件
│   ├── app.py                      # FastAPI 应用工厂
│   ├── database.py                 # 数据库配置
│   ├── settings.py                 # 应用设置
│   └── middleware.py               # 中间件
├── globalobjects/                  # 全局对象管理
│   └── logger/                     # 统一日志系统
├── project_files/                  # 租户配置目录
├── scripts/                        # 脚本目录
│   ├── dev_server.sh               # 开发服务管理
│   └── deploy/                     # 部署脚本
├── static/                         # 前端静态资源
├── tests/                          # 测试文件
├── main.py                         # 应用入口
├── requirements.txt                # 依赖清单
├── .env                            # 环境变量配置
└── .offline_dev/                   # 离线迁移工具
    └── to_linux/                   # Linux迁移工具
        ├── README.md               # 本手册
        ├── scripts/                # 辅助脚本
        └── packages/               # 离线依赖包
```

### 附录 B：关键配置文件说明

| 文件 | 用途 | 是否必须修改 |
|------|------|-------------|
| `.env` | 环境变量配置 | 是 |
| `requirements.txt` | Python 依赖清单 | 否 |
| `core/settings.py` | 应用设置 | 一般不需要 |
| `core/database.py` | 数据库连接配置 | 一般不需要 |

### 附录 C：常用命令速查

```bash
# 启动开发服务器
./scripts/dev_server.sh start

# 停止服务
./scripts/dev_server.sh stop

# 重启服务
./scripts/dev_server.sh restart

# 查看状态
./scripts/dev_server.sh status

# 查看日志
./scripts/dev_server.sh logs

# 使用 uvicorn 直接启动
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 运行测试
python -m pytest tests/ -v

# 数据库迁移
python scripts/migrate/auto_migrate.py
```

### 附录 D：Systemd 服务管理

```bash
# 启动服务
sudo systemctl start myaps-api

# 停止服务
sudo systemctl stop myaps-api

# 重启服务
sudo systemctl restart myaps-api

# 查看状态
sudo systemctl status myaps-api

# 查看日志
sudo journalctl -u myaps-api -f

# 开机自启
sudo systemctl enable myaps-api

# 禁用自启
sudo systemctl disable myaps-api
```

### 附录 E：联系与支持

- **项目文档**: 参见项目根目录 `AGENTS.md`
- **API 文档**: 启动后访问 http://localhost:8000/docs
- **日志目录**: `logs/`

---

## 迁移检查清单

在迁移完成后，请逐项确认：

- [ ] Python 3.11+ 已安装
- [ ] 编译工具已安装（gcc, make, python3-devel）
- [ ] 项目文件完整复制到内网机器
- [ ] 离线依赖包完整（`.offline_dev/to_linux/packages/`）
- [ ] 虚拟环境创建成功（`venv/`）
- [ ] 所有依赖安装成功（`pip list` 验证）
- [ ] `.env` 文件已配置内网数据库连接
- [ ] MySQL 服务可连接
- [ ] PostgreSQL 服务可连接（如使用）
- [ ] Redis 服务可连接
- [ ] 服务可正常启动
- [ ] API 文档可访问（http://localhost:8000/docs）
- [ ] 日志正常输出

---

**文档结束**