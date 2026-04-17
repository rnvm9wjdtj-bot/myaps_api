from tortoise import fields
from tortoise.models import Model
from datetime import datetime, timezone
import ipaddress
from typing import Optional


def is_internal_ip(ip_str: str) -> bool:
    """判断IP地址是否为内部/本地地址

    判断依据：
    - 127.0.0.0/8 (127.0.0.0 - 127.255.255.255) - IPv4本地回环
    - ::1 - IPv6本地回环
    - ::ffff:127.0.0.0/104 - IPv4映射的IPv6地址
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

        return False
    except ValueError:
        # 如果不是有效的IP地址格式，检查特殊的主机名
        lower_ip = ip_str.lower()
        if lower_ip in ('localhost', 'localhost.localdomain'):
            return True
        return False


def is_internal_url(url: str) -> bool:
    """判断URL是否为内部/本地地址的请求

    通过解析URL获取主机名，然后判断是否为内部IP地址。

    Args:
        url: 请求的URL

    Returns:
        bool: True 表示是内部请求，False 表示外部请求
    """
    if not url:
        return False

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False

        # 检查主机名是否为localhost
        if hostname.lower() in ('localhost', 'localhost.localdomain'):
            return True

        # 如果主机名是IP地址，使用 is_internal_ip 判断
        try:
            return is_internal_ip(hostname)
        except ValueError:
            # 如果不是有效的IP地址，尝试解析域名
            return False
    except Exception:
        return False


def get_host_from_url(url: str) -> Optional[str]:
    """从URL中提取主机名（包含端口）

    Args:
        url: 请求的URL

    Returns:
        str: 主机名（包含端口），如果解析失败则返回None
    """
    if not url:
        return None

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port

        if not hostname:
            return None

        if port:
            return f"{hostname}:{port}"
        return hostname
    except Exception:
        return None


class APIRequest(Model):
    """API 请求记录模型"""
    id = fields.IntField(pk=True, auto_generate=True)
    timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="请求时间")
    method = fields.CharField(max_length=10, description="HTTP 方法")
    path = fields.CharField(max_length=512, description="请求路径")
    query_params = fields.TextField(null=True, description="查询参数")
    status_code = fields.IntField(description="响应状态码")
    response_time = fields.FloatField(description="响应时间（毫秒）")
    client_ip = fields.CharField(max_length=64, null=True, description="客户端 IP")
    user_agent = fields.TextField(null=True, description="用户代理")
    payload_size = fields.IntField(null=True, description="请求体大小")
    response_size = fields.IntField(null=True, description="响应体大小")
    request_body = fields.TextField(null=True, description="请求体")
    response_body = fields.TextField(null=True, description="响应体")
    is_slow = fields.BooleanField(default=False, description="是否慢请求")
    slow_threshold = fields.FloatField(null=True, description="慢请求阈值（毫秒）")
    is_error = fields.BooleanField(default=False, description="是否错误请求")
    error_message = fields.TextField(null=True, description="错误信息")
    is_internal = fields.BooleanField(default=False, description="是否内部请求")

    class Meta:
        table = "api_requests"
        default_connection = "local_data"
        indexes = [
            ("timestamp",),
            ("path",),
            ("status_code",),
            ("response_time",),
            ("is_slow",),
            ("is_error",),
            ("is_internal",),
        ]


class OutboundAPIRequest(Model):
    """对外 HTTP 请求记录模型"""
    id = fields.IntField(pk=True, auto_generate=True)
    timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="请求时间")
    method = fields.CharField(max_length=10, description="HTTP 方法")
    url = fields.TextField(description="请求 URL")
    status_code = fields.IntField(description="响应状态码")
    duration = fields.FloatField(description="响应时间（秒）")
    request_headers = fields.TextField(null=True, description="请求头")
    request_body = fields.TextField(null=True, description="请求体")
    response_headers = fields.TextField(null=True, description="响应头")
    response_body = fields.TextField(null=True, description="响应体")
    error_message = fields.TextField(null=True, description="错误信息")
    module = fields.CharField(max_length=255, null=True, description="发起请求的模块")
    is_error = fields.BooleanField(default=False, description="是否错误请求")
    is_slow = fields.BooleanField(default=False, description="是否慢请求")
    is_internal = fields.BooleanField(default=False, description="是否内部请求")

    class Meta:
        table = "outbound_api_requests"
        default_connection = "local_data"
        indexes = [
            ("timestamp",),
            ("module",),
            ("status_code",),
            ("is_error",),
            ("is_slow",),
            ("is_internal",),
        ]


class SystemLog(Model):
    """系统日志模型"""
    id = fields.IntField(pk=True, auto_generate=True)
    timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="日志时间")
    level = fields.CharField(max_length=10, description="日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL")
    module = fields.CharField(max_length=255, description="模块名称")
    function = fields.CharField(max_length=255, description="函数名称")
    line_number = fields.IntField(description="行号")
    message = fields.TextField(description="日志消息")
    details = fields.TextField(null=True, description="详细信息")
    stack_trace = fields.TextField(null=True, description="堆栈跟踪")
    process_id = fields.IntField(null=True, description="进程ID")
    thread_id = fields.IntField(null=True, description="线程ID")
    thread_name = fields.CharField(max_length=255, null=True, description="线程名称")

    class Meta:
        table = "system_logs"
        default_connection = "local_data"
        indexes = [
            ("timestamp",),
            ("level",),
            ("module",),
            ("function",),
        ]


# class APILog(Model):
#     """API 相关日志模型"""
#     id = fields.IntField(pk=True, auto_generate=True)
#     timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="日志时间")
#     level = fields.CharField(max_length=10, description="日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL")
#     api_request = fields.ForeignKeyField("monitor_models.APIRequest", null=True, description="关联的内部API请求")
#     outbound_api_request = fields.ForeignKeyField("monitor_models.OutboundAPIRequest", null=True, description="关联的对外API请求")
#     message = fields.TextField(description="日志消息")
#     details = fields.TextField(null=True, description="详细信息")
#     stack_trace = fields.TextField(null=True, description="堆栈跟踪")

#     class Meta:
#         table = "api_logs"
#         default_connection = "local_data"
#         indexes = [
#             ("timestamp",),
#             ("level",),
#             ("api_request",),
#             ("outbound_api_request",),
#         ]


# class PerformanceLog(Model):
#     """性能日志模型"""
#     id = fields.IntField(pk=True, auto_generate=True)
#     timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="日志时间")
#     operation = fields.CharField(max_length=255, description="操作名称")
#     duration = fields.FloatField(description="执行时间（毫秒）")
#     module = fields.CharField(max_length=255, description="模块名称")
#     function = fields.CharField(max_length=255, description="函数名称")
#     details = fields.TextField(null=True, description="详细信息")
#     is_slow = fields.BooleanField(default=False, description="是否慢操作")
#     slow_threshold = fields.FloatField(null=True, description="慢操作阈值（毫秒）")

#     class Meta:
#         table = "performance_logs"
#         default_connection = "local_data"
#         indexes = [
#             ("timestamp",),
#             ("operation",),
#             ("duration",),
#             ("module",),
#             ("is_slow",),
#         ]


# class SecurityLog(Model):
#     """安全日志模型"""
#     id = fields.IntField(pk=True, auto_generate=True)
#     timestamp = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="日志时间")
#     event_type = fields.CharField(max_length=50, description="事件类型：登录、登出、权限变更等")
#     user = fields.CharField(max_length=255, null=True, description="用户标识")
#     ip_address = fields.CharField(max_length=64, null=True, description="IP地址")
#     action = fields.TextField(description="操作描述")
#     status = fields.CharField(max_length=20, description="状态：成功、失败")
#     details = fields.TextField(null=True, description="详细信息")

#     class Meta:
#         table = "security_logs"
#         default_connection = "local_data"
#         indexes = [
#             ("timestamp",),
#             ("event_type",),
#             ("user",),
#             ("ip_address",),
#             ("status",),
#         ]