"""
异步HTTP客户端实现

基于aiohttp库，提供真正的异步HTTP请求功能。
"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional, Union
from ._base import console_log, _DEFAULT_CONNECT_TIMEOUT, _DEFAULT_READ_TIMEOUT


class AsyncHttpClient:
    """异步HTTP客户端
    
    基于aiohttp库，提供真正的异步HTTP请求功能。
    """
    
    def __init__(
        self,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = _DEFAULT_READ_TIMEOUT,
        max_connections: int = 100,
        enable_http2: bool = True
    ):
        """
        初始化异步HTTP客户端
        
        Args:
            connect_timeout: 连接超时时间（秒）
            read_timeout: 读取超时时间（秒）
            max_connections: 最大连接数
            enable_http2: 是否启用HTTP/2
        """
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._max_connections = max_connections
        self._enable_http2 = enable_http2
        self._session = None
    
    async def __aenter__(self):
        """异步上下文管理入口"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理出口"""
        await self.close()
    
    async def _ensure_session(self):
        """确保会话存在"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                connect=self._connect_timeout,
                sock_read=self._read_timeout
            )
            connector = aiohttp.TCPConnector(
                limit=self._max_connections,
                limit_per_host=max(10, self._max_connections // 5),
                enable_cleanup_closed=True,
                force_close=False,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                http2=self._enable_http2
            )
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法
            url: 请求URL
            headers: 请求头
            json: JSON数据
            params: 查询参数
            **kwargs: 其他参数
            
        Returns:
            aiohttp.ClientResponse: 响应对象
        """
        await self._ensure_session()
        
        try:
            response = await self._session.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
                **kwargs
            )
            return response
        except Exception as e:
            console_log.fail("异步HTTP请求", url, str(e))
            raise
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """发送GET请求"""
        return await self.request(
            method="GET",
            url=url,
            headers=headers,
            params=params,
            **kwargs
        )
    
    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """发送POST请求"""
        return await self.request(
            method="POST",
            url=url,
            headers=headers,
            json=json,
            **kwargs
        )
    
    async def patch(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """发送PATCH请求"""
        return await self.request(
            method="PATCH",
            url=url,
            headers=headers,
            json=json,
            **kwargs
        )
    
    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """发送DELETE请求"""
        return await self.request(
            method="DELETE",
            url=url,
            headers=headers,
            json=json,
            **kwargs
        )
    
    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        """获取会话对象"""
        return self._session
