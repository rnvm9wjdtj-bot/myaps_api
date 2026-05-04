from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt
from apps.common.monitor.routers import router as monitor_rt
from apps.common.help.routers import router as help_rt


router = APIRouter()

def register_routes(app):
    app.include_router(io_rt, prefix="/api", tags=[])
    app.include_router(do_rt, prefix="/do", tags=[], include_in_schema=False)
    app.include_router(monitor_rt, tags=["monitor"], include_in_schema=False)
    app.include_router(help_rt, tags=["help"], include_in_schema=False)


    @app.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
    async def monitor_dashboard():
        with open("static/monitor/index.html", "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/monitor/live-logs", response_class=HTMLResponse, include_in_schema=False)
    async def live_logs_page():
        with open("static/monitor/live-logs.html", "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/monitor/history-logs", response_class=HTMLResponse, include_in_schema=False)
    async def history_logs_page():
        with open("static/monitor/history-logs.html", "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/", include_in_schema=False)
    async def read_root():
        return {
            "message": "Welcome to MyAPI",
            "version": "1.0.0",
            "status": "running"
        }
