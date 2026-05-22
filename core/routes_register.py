from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from apps.io_api.routers import rt as io_rt
from apps.data_opt.routers import rt as do_rt
from apps.data_opt.mds.staging_routers import rt as mds_rt
from apps.common.monitor.routers import router as monitor_rt
from apps.common.help.routers import router as help_rt
from apps.data_opt.mds.config_generator import TABLE_DISPLAY_CONFIG
from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG
from core.settings import MDS_MANUAL_REMOVE
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
    """动态渲染 MDS 首页卡片布局"""
    template_path = os.path.join(BASE_DIR, "static", "mds", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    # 生成模块配置JSON（注入到前端）
    modules_config = []
    for table_key, display_config in TABLE_DISPLAY_CONFIG.items():
        route = display_config["route"]
        gradient = display_config["gradient"]
        icon = display_config.get("icon", "bi-folder")
        display_name = STAGING_TABLE_CONFIG.get(table_key, {}).get("display_name", table_key)
        
        modules_config.append({
            "table_key": table_key,
            "table_name": f"{table_key}_staging",
            "title": display_name,
            "route": route,
            "icon": icon,
            "description": display_config["description"],
            "gradient": list(gradient),
        })
    
    # 生成卡片HTML
    cards_html = []
    for module in modules_config:
        card = f'''
                <div class="col-12 col-sm-6 col-md-4 col-lg-3">
                    <a href="/mds/{module["route"]}" class="card-nav-link" target="_blank">
                        <div class="card-nav">
                            <div class="card-nav-badge" data-badge-table="{module["table_name"]}"></div>
                            <div class="card-nav-icon" style="background: linear-gradient(135deg, {module["gradient"][0]}, {module["gradient"][1]});">
                                <i class="bi {module["icon"]}"></i>
                            </div>
                            <div class="card-nav-body">
                                <h5 class="card-nav-title">{module["title"]}</h5>
                                <p class="card-nav-desc">{module["description"]}</p>
                                <div class="card-nav-stats" data-table="{module["table_name"]}">
                                    <span class="stats-loading text-muted">加载中...</span>
                                </div>
                            </div>
                        </div>
                    </a>
                </div>'''
        cards_html.append(card)
    
    cards_html_str = '\n'.join(cards_html)
    modules_config_json = json.dumps(modules_config, ensure_ascii=False)
    
    html = template.replace('{cards}', cards_html_str)
    html = html.replace('{modules_config}', modules_config_json)
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
    
    # 注入删除模式配置到前端
    if frontend_config:
        frontend_config["removeMode"] = MDS_MANUAL_REMOVE
        frontend_config["removeAllowed"] = MDS_MANUAL_REMOVE != "never"
    
    # 准备替换变量
    replacements = {
        "{page_title}": config["page_title"],
        "{keyword_placeholder}": config["keyword_placeholder"],
        "{MDS_PAGE_CONFIG}": json.dumps(frontend_config, ensure_ascii=False) if frontend_config else "null"
    }
    
    # 设置导航栏高亮和图标
    for key in MDS_PAGE_CONFIG.keys():
        replacements[f"{{{key.replace('-', '_')}_active}}"] = "active" if key == page_key else ""
        # 设置导航栏图标
        table_key = MDS_PAGE_CONFIG[key]["table_key"]
        icon = TABLE_DISPLAY_CONFIG.get(table_key, {}).get("icon", "bi-folder")
        replacements[f"{{{key.replace('-', '_')}_icon}}"] = icon
    
    # 执行替换
    html = template
    for old, new in replacements.items():
        html = html.replace(old, new)
    
    return html


router = APIRouter()

def register_routes(app):
    app.include_router(io_rt, prefix="/api", tags=[])
    app.include_router(do_rt, prefix="/do", tags=[], include_in_schema=False)
    app.include_router(mds_rt, prefix="/api", tags=["数据清洗"], include_in_schema=False)
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
    
    @app.get("/mds/user-guide", response_class=HTMLResponse, include_in_schema=False)
    async def mds_user_guide():
        file_path = os.path.join(BASE_DIR, "static", "mds", "user-guide.html")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
