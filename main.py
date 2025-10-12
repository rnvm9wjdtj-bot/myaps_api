import uvicorn
from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise

from config import settings
from project_code.routers import rt  

# 创建FastAPI应用实例
app = FastAPI(
    title="MyAPS API",
    description="MyAPS API",
    version="1.0.0"
)

# 包含路由
app.include_router(rt, prefix="/api", tags=[])

# 根路由
# @app.get("/")
# async def read_root():
#     return {
#         "message": "Welcome to MyAPS API",
#         "version": "1.0.0",
#         "status": "running"
#     }

# 示例路由 - 获取项目信息
# @app.get("/api/info")
# async def get_info():
#     return {
#         "app_name": "MyAPS API",
#         "description": "A FastAPI project template",
#         "version": "1.0.0",
#         "docs_url": "/docs",
#         "redoc_url": "/redoc"
#     }


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
    uvicorn.run(
        app,
        host=settings.THIS_SERVER_HOST,
        port=settings.THIS_SERVER_PORT,
    ) 
