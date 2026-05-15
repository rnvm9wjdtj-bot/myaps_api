from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt
from apps.data_opt.mds.staging_routers import rt as mds_rt
from apps.common.monitor.routers import router as monitor_rt
from apps.common.help.routers import router as help_rt
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# MDS 页面配置字典
MDS_PAGE_CONFIG = {
    "material": {
        "page_title": "物料数据清洗管理",
        "keyword_placeholder": "搜索物料号或描述...",
        "config_file": "material.config.js"
    },
    "workcenter": {
        "page_title": "工作中心数据清洗管理",
        "keyword_placeholder": "搜索工作中心或描述...",
        "config_file": "workcenter.config.js"
    },
    "mat-ver": {
        "page_title": "产线版本数据清洗管理",
        "keyword_placeholder": "搜索物料号或版本号...",
        "config_file": "mat-ver.config.js"
    },
    "mat-wc": {
        "page_title": "工艺路线数据清洗管理",
        "keyword_placeholder": "搜索物料号或工作中心...",
        "config_file": "mat-wc.config.js"
    },
    "mat-wc-bom": {
        "page_title": "BOM数据清洗管理",
        "keyword_placeholder": "搜索父件或子件料号...",
        "config_file": "mat-wc-bom.config.js"
    },
    "mold": {
        "page_title": "模具数据清洗管理",
        "keyword_placeholder": "搜索模具编号或描述...",
        "config_file": "mold.config.js"
    },
    "mat-wc-mold": {
        "page_title": "机台模具数据清洗管理",
        "keyword_placeholder": "搜索物料号或模具编号...",
        "config_file": "mat-wc-mold.config.js"
    }
}

def render_mds_page(page_key):
    """使用模板渲染MDS页面"""
    template_path = os.path.join(BASE_DIR, "static", "mds", "pages", "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    config = MDS_PAGE_CONFIG[page_key]
    
    # 生成前端配置（所有页面都使用动态配置）
    frontend_config = None
    from apps.data_opt.mds.config_generator import get_cached_config
    frontend_config = get_cached_config(page_key)
    
    # 准备替换变量
    import json
    replacements = {
        "{page_title}": config["page_title"],
        "{keyword_placeholder}": config["keyword_placeholder"],
        "{config_file}": config["config_file"],
        "{MDS_PAGE_CONFIG}": json.dumps(frontend_config, ensure_ascii=False) if frontend_config else "null"
    }
    
    # 设置导航栏高亮
    for key in MDS_PAGE_CONFIG.keys():
        replacements[f"{{{key.replace('-', '_')}_active}}"] = "active" if key == page_key else ""
    
    # 执行替换
    html = template
    for old, new in replacements.items():
        html = html.replace(old, new)
    
    return html


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
        return render_mds_page("material")
    
    @app.get("/mds/workcenter", response_class=HTMLResponse, include_in_schema=False)
    async def mds_workcenter():
        return render_mds_page("workcenter")
    
    @app.get("/mds/mat-ver", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_ver():
        return render_mds_page("mat-ver")
    
    @app.get("/mds/mat-wc", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc():
        return render_mds_page("mat-wc")
    
    @app.get("/mds/mat-wc-bom", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc_bom():
        return render_mds_page("mat-wc-bom")
    
    @app.get("/mds/mold", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mold():
        return render_mds_page("mold")
    
    @app.get("/mds/mat-wc-mold", response_class=HTMLResponse, include_in_schema=False)
    async def mds_mat_wc_mold():
        return render_mds_page("mat-wc-mold")
