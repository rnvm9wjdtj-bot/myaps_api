from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt
from apps.data_opt.mds.staging_routers import rt as mds_rt
from apps.common.monitor.routers import router as monitor_rt
from apps.common.help.routers import router as help_rt
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


router = APIRouter()

def register_routes(app):
    app.include_router(io_rt, prefix="/api", tags=[])
    app.include_router(do_rt, prefix="/do", tags=[], include_in_schema=False)
    app.include_router(mds_rt, prefix="/api", tags=["数据清洗"])
    app.include_router(monitor_rt, tags=["monitor"], include_in_schema=False)
    app.include_router(help_rt, tags=["help"], include_in_schema=False)


    @app.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
    async def monitor_dashboard():
        file_path = os.path.join(BASE_DIR, "static", "monitor", "index.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/monitor/live-logs", response_class=HTMLResponse, include_in_schema=False)
    async def live_logs_page():
        file_path = os.path.join(BASE_DIR, "static", "monitor", "live-logs.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/monitor/history-logs", response_class=HTMLResponse, include_in_schema=False)
    async def history_logs_page():
        file_path = os.path.join(BASE_DIR, "static", "monitor", "history-logs.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/", include_in_schema=False)
    async def read_root():
        return {
            "message": "Welcome to MyAPI",
            "version": "1.0.0",
            "status": "running"
        }
    
    # MDS 数据清洗页面路由
    @app.get("/mds", response_class=HTMLResponse, include_in_schema=False)
    async def mds_index():
        file_path = os.path.join(BASE_DIR, "static", "mds", "index.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/material", response_class=HTMLResponse, include_in_schema=False)
    async def mds_material():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "material.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/workcenter", response_class=HTMLResponse, include_in_schema=False)
    async def mds_workcenter():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "workcenter.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/mat-ver", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_ver():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "mat-ver.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/mat-wc", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "mat-wc.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/mat-wc-bom", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc_bom():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "mat-wc-bom.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/mold", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mold():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "mold.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @app.get("/mds/mat-wc-mold", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc_mold():
        file_path = os.path.join(BASE_DIR, "static", "mds", "pages", "mat-wc-mold.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
