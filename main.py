import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
# from fastapi.responses import RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html
from tortoise.contrib.fastapi import register_tortoise

from config import settings
from apps.io_api.routers import rt as io_rt
from apps.io_api.common import register_exception_handlers
# from apps.data_manager.routers import rt as dm_rt
# from apps.data_manager.common import register_exception_handlers as register_data_manager_exception_handlers


# 创建FastAPI应用实例
app = FastAPI(
    title="MyAPS API",
    description="MyAPS API",
    version="1.0.0",
    # 配置文档页面URL，禁用默认的 Swagger UI​，防止CDN资源不稳定导致无法访问文档页
    docs_url=None,  
    redoc_url=None,
    swagger_js_url="/static/swagger/swagger-ui-bundle.js",
    swagger_css_url="/static/swagger/swagger-ui.css",
    swagger_favicon_url="/static/swagger/favicon-32x32.png",
    swagger_ui_parameters={"configUrl": None}
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
# app.include_router(dm_rt, prefix="/dm", tags=["data_manager"])

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

# 启动说明：
# 使用命令: uvicorn main:app --reload
# 然后访问 http://127.0.0.1:8000 或 http://127.0.0.1:8000/docs
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    env_file = os.path.join(os.getcwd(), '.env')
    os.environ.setdefault('ENV_FILE', env_file)
    load_dotenv(env_file)
    uvicorn.run(
        app,
        host=settings.THIS_SERVER_HOST,
        port=settings.THIS_SERVER_PORT,
    )
