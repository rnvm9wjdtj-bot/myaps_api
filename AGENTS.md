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

### Docker运行
```bash
# 使用Docker Compose（包含Redis）
docker-compose up -d

# 单独构建
docker build -t myaps-api .
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
复制`.env.example`（如存在）或创建`.env`文件：
```bash
# 应用配置
PORT=8000
HOST=0.0.0.0
LOG_LEVEL=INFO

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=password
DB_NAME=myaps

# 功能开关
TURNON_BINLOG_LISTENER=False
TRUNON_SCHEDULER=False

# Staging模式配置
# 用于数据清洗模式的特殊数据库名称标识（默认--s）
STAGING_DB_NAME=--s
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
1. **端口占用**: 修改`.env`中的`PORT`配置
2. **数据库连接失败**: 检查数据库配置和环境变量
3. **依赖安装失败**: 使用离线包或调整pip源
4. **权限问题**: 确保`logs/`和`storage/`目录可写

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

**最后更新**: 2026-05-21  
**维护者**: MyAPS开发团队  
**版本**: 1.0.0