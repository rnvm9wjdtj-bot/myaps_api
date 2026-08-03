import os, uvicorn
import asyncio
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(BASE_DIR, '.env')
os.environ.setdefault('ENV_FILE', env_file)
load_dotenv(env_file)

# 自定义事件循环工厂，处理Windows socket资源不足的问题
def create_event_loop():
    if os.name == 'nt':
        # 在Windows上，socket.socketpair()可能因系统缓冲区不足而失败
        # 需要使用替代方案
        errors = []
        try:
            # 尝试创建ProactorEventLoop（Windows推荐）
            loop = asyncio.ProactorEventLoop()
            return loop
        except OSError as e:
            errors.append(f"ProactorEventLoop: {e}")
        except Exception as e:
            errors.append(f"ProactorEventLoop (unknown): {e}")
        
        try:
            # 尝试创建SelectorEventLoop
            loop = asyncio.SelectorEventLoop()
            return loop
        except OSError as e:
            errors.append(f"SelectorEventLoop: {e}")
        except Exception as e:
            errors.append(f"SelectorEventLoop (unknown): {e}")
        
        # 如果所有事件循环都创建失败，抛出带有详细信息的异常
        raise RuntimeError(
            f"无法创建事件循环。Windows套接字资源可能已耗尽。\n"
            f"错误详情: {'; '.join(errors)}\n\n"
            f"建议解决方法:\n"
            f"1. 重启计算机以释放系统资源\n"
            f"2. 关闭其他占用大量网络连接的程序\n"
            f"3. 检查是否有程序泄漏socket连接\n"
            f"4. 增加Windows系统的TCP缓冲区设置"
        )
    
    # 默认使用asyncio的新事件循环
    return asyncio.new_event_loop()

# 导入模块
from core.app import create_app
from core.lifespan import lifespan
from core.openapi import setup_custom_openapi
from core.middleware import create_security_middleware, IP_WHITELIST, API_KEY, init_registered_routes
from core.websocket import websocket_endpoint, websocket_root
from core.routes_register import register_routes
from core.database import register_database
from apps.io_api.utils.common import register_exception_handlers
from core.settings import PORT

# 创建应用实例
app = create_app(lifespan=lifespan)
# 设置自定义的OpenAPI schema生成函数
setup_custom_openapi(app)

# 配置HTTP监控中间件（先注册，在内层）
from apps.common.monitor.middleware import HTTPMonitorMiddleware
app.add_middleware(HTTPMonitorMiddleware)

# 配置安全中间件（后注册，在外层，优先检查端点存在性）
# 当IP_WHITELIST或API_KEY配置时启用安全中间件
# API_KEY配置后，非白名单请求必须携带HMAC签名
if IP_WHITELIST or API_KEY:
    app.middleware("http")(create_security_middleware())

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

# 初始化已注册路由列表（用于端点存在性校验）
init_registered_routes(app)

# 注册WebSocket路由
app.websocket("/")(websocket_root)
app.websocket("/ws/{path:path}")(websocket_endpoint)

# 注册数据库（通过 register_tortoise 管理 context）
register_database(app)

# 启动说明：
# 进入 venv python虚拟环境：
# venv\Scripts\activate
# 使用命令: uvicorn main:app --host 0.0.0.0 --port 8000 
# 然后访问 http://127.0.0.1:8000 或 http://127.0.0.1:8000/docs
if __name__ == "__main__":
    import traceback
    
    try:
        from uvicorn.config import LOGGING_CONFIG
        # 清空所有处理器，禁用uvicorn默认日志
        LOGGING_CONFIG['handlers'] = {}
        LOGGING_CONFIG['loggers'] = {
            'uvicorn': {'handlers': [], 'level': 'CRITICAL', 'propagate': False},
            'uvicorn.access': {'handlers': [], 'level': 'CRITICAL', 'propagate': False},
            'uvicorn.error': {'handlers': [], 'level': 'CRITICAL', 'propagate': False},
        }
        
        # Windows上需要预先设置事件循环，解决socket资源不足问题
        if os.name == 'nt':
            loop = create_event_loop()
            asyncio.set_event_loop(loop)

        print("Starting application...")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
            access_log=True,
            log_config=LOGGING_CONFIG,
        )
    except Exception as e:
        print(f"Application failed to start: {e}")
        print("Traceback:")
        print(traceback.format_exc())
        import time
        time.sleep(10)  # 等待10秒，以便查看错误信息


