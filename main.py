import os, uvicorn
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(BASE_DIR, '.env')
os.environ.setdefault('ENV_FILE', env_file)
load_dotenv(env_file)

# 导入模块
from core.app import create_app
from core.lifespan import lifespan
from core.openapi import setup_custom_openapi
from core.middleware import create_security_middleware, IP_WHITELIST, API_KEY
from core.websocket import websocket_endpoint, websocket_root
from core.routes_register import register_routes
from core.database import register_database
from apps.io_api.utils.common import register_exception_handlers
from config.settings import PORT

# 创建应用实例
app = create_app(lifespan=lifespan)
# 设置自定义的OpenAPI schema生成函数
setup_custom_openapi(app)

# 配置安全中间件
if IP_WHITELIST or API_KEY:
    app.middleware("http")(create_security_middleware())

# 配置HTTP监控中间件
from apps.common.monitor.middleware import HTTPMonitorMiddleware
app.add_middleware(HTTPMonitorMiddleware)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名列表
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 覆写原有文档页面路由函数
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

# 注册异常处理器
register_exception_handlers(app)

# 注册路由
register_routes(app)

# 注册WebSocket路由
app.websocket("/{path:path}")(websocket_endpoint)
app.websocket("/")(websocket_root)

# 注册数据库
register_database(app)

# 启动说明：
# 使用命令: uvicorn main:app --host 0.0.0.0 --port 8000 
# 然后访问 http://127.0.0.1:8000 或 http://127.0.0.1:8000/docs
if __name__ == "__main__":
    import traceback
    
    try:
        # 配置uvicorn日志格式，与我们的日志系统格式一致
        from uvicorn.config import LOGGING_CONFIG
        LOGGING_CONFIG['formatters']['default']['fmt'] = '%(asctime)s - %(levelname)s - %(message)s'
        # 精简访问日志格式，只包含必要信息
        LOGGING_CONFIG['formatters']['access']['fmt'] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'
        
        # 禁用访问日志处理器
        LOGGING_CONFIG['handlers'].pop('access', None)
        LOGGING_CONFIG['loggers']['uvicorn.access'] = {
            'handlers': [],
            'level': 'CRITICAL',
            'propagate': False,
        }
        
        print("Starting application...")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=PORT + 1,
            log_level="info",
            access_log=False,
            log_config=LOGGING_CONFIG
        )
    except Exception as e:
        print(f"Application failed to start: {e}")
        print("Traceback:")
        print(traceback.format_exc())
        import time
        time.sleep(10)  # 等待10秒，以便查看错误信息


