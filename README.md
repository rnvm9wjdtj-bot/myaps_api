# MyAPS API

MyAPS API 是一个基于 FastAPI 的企业级数据操作平台，包含数据接口、数据清洗、监控、WebSocket 通信、日志与定时任务等能力。

## 项目概览

### 目录结构

```text
myaps_api/
├── apps/                 # 业务模块
│   ├── common/           # 监控、帮助、通用工具
│   ├── data_opt/         # 数据操作、清洗、binlog、调度
│   └── io_api/           # 对外 API 接口
├── core/                 # 应用工厂、配置、数据库、生命周期
├── globalobjects/        # 全局对象、日志、数据库管理
├── static/               # 前端静态资源
├── scripts/              # 开发、部署、迁移脚本
├── tests/                # 自动化测试
├── main.py               # 应用入口
├── requirements.txt      # Python 依赖
└── .env.example          # 环境变量示例
```

### 技术栈

- FastAPI
- Uvicorn
- Tortoise ORM
- Pydantic
- MySQL / PostgreSQL / SQLite
- Redis

## 快速开始

### 1. 准备虚拟环境

项目依赖当前已安装在仓库内虚拟环境 `venv` 中。

Linux / macOS:

```bash
source venv/bin/activate
```

或者直接使用虚拟环境解释器执行命令：

```bash
./venv/bin/python --version
```

### 2. 准备环境变量

复制示例文件并按实际环境填写：

```bash
cp .env.example .env
```

至少需要确认以下配置：

```bash
PROJECT_DIR=YOUR_PROJECT_DIR
MYAPS_DB_HOST=localhost
MYAPS_DB_PORT=3333
MYAPS_DB_USER=your_db_user
MYAPS_DB_PASSWORD=your_db_password
MYAPS_DB_SET=db1,db2
MYAPS_MAIN_DB=db1
```

如使用 PostgreSQL staging / 清洗能力，还需要补充：

```bash
THIS_DB_HOST=localhost
THIS_DB_PORT=5432
THIS_DB_USER=postgres
THIS_DB_PASSWORD=your_password
THIS_DB_NAME=appsmith
```

### 3. 启动服务

使用项目脚本：

```bash
./scripts/dev_server.sh start
```

直接启动：

```bash
./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问服务

- 首页: `http://127.0.0.1:8000/`
- Swagger 文档: `http://127.0.0.1:8000/docs`

## 常用命令

### 测试

运行全部测试：

```bash
./venv/bin/python -m pytest tests/ -v
```

验证应用可导入：

```bash
./venv/bin/python -c "import main; print(main.app.title)"
```

### 开发脚本

```bash
./scripts/dev_server.sh start
./scripts/dev_server.sh stop
./scripts/dev_server.sh restart
./scripts/dev_server.sh status
./scripts/dev_server.sh logs
```

## 数据库配置说明

### 全局数据库账号

项目统一使用以下变量作为主数据库连接配置：

```bash
MYAPS_DB_HOST
MYAPS_DB_PORT
MYAPS_DB_USER
MYAPS_DB_PASSWORD
```

### binlog 配置说明

binlog 相关校验与参数设置逻辑当前也统一使用：

```bash
MYAPS_DB_USER
MYAPS_DB_PASSWORD
```

注意事项：

- 不再使用单独的 `MYAPS_ROOT_PASSWORD`
- binlog 相关逻辑不会再写死 `root` 用户
- 若 `MYAPS_DB_USER` 或 `MYAPS_DB_PASSWORD` 未配置，相关校验会显式失败
- 如需执行高权限 binlog 配置操作，请确保 `MYAPS_DB_USER` 对应账号本身具备所需权限

### staging / 清洗模式

- `THIS_DB_*` 用于 PostgreSQL staging 数据库配置
- `STAGING_DB_NAME` 默认为 `--s`
- 清洗模式与主业务数据库配置分离

## 监控与日志

- 实时日志与历史日志页面位于 `/monitor`
- 统一日志系统位于 `globalobjects/logger/`
- 开发期可通过 `./scripts/dev_server.sh logs -f` 查看实时日志

## 当前验证状态

在当前仓库环境下，以下命令已验证通过：

```bash
./venv/bin/python -m pytest tests/ -v
./venv/bin/python -c "import main; print(main.app.title)"
```

## 备注

- 若 `PROJECT_DIR` 未配置，应用配置加载会失败
- 若数据库或 Redis 未就绪，部分功能会在启动或运行阶段报出明确错误
- 修改数据库、binlog、生命周期逻辑后，建议至少重新执行一次测试和导入校验
