from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt
from apps.data_opt.mds.staging_routers import rt as mds_rt
from apps.common.monitor.routers import router as monitor_rt
from apps.common.help.routers import router as help_rt
from apps.data_opt.mds.config_generator import TABLE_DISPLAY_CONFIG
from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_mds_page_config():
    """从 TABLE_DISPLAY_CONFIG 生成页面配置"""
    config = {}
    for table_key, display_config in TABLE_DISPLAY_CONFIG.items():
        route = display_config["route"]
        config[route] = {
            "page_title": display_config["page_title"],
            "keyword_placeholder": display_config["keyword_placeholder"],
            "table_key": table_key,
        }
    return config

MDS_PAGE_CONFIG = get_mds_page_config()


def render_mds_index():
    """动态渲染 MDS 首页导航"""
    template_path = os.path.join(BASE_DIR, "static", "mds", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    # 生成导航列表 HTML
    nav_items = []
    for table_key, display_config in TABLE_DISPLAY_CONFIG.items():
        route = display_config["route"]
        gradient = display_config["gradient"]
        # 从 STAGING_TABLE_CONFIG 获取 display_name
        display_name = STAGING_TABLE_CONFIG.get(table_key, {}).get("display_name", table_key)
        nav_item = f'''
                    <a href="/mds/{route}" class="table-link border-bottom">
                        <div class="d-flex align-items-center">
                            <div class="table-icon" style="background: linear-gradient(135deg, {gradient[0]}, {gradient[1]});">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" viewBox="0 0 16 16">
                                    <path d="M8.186 1.113a.5.5 0 0 0 0 1l1.5 1.5a.5.5 0 0 0 1 0l1.5-1.5a.5.5 0 0 0 0-1l-1.5-1.5a.5.5 0 0 0-1 0zM4 4a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1A.5.5 0 0 0 5 4zm2 0a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1A.5.5 0 0 0 7 4zm2 0a.5.5 0 0 0-.5.5v1a.5.5 0 0 0 .5.5h1a.5.5 0 0 0 .5-.5v-1A.5.5 0 0 0 9 4z"/>
                                </svg>
                            </div>
                            <div class="table-info ms-3">
                                <div class="table-title">{display_name}</div>
                                <div class="table-desc">{display_config["description"]}</div>
                            </div>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="#ccc" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M4 8a.5.5 0 0 1 .5-.5h5.793L8.146 5.354a.5.5 0 1 1 .708-.708l3 3a.5.5 0 0 1 0 .708l-3 3a.5.5 0 0 1-.708-.708L10.293 8.5H4.5A.5.5 0 0 1 4 8"/>
                            </svg>
                        </div>
                    </a>'''
        nav_items.append(nav_item)
    
    # 最后一个移除 border-bottom
    nav_items[-1] = nav_items[-1].replace('class="table-link border-bottom"', 'class="table-link"')
    
    nav_html = '\n'.join(nav_items)
    html = template.replace('{nav_items}', nav_html)
    return html


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
    replacements = {
        "{page_title}": config["page_title"],
        "{keyword_placeholder}": config["keyword_placeholder"],
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
        return render_mds_index()
    
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
