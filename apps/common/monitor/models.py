from tortoise import fields
from tortoise.models import Model
from datetime import datetime


class APIRequest(Model):
    """API 请求记录模型"""
    id = fields.IntField(pk=True, auto_generate=True)
    timestamp = fields.DatetimeField(default=datetime.utcnow, description="请求时间")
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
    
    class Meta:
        table = "api_requests"
        indexes = [
            ("timestamp",),
            ("path",),
            ("status_code",),
            ("response_time",),
            ("is_slow",),
            ("is_error",),
        ]


class OutboundAPIRequest(Model):
    """对外 HTTP 请求记录模型"""
    id = fields.IntField(pk=True, auto_generate=True)
    timestamp = fields.DatetimeField(default=datetime.utcnow, description="请求时间")
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
    
    class Meta:
        table = "outbound_api_requests"
        indexes = [
            ("timestamp",),
            ("module",),
            ("status_code",),
            ("is_error",),
            ("is_slow",),
        ]
