"""
HTTP 客户端包装器

用于捕获所有对外 HTTP 请求，记录请求和响应信息
"""

import time
import inspect
from typing import Dict, Any, Optional, Union
import json
from .collectors.outbound_http_collector import outbound_http_collector


class HTTPMonitorWrapper:
    """接收请求包装器"""
    
    def __init__(self, client):
        """
        初始化 HTTP 监控包装器
        
        Args:
            client: 原始 HTTP 客户端（requests.Session 或 httpx.Client 等）
        """
        self.client = client
        self.collector = outbound_http_collector
    
    def request(self, method: str, url: str, **kwargs) -> Any:
        """
        执行 HTTP 请求并记录监控信息
        
        Args:
            method: HTTP 方法
            url: 请求 URL
            **kwargs: 其他请求参数
            
        Returns:
            响应对象
        """
        # 记录请求开始时间
        start_time = time.time()
        error_message = None
        request_body = None
        response_body = None
        response_headers = {}
        
        try:
            # 提取请求体
            if 'json' in kwargs:
                request_body = kwargs['json']
            elif 'data' in kwargs:
                request_body = kwargs['data']
            
            # 执行请求
            response = self.client.request(method, url, **kwargs)
            status_code = response.status_code
            
            # 提取响应头
            if hasattr(response, 'headers'):
                response_headers = dict(response.headers)
            
            # 尝试提取响应体
            try:
                if hasattr(response, 'json'):
                    response_body = response.json()
                elif hasattr(response, 'text'):
                    response_body = response.text
            except Exception:
                # JSON解析失败，尝试获取响应文本
                if hasattr(response, 'text'):
                    response_body = response.text
                
        except Exception as e:
            status_code = 500
            error_message = str(e)
            raise
        finally:
            # 计算响应时间
            duration = time.time() - start_time
            
            # 获取调用模块
            module = self._get_calling_module()
            
            # 记录请求信息
            self.collector.record_request_sync(
                method=method,
                url=url,
                status_code=status_code,
                duration=duration,
                request_headers=kwargs.get('headers', {}),
                request_body=request_body,
                response_headers=response_headers,
                response_body=response_body,
                error_message=error_message,
                module=module
            )
        
        return response
    
    def get(self, url: str, **kwargs) -> Any:
        """执行 GET 请求"""
        return self.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> Any:
        """执行 POST 请求"""
        return self.request('POST', url, **kwargs)
    
    def put(self, url: str, **kwargs) -> Any:
        """执行 PUT 请求"""
        return self.request('PUT', url, **kwargs)
    
    def patch(self, url: str, **kwargs) -> Any:
        """执行 PATCH 请求"""
        return self.request('PATCH', url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> Any:
        """执行 DELETE 请求"""
        return self.request('DELETE', url, **kwargs)
    
    def head(self, url: str, **kwargs) -> Any:
        """执行 HEAD 请求"""
        return self.request('HEAD', url, **kwargs)
    
    def options(self, url: str, **kwargs) -> Any:
        """执行 OPTIONS 请求"""
        return self.request('OPTIONS', url, **kwargs)
    
    def send(self, request, **kwargs) -> Any:
        """
        执行 HTTP 请求并记录监控信息（覆盖 requests.Session.send 方法）
        
        Args:
            request: PreparedRequest 对象
            **kwargs: 其他请求参数
            
        Returns:
            响应对象
        """
        # 记录请求开始时间
        start_time = time.time()
        error_message = None
        request_body = None
        response_body = None
        response_headers = {}
        method = None
        url = None
        status_code = 500
        request_headers = {}
        
        try:
            # 提取请求信息
            method = request.method
            url = request.url
            
            # 提取请求体
            if hasattr(request, 'body') and request.body:
                request_body = request.body
            
            # 提取请求头
            request_headers = dict(request.headers) if hasattr(request, 'headers') else {}
            
            # 执行请求
            if hasattr(self.client, 'send'):
                # 使用 send 方法
                response = self.client.send(request, **kwargs)
            else:
                # 对于没有 send 方法的客户端（如 HttpxSessionWrapper），使用 request 方法
                # 提取请求数据
                if hasattr(request, 'body'):
                    kwargs['data'] = request.body
                kwargs['headers'] = request.headers
                response = self.client.request(method, url, **kwargs)
            
            status_code = response.status_code
            
            # 提取响应头
            if hasattr(response, 'headers'):
                response_headers = dict(response.headers)
            
            # 尝试提取响应体
            try:
                if hasattr(response, 'json'):
                    response_body = response.json()
                elif hasattr(response, 'text'):
                    response_body = response.text
            except Exception:
                # JSON解析失败，尝试获取响应文本
                if hasattr(response, 'text'):
                    response_body = response.text
                
        except Exception as e:
            status_code = 500
            error_message = str(e)
            raise
        finally:
            # 计算响应时间
            duration = time.time() - start_time
            
            # 获取调用模块
            module = self._get_calling_module()
            
            # 确保 method 和 url 有值
            if not method:
                method = 'UNKNOWN'
            if not url:
                url = 'UNKNOWN'
            
            # 记录请求信息
            self.collector.record_request_sync(
                method=method,
                url=url,
                status_code=status_code,
                duration=duration,
                request_headers=request_headers,
                request_body=request_body,
                response_headers=response_headers,
                response_body=response_body,
                error_message=error_message,
                module=module
            )
        
        return response
    
    def _get_calling_module(self) -> str:
        """
        获取调用模块的名称
        
        Returns:
            模块名称
        """
        # 遍历调用栈，找到第一个不是本文件的调用者
        for frame in inspect.stack():
            module = inspect.getmodule(frame[0])
            if module and module.__name__ != __name__:
                return module.__name__
        return 'unknown'
    
    # 代理其他属性和方法
    def __getattr__(self, name):
        """代理属性和方法到原始客户端"""
        # 对于 HTTP 请求方法，确保调用的是本类中覆盖的方法
        if name in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'send']:
            return getattr(self, name)
        
        # 对于其他属性和方法，代理到原始客户端
        return getattr(self.client, name)
    
    def __enter__(self):
        """支持上下文管理器"""
        if hasattr(self.client, '__enter__'):
            self.client.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        if hasattr(self.client, '__exit__'):
            return self.client.__exit__(exc_type, exc_val, exc_tb)
