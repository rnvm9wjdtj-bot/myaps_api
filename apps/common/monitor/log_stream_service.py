"""
日志流服务 - 完全独立于现有日志系统

通过添加额外的日志处理器来收集日志，不影响现有日志输出
"""

import asyncio
import logging
from collections import deque
from typing import Set, List, Dict, Optional


class LogStreamService:
    """独立的日志流服务"""

    def __init__(self, max_queue_size: int = 1000):
        self._log_queue = deque(maxlen=max_queue_size)
        self._active_connections: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._is_running = False
        self._broadcast_task = None
        self._handler = None
        self._registered_loggers = set()  # 记录已注册的logger

    async def start(self):
        """启动日志流服务"""
        self._is_running = True
        self._broadcast_task = asyncio.create_task(self._broadcast_logs())
        # 添加日志处理器（不影响现有日志）
        self._add_log_handler()
        logging.info("[日志流] 服务已启动")

    async def stop(self):
        """停止日志流服务"""
        self._is_running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()
        # 移除日志处理器
        self._remove_log_handler()
        async with self._lock:
            for queue in self._active_connections:
                await queue.put(None)
        logging.info("[日志流] 服务已停止")

    def _add_log_handler(self):
        """添加自定义日志处理器（不影响现有处理器）"""
        if self._handler is None:
            self._handler = _LogStreamHandler(self)
            # 设置 handler 的级别为 DEBUG，确保能捕获所有级别
            self._handler.setLevel(logging.DEBUG)
            
            # 将处理器注册到 logger 模块的全局列表中
            try:
                from globalobjects import logger as log_module
                if hasattr(log_module, '_log_stream_handlers'):
                    if self._handler not in log_module._log_stream_handlers:
                        log_module._log_stream_handlers.append(self._handler)
                        logging.info(f"[日志流] 已注册处理器到日志模块")
            except Exception as e:
                logging.error(f"[日志流] 注册处理器失败: {e}", exc_info=True)
            
            logging.info("[日志流] 日志处理器已注册")

    def _remove_log_handler(self):
        """移除日志处理器"""
        if self._handler:
            # 从 root logger 移除
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._handler)
            
            # 从日志模块的 logger 实例移除
            for logger in self._registered_loggers:
                try:
                    logger.removeHandler(self._handler)
                except Exception:
                    pass
            
            # 移除钩子
            try:
                from globalobjects import logger as log_module
                if hasattr(log_module, '_log_stream_handlers'):
                    if self._handler in log_module._log_stream_handlers:
                        log_module._log_stream_handlers.remove(self._handler)
            except Exception:
                pass
            
            self._registered_loggers.clear()
            self._handler = None
            logging.info("[日志流] 日志处理器已移除")

    def enqueue_log(self, record: logging.LogRecord):
        """将日志加入队列"""
        log_data = {
            "timestamp": record.created,
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "logger_name": record.name
        }
        self._log_queue.append(log_data)

    def enqueue_log_dict(self, log_data: dict):
        """直接将日志字典加入队列"""
        self._log_queue.append(log_data)

    async def subscribe(self) -> asyncio.Queue:
        """订阅日志流"""
        queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._active_connections.add(queue)
        # 发送最近的历史日志
        recent_logs = self.get_recent_logs(50)
        for log in recent_logs:
            await queue.put(log)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """取消订阅"""
        async with self._lock:
            self._active_connections.discard(queue)

    def get_recent_logs(self, count: int = 50) -> List[dict]:
        """获取最近的日志"""
        return list(self._log_queue)[-count:]

    async def _broadcast_logs(self):
        """广播日志到所有订阅者"""
        while self._is_running:
            if self._log_queue:
                log_data = self._log_queue.popleft()
                async with self._lock:
                    queues = list(self._active_connections)
                for queue in queues:
                    try:
                        queue.put_nowait(log_data)
                    except asyncio.QueueFull:
                        pass
            await asyncio.sleep(0.01)


class _LogStreamHandler(logging.Handler):
    """
    内部日志处理器 - 只负责收集日志到日志流服务
    不输出到任何地方，不影响现有日志
    """

    def __init__(self, service: LogStreamService):
        super().__init__(logging.DEBUG)  # 捕获所有级别
        self._service = service

    def emit(self, record: logging.LogRecord):
        """处理日志记录 - 只是收集，不输出"""
        self._service.enqueue_log(record)


# 创建全局实例
log_stream_service = LogStreamService()


# 启动/停止函数
async def start_log_stream():
    await log_stream_service.start()


async def stop_log_stream():
    await log_stream_service.stop()
