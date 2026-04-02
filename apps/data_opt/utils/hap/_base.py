"""
基础配置和类型定义
"""

import os
import queue
import threading
from typing import TypeVar

from globalobjects import CACHE_JSON, logger as log_config
from globalobjects.logger import LogHelper
from globalobjects.json_manager import JSONManager


# 初始化日志系统（确保日志监听器已启动）
log_config.initialize_logging()
# 获取基础日志器
logger = log_config.get_logger(__name__)
# 为 HAP 模块创建专用的异步日志队列
_hap_log_queue = queue.Queue(-1)

# 创建自定义的异步日志处理器
class AsyncLogHandler:
    """异步日志处理器，支持缓冲和批量写入"""
    def __init__(self, queue_size=100, flush_interval=1.0):
        self.queue = queue.Queue(maxsize=queue_size)
        self.flush_interval = flush_interval
        self.running = True
        self.buffer = []
        self.buffer_size = 0
        self.max_buffer_size = 50
        self.lock = threading.Lock()
        
        # 启动后台刷新线程
        self.flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.flush_thread.start()
    
    def _flush_loop(self):
        """后台刷新循环"""
        while self.running:
            try:
                # 等待指定时间或队列中有数据
                try:
                    item = self.queue.get(timeout=self.flush_interval)
                    self._add_to_buffer(item)
                except queue.Empty:
                    pass
                
                # 检查是否需要刷新
                self._flush_if_needed()
            except Exception:
                pass
    
    def _add_to_buffer(self, item):
        """添加到缓冲区"""
        with self.lock:
            self.buffer.append(item)
            self.buffer_size += 1
            if self.buffer_size >= self.max_buffer_size:
                self._flush_buffer()
    
    def _flush_if_needed(self):
        """检查并刷新缓冲区"""
        with self.lock:
            if self.buffer:
                self._flush_buffer()
    
    def _flush_buffer(self):
        """刷新缓冲区"""
        if not self.buffer:
            return
        
        # 批量处理日志
        buffer_copy = self.buffer.copy()
        self.buffer.clear()
        self.buffer_size = 0
        
        # 实际写入日志
        for level, msg, args, kwargs in buffer_copy:
            if level == 'debug':
                logger.debug(msg, *args, **kwargs)
            elif level == 'info':
                logger.info(msg, *args, **kwargs)
            elif level == 'warning':
                logger.warning(msg, *args, **kwargs)
            elif level == 'error':
                logger.error(msg, *args, **kwargs)
            elif level == 'critical':
                logger.critical(msg, *args, **kwargs)
    
    def log(self, level, msg, *args, **kwargs):
        """记录日志"""
        try:
            self.queue.put((level, msg, args, kwargs), block=False)
        except queue.Full:
            # 队列满时直接写入
            if level == 'debug':
                logger.debug(msg, *args, **kwargs)
            elif level == 'info':
                logger.info(msg, *args, **kwargs)
            elif level == 'warning':
                logger.warning(msg, *args, **kwargs)
            elif level == 'error':
                logger.error(msg, *args, **kwargs)
            elif level == 'critical':
                logger.critical(msg, *args, **kwargs)
    
    def stop(self):
        """停止日志处理器"""
        self.running = False
        self.flush_thread.join(timeout=2.0)
        self._flush_buffer()




# 创建异步日志处理器实例
_async_log_handler = AsyncLogHandler()

# 创建异步日志包装器
class AsyncLogger:
    """异步日志包装器"""
    def __init__(self, name):
        self.name = name
    
    def debug(self, msg, *args, **kwargs):
        _async_log_handler.log('debug', msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        _async_log_handler.log('info', msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        _async_log_handler.log('warning', msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        _async_log_handler.log('error', msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        _async_log_handler.log('critical', msg, *args, **kwargs)
    
    def exception(self, msg, *args, **kwargs):
        logger.exception(msg, *args, **kwargs)
    
    def success(self, action: str, subject: str = "", details: str = "", to_file: bool = False):
        _async_log_handler.log('info', LogHelper.success(action, subject, details))
    
    def fail(self, action: str, subject: str = "", reason: str = "", to_file: bool = True):
        _async_log_handler.log('error', LogHelper.fail(action, subject, reason))
    
    def start(self, action: str, subject: str = "", to_file: bool = False):
        _async_log_handler.log('info', LogHelper.start(action, subject))
    
    def stop(self, action: str, subject: str = "", to_file: bool = False):
        _async_log_handler.log('info', LogHelper.stop(action, subject))
    
    def status_change(self, subject: str, old_status: str, new_status: str, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.status_change(subject, old_status, new_status))
    
    def api_response(self, api_name: str, status_code: int, details: str = "", to_file: bool = False):
        msg = LogHelper.api_response(api_name, status_code, details)
        if 200 <= status_code < 300:
            _async_log_handler.log('info', msg)
        else:
            _async_log_handler.log('error', msg)
    
    def query(self, target: str, result: str = "", count: int = None, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.query(target, result, count))
    
    def insert(self, target: str, subject: str = "", count: int = None, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.insert(target, subject, count))
    
    def update(self, target: str, subject: str = "", count: int = None, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.update(target, subject, count))
    
    def delete(self, target: str, subject: str = "", count: int = None, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.delete(target, subject, count))
    
    def warning_msg(self, subject: str, message: str, to_file: bool = True):
        _async_log_handler.log('warning', LogHelper.warning(subject, message))
    
    def sync(self, action: str, subject: str = "", details: str = "", to_file: bool = False):
        _async_log_handler.log('info', LogHelper.sync(action, subject, details))
    
    def connect(self, target: str, status: str = "成功", to_file: bool = False):
        msg = LogHelper.connect(target, status)
        if status == "成功":
            _async_log_handler.log('info', msg)
        else:
            _async_log_handler.log('error', msg)
    
    def disconnect(self, target: str, to_file: bool = False):
        _async_log_handler.log('info', LogHelper.disconnect(target))
    
    def cache(self, action: str, target: str = "", details: str = "", to_file: bool = False):
        _async_log_handler.log('info', LogHelper.cache(action, target, details))


# 替换为异步日志器
console_log = AsyncLogger(__name__)


def shutdown_hap_logging():
    """关闭 HAP 模块的日志系统"""
    global _async_log_handler
    if _async_log_handler:
        _async_log_handler.stop()
        console_log.stop("HAP模块日志系统")


# 类型定义
ModelType = TypeVar('ModelType', bound='Model')

_CACHE_HAP = CACHE_JSON.get("hap", {})
_SAAS_BASEURL = "https://api.mingdao.com"

class HapConfig:
    """HAP 配置类"""
    def __init__(self, cache_file: str | JSONManager = CACHE_JSON):
        if isinstance(cache_file, str):
            self.cache_file = JSONManager(cache_file)
        else:
            self.cache_file = cache_file
        
        CACHE_HAP = self.cache_file.get("hap", {})
        self.MAX_WORKERS = CACHE_HAP.get("max_workers", os.cpu_count() * 10)
        # 调用刷新函数时，距离上次刷新超过这个秒数，才会刷新行数据，否则直接返回缓存数据
        self.REFRESH_INTERVAL_SECONDS = 60
        self.BASE_URL = CACHE_HAP.get("base_url", _SAAS_BASEURL)
        # QPS 限制，SAAS环境默认 50
        self.QPS_LIMIT = 50 if self.BASE_URL == _SAAS_BASEURL else 1000
        self.APP_KEY = CACHE_HAP.get("app_key", "")
        self.SIGN = CACHE_HAP.get("sign", "")
        self.DESCRIPTION = CACHE_HAP.get("description", "")
        # 是否启用 HTTP/2 支持，当私有部署时默认启用
        self.ENABLE_HTTP2 = CACHE_HAP.get("enable_http2", True) and self.BASE_URL != _SAAS_BASEURL
        # 每个模型缓存的最大记录数
        self.CACHE_MAX_SIZE = CACHE_HAP.get("cache_max_size", 10000)
        # 内存阈值（MB），超过时触发清理
        self.MEMORY_THRESHOLD_MB = CACHE_HAP.get("memory_threshold_mb", 2048)
        # 是否启用内存管理（默认 True）
        self.ENABLE_MEMORY_MANAGEMENT = CACHE_HAP.get("enable_memory_management", True)

# 配置常量
_MAX_CONCURRENCY = _CACHE_HAP.get("max_concurrency", os.cpu_count() * 8)
_DEFAULT_BUFFER_SIZE = _CACHE_HAP.get("default_buffer_size", 200)
_ADAPTIVE_MIN_BUFFER_SIZE = _CACHE_HAP.get("adaptive_min_buffer_size", 50)
_ADAPTIVE_SCALE_UP_FAST = _CACHE_HAP.get("adaptive_scale_up_fast", 1.5)
_ADAPTIVE_SCALE_UP_SLOW = _CACHE_HAP.get("adaptive_scale_up_slow", 1.3)
_ADAPTIVE_SCALE_DOWN = _CACHE_HAP.get("adaptive_scale_down", 0.8)
_ADAPTIVE_SCALE_DOWN_FAST = _CACHE_HAP.get("adaptive_scale_down_fast", 0.5)
_DEFAULT_MAX_RETRIES = _CACHE_HAP.get("default_max_retries", 3)
_DEFAULT_RETRY_DELAY = _CACHE_HAP.get("default_retry_delay", 1.0)



_DEFAULT_CONNECT_TIMEOUT = _CACHE_HAP.get("connect_timeout", 10.0)    # 增加连接超时时间
_DEFAULT_READ_TIMEOUT = _CACHE_HAP.get("read_timeout", 120.0) # 增加读取超时时间
_DEFAULT_BASE_CONNECT_TIMEOUT = _CACHE_HAP.get("base_connect_timeout", 10.0)
_DEFAULT_BASE_READ_TIMEOUT = _CACHE_HAP.get("base_read_timeout", 120.0)

_DEFAULT_RETRY_BASE_DELAY = _CACHE_HAP.get("retry_base_delay", 0.5)
_DEFAULT_RETRY_MAX_DELAY = _CACHE_HAP.get("retry_max_delay", 30.0)
_DEFAULT_RETRY_EXPONENTIAL_BASE = _CACHE_HAP.get("retry_exponential_base", 2.0)
_DEFAULT_RETRY_JITTER = _CACHE_HAP.get("retry_jitter", 0.1)

_DEFAULT_BATCH_MAX_SIZE = _CACHE_HAP.get("batch_max_size", 500)

_DEFAULT_WARM_CONNECTIONS = _CACHE_HAP.get("warm_connections", 5)    # 预热连接数不超过池大小
_DEFAULT_WARMUP_TIMEOUT = _CACHE_HAP.get("warmup_timeout", 5.0)

_DEFAULT_NETWORK_LATENCY = _CACHE_HAP.get("default_network_latency", 100.0)  # 估算网络延迟ms（可以根据实际情况调整）
_DEFAULT_PAGE_SIZE = _CACHE_HAP.get("page_size", 1000)   # 设置每页大小
