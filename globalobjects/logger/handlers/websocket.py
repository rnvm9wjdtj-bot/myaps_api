"""
统一日志系统 - WebSocket处理器

支持实时日志流推送
"""

import sys
import logging
import asyncio
import json
from typing import Set, Optional, Any, Dict
from datetime import datetime

from ..models import LogRecord
from .base import StreamHandler


class WebSocketHandler(StreamHandler):
    """
    WebSocket处理器
    
    特性：
    - 实时推送日志到WebSocket客户端
    - 支持订阅级别过滤
    - 断线自动清理
    - 连接数限制
    """
    
    def __init__(
        self,
        level: int = logging.DEBUG,
        enabled: bool = True,
        max_connections: int = 100
    ):
        """
        初始化WebSocket处理器
        
        Args:
            level: 最低日志级别
            enabled: 是否启用
            max_connections: 最大连接数
        """
        super().__init__(level, enabled)
        
        self._max_connections = max_connections
        self._connections: Set[Any] = set()
        self._level_filters: Dict[Any, int] = {}
        self._lock = asyncio.Lock()
        
        self._stats = {
            'total_sent': 0,
            'total_failed': 0,
            'connections_total': 0
        }
    
    async def emit_async(self, record: LogRecord) -> None:
        """异步推送日志"""
        if not self._enabled:
            return
        
        if not self._connections:
            return
        
        message = self._build_message(record)
        message_str = json.dumps(message, ensure_ascii=False)
        
        disconnected = set()
        
        async with self._lock:
            for ws in self._connections:
                level_filter = self._level_filters.get(ws, logging.DEBUG)
                
                if record.level < level_filter:
                    continue
                
                try:
                    await ws.send_text(message_str)
                    self._stats['total_sent'] += 1
                except Exception:
                    disconnected.add(ws)
                    self._stats['total_failed'] += 1
            
            for ws in disconnected:
                self._connections.discard(ws)
                self._level_filters.pop(ws, None)
    
    def emit(self, record: LogRecord) -> None:
        """同步推送（通过队列）"""
        pass
    
    def _build_message(self, record: LogRecord) -> Dict[str, Any]:
        """构建WebSocket消息"""
        return {
            'type': 'log',
            'time': record.timestamp.isoformat(),
            'level': record.level_name,
            'message': record.message,
            'module': record.module,
            'function': record.function,
            'line': record.line,
            'extra': record.extra
        }
    
    async def subscribe(
        self,
        ws: Any,
        level: str = "DEBUG"
    ) -> bool:
        """
        订阅日志流
        
        Args:
            ws: WebSocket连接
            level: 最低日志级别
            
        Returns:
            bool: 成功订阅返回True
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                return False
            
            self._connections.add(ws)
            
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            self._level_filters[ws] = level_map.get(level.upper(), logging.DEBUG)
            
            self._stats['connections_total'] += 1
            return True
    
    async def unsubscribe(self, ws: Any) -> None:
        """
        取消订阅
        
        Args:
            ws: WebSocket连接
        """
        async with self._lock:
            self._connections.discard(ws)
            self._level_filters.pop(ws, None)
    
    def get_connections_count(self) -> int:
        """获取当前连接数"""
        return len(self._connections)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            'current_connections': len(self._connections),
            'max_connections': self._max_connections
        }
    
    async def broadcast(self, message: str) -> None:
        """
        广播消息到所有连接
        
        Args:
            message: 消息内容
        """
        disconnected = set()
        
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.add(ws)
            
            for ws in disconnected:
                self._connections.discard(ws)
                self._level_filters.pop(ws, None)
    
    def close(self) -> None:
        """关闭处理器"""
        self._connections.clear()
        self._level_filters.clear()


class LogStreamManager:
    """
    日志流管理器
    
    管理多个WebSocket连接和日志推送
    """
    
    def __init__(self, max_connections: int = 100):
        self._handler = WebSocketHandler(
            level=logging.DEBUG,
            enabled=True,
            max_connections=max_connections
        )
        self._handlers: Set[Any] = set()
    
    def get_handler(self) -> WebSocketHandler:
        """获取WebSocket处理器"""
        return self._handler
    
    def add_handler(self, handler: Any) -> None:
        """添加外部处理器"""
        self._handlers.add(handler)
    
    def remove_handler(self, handler: Any) -> None:
        """移除外部处理器"""
        self._handlers.discard(handler)
    
    def get_handlers(self) -> Set[Any]:
        """获取所有处理器"""
        return self._handlers
    
    def emit_to_handlers(self, record: Any) -> None:
        """
        发送到所有处理器
        
        Args:
            record: 日志记录（logging.LogRecord）
        """
        for handler in self._handlers:
            try:
                handler.emit(record)
            except Exception:
                pass
    
    async def subscribe(self, ws: Any, level: str = "DEBUG") -> bool:
        """订阅日志流"""
        return await self._handler.subscribe(ws, level)
    
    async def unsubscribe(self, ws: Any) -> None:
        """取消订阅"""
        await self._handler.unsubscribe(ws)


_log_stream_manager = LogStreamManager()
