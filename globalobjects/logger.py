import os
import logging
import queue
import time
import sys
import platform
from typing import Optional, Dict, Any
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener

# 检测终端是否支持ANSI颜色
def is_terminal_supports_ansi():
    """
    检测终端是否支持ANSI颜色
    """
    # 检查是否在Windows系统上
    if platform.system() == 'Windows':
        # 在Windows上，检查是否是现代终端
        import ctypes
        try:
            # 获取控制台句柄
            hConsole = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            # 检查是否支持虚拟终端处理
            mode = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetConsoleMode(hConsole, ctypes.byref(mode)):
                # 启用虚拟终端处理
                new_mode = mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                if ctypes.windll.kernel32.SetConsoleMode(hConsole, new_mode):
                    return True
        except Exception:
            pass
        # 回退到不支持
        return False
    else:
        # 在非Windows系统上，检查是否连接到终端
        return sys.stdout.isatty()

# 全局变量
TERMINAL_SUPPORTS_ANSI = is_terminal_supports_ansi()

# 尝试导入ctypes并获取控制台句柄
import ctypes
try:
    # 获取控制台句柄
    hConsole = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    
    # 定义CONSOLE_SCREEN_BUFFER_INFO结构
    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("dwCursorPosition", ctypes.c_ulong * 2),
            ("wAttributes", ctypes.c_ushort),
            ("srWindow", ctypes.c_ulong * 4),
            ("dwMaximumWindowSize", ctypes.c_ulong * 2),
        ]
    
    # 保存当前颜色
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(hConsole, ctypes.byref(csbi))
    original_color = csbi.wAttributes
    
    # Windows控制台颜色常量
    FOREGROUND_BLUE = 0x0001
    FOREGROUND_GREEN = 0x0002
    FOREGROUND_RED = 0x0004
    FOREGROUND_INTENSITY = 0x0008
    
    # 颜色映射
    LEVEL_COLORS = {
        'DEBUG': FOREGROUND_BLUE | FOREGROUND_GREEN | FOREGROUND_INTENSITY,  # 青色
        'INFO': FOREGROUND_GREEN | FOREGROUND_INTENSITY,  # 绿色
        'WARNING': FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_INTENSITY,  # 黄色
        'ERROR': FOREGROUND_RED | FOREGROUND_INTENSITY,  # 红色
        'CRITICAL': FOREGROUND_RED | FOREGROUND_INTENSITY,  # 红色
    }
    
    # 是否支持Windows API
    SUPPORT_WINDOWS_API = True
except Exception as e:
    # 如果出错，设置为不支持
    SUPPORT_WINDOWS_API = False
    hConsole = None
    original_color = 0
    LEVEL_COLORS = {}
    print(f"获取控制台句柄失败: {e}")

# ANSI颜色代码
ANSI_COLORS = {
    'DEBUG': '\033[36m',  # 青色
    'INFO': '\033[32m',  # 绿色
    'WARNING': '\033[33m',  # 黄色
    'ERROR': '\033[31m',  # 红色
    'CRITICAL': '\033[31m',  # 红色
    'RESET': '\033[0m',  # 重置
}

# 全局日志配置
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# 默认日志格式
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(funcName)s:%(lineno)d - %(levelname)s - %(message)s'

# 结构化日志格式（JSON）
JSON_LOG_FORMAT = '''
{
    "timestamp": "%(asctime)s",
    "module": "%(name)s",
    "function": "%(funcName)s",
    "line": %(lineno)d,
    "level": "%(levelname)s",
    "message": "%(message)s"
}
'''

# 日志文件配置
LOG_CONFIG = {
    'default': {
        'filename': 'app.log',
        'level': 'INFO'
    },
    'error': {
        'filename': 'error.log',
        'level': 'ERROR'
    },
    'debug': {
        'filename': 'debug.log',
        'level': 'DEBUG'
    }
}

# 存储多个logger实例和对应的listener
logger_instances = {}
listeners = {}

# 存储日志器实例
_loggers: Dict[str, logging.Logger] = {}
_file_loggers: Dict[str, logging.Logger] = {}

# 是否已初始化
_initialized = False

# 模块日志器
_module_logger = None


class DatePrefixRotatingFileHandler(TimedRotatingFileHandler):
    """自定义的按时间轮转的文件处理器，支持日期前缀"""
    
    def __init__(self, *args, **kwargs):
        """初始化方法，确保编码参数被正确处理"""
        super().__init__(*args, **kwargs)
        # 确保编码参数被正确存储
        self.encoding = kwargs.get('encoding', 'utf-8')
        # 计算初始轮替时间
        self.rolloverAt = self.computeRollover(int(time.time()))
        get_module_logger().debug(f"初始化轮替时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.rolloverAt))}")
    
    def emit(self, record):
        """重写 emit 方法，确保轮替检查能够正常执行"""
        # 检查是否需要轮替
        current_time = int(time.time())
        if current_time >= self.rolloverAt:
            get_module_logger().debug(f"触发轮替检查，当前时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}, 轮替时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.rolloverAt))}")
            self.doRollover()
        super().emit(record)
    
    def doRollover(self):
        """重写轮转方法，实现日期前缀"""
        get_module_logger().debug("开始执行轮替操作")
        if self.stream:
            self.stream.close()
            self.stream = None
            get_module_logger().debug("已关闭当前日志流")
            
        # 获取当前时间
        current_time = int(time.time())
        get_module_logger().debug(f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))}")
        
        # 计算下一次轮转的时间
        self.rolloverAt = self.computeRollover(current_time)
        get_module_logger().debug(f"下一次轮替时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.rolloverAt))}")
        
        # 处理文件名
        if self.backupCount > 0:
            # 获取原始文件名的信息
            base_dir, filename = os.path.split(self.baseFilename)
            name_without_ext, ext = os.path.splitext(filename)
            get_module_logger().debug(f"原始文件名: {filename}")
            
            # 生成带日期前缀的文件名
            date_prefix = time.strftime("%Y%m%d", time.localtime(current_time))
            
            # 新的文件名格式：[日期前缀]_[原始文件名][扩展名]
            new_filename = f"{date_prefix}_{name_without_ext}{ext}"
            new_filepath = os.path.join(base_dir, new_filename)
            get_module_logger().debug(f"新文件名: {new_filename}")
            
            # 如果文件已存在，先删除
            if os.path.exists(new_filepath):
                os.remove(new_filepath)
                get_module_logger().debug(f"已删除已存在的文件: {new_filepath}")
            
            # 重命名当前文件（带重试机制，解决Windows文件占用问题）
            if os.path.exists(self.baseFilename):
                max_retries = 10
                retry_delay = 0.1
                for attempt in range(max_retries):
                    try:
                        os.rename(self.baseFilename, new_filepath)
                        get_module_logger().debug(f"已重命名文件: {self.baseFilename} -> {new_filepath}")
                        break
                    except PermissionError:
                        if attempt < max_retries - 1:
                            get_module_logger().debug(f"文件被占用，等待后重试 ({attempt + 1}/{max_retries})")
                            time.sleep(retry_delay)
                        else:
                            get_module_logger().error(f"重命名文件失败，已达到最大重试次数: {self.baseFilename}")
                            raise
        
        # 重新打开文件
        self.mode = 'a'
        self.stream = self._open()
        get_module_logger().debug(f"已重新打开日志文件: {self.baseFilename}")
        get_module_logger().debug("轮替操作完成")


def get_module_logger() -> logging.Logger:
    """获取模块日志器"""
    global _module_logger
    if _module_logger is None:
        _module_logger = logging.getLogger(__name__)
        _module_logger.setLevel(logging.DEBUG)
        _module_logger.propagate = False
        
        # 配置控制台日志
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
        console_handler.setFormatter(formatter)
        _module_logger.addHandler(console_handler)
    return _module_logger


def setup_file_logging(log_name: str, log_filename='app.log') -> logging.Logger:
    """
    设置文件日志配置
    支持多个不同文件名的logger实例
    
    Args:
        log_name: 日志名称
        log_filename: 日志文件名
    
    Returns:
        logging.Logger: 配置好的logger实例
    """
    # 使用log_filename作为key，确保不同文件名有不同的logger
    logger_key = f"{log_name}:{log_filename}"
    
    if logger_key in logger_instances:
        return logger_instances[logger_key]

    logger = logging.getLogger(f"{log_name}_{log_filename}")
    # 防止重复添加处理器
    if logger.handlers:
        logger_instances[logger_key] = logger
        return logger

    logger.setLevel(logging.DEBUG)
    # 关闭日志传播，防止重复输出
    logger.propagate = False
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    # 创建按时间轮替的 FileHandler（支持日期前缀）
    get_module_logger().debug(f"创建日志处理器: {log_filename}")
    timed_handler = DatePrefixRotatingFileHandler(
        filename=os.path.join(log_dir, log_filename),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    timed_handler.setLevel(logging.DEBUG)
    timed_handler.setFormatter(formatter)

    # 创建队列和 QueueListener
    log_queue = queue.Queue(-1)
    listener = QueueListener(log_queue, timed_handler, respect_handler_level=True)
    
    # 存储listener
    listeners[logger_key] = listener

    # 创建 QueueHandler 并添加到 logger
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)

    # 存储logger实例
    logger_instances[logger_key] = logger

    # 注意：这里不在这里启动 listener，而是在 lifespan 的启动阶段启动
    get_module_logger().debug(f"日志配置完成: {logger_key}")
    return logger


def start_all_listeners():
    """启动所有存储的listener"""
    for key, listener in listeners.items():
        try:
            listener.start()
            get_module_logger().debug(f"已启动日志监听器: {key}")
        except Exception as e:
            get_module_logger().error(f"启动日志监听器失败 {key}: {e}")


def close_logging():
    """关闭所有日志系统"""
    # 停止并清理所有listener
    for key, listener in listeners.items():
        try:
            listener.stop()
        except AttributeError:
            # 处理listener未启动的情况
            pass
    listeners.clear()
    
    # 清理所有logger实例和其handlers
    for key, logger in logger_instances.items():
        # 移除所有handlers
        for handler in logger.handlers[:]:
            # 关闭handler
            if hasattr(handler, 'close'):
                handler.close()
            # 移除handler
            logger.removeHandler(handler)
    logger_instances.clear()


def get_log_level(level_name: str) -> int:
    """
    获取日志级别
    
    Args:
        level_name: 日志级别名称
        
    Returns:
        对应的日志级别数值
    """
    return LOG_LEVELS.get(level_name.upper(), logging.INFO)


def setup_console_logger(logger: logging.Logger, level: int = logging.INFO) -> None:
    """
    配置控制台日志处理器（支持彩色输出）
    
    Args:
        logger: 日志器实例
        level: 日志级别
    """
    # 移除已有的控制台处理器
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            logger.removeHandler(handler)
    
    # 移除logger的所有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 设置logger的级别
    logger.setLevel(level)
    
    # 重写logger的debug、info、warning、error和critical方法
    original_debug = logger.debug
    original_info = logger.info
    original_warning = logger.warning
    original_error = logger.error
    original_critical = logger.critical
    
    def debug_wrapper(msg, *args, **kwargs):
        """包装debug方法，添加彩色输出"""
        if TERMINAL_SUPPORTS_ANSI:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 使用ANSI颜色代码
                print(f"{ANSI_COLORS['DEBUG']}{timestamp} - DEBUG - {formatted_msg}{ANSI_COLORS['RESET']}")
            except Exception:
                # 如果出错，使用原始方法
                original_debug(msg, *args, **kwargs)
        elif SUPPORT_WINDOWS_API:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 设置控制台颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['DEBUG'])
                
                # 输出日志消息
                print(f"{timestamp} - DEBUG - {formatted_msg}")
                
                # 恢复原始颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                # 如果出错，使用原始方法
                original_debug(msg, *args, **kwargs)
        else:
            # 如果不支持任何颜色输出，使用原始方法
            original_debug(msg, *args, **kwargs)
    
    def info_wrapper(msg, *args, **kwargs):
        """包装info方法，添加彩色输出"""
        if TERMINAL_SUPPORTS_ANSI:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 使用ANSI颜色代码
                print(f"{ANSI_COLORS['INFO']}{timestamp} - INFO - {formatted_msg}{ANSI_COLORS['RESET']}")
            except Exception:
                # 如果出错，使用原始方法
                original_info(msg, *args, **kwargs)
        elif SUPPORT_WINDOWS_API:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 设置控制台颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['INFO'])
                
                # 输出日志消息
                print(f"{timestamp} - INFO - {formatted_msg}")
                
                # 恢复原始颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                # 如果出错，使用原始方法
                original_info(msg, *args, **kwargs)
        else:
            # 如果不支持任何颜色输出，使用原始方法
            original_info(msg, *args, **kwargs)
    
    def warning_wrapper(msg, *args, **kwargs):
        """包装warning方法，添加彩色输出"""
        if TERMINAL_SUPPORTS_ANSI:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 使用ANSI颜色代码
                print(f"{ANSI_COLORS['WARNING']}{timestamp} - WARNING - {formatted_msg}{ANSI_COLORS['RESET']}")
            except Exception:
                # 如果出错，使用原始方法
                original_warning(msg, *args, **kwargs)
        elif SUPPORT_WINDOWS_API:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 设置控制台颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['WARNING'])
                
                # 输出日志消息
                print(f"{timestamp} - WARNING - {formatted_msg}")
                
                # 恢复原始颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                # 如果出错，使用原始方法
                original_warning(msg, *args, **kwargs)
        else:
            # 如果不支持任何颜色输出，使用原始方法
            original_warning(msg, *args, **kwargs)
    
    def error_wrapper(msg, *args, **kwargs):
        """包装error方法，添加彩色输出"""
        if TERMINAL_SUPPORTS_ANSI:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 使用ANSI颜色代码
                print(f"{ANSI_COLORS['ERROR']}{timestamp} - ERROR - {formatted_msg}{ANSI_COLORS['RESET']}")
            except Exception:
                # 如果出错，使用原始方法
                original_error(msg, *args, **kwargs)
        elif SUPPORT_WINDOWS_API:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 设置控制台颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['ERROR'])
                
                # 输出日志消息
                print(f"{timestamp} - ERROR - {formatted_msg}")
                
                # 恢复原始颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                # 如果出错，使用原始方法
                original_error(msg, *args, **kwargs)
        else:
            # 如果不支持任何颜色输出，使用原始方法
            original_error(msg, *args, **kwargs)
    
    def critical_wrapper(msg, *args, **kwargs):
        """包装critical方法，添加彩色输出"""
        if TERMINAL_SUPPORTS_ANSI:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 使用ANSI颜色代码
                print(f"{ANSI_COLORS['CRITICAL']}{timestamp} - CRITICAL - {formatted_msg}{ANSI_COLORS['RESET']}")
            except Exception:
                # 如果出错，使用原始方法
                original_critical(msg, *args, **kwargs)
        elif SUPPORT_WINDOWS_API:
            try:
                # 获取当前时间
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                
                # 格式化日志消息
                formatted_msg = msg % args
                
                # 设置控制台颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['CRITICAL'])
                
                # 输出日志消息
                print(f"{timestamp} - CRITICAL - {formatted_msg}")
                
                # 恢复原始颜色
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                # 如果出错，使用原始方法
                original_critical(msg, *args, **kwargs)
        else:
            # 如果不支持任何颜色输出，使用原始方法
            original_critical(msg, *args, **kwargs)
    
    # 替换logger的方法
    logger.debug = debug_wrapper
    logger.info = info_wrapper
    logger.warning = warning_wrapper
    logger.error = error_wrapper
    logger.critical = critical_wrapper


# 定义一个彩色日志器类
class ColoredLogger(logging.Logger):
    """彩色日志器类"""
    def debug(self, msg, *args, **kwargs):
        """记录 DEBUG 级别的日志"""
        # 直接使用Windows API设置控制台颜色
        if SUPPORT_WINDOWS_API:
            try:
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['DEBUG'])
                super().debug(msg, *args, **kwargs)
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                super().debug(msg, *args, **kwargs)
        else:
            super().debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        """记录 INFO 级别的日志"""
        # 直接使用Windows API设置控制台颜色
        if SUPPORT_WINDOWS_API:
            try:
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['INFO'])
                super().info(msg, *args, **kwargs)
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                super().info(msg, *args, **kwargs)
        else:
            super().info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        """记录 WARNING 级别的日志"""
        # 直接使用Windows API设置控制台颜色
        if SUPPORT_WINDOWS_API:
            try:
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['WARNING'])
                super().warning(msg, *args, **kwargs)
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                super().warning(msg, *args, **kwargs)
        else:
            super().warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        """记录 ERROR 级别的日志"""
        # 直接使用Windows API设置控制台颜色
        if SUPPORT_WINDOWS_API:
            try:
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['ERROR'])
                super().error(msg, *args, **kwargs)
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                super().error(msg, *args, **kwargs)
        else:
            super().error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        """记录 CRITICAL 级别的日志"""
        # 直接使用Windows API设置控制台颜色
        if SUPPORT_WINDOWS_API:
            try:
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['CRITICAL'])
                super().critical(msg, *args, **kwargs)
                ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
            except Exception:
                super().critical(msg, *args, **kwargs)
        else:
            super().critical(msg, *args, **kwargs)

# 注册彩色日志器类
logging.setLoggerClass(ColoredLogger)

def setup_logger(name: str, level: str = 'INFO') -> logging.Logger:
    """
    设置日志器
    
    Args:
        name: 日志器名称
        level: 日志级别
        
    Returns:
        配置好的日志器实例
    """
    if name in _loggers:
        return _loggers[name]
    
    # 创建日志器
    logger = logging.getLogger(name)
    logger.setLevel(get_log_level(level))
    logger.propagate = False  # 防止日志传播
    
    # 配置控制台日志
    setup_console_logger(logger, get_log_level(level))
    
    # 存储日志器实例
    _loggers[name] = logger
    
    return logger


def get_file_logger(name: str, log_type: str = 'default') -> logging.Logger:
    """
    获取文件日志器
    
    Args:
        name: 日志器名称
        log_type: 日志类型，可选值: default, error, debug
        
    Returns:
        配置好的文件日志器实例
    """
    key = f"{name}:{log_type}"
    if key in _file_loggers:
        return _file_loggers[key]
    
    # 获取日志配置
    config = LOG_CONFIG.get(log_type, LOG_CONFIG['default'])
    
    # 使用 file_timed_logger 设置文件日志
    logger = setup_file_logging(name, config['filename'])
    logger.setLevel(get_log_level(config['level']))
    
    # 存储文件日志器实例
    _file_loggers[key] = logger
    
    return logger


def get_logger(name: Optional[str] = None, include_file: bool = False, log_type: str = 'default') -> logging.Logger:
    """
    获取统一的日志器
    
    Args:
        name: 日志器名称，默认使用调用模块的名称
        include_file: 是否包含文件日志
        log_type: 日志类型，可选值: default, error, debug
        
    Returns:
        配置好的日志器实例
    """
    # 如果没有提供名称，自动获取调用模块的名称
    if name is None:
        import inspect
        frame = inspect.currentframe()
        try:
            # 获取调用者的模块名
            if frame and frame.f_back:
                name = frame.f_back.f_globals.get('__name__', 'unknown')
            else:
                name = 'unknown'
        finally:
            if frame:
                del frame
    
    # 获取基础日志器
    logger = setup_logger(name)
    
    # 如果需要文件日志，添加文件处理器
    if include_file:
        file_logger = get_file_logger(name, log_type)
        # 确保文件日志器的处理器被正确添加
        for handler in file_logger.handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
    
    return logger


def initialize_logging() -> None:
    """
    初始化日志系统
    """
    global _initialized
    
    if _initialized:
        return
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 移除默认处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 定义一个使用Windows API的彩色StreamHandler
    class WindowsColorStreamHandler(logging.StreamHandler):
        """使用Windows API设置控制台颜色的StreamHandler"""
        def __init__(self, stream=None):
            super().__init__(stream)
        
        def emit(self, record):
            # 直接使用Windows API输出彩色日志
            try:
                # 使用全局的控制台句柄
                global hConsole, original_color, SUPPORT_WINDOWS_API, LEVEL_COLORS
                
                # 检查是否支持Windows API
                if SUPPORT_WINDOWS_API and hConsole:
                    # 获取对应级别的颜色
                    color = LEVEL_COLORS.get(record.levelname, original_color)
                    
                    # 设置控制台颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, color)
                    
                    # 调用父类的emit方法
                    super().emit(record)
                    
                    # 恢复原始颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
                else:
                    # 如果不支持Windows API，直接调用父类的emit方法
                    super().emit(record)
            except Exception:
                # 如果出错，调用父类的emit方法
                super().emit(record)
    
    # 使用basicConfig函数配置根日志器
    logging.basicConfig(
        level=logging.INFO,
        format=DEFAULT_LOG_FORMAT,
        handlers=[
            WindowsColorStreamHandler()
        ]
    )
    
    # 启动文件日志监听器
    start_all_listeners()
    
    _initialized = True
    
    # 记录初始化信息
    logger = get_logger(__name__)
    logger.info("✅ 日志系统初始化完成")


def shutdown_logging() -> None:
    """
    关闭日志系统
    """
    global _initialized
    
    if not _initialized:
        return
    
    # 关闭所有文件日志
    close_logging()
    
    # 清理日志器实例
    _loggers.clear()
    _file_loggers.clear()
    
    _initialized = False
    
    get_module_logger().info("✅ 日志系统已关闭")


# 便捷函数
def debug(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 DEBUG 级别的日志
    """
    if TERMINAL_SUPPORTS_ANSI:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 使用ANSI颜色代码
            print(f"{ANSI_COLORS['DEBUG']}{timestamp} - DEBUG - {formatted_msg}{ANSI_COLORS['RESET']}")
        except Exception:
            # 如果出错，使用标准输出
            get_logger().debug(msg, *args, **kwargs)
    elif SUPPORT_WINDOWS_API:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 设置控制台颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['DEBUG'])
            
            # 输出日志消息
            print(f"{timestamp} - DEBUG - {formatted_msg}")
            
            # 恢复原始颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
        except Exception:
            # 如果出错，使用标准输出
            get_logger().debug(msg, *args, **kwargs)
    else:
        # 如果不支持任何颜色输出，使用标准输出
        get_logger().debug(msg, *args, **kwargs)


def info(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 INFO 级别的日志
    """
    if TERMINAL_SUPPORTS_ANSI:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 使用ANSI颜色代码
            print(f"{ANSI_COLORS['INFO']}{timestamp} - INFO - {formatted_msg}{ANSI_COLORS['RESET']}")
        except Exception:
            # 如果出错，使用标准输出
            get_logger().info(msg, *args, **kwargs)
    elif SUPPORT_WINDOWS_API:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 设置控制台颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['INFO'])
            
            # 输出日志消息
            print(f"{timestamp} - INFO - {formatted_msg}")
            
            # 恢复原始颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
        except Exception:
            # 如果出错，使用标准输出
            get_logger().info(msg, *args, **kwargs)
    else:
        # 如果不支持任何颜色输出，使用标准输出
        get_logger().info(msg, *args, **kwargs)


def warning(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 WARNING 级别的日志
    """
    if TERMINAL_SUPPORTS_ANSI:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 使用ANSI颜色代码
            print(f"{ANSI_COLORS['WARNING']}{timestamp} - WARNING - {formatted_msg}{ANSI_COLORS['RESET']}")
        except Exception:
            # 如果出错，使用标准输出
            get_logger().warning(msg, *args, **kwargs)
    elif SUPPORT_WINDOWS_API:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 设置控制台颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['WARNING'])
            
            # 输出日志消息
            print(f"{timestamp} - WARNING - {formatted_msg}")
            
            # 恢复原始颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
        except Exception:
            # 如果出错，使用标准输出
            get_logger().warning(msg, *args, **kwargs)
    else:
        # 如果不支持任何颜色输出，使用标准输出
        get_logger().warning(msg, *args, **kwargs)


def error(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 ERROR 级别的日志
    """
    if TERMINAL_SUPPORTS_ANSI:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 使用ANSI颜色代码
            print(f"{ANSI_COLORS['ERROR']}{timestamp} - ERROR - {formatted_msg}{ANSI_COLORS['RESET']}")
        except Exception:
            # 如果出错，使用标准输出
            get_logger().error(msg, *args, **kwargs)
    elif SUPPORT_WINDOWS_API:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 设置控制台颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['ERROR'])
            
            # 输出日志消息
            print(f"{timestamp} - ERROR - {formatted_msg}")
            
            # 恢复原始颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
        except Exception:
            # 如果出错，使用标准输出
            get_logger().error(msg, *args, **kwargs)
    else:
        # 如果不支持任何颜色输出，使用标准输出
        get_logger().error(msg, *args, **kwargs)


def critical(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 CRITICAL 级别的日志
    """
    if TERMINAL_SUPPORTS_ANSI:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 使用ANSI颜色代码
            print(f"{ANSI_COLORS['CRITICAL']}{timestamp} - CRITICAL - {formatted_msg}{ANSI_COLORS['RESET']}")
        except Exception:
            # 如果出错，使用标准输出
            get_logger().critical(msg, *args, **kwargs)
    elif SUPPORT_WINDOWS_API:
        try:
            # 获取当前时间
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            
            # 格式化日志消息
            formatted_msg = msg % args
            
            # 设置控制台颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['CRITICAL'])
            
            # 输出日志消息
            print(f"{timestamp} - CRITICAL - {formatted_msg}")
            
            # 恢复原始颜色
            ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
        except Exception:
            # 如果出错，使用标准输出
            get_logger().critical(msg, *args, **kwargs)
    else:
        # 如果不支持任何颜色输出，使用标准输出
        get_logger().critical(msg, *args, **kwargs)


def exception(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录异常信息
    """
    get_logger().exception(msg, *args, **kwargs)


# 导出的便捷日志器
logger = get_logger(__name__)



if __name__ == "__main__":
    """
    日志模块使用范例
    """
    print("=== 日志模块使用范例 ===")
    
    # 1. 初始化日志系统
    print("\n1. 初始化日志系统:")
    initialize_logging()
    
    # 2. 基本使用 - 获取日志器
    print("\n2. 基本使用 - 获取日志器:")
    # 自动识别模块名
    logger1 = get_logger()
    print(f"   ✅ 获取默认日志器: {logger1.name}")
    
    # 手动指定模块名
    logger2 = get_logger("my_module")
    print(f"   ✅ 获取指定模块日志器: {logger2.name}")
    
    # 3. 测试不同级别的日志
    print("\n3. 测试不同级别的日志:")
    logger = get_logger("test_logger")
    logger.debug("这是一条 DEBUG 级别的日志")
    logger.info("这是一条 INFO 级别的日志")
    logger.warning("这是一条 WARNING 级别的日志")
    logger.error("这是一条 ERROR 级别的日志")
    logger.critical("这是一条 CRITICAL 级别的日志")
    
    # 4. 测试异常日志
    print("\n4. 测试异常日志:")
    try:
        1 / 0
    except Exception as e:
        logger.exception("发生了一个异常")
    
    # 5. 测试文件日志
    print("\n5. 测试文件日志:")
    # 获取默认文件日志器
    file_logger = get_file_logger("file_test", "default")
    file_logger.info("这是一条写入文件的 INFO 日志")
    file_logger.error("这是一条写入文件的 ERROR 日志")
    
    # 获取错误文件日志器
    error_logger = get_file_logger("file_test", "error")
    error_logger.error("这是一条写入错误文件的日志")
    
    # 6. 使用便捷函数
    print("\n6. 使用便捷函数:")
    debug("使用便捷函数记录 DEBUG 日志")
    info("使用便捷函数记录 INFO 日志")
    warning("使用便捷函数记录 WARNING 日志")
    error("使用便捷函数记录 ERROR 日志")
    critical("使用便捷函数记录 CRITICAL 日志")
    
    # 7. 测试应用生命周期管理
    print("\n7. 测试应用生命周期管理:")
    print("   模拟应用运行中...")
    
    # 8. 关闭日志系统
    print("\n8. 关闭日志系统:")
    shutdown_logging()
    
    print("\n=== 使用范例结束 ===")
    print("\n完整使用流程:")
    print("1. 导入: from globalobjects import logger as log_config")
    print("2. 初始化: log_config.initialize_logging() (应用启动时)")
    print("3. 获取日志器: logger = log_config.get_logger(__name__)")
    print("4. 记录日志: logger.info('日志内容')")
    print("5. 关闭日志: log_config.shutdown_logging() (应用关闭时)")
    print("\n文件日志使用:")
    print("file_logger = log_config.get_file_logger(__name__, 'default')")
    print("file_logger.info('文件日志内容')")