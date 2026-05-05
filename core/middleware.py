import os
import ipaddress
from fastapi import Request
from fastapi.responses import JSONResponse

IP_WHITELIST = [ip.strip() for ip in os.getenv("IP_WHITELIST", "").split(",") if ip.strip()]
API_KEY = os.getenv("API_KEY", "")


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
        # 对GET和OPTIONS方法直接放行
        if request.method in ["GET", "OPTIONS"]:
            return await call_next(request)

        # 允许查阅文档等无需认证的请求
        url_path = request.url.path
        if url_path in ["/docs", "/redoc", "/openapi.json"] or url_path.startswith("/static/swagger"):
            return await call_next(request)
        
        # 检查IP是否在白名单中
        client_ip = request.client.host
        if is_ip_allowed(client_ip):
            return await call_next(request)
            
        # 若不在IP白名单则需要认证请求头X-API-Key
        if not API_KEY or request.headers.get("X-API-Key") == API_KEY:
            return await call_next(request)

        return JSONResponse(status_code=200, content={"status_code": 403, "success": 0, "meta": {}, "message": "Forbidden: Invalid or missing API Key"})
    
    return security_middleware
