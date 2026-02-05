import os, uvicorn, asyncio#, hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
# from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from tortoise.contrib.fastapi import register_tortoise

from config.settings import TORTOISE_ORM_CONFIG, PORT, BASE_DIR, TURNON_DBMONITOR
from globalobjects import logger as log_config
from apps.io_api.routers import rt as io_rt
from apps.io_api.utils.common import register_exception_handlers
from apps.data_opt.routers import rt as do_rt
# from apps.data_opt.common import register_exception_handlers as register_data_manager_exception_handlers

# 导入全局MySQL监控实例
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from apps.data_opt.utils.scheduler import scheduler_manager

# 定义生命周期事件处理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 应用启动时执行的操作
    # 初始化统一日志系统
    log_config.initialize_logging()
    
    # 将主应用事件循环传递给调度器（在 uvicorn 启动后获取正确的事件循环）
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    if TURNON_DBMONITOR:
        mysql_monitor.start_monitoring()
        log_config.info("MySQL Binlog监控已启动")
    else:
        log_config.warning("⚠️ MySQL Binlog监控未启动\，请确认环境变量 TURNON_DBMONITOR 是否配置为期望的值")
    
    yield  # 应用运行期间
    
    # 应用关闭时执行的操作
    log_config.info("应用关闭中...")
    
    if TURNON_DBMONITOR:
        mysql_monitor.stop_monitoring()
        log_config.info("MySQL Binlog监控已停止")
    # 关闭调度器
    scheduler_manager.shutdown()
    log_config.info("定时任务管理器已关闭")
    # 关闭统一日志系统
    log_config.shutdown_logging()



# 创建FastAPI应用实例
app = FastAPI(
    title="MyAPS API",
    description="MyAPS API系统接口文档，提供物料、工作中心、工序、BOM等主数据管理，以及供应需求等生产数据管理功能。",
    version="1.0.0",
    # 配置文档页面URL，禁用默认的 Swagger UI​，防止CDN资源不稳定导致无法访问文档页
    docs_url=None,  
    redoc_url=None,
    swagger_js_url="/static/swagger/swagger-ui-bundle.js",
    swagger_css_url="/static/swagger/swagger-ui.css",
    swagger_favicon_url="/static/swagger/favicon-32x32.png",
    swagger_ui_parameters={
        "configUrl": None,
        "defaultModelsExpandDepth": 2,  # 默认展开模型深度
        "defaultModelExpandDepth": 3,  # 默认展开模型属性深度
        "displayRequestDuration": True,  # 显示请求持续时间
        "docExpansion": "list",  # 文档展开方式: 'list', 'full', 'none'
        "tryItOutEnabled": True,  # 启用"Try it out"功能
        "jsonEditor": True,  # 使用JSON编辑器编辑请求体
        "showCommonExtensions": True,  # 显示扩展字段
        "showExtensions": True,  # 显示OpenAPI扩展
        "showMutatedRequest": True  # 显示修改后的请求
    },
    lifespan=lifespan  # 使用新的生命周期事件处理器
)

# 增强OpenAPI schema配置
app.openapi_version = "3.0.2"

# 保存原始的openapi方法
original_openapi = app.openapi

# 自定义OpenAPI schema生成
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # 调用原始的openapi方法获取schema
    openapi_schema = original_openapi()
    
    # 确保所有schemas都有详细的描述和示例
    for schema_name, schema in openapi_schema.get("components", {}).get("schemas", {}).items():
        # 添加更多描述信息
        if "properties" in schema:
            for prop_name, prop in schema["properties"].items():
                # 确保每个属性都有描述
                if "description" not in prop and "title" not in prop:
                    prop["description"] = f"字段: {prop_name}"
                # 确保每个属性都有示例值
                if "example" not in prop and "examples" not in prop:
                    # 根据类型设置默认示例值
                    if prop.get("type") == "string":
                        prop["example"] = f"示例{prop_name}"
                    elif prop.get("type") == "integer":
                        prop["example"] = 1
                    elif prop.get("type") == "number":
                        prop["example"] = 1.0
                    elif prop.get("type") == "boolean":
                        prop["example"] = True
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# 设置自定义的OpenAPI schema生成函数
app.openapi = custom_openapi


# 定义安全验证验证中间件

IP_WHITELIST = os.getenv("IP_WHITELIST", "")
API_KEY = os.getenv("API_KEY", "")      

if IP_WHITELIST or API_KEY:
    IP_WHITELIST = os.getenv("IP_WHITELIST", "").split(",")
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # 对GET和OPTIONS方法直接放行
        if request.method in ["GET", "OPTIONS"]:
            return await call_next(request)

        # 允许查阅文档等无需认证的请求
        url_path = request.url.path
        if url_path in ["/docs", "/redoc", "/openapi.json"] or url_path.startswith("/static/swagger"):
            return await call_next(request)
        
        # 检查IP是否在白名单中
        client_ip = request.client.host
        if client_ip in ["127.0.0.1", "localhost"] or client_ip in IP_WHITELIST:
            return await call_next(request)
            
        # 若不在IP白名单则需要认证请求头X-API-Key
        if request.headers.get("X-API-Key") == API_KEY:
            return await call_next(request)

        return JSONResponse(status_code=200, content={"status_code": 403, "success": 0, "meta": {}, "message": "Forbidden: Invalid or missing API Key"})


# 配置CORS中间件解决跨域访问问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名列表
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)



# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 覆写原有文档页面路由函数，所有静态资源采用本地文件
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon.png",
        swagger_ui_parameters=app.swagger_ui_parameters
    )


# 注册自定义的异常处理器
register_exception_handlers(app)
# register_data_manager_exception_handlers(app)

# 包含子路由
app.include_router(io_rt, prefix="/api", tags=[])
app.include_router(do_rt, prefix="/do", tags=[])


# 根路由
@app.get("/")
async def read_root():
    return {
        "message": "Welcome to MyAPI",
        "version": "1.0.0",
        "status": "running"
    }

# 注册Tortoise ORM
register_tortoise(
    app = app,
    config=TORTOISE_ORM_CONFIG,
    # modules={"models": ["project_code.models"]},
    # generate_schemas=True,    # 生产环境不要开，若数据库为空则自动生成对应表单
    # add_exception_handlers=True,  # 生产环境不要开，会泄露调试信息
)


# 初始化定时任务管理器
from apps.data_opt.utils.scheduler import initialize_scheduler, get_scheduler_status, scheduler_manager

initialize_scheduler()
log_config.info(f"定时任务管理器状态: {get_scheduler_status()}")


# 启动说明：
# 使用命令: uvicorn main:app --host 0.0.0.0 --port 8000 
# 然后访问 http://127.0.0.1:8000 或 http://127.0.0.1:8000/docs
if __name__ == "__main__":
    from dotenv import load_dotenv
    env_file = os.path.join(BASE_DIR, '.env')
    os.environ.setdefault('ENV_FILE', env_file)
    load_dotenv(env_file)
    
    # 配置uvicorn日志格式，与我们的日志系统格式一致
    from uvicorn.config import LOGGING_CONFIG
    LOGGING_CONFIG['formatters']['default']['fmt'] = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    # 精简访问日志格式，只包含必要信息
    LOGGING_CONFIG['formatters']['access']['fmt'] = '%(asctime)s - %(name)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
    
    # 禁用访问日志处理器
    LOGGING_CONFIG['handlers'].pop('access', None)
    LOGGING_CONFIG['loggers']['uvicorn.access'] = {
        'handlers': [],
        'level': 'CRITICAL',
        'propagate': False,
    }
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        access_log=False,
        log_config=LOGGING_CONFIG
    )


