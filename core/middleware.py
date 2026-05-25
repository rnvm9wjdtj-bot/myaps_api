import os
import ipaddress
import re
from fastapi import Request
from fastapi.responses import JSONResponse

IP_WHITELIST = [ip.strip() for ip in os.getenv("IP_WHITELIST", "").split(",") if ip.strip()]
API_KEY = os.getenv("API_KEY", "")

# 文档相关路径，只能在内网访问
DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]
DOC_PREFIXES = ["/static/swagger"]

# MDS页面路径（不需要API Key验证）
MDS_PATHS = ["/mds", "/mds/material", "/mds/workcenter", "/mds/mat-ver", 
             "/mds/mat-wc", "/mds/mat-wc-bom", "/mds/mold", "/mds/mat-wc-mold"]

# 公开的GET接口（不需要认证）
# 用于健康检查、静态资源等
PUBLIC_GET_PATHS = [
    "/health",           # K8s/负载均衡健康检查
    "/health/database",  # 数据库健康检查
]

# 公开的路径前缀
PUBLIC_GET_PREFIXES = [
    "/static/",          # 静态资源
]

# 缓存已注册的路由信息，避免每次请求都重新解析
REGISTERED_ROUTES = []


def is_internal_ip(ip_str: str) -> bool:
    """判断IP地址是否为内部/本地地址
    
    判断依据：
    - 127.0.0.0/8 (127.0.0.0 - 127.255.255.255) - IPv4本地回环
    - 10.0.0.0/8 - A类私有地址
    - 172.16.0.0/12 - B类私有地址
    - 192.168.0.0/16 - C类私有地址
    - ::1 - IPv6本地回环
    """
    if not ip_str:
        return False

    try:
        # 处理 IPv4映射的IPv6地址 (如 ::ffff:127.0.0.1)
        if ip_str.startswith('::ffff:'):
            ip_str = ip_str[7:]

        ip = ipaddress.ip_address(ip_str)

        # 检查是否为本地回环地址
        if ip.is_loopback:
            return True

        # 检查是否为私有地址
        if ip.is_private:
            return True

        return False
    except ValueError:
        # 如果不是有效的IP地址格式，检查特殊的主机名
        lower_ip = ip_str.lower()
        if lower_ip in ('localhost', 'localhost.localdomain'):
            return True
        return False


def init_registered_routes(app):
    """
    初始化已注册路由列表
    在应用启动后调用此函数来缓存所有路由信息
    """
    global REGISTERED_ROUTES
    REGISTERED_ROUTES = []
    
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            REGISTERED_ROUTES.append({
                'path': route.path,
                'methods': route.methods
            })


def is_route_exists(request_path: str, request_method: str) -> bool:
    """
    检查请求的路径和方法是否匹配已注册的路由
    
    FastAPI路由支持路径参数，如 /api/{id}
    这里实现简单的路径参数匹配
    """
    # 去除末尾斜杠以便统一比较
    request_path = request_path.rstrip('/')
    
    for route in REGISTERED_ROUTES:
        route_path = route['path'].rstrip('/')
        route_methods = route['methods']
        
        # 检查HTTP方法是否匹配
        if request_method not in route_methods:
            continue
        
        # 精确匹配
        if request_path == route_path:
            return True
        
        # 处理路径参数，将 {param} 转换为正则表达式
        # 例如: /api/{id} -> /api/(\w+)
        pattern = re.escape(route_path).replace(r'\{', '(').replace(r'\}', ')')
        # 将 (\w+) 替换为更通用的匹配模式 ([^/]+)
        pattern = pattern.replace(r'\(\w+\)', r'([^/]+)')
        
        # 添加开始和结束标记
        pattern = f"^{pattern}$"
        
        try:
            if re.match(pattern, request_path):
                return True
        except re.error:
            continue
    
    return False


def _match_ip_wildcard(client_ip: str, pattern: str) -> bool:
    """
    检查IP是否匹配通配符模式
    支持格式: 192.168.1.*, 192.168.*.*, 10.*.*.*
    """
    client_parts = client_ip.split(".")
    pattern_parts = pattern.split(".")
    
    if len(client_parts) != 4 or len(pattern_parts) != 4:
        return False
    
    for c, p in zip(client_parts, pattern_parts):
        if p == "*":
            continue
        if c != p:
            return False
    return True


def _match_ip_range(client_ip: str, range_pattern: str) -> bool:
    """
    检查IP是否在指定范围内
    支持格式: 192.168.1.100-200, 192.168.1.50-192.168.1.100
    """
    try:
        if "-" in range_pattern:
            parts = range_pattern.split("-")
            if len(parts) == 2:
                start_ip, end_ip = parts[0].strip(), parts[1].strip()
                
                # 如果结束IP只有一个数字（如 100-200），则继承前三个段
                if end_ip.count(".") == 0:
                    start_parts = start_ip.split(".")
                    if len(start_parts) == 4:
                        end_ip = ".".join(start_parts[:3] + [end_ip])
                
                start_int = int(ipaddress.IPv4Address(start_ip))
                end_int = int(ipaddress.IPv4Address(end_ip))
                client_int = int(ipaddress.IPv4Address(client_ip))
                
                return start_int <= client_int <= end_int
    except (ValueError, ipaddress.AddressValueError):
        pass
    return False


def _match_ip_cidr(client_ip: str, cidr_pattern: str) -> bool:
    """
    检查IP是否在CIDR范围内
    支持格式: 192.168.1.0/24, 10.0.0.0/8, 172.16.0.0/12
    """
    try:
        network = ipaddress.ip_network(cidr_pattern, strict=False)
        return ipaddress.ip_address(client_ip) in network
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        return False


def is_ip_allowed(client_ip: str) -> bool:
    """
    检查IP是否在白名单中
    支持多种格式:
    - 精确IP: 192.168.1.100
    - 通配符: 192.168.1.*
    - IP范围: 192.168.1.100-200 或 192.168.1.50-192.168.1.100
    - CIDR表示法: 192.168.1.0/24
    """
    # 本地地址直接放行
    if client_ip in ["127.0.0.1", "localhost", "::1"]:
        return True
    
    for allowed_pattern in IP_WHITELIST:
        if not allowed_pattern:
            continue
        
        # 精确匹配
        if client_ip == allowed_pattern:
            return True
        
        # 通配符匹配
        if "*" in allowed_pattern and _match_ip_wildcard(client_ip, allowed_pattern):
            return True
        
        # IP范围匹配
        if "-" in allowed_pattern and _match_ip_range(client_ip, allowed_pattern):
            return True
        
        # CIDR表示法匹配
        if "/" in allowed_pattern and _match_ip_cidr(client_ip, allowed_pattern):
            return True
    
    return False


def create_security_middleware():
    async def security_middleware(request: Request, call_next):
        url_path = request.url.path
        request_method = request.method
        client_ip = request.client.host
        
        # MDS页面路径直接放行
        if url_path in MDS_PATHS:
            return await call_next(request)
        
        # 检查是否为文档相关路径（只能在内网访问）
        is_doc_path = url_path in DOC_PATHS or any(url_path.startswith(prefix) for prefix in DOC_PREFIXES)
        if is_doc_path:
            # 文档路径只允许内网访问
            if not is_internal_ip(client_ip):
                return JSONResponse(
                    status_code=403,
                    content={"status_code": 403, "success": 0, "meta": {}, "message": "Forbidden: Documentation access is restricted to internal network"}
                )
            return await call_next(request)
        
        # 检查请求的端点是否存在
        if not is_route_exists(url_path, request_method):
            # 端点不存在时返回404，不暴露服务器信息
            return JSONResponse(
                status_code=404, 
                content={"status_code": 404, "success": 0, "meta": {}, "message": "Not Found"}
            )
        
        # OPTIONS方法直接放行（CORS预检）
        if request_method == "OPTIONS":
            return await call_next(request)
        
        # GET方法需要检查是否在公开路径列表
        if request_method == "GET":
            is_public_path = (
                url_path in PUBLIC_GET_PATHS or
                any(url_path.startswith(prefix) for prefix in PUBLIC_GET_PREFIXES)
            )
            if is_public_path:
                return await call_next(request)
            # 非公开GET路径需要继续鉴权
        
        # 检查IP是否在白名单中
        client_ip = request.client.host
        if is_ip_allowed(client_ip):
            return await call_next(request)
            
        # 若不在IP白名单则需要认证请求头X-API-Key
        if not API_KEY or request.headers.get("X-API-Key") == API_KEY:
            return await call_next(request)

        # 未授权请求返回真实HTTP 401状态码
        return JSONResponse(
            status_code=401,
            content={"status_code": 401, "success": 0, "meta": {}, "message": "Unauthorized: Invalid or missing API Key"}
        )
    
    return security_middleware
