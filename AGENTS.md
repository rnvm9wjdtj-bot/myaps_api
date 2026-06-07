# MyAPS API - 开发者指南

本文档为代码助手（如华为云CodeArts代码智能体）提供项目开发所需的关键信息，包括构建命令、代码风格指南和最佳实践。

## 项目概述

MyAPS API 是一个基于FastAPI的企业级数据操作平台，支持数据清洗、监控、WebSocket通信和定时任务调度。

**技术栈：**
- **后端框架**: FastAPI (>=0.110.0)
- **异步服务器**: Uvicorn (>=0.29.0)
- **数据库ORM**: Tortoise-ORM (>=1.1.7)
- **数据验证**: Pydantic (>=2.0.0)
- **前端**: 原生HTML/JS + Bootstrap CSS

## 统一日志系统

项目使用统一的日志系统（`globalobjects/logger/`），替代原有的logger.py和logger_v2.py。

### 特性
- 异步写入，不阻塞业务线程
- 多目标输出（控制台、文件、数据库、WebSocket）
- 敏感信息自动脱敏
- 日期前缀文件轮转
- API完全向后兼容

### 使用方法
```python
from globalobjects import logger

# 基本日志
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.exception("异常信息")  # 自动捕获异常堆栈

# 业务便捷方法
logger.success("推送数据", "单号001", "共5条")
logger.fail("查询失败", "表A", "连接超时")
logger.start("同步任务", "账套A01")
logger.stop("同步任务", "账套A01")
logger.query("用户表", count=100)
logger.insert("日志表", count=50)

# 配置
logger.set_level("DEBUG")
logger.set_db_initialized(True)
```

### 环境变量配置
```bash
LOG_LEVEL=INFO              # 日志级别
LOG_DIR=logs               # 日志目录
TO_CONSOLE=true            # 输出到控制台
TO_FILE=true               # 输出到文件
TO_DATABASE=true           # 写入数据库
LOG_STACK_TRACE=false      # 是否启用调用栈追踪
```

### 旧版本备份
- `logger_v1_backup.py` - 原logger.py备份
- `logger_v2_backup.py` - 原logger_v2.py备份

## 构建和运行命令

### 开发环境运行
```bash
# 启动开发服务器（默认端口8001）
./scripts/dev_server.sh start

# 查看状态
./scripts/dev_server.sh status

# 停止服务
./scripts/dev_server.sh stop

# 重启服务
./scripts/dev_server.sh restart

# 查看日志
./scripts/dev_server.sh logs
./scripts/dev_server.sh logs -f  # 实时查看

# 清除Python缓存
./scripts/dev_server.sh clear_cache
```

### 直接运行
```bash
# 使用uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000

# 带热重载
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker 运行

#### 方式一：Docker Compose 部署（推荐）

**生产部署（从 Docker Hub 拉取）：**
```bash
# 使用 Docker Hub 镜像（host 网络模式）
DOCKER_IMAGE=qsct/myaps-api:master docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

**本地构建部署：**
```bash
# 本地构建并部署
docker-compose up -d --build

# 重新构建特定服务
docker-compose build app
docker-compose up -d app
```

**镜像说明：**
- Docker Hub 镜像：`qsct/myaps-api:master`
- 本地镜像：`myaps_api:latest`
- 网络模式：全部使用 `host` 模式，统一通过 `localhost` 访问各服务
- 配置文件挂载：自动根据 `.env` 中的 `PROJECT_DIR` 挂载对应租户配置目录

#### 方式二：Docker Run 部署

```bash
# 启动 Redis（host 网络模式）
docker run -d \
  --name myaps_redis \
  --network host \
  -v redis_data:/data \
  redis:7-alpine \
  redis-server --appendonly yes

# 启动 PostgreSQL（host 网络模式）
docker run -d \
  --name myaps_postgres \
  --network host \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=appsmith \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:16-alpine

# 启动 App（host 网络模式）
docker run -d \
  --name myaps-api \
  --network host \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/storage:/app/storage \
  -v $(pwd)/project_files/${PROJECT_DIR}:/app/project_files/${PROJECT_DIR} \
  --env-file .env \
  qsct/myaps-api:master
```

#### 方式三：单独构建
```bash
# 构建镜像
docker build -t myaps-api .

# 运行容器（不推荐，缺少依赖服务）
docker run -p 8000:8000 myaps-api
```

### 生产部署
```bash
# 使用Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 使用配置文件
gunicorn -c scripts/deploy/gunicorn.conf.py main:app
```

## 测试命令

### 运行所有测试
```bash
# 在项目根目录运行
python -m pytest tests/ -v

# 或直接使用pytest
pytest tests/ -v
```

### 运行单个测试文件
```bash
# 测试统一数据入口
python -m pytest tests/test_unified_router.py -v

# 测试业务规则
python -m pytest tests/test_business_rules.py -v

# 测试日志系统
python -m pytest tests/test_logger.py -v
```

### 运行单个测试类
```bash
# 测试特定的测试类
python -m pytest tests/test_unified_router.py::TestIsStagingMode -v
python -m pytest tests/test_unified_router.py::TestMapStagingResponseToDirect -v
```

### 运行单个测试方法
```bash
# 测试特定的测试方法
python -m pytest tests/test_unified_router.py::TestIsStagingMode::test_staging_mode_with_reserved_value -v
```

### 测试标记
项目使用pytest标记：
- `@pytest.mark.asyncio` - 异步测试标记
- 无其他特殊标记

### 测试覆盖率（如需要）
```bash
# 安装pytest-cov
pip install pytest-cov

# 运行测试并计算覆盖率
pytest --cov=. --cov-report=html tests/
```

## 代码风格指南

### Python代码风格
项目遵循PEP 8标准，但没有配置正式的lint工具。建议遵循以下约定：

#### 导入顺序
```python
# 1. 标准库导入
import os
import sys
from pathlib import Path

# 2. 第三方库导入
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
import pandas as pd

# 3. 本地应用导入
from core.app import create_app
from core.settings import PORT
from apps.io_api.routers import rt as io_rt
```

#### 命名约定
- **变量/函数**: `snake_case`
- **常量**: `UPPER_CASE_WITH_UNDERSCORES`
- **类名**: `PascalCase`
- **模块/包**: `snake_case`
- **私有成员**: `_private_variable` 或 `__really_private`

#### 类型提示
使用Python类型提示：
```python
from typing import Optional, List, Dict, Any

def process_data(
    data: List[Dict[str, Any]],
    config: Optional[Dict] = None
) -> Dict[str, Any]:
    """处理数据的函数文档字符串"""
    pass
```

#### FastAPI特定约定
1. **路由函数**: 使用异步(async/await)
2. **Pydantic模型**: 使用BaseModel派生
3. **API响应**: 统一返回JSON格式
4. **错误处理**: 使用FastAPI异常处理器

#### 数据库相关
- **表名**: `snake_case` (如 `t_material_staging`)
- **列名**: `PascalCase` (如 `MaterialNo`)
- **注意**: 数据库字段名大小写敏感

### API设计规范

#### 路由定义
```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api", tags=["materials"])

@router.post("/upload", response_model=UploadResponse)
async def upload_materials(
    data: UploadRequest,
    db_name: str = Query(..., description="数据库名称")
):
    """上传物料数据"""
    pass
```

#### 请求/响应模型
```python
from pydantic import BaseModel
from typing import Optional

class UploadRequest(BaseModel):
    file_content: str
    file_name: str
    overwrite: bool = False

class UploadResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None
    meta: Optional[Dict] = None
```

#### API字段名
- **POST字段名**: 使用小写格式 (如 `file_content`, `db_name`)
- **Query参数**: 使用snake_case (如 `db_name`, `overwrite`)
- **路径参数**: 使用snake_case (如 `{material_id}`)

### 错误处理

#### HTTP状态码
- `200`: 成功
- `400`: 请求参数错误
- `401`: 未授权
- `403`: 禁止访问
- `404`: 资源不存在
- `500`: 服务器内部错误

#### 错误响应格式
```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "字段验证失败",
        "details": {
            "field_name": "具体错误信息"
        }
    }
}
```

### 日志记录
项目使用loguru或原生logging：
```python
from globalobjects import logger

logger.info("操作成功")
logger.warning("警告信息")
logger.error("错误信息", exc_info=True)
```

## 项目结构

```
myaps_api/
├── apps/                    # 应用模块
│   ├── common/             # 通用模块（监控、帮助）
│   ├── data_opt/           # 数据操作模块
│   └── io_api/             # I/O API模块
├── core/                   # 核心组件
│   ├── app.py             # FastAPI应用工厂
│   ├── database.py        # 数据库配置
│   ├── settings.py        # 应用设置
│   └── middleware.py      # 中间件
├── globalobjects/          # 全局对象管理
├── scripts/               # 脚本目录
│   ├── dev_server.sh     # 开发服务器管理
│   ├── deploy/           # 部署配置
│   └── migrate/          # 数据库迁移
├── static/               # 静态文件
├── storage/             # 数据存储
├── tests/               # 测试文件
├── .env                 # 环境变量配置
├── main.py              # 应用入口
└── requirements.txt     # 依赖包
```

## 开发工作流

### 1. 环境设置
```bash
# 创建虚拟环境（如不存在）
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 代码规范检查
项目目前没有配置lint工具，建议添加以下工具：

**可选配置（如需要）：**
```bash
# 安装格式化工具
pip install black isort ruff

# 代码格式化
black .
isort .
ruff check --fix

# 类型检查（如需）
pip install mypy
mypy .
```

### 3. 运行测试
```bash
# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/test_unified_router.py

# 运行带详细输出
pytest -v

# 运行并输出覆盖率
pytest --cov=. --cov-report=html
```

### 4. 代码提交前检查
1. 确保测试通过
2. 检查代码格式（如配置了lint工具）
3. 更新相关文档
4. 验证API接口

## 数据库操作

### 迁移脚本
```bash
# 数据库迁移
python scripts/migrate/auto_migrate.py

# Tortoise-ORM迁移
python scripts/migrate/migrate_with_tortoise.py
```

### 模型定义
```python
from tortoise.models import Model
from tortoise import fields

class MaterialStaging(Model):
    """物料暂存表"""
    id = fields.IntField(pk=True)
    MaterialNo = fields.CharField(max_length=50)
    MaterialName = fields.CharField(max_length=255)
    # 注意：列名使用PascalCase
    
    class Meta:
        table = "t_material_staging"  # 表名使用snake_case
```

## 前端约定

### HTML/JS约定
1. **样式**: 使用Bootstrap 5.x
2. **图标**: 使用Bootstrap Icons (`bi-*`)
3. **字体**: 整个页面统一使用等宽字体
4. **布局**: 偏好卡片布局而非列表布局
5. **颜色**: 特定颜色使用十六进制值（如`#ff9300`）

### 错误提示
1. **布局**: 横版布局，错误类型横向排列
2. **样式**: 统一错误高亮提示样式
3. **交互**: 手型光标用于可交互元素，插入光标用普通指针

### 验证规则显示
- 必填字段、枚举字段、业务规则块左右排列
- 内容在每个块内垂直分布
- 必填星号紧贴字段名右侧

## 部署配置

### 环境变量
复制`.env.example` 文件并按实际环境配置：
```bash
cp .env.example .env
```

#### 应用配置
```bash
PORT=8000                    # 生产环境端口（开发环境默认 8001）
HOST=0.0.0.0
LOG_LEVEL=INFO
TIMEZONE=Asia/Shanghai
```

#### 数据库配置
**MySQL（业务数据库 - 多账套支持）：**
```bash
MYAPS_DB_HOST=localhost
MYAPS_DB_PORT=3333
MYAPS_DB_USER=your_db_user
MYAPS_DB_PASSWORD=your_db_password
MYAPS_DB_SET=db1,db2         # 多账套数据库列表，逗号分隔
MYAPS_MAIN_DB=db1            # 主账套数据库
```

**PostgreSQL（Staging 清洗数据库）：**
```bash
THIS_DB_HOST=localhost
THIS_DB_PORT=5432
THIS_DB_USER=postgres
THIS_DB_PASSWORD=your_password
THIS_DB_NAME=appsmith        # Staging 数据库名
```

#### Redis 配置
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=              # 可选
```

#### 功能开关
```bash
TURNON_BINLOG_LISTENER=False  # 是否启用 binlog 监听
TRUNON_SCHEDULER=False        # 是否启用定时任务调度
```

#### Staging 模式配置
```bash
STAGING_DB_NAME=--s           # 用于数据清洗模式的特殊数据库标识（默认--s）
                              # 当 db_name 参数为此值时，启用 PostgreSQL 清洗流程
```

#### 项目配置
```bash
PROJECT_DIR=HACYXS            # 租户项目目录名（对应 project_files/ 下的子目录）
PROJECT_JSON=dev              # 配置文件名（不含.json 后缀）
```

### Gunicorn配置
生产环境使用Gunicorn多进程配置：
```python
# scripts/deploy/gunicorn.conf.py
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
```

## 监控和调试

### 监控功能
- HTTP请求监控（`HTTPMonitorMiddleware`）
- 资源使用监控
- 数据库监控（binlog监听）
- 定时任务监控

### 调试技巧
1. 使用`scripts/dev_server.sh logs -f`实时查看日志
2. 检查`logs/`目录下的日志文件
3. 使用FastAPI自动生成的API文档（`/docs`和`/redoc`）

## 华为云CodeArts集成

项目已配置华为云CodeArts Doer：
- 配置文件位于`.codeartsdoer/`
- 技能配置在`.codeartsdoer/skills/`
- 规范配置在`.codeartsdoer/specs/`

## 数据库连接池管理

项目实现了增强的数据库连接池管理功能，解决连接泄漏问题。

### 功能特性

- **状态管理**：连接池生命周期状态管理（OPEN/CLOSED/REFRESHING）
- **健康检查**：定期检查连接健康状态，支持超时控制和重试机制
- **安全刷新**：刷新前标记状态，刷新后健康验证，失败时回滚
- **泄漏检测**：基于历史数据分析使用趋势，分级告警（WARNING/CRITICAL/EMERGENCY）
- **后台清理**：定期清理异常连接，处理事件循环冲突

### 使用方法

```python
from globalobjects.db_pool import get_enhanced_db_manager

# 获取增强管理器
manager = get_enhanced_db_manager("my_connection")

# 检查健康状态
health_result = await manager.check_health()
if health_result.is_healthy:
    print("连接健康")

# 获取连接（自动检查状态）
async with manager.get_connection() as conn:
    result = await conn.execute_query("SELECT * FROM users")

# 刷新连接
success = await manager.refresh_connection(fast_mode=True)

# 获取连接池状态
status = await manager.get_connection_pool_status()
print(f"使用率: {status.usage_rate}%")
```

### 启动监控

```python
from globalobjects.db_pool import start_pool_monitoring

# 启动连接池监控
await start_pool_monitoring(["db1", "db2", "db3"])
```

### 环境变量配置

```bash
USE_ENHANCED_POOL=true            # 是否使用增强的连接池管理
POOL_STATE_LOCK_TIMEOUT=10.0      # 状态锁超时时间（秒）
HEALTH_CHECK_TIMEOUT=5.0          # 健康检查超时时间（秒）
CLEANUP_INTERVAL=300              # 后台清理任务间隔（秒）
LEAK_WARNING_THRESHOLD=80         # 泄漏警告阈值（百分比）
LEAK_CRITICAL_THRESHOLD=90        # 泄漏严重阈值（百分比）
LEAK_EMERGENCY_THRESHOLD=95       # 泄漏紧急阈值（百分比）
```

### 相关文档

- 模块文档：`globalobjects/db_pool/README.md`
- 使用示例：`globalobjects/db_pool/examples.py`
- 部署指南：`docs/db_pool_deployment_guide.md`

## 注意事项

1. **代码质量**: 确保新代码遵循项目现有模式
2. **API兼容性**: 修改API时保持向后兼容
3. **错误处理**: 所有API端点应有适当的错误处理
4. **日志记录**: 重要操作需记录日志
5. **测试覆盖**: 新功能应包含单元测试
6. **配置管理**: 避免硬编码，使用环境变量和配置对象
7. **数据库命名**: 表名用snake_case，列名用PascalCase，注意大小写敏感

## 故障排除

### 常见问题

#### 1. 端口占用
**症状**：启动时提示 `Address already in use`
**解决**：修改 `.env` 中的 `PORT` 配置，或停止占用端口的进程
```bash
# 查看端口占用
lsof -i :8000

# 停止占用进程
kill -9 <PID>
```

#### 2. 数据库连接失败
**症状**：启动时提示数据库连接超时或认证失败
**解决**：
- 检查 `.env` 中的数据库配置是否正确
- 确认数据库服务已启动
- 检查防火墙规则
- MySQL 和 PostgreSQL 需分别配置

#### 3. 依赖安装失败
**症状**：`pip install` 时下载失败或编译错误
**解决**：
- 使用国内 pip 源（阿里云、清华源）
- 使用项目提供的离线包（如配置）
- 确保系统依赖已安装（gcc, libpq-dev 等）

#### 4. 权限问题
**症状**：日志或存储目录写入失败
**解决**：
```bash
# 确保目录可写
chmod -R 755 logs/ storage/
chown -R $(whoami) logs/ storage/
```

#### 5. Docker 部署问题
**症状**：容器启动失败或无法访问
**解决**：
- 确认 Docker 和 Docker Compose 版本（Docker 20.10+, Docker Compose V2）
- 检查 `.env` 文件配置是否完整
- 查看容器日志：`docker-compose logs -f app`
- 确认 host 网络模式未与其他服务冲突
- 验证配置文件挂载：`docker exec myaps-api ls /app/project_files/`

### Tortoise ORM 初始化竞态条件

**问题描述**：
启动时偶尔出现"Tortoise ORM 初始化超时"错误，即使数据库可连接。

**根本原因**：
FastAPI启动时，`register_tortoise`异步初始化与`lifespan`检查存在竞态条件：
- PostgreSQL首次连接可能需要3-5秒
- 启动事件和lifespan并行执行
- 早期请求到达时，ORM可能未完全初始化

**解决方案**（已实施）：
使用**事件驱动的智能等待机制**（非硬编码等待）：

1. **DatabaseInitManager** (`core/db_init_manager.py`)
   - 事件驱动：初始化完成后主动通知等待者
   - 精确计时：记录实际初始化耗时
   - 状态追踪：监控初始化进度

2. **启动事件通知** (`core/database.py`)
   - `@app.on_event("startup")` 中标记初始化完成
   - 通知所有等待的协程

3. **智能等待** (`core/lifespan.py`, `apps/common/utils/db_helpers.py`)
   - 使用`asyncio.Event`而非轮询
   - 实际等待时间 = 数据库真实初始化时间
   - 超时保护：最多等待30秒

**对比传统方案**：
```python
# ❌ 旧方案：硬编码轮询
for i in range(20):  # 固定等待10秒
    await asyncio.sleep(0.5)
    if Tortoise._inited:
        break

# ✅ 新方案：事件驱动
result = await db_init_manager.wait_for_init(max_wait=30.0)
# 实际等待时间 = 数据库初始化实际耗时（通常1-3秒）
```

**相关配置**：
- `STAGING_DB_NAME`: 清洗模式数据库标识（默认`--s`）
- `THIS_DB_*`: PostgreSQL连接配置

### 调试指南
如需调试指导（如断点设置），请参考：
1. VS Code调试配置在`.vscode/`
2. 使用Python内置`pdb`模块
3. 或使用更高级的调试器如`debugpy`

---

**最后更新**: 2026-06-04  
**维护者**: MyAPS 开发团队  
**版本**: 2.0.0

## 附录：快速参考

### 核心目录
- `/opt/myaps_api/scripts/deploy_docker/` - Docker 部署脚本
- `/opt/myaps_api/project_files/` - 租户配置目录
- `/opt/myaps_api/static/` - 前端静态资源

### 常用命令速查
```bash
# 开发环境
./scripts/dev_server.sh start|stop|restart|status|logs

# Docker 部署
DOCKER_IMAGE=qsct/myaps-api:master docker-compose up -d
docker-compose logs -f app

# 测试
pytest tests/ -v
pytest tests/test_unified_router.py::TestIsStagingMode -v
```

### 关键配置
- **开发端口**: 8001
- **生产端口**: 8000
- **Staging 标识**: `--s`
- **Docker Hub**: `qsct/myaps-api:master`
- **网络模式**: host