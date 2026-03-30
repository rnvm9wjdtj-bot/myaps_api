from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt

def register_routes(app):
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
