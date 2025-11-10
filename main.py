import os, uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html
from tortoise.contrib.fastapi import register_tortoise

from config import settings
from apps.io_api.routers import rt as io_rt
from apps.io_api.common import register_exception_handlers
from apps.data_opt.routers import rt as do_rt
# from apps.data_opt.common import register_exception_handlers as register_data_manager_exception_handlers


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
    }
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

# 配置CORS中间件解决跨域访问问题
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # 在生产环境中应该设置具体的域名列表
#     allow_credentials=True,
#     allow_methods=["*"],  # 允许所有HTTP方法
#     allow_headers=["*"],  # 允许所有请求头
# )

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


# 导入全局MySQL监控实例
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from apps.data_opt.utils.scheduler import scheduler_manager

# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化MySQL监控"""
    # 直接使用全局monitor实例启动监控
    await mysql_monitor.start_monitoring()
    print("MySQL Binlog监控已启动")

# 应用关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时停止MySQL监控"""
    # 停止监控
    mysql_monitor.stop_monitoring()
    print("MySQL Binlog监控已停止")
    # 关闭调度器
    scheduler_manager.shutdown()
    print("定时任务管理器已关闭")

# 根路由
@app.get("/")
async def read_root():
    return {
        "message": "Welcome to MyAPS API",
        "version": "1.0.0",
        "status": "running"
    }

# 注册Tortoise ORM
register_tortoise(
    app = app,
    config=settings.TORTOISE_ORM_CONFIG,
    # modules={"models": ["project_code.models"]},
    # generate_schemas=True,    # 生产环境不要开，若数据库为空则自动生成对应表单
    # add_exception_handlers=True,  # 生产环境不要开，会泄露调试信息
)

# 检查是否开启定时任务
if os.getenv("TURN_ON_SCHEDULE_TASK", False).lower() == "true":
    # 初始化定时任务管理器
    from apps.data_opt.utils.scheduler import initialize_scheduler, get_scheduler_status
    initialize_scheduler()
    print(f"定时任务管理器状态: {get_scheduler_status()}")

# 启动说明：
# 使用命令: uvicorn main:app --reload
# 然后访问 http://127.0.0.1:8000 或 http://127.0.0.1:8000/docs
if __name__ == "__main__":

    from dotenv import load_dotenv
    env_file = os.path.join(os.getcwd(), '.env')
    os.environ.setdefault('ENV_FILE', env_file)
    load_dotenv(env_file)
    uvicorn.run(
        app,
        host=settings.THIS_SERVER_HOST,
        port=settings.THIS_SERVER_PORT,
    )


