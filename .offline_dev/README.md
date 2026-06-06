# MyAPS API - 完全离线环境迁移手册

> **版本**: 2.0  
> **适用场景**: 无外网访问的内网 Windows 开发环境  
> **最后更新**: 2026-06-06

---

## 🎉 新增功能：可视化 GUI 工具

本项目现在提供一个基于 Python tkinter 的可视化界面工具，让离线迁移更加简单直观！

| 方式 | 推荐人群 | 说明 |
|------|----------|------|
| **GUI 工具** | 所有用户 | 可视化操作，推荐优先使用 |
| **命令行脚本** | 高级用户/CI | 保留原有的命令行方式 |

### 快速启动 GUI

**Windows**:
```cmd
.offline_dev\gui\run_gui.bat
```

**Linux/macOS**:
```bash
bash .offline_dev/gui/run_gui.sh
```

详细说明请查看: [GUI_README.md](./GUI_README.md)

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

将 MyAPS API 项目从当前开发环境（macOS/Linux，有外网）迁移到**完全无外网访问**的内网 Windows 环境继续开发。

### 1.2 迁移流程概览

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   外网机器       │     │   文件传输       │     │   内网Windows   │
│  (准备离线包)    │────▶│  (U盘/光盘/网闸) │────▶│  (部署运行)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 1.3 需要迁移的内容

| 类别 | 内容 | 说明 |
|------|------|------|
| 源代码 | `myaps_api/` 整个项目目录 | 包含所有 Python 代码、前端资源、配置文件 |
| 依赖包 | `.offline_dev/packages/` 目录 | 所有 Python 第三方库的离线安装包 |
| 数据库 | MySQL / PostgreSQL / Redis | 需在内网单独部署或已有 |
| 环境配置 | `.env` 文件 | 内网数据库连接等配置 |

---

## 二、前置准备

### 2.1 外网机器要求

- **操作系统**: Linux / macOS / Windows（有外网访问）
- **Python**: 3.11 或 3.12（**必须与内网目标机器版本一致**）
- **pip**: 最新版本
- **磁盘空间**: 至少 2GB 可用空间（用于下载依赖包）

### 2.2 内网 Windows 机器要求

- **操作系统**: Windows 10 / Windows 11 / Windows Server 2019+
- **Python**: 3.11 或 3.12（**必须与外网打包机器版本一致**）
- **内存**: 至少 4GB RAM
- **磁盘空间**: 至少 5GB 可用空间
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
├── Dockerfile               # Docker配置
└── .offline_dev/            # 本手册所在目录
    ├── README.md            # 本手册
    ├── scripts/             # 辅助脚本
    │   ├── download_packages.sh      # Linux/macOS 下载脚本
    │   ├── download_packages.ps1     # Windows PowerShell 下载脚本
    │   ├── install_packages.bat      # 内网安装脚本
    │   └── setup_env.bat             # 环境配置向导
    └── packages/            # 离线包存放目录（自动生成）
```

### 3.2 下载 Python 依赖包

#### 方式 A：Linux / macOS 执行

```bash
# 进入项目目录
cd /path/to/myaps_api

# 执行下载脚本
bash .offline_dev/scripts/download_packages.sh
```

#### 方式 B：Windows 执行

```powershell
# 进入项目目录
cd D:\path\to\myaps_api

# 执行下载脚本
.\offline_dev\scripts\download_packages.ps1
```

#### 方式 C：手动执行 pip download

如果脚本执行失败，可手动执行：

```bash
# 创建存放目录
mkdir -p .offline_dev/packages

# 下载所有依赖（包括子依赖）
pip download \
    --requirement requirements.txt \
    --dest .offline_dev/packages \
    --only-binary :all: \
    --python-version 3.12 \
    --platform win_amd64

# 补充下载源码包（部分包可能没有Windows wheel）
pip download \
    --requirement requirements.txt \
    --dest .offline_dev/packages \
    --no-binary :all:
```

### 3.3 验证下载结果

下载完成后，检查 `.offline_dev/packages/` 目录：

```bash
# 查看下载的包数量
ls .offline_dev/packages/*.whl .offline_dev/packages/*.tar.gz | wc -l

# 查看清单文件
cat .offline_dev/packages/MANIFEST.txt
```

### 3.4 打包待传输文件

将以下文件/目录打包，准备传输到内网：

```
myaps_api/                      # 整个项目目录
├── .offline_dev/packages/       # 离线依赖包 [必须]
├── requirements.txt            # 依赖清单 [必须]
├── .env.example                # 环境模板 [必须]
└── ...                         # 其他项目文件
```

打包命令示例：

```bash
# Linux/macOS
tar -czf myaps_api_offline.tar.gz myaps_api/

# Windows (PowerShell)
Compress-Archive -Path myaps_api\* -DestinationPath myaps_api_offline.zip
```

---

## 四、第二阶段：内网机器部署

> **执行环境**: 无外网访问的内网 Windows 机器  
> **执行人员**: 内网运维/开发人员  
> **预计耗时**: 15-30 分钟

### 4.1 安装 Python

**如果内网机器已安装 Python，请跳过此步骤。**

1. 提前在外网下载 Python 安装包：
   - 官网: https://www.python.org/downloads/
   - 推荐: `python-3.12.x-amd64.exe`

2. 在内网机器运行安装程序：
   - 勾选 **"Add Python to PATH"**
   - 选择 **"Customize installation"**
   - 确保勾选 **"pip"** 和 **"Add Python to environment variables"**

3. 验证安装：
   ```cmd
   python --version
   pip --version
   ```

### 4.2 解压项目文件

将传输过来的项目文件解压到目标目录，例如：

```
D:\myaps_api\
```

### 4.3 安装离线依赖

#### 方式 A：使用自动安装脚本（推荐）

```cmd
:: 进入项目目录
cd D:\myaps_api

:: 运行安装脚本
.offline_dev\scripts\install_packages.bat
```

脚本会自动完成：
- 检查 Python 环境
- 创建虚拟环境 (`venv`)
- 从离线包安装所有依赖
- 验证关键包安装状态

#### 方式 B：手动安装

如果脚本执行失败，可手动执行：

```cmd
:: 1. 创建虚拟环境
cd D:\myaps_api
python -m venv venv

:: 2. 激活虚拟环境
venv\Scripts\activate.bat

:: 3. 升级 pip
python -m pip install --upgrade pip --no-index --find-links=.offline_dev/packages

:: 4. 安装依赖
pip install --no-index --find-links=.offline_dev/packages -r requirements.txt
```

### 4.4 配置环境变量

#### 方式 A：使用配置向导（推荐）

```cmd
cd D:\myaps_api
.offline_dev\scripts\setup_env.bat
```

按提示输入内网数据库连接信息。

#### 方式 B：手动配置

1. 复制环境模板：
   ```cmd
   copy .env.example .env
   ```

2. 使用记事本或 VS Code 编辑 `.env` 文件：
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

### 4.5 启动服务

#### 开发模式

```cmd
cd D:\myaps_api

:: 方式1：使用 uvicorn 直接启动
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

:: 方式2：使用项目自带的批处理脚本
scripts\dev_server.bat start
```

#### 生产模式（Windows 服务）

项目已内置 NSSM 服务部署工具：

```cmd
:: 以管理员身份运行
cd D:\myaps_api
scripts\deploy\simple_deploy.bat
```

按菜单提示选择：
- `1` - 安装服务（在线模式，内网选此项）
- `C` - 安装服务（离线模式）

### 4.6 验证部署

1. **访问 API 文档**：
   - 打开浏览器访问: http://localhost:8000/docs
   - 或: http://localhost:8000/redoc

2. **检查服务状态**：
   ```cmd
   scripts\dev_server.bat status
   ```

3. **查看日志**：
   ```cmd
   scripts\dev_server.bat logs
   :: 或查看 logs/ 目录下的日志文件
   ```

---

## 五、常见问题排查

### 5.1 依赖安装失败

**现象**: `pip install` 报错，提示找不到某些包

**解决步骤**:

1. 检查离线包是否完整：
   ```cmd
   dir .offline_dev\packages\*.whl /s
   ```

2. 确认 Python 版本与打包时一致：
   ```cmd
   python --version
   ```

3. 部分包需要编译环境，安装 Visual Studio Build Tools：
   - 下载地址（需外网）: https://visualstudio.microsoft.com/visual-cpp-build-tools/
   - 或在内网提前准备好离线安装包

4. 手动安装缺失的包：
   ```cmd
   venv\Scripts\pip.exe install --no-index --find-links=.offline_dev\packages 包名
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

```cmd
:: 查看端口占用
netstat -ano | findstr :8000

:: 结束占用进程
taskkill /F /PID <进程ID>
```

### 5.4 编码问题

**现象**: 中文乱码或脚本执行报错

**解决**:

```cmd
:: 设置 UTF-8 编码
chcp 65001

:: 或在脚本开头添加
chcp 65001 >nul
```

### 5.5 虚拟环境激活失败

**现象**: `venv\Scripts\activate.bat` 执行无反应

**解决**:

```cmd
:: 使用完整路径调用
D:\myaps_api\venv\Scripts\python.exe -m uvicorn main:app

:: 或手动设置 PATH
set PATH=D:\myaps_api\venv\Scripts;%PATH%
```

---

## 六、附录

### 附录 A：项目目录结构

```
myaps_api/
├── apps/                           # 应用模块
│   ├── common/                     # 通用模块（监控、帮助）
│   │   ├── help/                   # 帮助系统
│   │   ├── monitor/                # 监控模块
│   │   └── utils/                  # 通用工具
│   ├── data_opt/                   # 数据操作模块
│   │   ├── components/             # 业务组件
│   │   ├── mds/                    # MDS 数据清洗
│   │   └── utils/                  # 数据工具
│   └── io_api/                     # I/O API 模块
├── core/                           # 核心组件
│   ├── app.py                      # FastAPI 应用工厂
│   ├── database.py                 # 数据库配置
│   ├── settings.py                 # 应用设置
│   └── middleware.py               # 中间件
├── globalobjects/                  # 全局对象管理
│   └── logger/                     # 统一日志系统
├── project_files/                  # 租户配置目录
│   ├── HACYXS/                     # 示例租户
│   └── ...
├── scripts/                        # 脚本目录
│   ├── dev_server.bat              # 开发服务管理
│   ├── dev_run.bat                 # 开发运行脚本
│   └── deploy/                     # 部署脚本
├── static/                         # 前端静态资源
├── tests/                          # 测试文件
├── main.py                         # 应用入口
├── requirements.txt                # 依赖清单
├── .env                            # 环境变量配置
└── .offline_dev/                   # 离线迁移工具
    ├── README.md                   # 本手册
    ├── scripts/                    # 辅助脚本
    └── packages/                   # 离线依赖包
```

### 附录 B：关键配置文件说明

| 文件 | 用途 | 是否必须修改 |
|------|------|-------------|
| `.env` | 环境变量配置 | 是 |
| `requirements.txt` | Python 依赖清单 | 否 |
| `core/settings.py` | 应用设置 | 一般不需要 |
| `core/database.py` | 数据库连接配置 | 一般不需要 |

### 附录 C：常用命令速查

```cmd
:: 启动开发服务器
scripts\dev_server.bat start

:: 停止服务
scripts\dev_server.bat stop

:: 重启服务
scripts\dev_server.bat restart

:: 查看状态
scripts\dev_server.bat status

:: 查看日志
scripts\dev_server.bat logs

:: 使用 uvicorn 直接启动
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

:: 运行测试
venv\Scripts\python.exe -m pytest tests/ -v

:: 数据库迁移
venv\Scripts\python.exe scripts\migrate\auto_migrate.py
```

### 附录 D：Windows 服务管理

```cmd
:: 安装为 Windows 服务（管理员权限）
scripts\deploy\simple_deploy.bat

:: 或使用 sc 命令
sc create MyAPS_API binPath= "D:\myaps_api\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

:: 启动服务
sc start MyAPS_API

:: 停止服务
sc stop MyAPS_API

:: 删除服务
sc delete MyAPS_API
```

### 附录 E：联系与支持

- **项目文档**: 参见项目根目录 `AGENTS.md`
- **API 文档**: 启动后访问 http://localhost:8000/docs
- **日志目录**: `logs/`

---

## 迁移检查清单

在迁移完成后，请逐项确认：

- [ ] Python 3.11+ 已安装并配置 PATH
- [ ] 项目文件完整复制到内网机器
- [ ] 离线依赖包完整（`.offline_dev/packages/`）
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
