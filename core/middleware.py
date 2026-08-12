import os
import ipaddress
import re
import hashlib
import hmac
import time
from fastapi import Request
from fastapi.responses import JSONResponse

IP_WHITELIST = [ip.strip() for ip in os.getenv("IP_WHITELIST", "").split(",") if ip.strip()]
API_KEY = os.getenv("API_KEY", "")

# HMAC签名验证配置

SIGNATURE_MAX_AGE = int(os.getenv("SIGNATURE_MAX_AGE", "300"))

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
_ROUTE_EXACT_MAP = {}
_ROUTE_PREFIX_MAP = {}
_ROUTE_PARAM_ROUTES = []


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


def _collect_routes(routes, prefix=''):
    """递归收集所有路由，展开 _IncludedRouter 等嵌套结构"""
    results = []
    for route in routes:
        rtype = type(route).__name__
        if rtype == '_IncludedRouter':
            ctx = getattr(route, 'include_context', None)
            if ctx:
                sub_router = getattr(ctx, 'included_router', None)
                sub_prefix = prefix + getattr(ctx, 'prefix', '')
                if sub_router and hasattr(sub_router, 'routes'):
                    results.extend(_collect_routes(sub_router.routes, sub_prefix))
        elif hasattr(route, 'path') and hasattr(route, 'methods'):
            results.append({
                'path': prefix + route.path,
                'methods': route.methods
            })
        elif hasattr(route, 'path') and rtype == 'Mount':
            results.append({
                'path': prefix + route.path,
                'methods': {'GET', 'HEAD', 'OPTIONS'},
                'mount': True
            })
    return results


def _build_route_index(routes):
    """构建路由索引，加速查找

    - exact_map: 精确路径 -> 方法集合（O(1) 匹配）
    - prefix_map: Mount 子应用按一级路径段分组（前缀匹配，如 /static）
    - param_routes: 含路径参数的路由列表（正则匹配）
    """
    exact_map = {}
    prefix_map = {}
    param_routes = []

    for route in routes:
        path = route['path'].rstrip('/')
        if route.get('mount'):
            # Mount 子应用：同时支持精确访问与子路径前缀访问
            exact_map.setdefault(path, set()).update(route['methods'])
            segment = '/' + path.split('/', 2)[1] if path.count('/') >= 1 else path
            prefix_map.setdefault(segment, []).append(route)
        elif '{' in path:
            # 参数路由统一遍历，避免一级参数路由（如 /{page}）按段分组时键不匹配
            param_routes.append(route)
        else:
            # 同一路径可注册多个方法（如 GET 与 POST），累积方法集避免互相覆盖
            exact_map.setdefault(path, set()).update(route['methods'])

    return exact_map, prefix_map, param_routes


def init_registered_routes(app):
    """
    初始化已注册路由列表
    在应用启动后调用此函数来缓存所有路由信息
    """
    global REGISTERED_ROUTES, _ROUTE_EXACT_MAP, _ROUTE_PREFIX_MAP, _ROUTE_PARAM_ROUTES
    REGISTERED_ROUTES = _collect_routes(app.routes)
    _ROUTE_EXACT_MAP, _ROUTE_PREFIX_MAP, _ROUTE_PARAM_ROUTES = _build_route_index(REGISTERED_ROUTES)


def is_route_exists(request_path: str, request_method: str) -> bool:
    """
    检查请求的路径和方法是否匹配已注册的路由
    
    索引加速：先 O(1) 精确匹配，再匹配 Mount 子应用前缀，最后遍历参数路由正则匹配。
    """
    request_path = request_path.rstrip('/')

    # 1. 精确匹配（O(1)）
    methods = _ROUTE_EXACT_MAP.get(request_path)
    if methods is not None and request_method in methods:
        return True

    # 2. Mount 子应用前缀匹配（如 /static）
    segment = '/' + request_path.split('/', 2)[1] if request_path.count('/') >= 1 else request_path
    for route in _ROUTE_PREFIX_MAP.get(segment, []):
        route_path = route['path'].rstrip('/')
        if request_method in route['methods'] and request_path.startswith(route_path + '/'):
            return True

    # 3. 路径参数路由匹配
    for route in _ROUTE_PARAM_ROUTES:
        if request_method not in route['methods']:
            continue
        route_path = route['path'].rstrip('/')
        param_pattern = r'([^/]+)'
        placeholder = '\x00PARAM\x00'
        temp = re.sub(r'\{[^}]+\}', placeholder, route_path)
        pattern = re.escape(temp).replace(placeholder, param_pattern)
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


def _verify_hmac_signature(request: Request, body: bytes) -> bool:
    """
    验证HMAC-SHA256请求签名

    签名算法:
        sign_string = "{METHOD}{PATH}{QUERY}{TIMESTAMP}{BODY_SHA256}"
        signature = HMAC-SHA256(API_KEY, sign_string)
    QUERY: 请求 URL 的原始查询字符串（不含 "?"，无参数时为空字符串），
           与 request.url.query 保持一致（含顺序与编码），防止 query 参数被篡改。

    请求方需携带以下Header:
        X-Signature: HMAC-SHA256签名值（十六进制）
        X-Timestamp: 签名生成时的Unix时间戳（秒，浮点数）

    防重放机制:
        服务端校验 |当前时间 - X-Timestamp| <= SIGNATURE_MAX_AGE（默认300秒）

    使用示例（调用方）:
        import hmac, hashlib, time
        ts = str(time.time())
        query = "db_name=hacy_p"        # 与请求 URL 的 query 原样一致，无参数时为空串
        body_bytes = json.dumps(payload).encode()
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        sign_str = f"POST/api/t_material{query}{ts}{body_hash}"
        sig = hmac.new(API_KEY.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
        headers = {"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"}
    """
    if not API_KEY:
        return False

    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")

    if not signature or not timestamp:
        return False

    try:
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts_float) > SIGNATURE_MAX_AGE:
        return False

    body_hash = hashlib.sha256(body).hexdigest()
    sign_string = f"{request.method}{request.url.path}{request.url.query}{timestamp}{body_hash}"
    expected = hmac.new(
        API_KEY.encode(), sign_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


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

        # 未配置API_KEY则不做鉴权（开发模式）
        if not API_KEY:
            return await call_next(request)

        # HMAC签名验证（所有非白名单请求必须携带有效签名）
        body = b""
        if request_method in ("POST", "PUT", "PATCH", "DELETE"):
            body = await request.body()

        if _verify_hmac_signature(request, body):
            return await call_next(request)

        # 签名验证失败
        return JSONResponse(
            status_code=401,
            content={"status_code": 401, "success": 0, "meta": {}, "message": "Unauthorized: Invalid or expired HMAC signature"}
        )
    
    return security_middleware
