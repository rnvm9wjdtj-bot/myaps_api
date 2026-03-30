import os
from fastapi import Request
from fastapi.responses import JSONResponse

IP_WHITELIST = os.getenv("IP_WHITELIST", "").split(",")
API_KEY = os.getenv("API_KEY", "")

def create_security_middleware():
    async def security_middleware(request: Request, call_next):
        # 对GET和OPTIONS方法直接放行
        if request.method in ["GET", "OPTIONS"]:
            return await call_next(request)

        # 允许查阅文档等无需认证的请求
        url_path = request.url.path
        if url_path in ["/docs", "/redoc", "/openapi.json"] or url_path.startswith("/static/swagger"):
            return await call_next(request)
        
        # 检查IP是否在白名单中
        client_ip = request.client.host
        if client_ip in ["127.0.0.1", "localhost"] or client_ip in IP_WHITELIST:
            return await call_next(request)
            
        # 若不在IP白名单则需要认证请求头X-API-Key
        if request.headers.get("X-API-Key") == API_KEY:
            return await call_next(request)

        return JSONResponse(status_code=200, content={"status_code": 403, "success": 0, "meta": {}, "message": "Forbidden: Invalid or missing API Key"})
    
    return security_middleware
