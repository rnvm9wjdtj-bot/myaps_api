import os
import logging
import queue
import time
import sys
import platform
import threading
from typing import Optional, Dict, Any
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener


class EmojiManager:
    """
emoji 管理类，根据终端支持情况提供相应的图标"""
    
    def __init__(self):
        self._supported = self.is_emoji_supported()
        self._emojis = {
            'SUCCESS': '✅' if self._supported else '[OK]',
            'FAIL': '❌' if self._supported else '[FAIL]',
            'ERROR': '🚫' if self._supported else '[ERROR]',
            'WARNING': '⚠️' if self._supported else '[WARN]',
            'CRITICAL': '💥' if self._supported else '[CRIT]',
            'START': '⏰' if self._supported else '[START]',
            'STOP': '🛑' if self._supported else '[STOP]',
            'INSERT': '📥' if self._supported else '[INSERT]',
            'UPDATE': '🔄' if self._supported else '[UPDATE]',
            'DELETE': '🗑️' if self._supported else '[DELETE]',
            'QUERY': '🔍' if self._supported else '[QUERY]',
            'CONNECT': '🔗' if self._supported else '[CONNECT]',
            'DISCONNECT': '🔌' if self._supported else '[DISCONNECT]',
            'CACHE': '💾' if self._supported else '[CACHE]',
            'TIMER': '⏱️' if self._supported else '[TIMER]',
            'SYNC': '🔄' if self._supported else '[SYNC]',
            'DEBUG': '🔍' if self._supported else '[DEBUG]',
            'INFO': 'ℹ️' if self._supported else '[INFO]'
        }
    
    @property
    def supported(self) -> bool:
        """是否支持 emoji"""
        return self._supported
    
    def get(self, name: str) -> str:
        """
        获取指定名称的 emoji 或替代文本
        
        Args:
            name: emoji 名称
            
        Returns:
            str: emoji 或替代文本
        """
        return self._emojis.get(name.upper(), '')
    
    @property
    def SUCCESS(self) -> str:
        return self.get('SUCCESS')
    
    @property
    def FAIL(self) -> str:
        return self.get('FAIL')
    
    @property
    def ERROR(self) -> str:
        return self.get('ERROR')
    
    @property
    def WARNING(self) -> str:
        return self.get('WARNING')
    
    @property
    def CRITICAL(self) -> str:
        return self.get('CRITICAL')
    
    @property
    def START(self) -> str:
        return self.get('START')
    
    @property
    def STOP(self) -> str:
        return self.get('STOP')
    
    @property
    def INSERT(self) -> str:
        return self.get('INSERT')
    
    @property
    def UPDATE(self) -> str:
        return self.get('UPDATE')
    
    @property
    def DELETE(self) -> str:
        return self.get('DELETE')
    
    @property
    def QUERY(self) -> str:
        return self.get('QUERY')
    
    @property
    def CONNECT(self) -> str:
        return self.get('CONNECT')
    
    @property
    def DISCONNECT(self) -> str:
        return self.get('DISCONNECT')
    
    @property
    def CACHE(self) -> str:
        return self.get('CACHE')
    
    @property
    def TIMER(self) -> str:
        return self.get('TIMER')
    
    @property
    def SYNC(self) -> str:
        return self.get('SYNC')
    
    @property
    def DEBUG(self) -> str:
        return self.get('DEBUG')
    
    @property
    def INFO(self) -> str:
        return self.get('INFO')

    @staticmethod
    def is_emoji_supported() -> bool:
        """
        检测当前终端是否支持 emoji 显示
        
        Returns:
            bool: 如果终端支持 emoji 返回 True，否则返回 False
        """
        # 检查操作系统
        if platform.system() != 'Windows':
            # 非 Windows 系统通常支持 emoji
            return True
        
        # Windows 系统检查
        windows_version = platform.version()
        try:
            parts = windows_version.split('.')
            if len(parts) >= 3:
                major = int(parts[0])
                build = int(parts[2])
                
                # Windows 10 1809 (build 17763) 及以上版本支持 emoji
                # Windows 11 虽然内核版本是 10.0，但 build 版本更高
                if major >= 10 and build >= 17763:
                    # 检查是否为 Windows Terminal 或支持 emoji 的终端
                    terminal = os.environ.get('TERM', '')
                    console_host = os.environ.get('CONSOLE_HOST', '')
                    
                    # Windows Terminal
                    if 'WT_SESSION' in os.environ:
                        return True
                    
                    # VS Code 终端
                    if 'VSCODE_INTEGRATED_TERMINAL' in os.environ:
                        return True
                    
                    # ConEmu、Cmder 等增强终端
                    if any(term in terminal for term in ['conemu', 'cmder', 'mintty']):
                        return True
                    
                    # 检查 PowerShell 版本
                    try:
                        import subprocess
                        result = subprocess.run(
                            ['powershell', '-Command', '$PSVersionTable.PSVersion.Major'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            ps_version = int(result.stdout.strip())
                            # PowerShell 7+ 更好地支持 emoji
                            if ps_version >= 7:
                                return True
                    except:
                        pass
                    
                    # 对于 Windows 10 1809+ 或 Windows 11，默认支持 emoji
                    # 即使不是增强终端，现代 Windows 也支持基本 emoji
                    return True
        except:
            pass
        
        # 其他情况默认不支持
        return False

# 创建全局实例
emoji_manager = EmojiManager()


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


class LogHelper:
    """
    统一日志格式化工具类
    
    提供标准化的日志消息格式，确保项目中所有日志输出风格一致。
    
    使用示例:
        >>> console_log.info(LogHelper.success("推送采购申请", "单号PR001", "共5条"))
        >>> console_log.error(LogHelper.error("查询PL", "PL001", "网络超时"))
        >>> console_log.info(LogHelper.start("同步任务", "账套A01"))
    """
    

    class Emoji:
        SUCCESS = emoji_manager.SUCCESS
        FAIL = emoji_manager.FAIL
        ERROR = emoji_manager.ERROR
        WARNING = emoji_manager.WARNING
        CRITICAL = emoji_manager.CRITICAL
        START = emoji_manager.START
        STOP = emoji_manager.STOP
        
        INSERT = emoji_manager.INSERT
        UPDATE = emoji_manager.UPDATE
        DELETE = emoji_manager.DELETE
        QUERY = emoji_manager.QUERY
        
        CONNECT = emoji_manager.CONNECT
        DISCONNECT = emoji_manager.DISCONNECT
        CACHE = emoji_manager.CACHE
        TIMER = emoji_manager.TIMER
        SYNC = emoji_manager.SYNC
        
        DEBUG = emoji_manager.DEBUG
        INFO = emoji_manager.INFO
    
    class Template:
        SUCCESS = "{emoji} {action}成功：{subject}"
        SUCCESS_WITH_DETAILS = "{emoji} {action}成功：{subject}，{details}"
        
        FAIL = "{emoji} {action}失败：{subject}"
        FAIL_WITH_REASON = "{emoji} {action}失败：{subject} - {reason}"
        
        START = "{emoji} 开始{action}：{subject}"
        STOP = "{emoji} 结束{action}：{subject}"
        
        STATUS_CHANGE = "{emoji} {subject}状态变更：{old_status} -> {new_status}"
        
        API_RESPONSE = "{emoji} {api_name}响应：{status_code}"
        API_RESPONSE_WITH_DATA = "{emoji} {api_name}响应：{status_code}，{details}"
        
        QUERY_RESULT = "{emoji} 查询{target}：{result}"
        QUERY_RESULT_WITH_COUNT = "{emoji} 查询{target}成功：共{count}条数据"
        
        DATA_INSERT = "{emoji} 插入{target}：{subject}"
        DATA_INSERT_WITH_COUNT = "{emoji} 插入{target}成功：共{count}条数据"
        
        DATA_UPDATE = "{emoji} 更新{target}：{subject}"
        DATA_UPDATE_WITH_COUNT = "{emoji} 更新{target}成功：共{count}条数据"
        
        DATA_DELETE = "{emoji} 删除{target}：{subject}"
        DATA_DELETE_WITH_COUNT = "{emoji} 删除{target}成功：共{count}条数据"
        
        WARNING = "{emoji} {subject}：{message}"
        ERROR = "{emoji} {subject}：{message}"
    
    @staticmethod
    def success(action: str, subject: str, details: str = "") -> str:
        """
        格式化成功消息
        
        Args:
            action: 操作名称，如"推送采购申请"、"同步库存"
            subject: 操作主体，如"单号PR001"、"账套A01"
            details: 额外详情，如"共5条"、"耗时10秒"
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.success("推送采购申请", "单号PR001", "共5条")
            '✅ 推送采购申请成功：单号PR001，共5条'
        """
        if details:
            return LogHelper.Template.SUCCESS_WITH_DETAILS.format(
                emoji=LogHelper.Emoji.SUCCESS,
                action=action,
                subject=subject,
                details=details
            )
        return LogHelper.Template.SUCCESS.format(
            emoji=LogHelper.Emoji.SUCCESS,
            action=action,
            subject=subject
        )
    
    @staticmethod
    def fail(action: str, subject: str, reason: str = "") -> str:
        """
        格式化失败消息
        
        Args:
            action: 操作名称
            subject: 操作主体
            reason: 失败原因
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.fail("推送采购申请", "单号PR001", "网络超时")
            '❌ 推送采购申请失败：单号PR001 - 网络超时'
        """
        if reason:
            return LogHelper.Template.FAIL_WITH_REASON.format(
                emoji=LogHelper.Emoji.FAIL,
                action=action,
                subject=subject,
                reason=reason
            )
        return LogHelper.Template.FAIL.format(
            emoji=LogHelper.Emoji.FAIL,
            action=action,
            subject=subject
        )
    
    @staticmethod
    def error(action: str, subject: str, reason: str = "") -> str:
        """
        格式化错误消息（与fail类似，使用不同的emoji）
        
        Args:
            action: 操作名称
            subject: 操作主体
            reason: 错误原因
        
        Returns:
            格式化后的日志消息
        """
        if reason:
            return f"{LogHelper.Emoji.ERROR} {action}失败：{subject} - {reason}"
        return f"{LogHelper.Emoji.ERROR} {action}失败：{subject}"
    
    @staticmethod
    def start(action: str, subject: str = "") -> str:
        """
        格式化开始消息
        
        Args:
            action: 操作名称
            subject: 操作主体（可选）
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.start("同步任务", "账套A01")
            '⏰ 开始同步任务：账套A01'
        """
        if subject:
            return LogHelper.Template.START.format(
                emoji=LogHelper.Emoji.START,
                action=action,
                subject=subject
            )
        return f"{LogHelper.Emoji.START} 开始{action}"
    
    @staticmethod
    def stop(action: str, subject: str = "") -> str:
        """
        格式化结束消息
        
        Args:
            action: 操作名称
            subject: 操作主体（可选）
        
        Returns:
            格式化后的日志消息
        """
        if subject:
            return LogHelper.Template.STOP.format(
                emoji=LogHelper.Emoji.STOP,
                action=action,
                subject=subject
            )
        return f"{LogHelper.Emoji.STOP} 结束{action}"
    
    @staticmethod
    def status_change(subject: str, old_status: str, new_status: str) -> str:
        """
        格式化状态变更消息
        
        Args:
            subject: 操作主体
            old_status: 旧状态
            new_status: 新状态
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.status_change("PL001", "待处理", "已确认")
            '🔄 PL001状态变更：待处理 -> 已确认'
        """
        return LogHelper.Template.STATUS_CHANGE.format(
            emoji=LogHelper.Emoji.UPDATE,
            subject=subject,
            old_status=old_status,
            new_status=new_status
        )
    
    @staticmethod
    def api_response(api_name: str, status_code: int, details: str = "") -> str:
        """
        格式化API响应消息
        
        Args:
            api_name: API名称
            status_code: HTTP状态码
            details: 额外详情（可选）
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.api_response("更新PL状态", 200)
            '✅ 更新PL状态响应：200'
        """
        emoji = LogHelper.Emoji.SUCCESS if 200 <= status_code < 300 else LogHelper.Emoji.FAIL
        if details:
            return LogHelper.Template.API_RESPONSE_WITH_DATA.format(
                emoji=emoji,
                api_name=api_name,
                status_code=status_code,
                details=details
            )
        return LogHelper.Template.API_RESPONSE.format(
            emoji=emoji,
            api_name=api_name,
            status_code=status_code
        )
    
    @staticmethod
    def query(target: str, result: str = "", count: int = None) -> str:
        """
        格式化查询消息
        
        Args:
            target: 查询目标
            result: 查询结果描述
            count: 结果数量（可选）
        
        Returns:
            格式化后的日志消息
        
        Example:
            >>> LogHelper.query("PL信息", count=10)
            '✅ 查询PL信息成功：共10条'
        """
        if count is not None:
            return LogHelper.Template.QUERY_RESULT_WITH_COUNT.format(
                emoji=LogHelper.Emoji.SUCCESS,
                target=target,
                count=count
            )
        if result:
            return LogHelper.Template.QUERY_RESULT.format(
                emoji=LogHelper.Emoji.QUERY,
                target=target,
                result=result
            )
        return f"{LogHelper.Emoji.QUERY} 开始查询{target}"
    
    @staticmethod
    def insert(target: str, subject: str = "", count: int = None) -> str:
        """
        格式化插入消息
        
        Args:
            target: 插入目标表/集合
            subject: 插入主体（可选）
            count: 插入数量（可选）
        
        Returns:
            格式化后的日志消息
        """
        if count is not None:
            return LogHelper.Template.DATA_INSERT_WITH_COUNT.format(
                emoji=LogHelper.Emoji.INSERT,
                target=target,
                count=count
            )
        if subject:
            return LogHelper.Template.DATA_INSERT.format(
                emoji=LogHelper.Emoji.INSERT,
                target=target,
                subject=subject
            )
        return f"{LogHelper.Emoji.INSERT} 插入{target}"
    
    @staticmethod
    def update(target: str, subject: str = "", count: int = None) -> str:
        """
        格式化更新消息
        
        Args:
            target: 更新目标表/集合
            subject: 更新主体（可选）
            count: 更新数量（可选）
        
        Returns:
            格式化后的日志消息
        """
        if count is not None:
            return LogHelper.Template.DATA_UPDATE_WITH_COUNT.format(
                emoji=LogHelper.Emoji.UPDATE,
                target=target,
                count=count
            )
        if subject:
            return LogHelper.Template.DATA_UPDATE.format(
                emoji=LogHelper.Emoji.UPDATE,
                target=target,
                subject=subject
            )
        return f"{LogHelper.Emoji.UPDATE} 更新{target}"
    
    @staticmethod
    def delete(target: str, subject: str = "", count: int = None) -> str:
        """
        格式化删除消息
        
        Args:
            target: 删除目标表/集合
            subject: 删除主体（可选）
            count: 删除数量（可选）
        
        Returns:
            格式化后的日志消息
        """
        if count is not None:
            return LogHelper.Template.DATA_DELETE_WITH_COUNT.format(
                emoji=LogHelper.Emoji.DELETE,
                target=target,
                count=count
            )
        if subject:
            return LogHelper.Template.DATA_DELETE.format(
                emoji=LogHelper.Emoji.DELETE,
                target=target,
                subject=subject
            )
        return f"{LogHelper.Emoji.DELETE} 删除{target}"
    
    @staticmethod
    def warning(subject: str, message: str) -> str:
        """
        格式化警告消息
        
        Args:
            subject: 警告主体
            message: 警告信息
        
        Returns:
            格式化后的日志消息
        """
        return LogHelper.Template.WARNING.format(
            emoji=LogHelper.Emoji.WARNING,
            subject=subject,
            message=message
        )
    
    @staticmethod
    def sync(action: str, subject: str = "", details: str = "") -> str:
        """
        格式化同步消息
        
        Args:
            action: 同步操作名称
            subject: 同步主体
            details: 额外详情
        
        Returns:
            格式化后的日志消息
        """
        if details:
            return f"{LogHelper.Emoji.SYNC} {action}：{subject}，{details}"
        if subject:
            return f"{LogHelper.Emoji.SYNC} {action}：{subject}"
        return f"{LogHelper.Emoji.SYNC} {action}"
    
    @staticmethod
    def connect(target: str, status: str = "成功") -> str:
        """
        格式化连接消息
        
        Args:
            target: 连接目标
            status: 连接状态
        
        Returns:
            格式化后的日志消息
        """
        emoji = LogHelper.Emoji.CONNECT if status == "成功" else LogHelper.Emoji.ERROR
        return f"{emoji} 连接{target}{status}"
    
    @staticmethod
    def disconnect(target: str) -> str:
        """
        格式化断开连接消息
        
        Args:
            target: 断开目标
        
        Returns:
            格式化后的日志消息
        """
        return f"{LogHelper.Emoji.DISCONNECT} 断开{target}连接"
    
    @staticmethod
    def cache(action: str, target: str = "", details: str = "") -> str:
        """
        格式化缓存消息
        
        Args:
            action: 缓存操作（如"刷新"、"清理"）
            target: 缓存目标
            details: 额外详情
        
        Returns:
            格式化后的日志消息
        """
        if details:
            return f"{LogHelper.Emoji.CACHE} {action}缓存：{target}，{details}"
        if target:
            return f"{LogHelper.Emoji.CACHE} {action}缓存：{target}"
        return f"{LogHelper.Emoji.CACHE} {action}缓存"


# 存储多个logger实例和对应的listener
logger_instances = {}
listeners = {}
db_initialized = False  # 全局数据库初始化状态


class DatePrefixRotatingFileHandler(TimedRotatingFileHandler):
    """
    自定义的按时间轮转的文件处理器
    
    特点：
    - app.log 保存最近N天的日志（默认10天）
    - 轮替时，从 app.log 中提取历史日期的日志到单独文件
    - 自动清理超过备份数量的旧日志文件
    """
    
    DEFAULT_RETENTION_DAYS = 10
    
    def __init__(self, *args, **kwargs):
        self.retention_days = kwargs.pop('retention_days', self.DEFAULT_RETENTION_DAYS)
        super().__init__(*args, **kwargs)
        self.encoding = kwargs.get('encoding', 'utf-8')
        self.rolloverAt = self.computeRollover(int(time.time()))
        self._rollover_lock = threading.Lock()
        self._last_rollover_date = self._get_today_str()
    
    def _get_today_str(self) -> str:
        """获取今天的日期字符串"""
        return time.strftime("%Y-%m-%d", time.localtime())
    
    def _get_retention_dates(self) -> set:
        """获取需要保留的日期集合（最近N天）"""
        retention_dates = set()
        current_time = time.time()
        for i in range(self.retention_days):
            date_str = time.strftime("%Y-%m-%d", time.localtime(current_time - i * 86400))
            retention_dates.add(date_str)
        return retention_dates
    
    def emit(self, record):
        current_time = int(time.time())
        if current_time >= self.rolloverAt:
            if self._rollover_lock.acquire(blocking=False):
                try:
                    if current_time >= self.rolloverAt:
                        self.doRollover()
                finally:
                    self._rollover_lock.release()
        # 直接写入，不调用父类的emit以避免父类的doRollover被调用
        if self.stream is None:
            self.stream = self._open()
        logging.handlers.BaseRotatingHandler.emit(self, record)
    
    def doRollover(self):
        """
        轮替方法：
        1. 从 app.log 中提取历史日期的日志到单独文件
        2. 清理 app.log，仅保留最近N天的日志
        3. 清理超过备份数量的旧文件
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        
        current_time = int(time.time())
        self.rolloverAt = self.computeRollover(current_time)
        
        if self.backupCount > 0:
            base_dir, filename = os.path.split(self.baseFilename)
            name_without_ext, ext = os.path.splitext(filename)
            
            self._extract_and_clean_logs(base_dir, name_without_ext, ext)
            
            self._delete_old_logs(base_dir, name_without_ext, ext)
        
        self.mode = 'a'
        self.stream = self._open()
        self._last_rollover_date = self._get_today_str()
    
    def _extract_and_clean_logs(self, base_dir: str, name_without_ext: str, ext: str):
        """
        从 app.log 中提取历史日期的日志到单独文件，并清理 app.log
        
        Args:
            base_dir: 日志目录
            name_without_ext: 日志文件名（不含扩展名）
            ext: 日志文件扩展名
        """
        if not os.path.exists(self.baseFilename):
            return
        
        retention_dates = self._get_retention_dates()
        
        logs_by_date = {}
        retained_logs = []
        
        try:
            with open(self.baseFilename, 'r', encoding=self.encoding, errors='replace') as f:
                for line in f:
                    date_str = self._extract_date_from_line(line)
                    if date_str:
                        if date_str in retention_dates:
                            retained_logs.append(line)
                        else:
                            if date_str not in logs_by_date:
                                logs_by_date[date_str] = []
                            logs_by_date[date_str].append(line)
                    else:
                        retained_logs.append(line)
        except Exception:
            return
        
        for date_str, lines in logs_by_date.items():
            if not lines:
                continue
            
            date_prefix = date_str.replace('-', '')
            new_filename = f"{date_prefix}_{name_without_ext}{ext}"
            new_filepath = os.path.join(base_dir, new_filename)
            
            try:
                mode = 'a' if os.path.exists(new_filepath) else 'w'
                with open(new_filepath, mode, encoding=self.encoding) as f:
                    f.writelines(lines)
            except Exception:
                pass
        
        try:
            with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                f.writelines(retained_logs)
        except Exception:
            pass
    
    def _extract_date_from_line(self, line: str) -> str:
        """
        从日志行中提取日期
        
        Args:
            line: 日志行，格式如 "2026-04-05 09:35:01,177 - ..."
        
        Returns:
            日期字符串 "YYYY-MM-DD" 或 None
        """
        if len(line) < 10:
            return None
        
        date_part = line[:10]
        if (len(date_part) == 10 and 
            date_part[4] == '-' and date_part[7] == '-' and
            date_part[:4].isdigit() and date_part[5:7].isdigit() and date_part[8:10].isdigit()):
            return date_part
        return None
    
    def _delete_old_logs(self, base_dir: str, name_without_ext: str, ext: str):
        """
        删除超过备份数量的旧日志文件
        
        Args:
            base_dir: 日志目录
            name_without_ext: 日志文件名（不含扩展名）
            ext: 日志文件扩展名
        """
        import glob
        
        pattern = os.path.join(base_dir, f"????????_{name_without_ext}{ext}")
        log_files = glob.glob(pattern)
        
        if len(log_files) <= self.backupCount:
            return
        
        def extract_date(filepath: str) -> str:
            filename = os.path.basename(filepath)
            return filename[:8] if len(filename) >= 8 and filename[:8].isdigit() else "00000000"
        
        log_files.sort(key=extract_date, reverse=True)
        
        for old_file in log_files[self.backupCount:]:
            try:
                if os.path.exists(old_file):
                    os.remove(old_file)
            except Exception:
                pass





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
    return logger


def start_all_listeners():
    """启动所有存储的listener"""
    for key, listener in listeners.items():
        try:
            listener.start()
        except Exception as e:
            pass


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





class SmartLogger(logging.Logger):
    """
    智能日志器类，扩展便捷方法，支持同时输出到控制台和文件
    
    使用示例:
        >>> console_log.success("推送采购申请", "单号PR001", "共5条")
        >>> console_log.fail("查询PL", "PL001", "网络超时")  # 自动同时写入文件
        >>> console_log.start("同步任务", "账套A01")
    """
    
    _file_logger = None
    _auto_file_enabled = True
    _db_enabled = True
    _db_min_level = logging.DEBUG  # 记录所有级别的日志到数据库，便于调试
    _db_initialized = False  # 数据库是否已初始化
    
    def set_file_logger(self, file_logger) -> None:
        """
        设置关联的文件日志器
        
        Args:
            file_logger: 文件日志器实例
        """
        self._file_logger = file_logger
    
    def enable_auto_file(self) -> None:
        """启用自动文件日志（默认启用）"""
        self._auto_file_enabled = True
    
    def disable_auto_file(self) -> None:
        """禁用自动文件日志"""
        self._auto_file_enabled = False
    
    def enable_db_logging(self) -> None:
        """启用数据库日志（默认启用）"""
        self._db_enabled = True
    
    def disable_db_logging(self) -> None:
        """禁用数据库日志"""
        self._db_enabled = False
    
    def set_db_min_level(self, level: int) -> None:
        """设置数据库日志的最低级别"""
        self._db_min_level = level
    
    def set_db_initialized(self, initialized: bool = True) -> None:
        """标记数据库是否已初始化"""
        self._db_initialized = initialized
    
    def set_db_initialized_all(self, initialized: bool = True) -> None:
        """标记所有日志器数据库是否已初始化"""
        global db_initialized
        db_initialized = initialized
        for logger in logger_instances.values():
            if isinstance(logger, SmartLogger):
                logger.set_db_initialized(initialized)
    
    async def _log_to_database(self, level: int, msg: str, **kwargs) -> None:
        """
        异步写入数据库
        
        Args:
            level: 日志级别
            msg: 日志消息
            **kwargs: 额外的日志参数
        """
        from core.settings import SQLITE_FILE
        
        # 检查数据库是否已初始化
        global db_initialized
        if not db_initialized:
            return
        
        # 检查数据库日志是否启用
        if not self._db_enabled or level < self._db_min_level:
            return
        
        try:
            import inspect
            import os
            import threading
            
            # 尝试导入 SystemLog 模型
            try:
                from apps.common.monitor.models import SystemLog
            except Exception:
                # 导入失败，不记录到文件，避免递归
                return
            
            # 获取调用栈
            try:
                stack = inspect.stack()
            except Exception:
                # 获取调用栈失败，不记录到文件，避免递归
                stack = []
            
            # 跳过内部方法，找到原始调用位置
            caller_frame = None
            try:
                for i, frame_info in enumerate(stack[1:]):
                    frame = frame_info.frame
                    class_name = None
                    if 'self' in frame.f_locals:
                        try:
                            class_name = frame.f_locals['self'].__class__.__name__
                        except Exception:
                            pass
                    
                    if class_name != 'SmartLogger':
                        caller_frame = frame_info
                        break
                
                if not caller_frame and len(stack) > 1:
                    caller_frame = stack[-1]
            except Exception:
                # 解析调用栈失败，不记录到文件，避免递归
                pass
            
            # 获取堆栈跟踪（仅ERROR及以上级别）
            stack_trace = None
            if level >= logging.ERROR:
                try:
                    import traceback
                    stack_trace = ''.join(traceback.format_stack())
                except Exception:
                    # 获取堆栈跟踪失败，不记录到文件，避免递归
                    pass
            
            # 创建日志记录
            module_name = ''
            function_name = ''
            line_no = 0
            if caller_frame:
                try:
                    module_name = caller_frame.frame.f_globals.get('__name__', '')
                    function_name = caller_frame.function
                    line_no = caller_frame.lineno
                except Exception:
                    # 获取调用信息失败，使用默认值
                    pass
            
            # 尝试创建日志记录
            try:
                # 确保模型有正确的默认连接
                SystemLog._meta.default_connection = SQLITE_FILE
                
                await SystemLog.create(
                    level=logging.getLevelName(level),
                    module=module_name,
                    function=function_name,
                    line_number=line_no,
                    message=msg,
                    details=str(kwargs) if kwargs else None,
                    stack_trace=stack_trace,
                    process_id=os.getpid(),
                    thread_id=threading.get_ident(),
                    thread_name=threading.current_thread().name
                )
            except Exception:
                # 数据库写入失败，不记录到文件，避免递归
                pass
        except Exception:
            # 其他错误，不记录到文件，避免递归
            pass
    
    def _log_to_file(self, level: int, msg: str) -> None:
        """
        同时写入文件日志
        
        Args:
            level: 日志级别
            msg: 日志消息
        """
        if self._auto_file_enabled and self._file_logger:
            # 只在error级别及以上使用栈追踪
            if level >= logging.ERROR:
                import inspect
                import threading
                import os
                
                # 获取调用栈
                stack = inspect.stack()
                
                # 跳过内部方法，找到原始调用位置
                caller_frame = None
                # 遍历所有栈帧，找到第一个不是SmartLogger类的方法
                for i, frame_info in enumerate(stack[1:]):  # 从栈的第二个元素开始（跳过当前函数）
                    frame = frame_info.frame
                    # 获取类名
                    class_name = None
                    if 'self' in frame.f_locals:
                        try:
                            class_name = frame.f_locals['self'].__class__.__name__
                        except Exception:
                            pass
                    
                    # 检查是否是SmartLogger类的方法
                    if class_name != 'SmartLogger':
                        caller_frame = frame_info
                        break
                
                # 如果没有找到，使用栈的最后一个元素（最外层调用）
                if not caller_frame and len(stack) > 1:
                    caller_frame = stack[-1]
                
                # 如果找到原始调用位置，使用其信息
                if caller_frame:
                    # 创建一个自定义的日志记录，替换函数名和行号
                    record = logging.makeLogRecord({
                        'levelno': level,
                        'levelname': logging.getLevelName(level),
                        'msg': msg,
                        'args': (),
                        'exc_info': None,
                        'exc_text': None,
                        'stack_info': None,
                        'lineno': caller_frame.lineno,
                        'funcName': caller_frame.function,
                        'filename': caller_frame.filename,
                        'module': os.path.basename(caller_frame.filename).split('.')[0],
                        'name': self.name,
                        'created': time.time(),
                        'msecs': (time.time() % 1) * 1000,
                        'relativeCreated': 0,
                        'thread': threading.get_ident(),
                        'threadName': threading.current_thread().name,
                        'process': os.getpid(),
                        'processName': 'MainProcess'
                    })
                    self._file_logger.handle(record)
                else:
                    # 如果没有找到，使用默认方式
                    self._file_logger.log(level, msg)
            else:
                # 普通级别使用默认方式
                self._file_logger.log(level, msg)
    
    def debug(self, msg, *args, **kwargs):
        """记录 DEBUG 级别的日志"""
        # 检查当前日志器的级别
        if self.isEnabledFor(logging.DEBUG):
            # 异步写入数据库
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 格式化消息，处理格式化失败的情况
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    asyncio.create_task(self._log_to_database(logging.DEBUG, formatted_msg, **kwargs))
            except Exception:
                pass
            
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
                    super().debug(msg, *args, **kwargs)
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
                    super().debug(msg, *args, **kwargs)
            else:
                # 如果不支持任何颜色输出，使用原始方法
                super().debug(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        """记录 INFO 级别的日志"""
        # 检查当前日志器的级别
        if self.isEnabledFor(logging.INFO):
            # 异步写入数据库
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 格式化消息，处理格式化失败的情况
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    asyncio.create_task(self._log_to_database(logging.INFO, formatted_msg, **kwargs))
            except Exception:
                pass
            
            if TERMINAL_SUPPORTS_ANSI:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 使用ANSI颜色代码
                    print(f"{ANSI_COLORS['INFO']}{timestamp} - INFO - {formatted_msg}{ANSI_COLORS['RESET']}")
                except Exception:
                    # 如果出错，使用原始方法
                    super().info(msg, *args, **kwargs)
            elif SUPPORT_WINDOWS_API:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 设置控制台颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['INFO'])
                    
                    # 输出日志消息
                    print(f"{timestamp} - INFO - {formatted_msg}")
                    
                    # 恢复原始颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
                except Exception:
                    # 如果出错，使用原始方法
                    super().info(msg, *args, **kwargs)
            else:
                # 如果不支持任何颜色输出，使用原始方法
                super().info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        """记录 WARNING 级别的日志"""
        # 检查当前日志器的级别
        if self.isEnabledFor(logging.WARNING):
            # 异步写入数据库
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 格式化消息，处理格式化失败的情况
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    asyncio.create_task(self._log_to_database(logging.WARNING, formatted_msg, **kwargs))
            except Exception:
                pass
            
            if TERMINAL_SUPPORTS_ANSI:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 使用ANSI颜色代码
                    print(f"{ANSI_COLORS['WARNING']}{timestamp} - WARNING - {formatted_msg}{ANSI_COLORS['RESET']}")
                except Exception:
                    # 如果出错，使用原始方法
                    super().warning(msg, *args, **kwargs)
            elif SUPPORT_WINDOWS_API:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 设置控制台颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['WARNING'])
                    
                    # 输出日志消息
                    print(f"{timestamp} - WARNING - {formatted_msg}")
                    
                    # 恢复原始颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
                except Exception:
                    # 如果出错，使用原始方法
                    super().warning(msg, *args, **kwargs)
            else:
                # 如果不支持任何颜色输出，使用原始方法
                super().warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        """记录 ERROR 级别的日志"""
        # 检查当前日志器的级别
        if self.isEnabledFor(logging.ERROR):
            # 格式化消息，处理格式化失败的情况
            try:
                if args:
                    formatted_msg = msg % args
                else:
                    formatted_msg = msg
            except (TypeError, ValueError):
                # 如果格式化失败，将参数拼接到消息后面
                formatted_msg = f"{msg} {' '.join(map(str, args))}"
            
            # 写入数据库
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 事件循环已运行，创建异步任务
                    asyncio.create_task(self._log_to_database(logging.ERROR, formatted_msg, **kwargs))
                else:
                    # 事件循环未运行，同步执行
                    # 避免在应用关闭时使用 asyncio.run()，防止事件循环错误
                    try:
                        loop = asyncio.get_event_loop()
                        if not loop.is_closed():
                            asyncio.create_task(self._log_to_database(logging.ERROR, formatted_msg, **kwargs))
                    except:
                        # 事件循环已关闭，跳过日志记录
                        pass
            except Exception:
                pass
            
            if TERMINAL_SUPPORTS_ANSI:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 使用ANSI颜色代码
                    print(f"{ANSI_COLORS['ERROR']}{timestamp} - ERROR - {formatted_msg}{ANSI_COLORS['RESET']}")
                except Exception:
                    # 如果出错，使用原始方法
                    super().error(msg, *args, **kwargs)
            elif SUPPORT_WINDOWS_API:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 设置控制台颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['ERROR'])
                    
                    # 输出日志消息
                    print(f"{timestamp} - ERROR - {formatted_msg}")
                    
                    # 恢复原始颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
                except Exception:
                    # 如果出错，使用原始方法
                    super().error(msg, *args, **kwargs)
            else:
                # 如果不支持任何颜色输出，使用原始方法
                super().error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        """记录 CRITICAL 级别的日志"""
        # 检查当前日志器的级别
        if self.isEnabledFor(logging.CRITICAL):
            # 异步写入数据库
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 格式化消息，处理格式化失败的情况
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    asyncio.create_task(self._log_to_database(logging.CRITICAL, formatted_msg, **kwargs))
            except Exception:
                pass
            
            if TERMINAL_SUPPORTS_ANSI:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 使用ANSI颜色代码
                    print(f"{ANSI_COLORS['CRITICAL']}{timestamp} - CRITICAL - {formatted_msg}{ANSI_COLORS['RESET']}")
                except Exception:
                    # 如果出错，使用原始方法
                    super().critical(msg, *args, **kwargs)
            elif SUPPORT_WINDOWS_API:
                try:
                    # 获取当前时间
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    
                    # 格式化日志消息
                    try:
                        if args:
                            formatted_msg = msg % args
                        else:
                            formatted_msg = msg
                    except (TypeError, ValueError):
                        # 如果格式化失败，将参数拼接到消息后面
                        formatted_msg = f"{msg} {' '.join(map(str, args))}"
                    
                    # 设置控制台颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, LEVEL_COLORS['CRITICAL'])
                    
                    # 输出日志消息
                    print(f"{timestamp} - CRITICAL - {formatted_msg}")
                    
                    # 恢复原始颜色
                    ctypes.windll.kernel32.SetConsoleTextAttribute(hConsole, original_color)
                except Exception:
                    # 如果出错，使用原始方法
                    super().critical(msg, *args, **kwargs)
            else:
                # 如果不支持任何颜色输出，使用原始方法
                super().critical(msg, *args, **kwargs)
    
    def success(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        """
        记录成功消息
        
        Args:
            action: 操作名称
            subject: 操作主体
            details: 额外详情
            to_file: 是否同时写入文件
        """
        msg = LogHelper.success(action, subject, details)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def fail(self, action: str, subject: str = "", reason: str = "", to_file: bool = True) -> None:
        """
        记录失败消息（默认同时写入文件）
        
        Args:
            action: 操作名称
            subject: 操作主体
            reason: 失败原因
            to_file: 是否同时写入文件，默认True
        """
        msg = LogHelper.fail(action, subject, reason)
        self.error(msg)
        if to_file:
            self._log_to_file(logging.ERROR, msg)
    
    def start(self, action: str, subject: str = "", to_file: bool = False) -> None:
        """
        记录开始消息
        
        Args:
            action: 操作名称
            subject: 操作主体
            to_file: 是否同时写入文件
        """
        msg = LogHelper.start(action, subject)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def stop(self, action: str, subject: str = "", to_file: bool = False) -> None:
        """
        记录结束消息
        
        Args:
            action: 操作名称
            subject: 操作主体
            to_file: 是否同时写入文件
        """
        msg = LogHelper.stop(action, subject)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def status_change(self, subject: str, old_status: str, new_status: str, to_file: bool = False) -> None:
        """
        记录状态变更消息
        
        Args:
            subject: 操作主体
            old_status: 旧状态
            new_status: 新状态
            to_file: 是否同时写入文件
        """
        msg = LogHelper.status_change(subject, old_status, new_status)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def api_response(self, api_name: str, status_code: int, details: str = "", to_file: bool = False) -> None:
        """
        记录API响应消息
        
        Args:
            api_name: API名称
            status_code: HTTP状态码
            details: 额外详情
            to_file: 是否同时写入文件
        """
        msg = LogHelper.api_response(api_name, status_code, details)
        if 200 <= status_code < 300:
            self.info(msg)
            if to_file:
                self._log_to_file(logging.INFO, msg)
        else:
            self.error(msg)
            self._log_to_file(logging.ERROR, msg)
    
    def query(self, target: str, result: str = "", count: int = None, to_file: bool = False) -> None:
        """
        记录查询消息
        
        Args:
            target: 查询目标
            result: 查询结果描述
            count: 结果数量
            to_file: 是否同时写入文件
        """
        msg = LogHelper.query(target, result, count)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def insert(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """
        记录插入消息
        
        Args:
            target: 插入目标
            subject: 插入主体
            count: 插入数量
            to_file: 是否同时写入文件
        """
        msg = LogHelper.insert(target, subject, count)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def update(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """
        记录更新消息
        
        Args:
            target: 更新目标
            subject: 更新主体
            count: 更新数量
            to_file: 是否同时写入文件
        """
        msg = LogHelper.update(target, subject, count)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def delete(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """
        记录删除消息
        
        Args:
            target: 删除目标
            subject: 删除主体
            count: 删除数量
            to_file: 是否同时写入文件
        """
        msg = LogHelper.delete(target, subject, count)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def warning_msg(self, subject: str, message: str, to_file: bool = True) -> None:
        """
        记录警告消息（默认同时写入文件）
        
        Args:
            subject: 警告主体
            message: 警告信息
            to_file: 是否同时写入文件，默认True
        """
        msg = LogHelper.warning(subject, message)
        self.warning(msg)
        if to_file:
            self._log_to_file(logging.WARNING, msg)
    
    def sync(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        """
        记录同步消息
        
        Args:
            action: 同步操作名称
            subject: 同步主体
            details: 额外详情
            to_file: 是否同时写入文件
        """
        msg = LogHelper.sync(action, subject, details)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def connect(self, target: str, status: str = "成功", to_file: bool = False) -> None:
        """
        记录连接消息
        
        Args:
            target: 连接目标
            status: 连接状态
            to_file: 是否同时写入文件
        """
        msg = LogHelper.connect(target, status)
        if status == "成功":
            self.info(msg)
            if to_file:
                self._log_to_file(logging.INFO, msg)
        else:
            self.error(msg)
            self._log_to_file(logging.ERROR, msg)
    
    def disconnect(self, target: str, to_file: bool = False) -> None:
        """
        记录断开连接消息
        
        Args:
            target: 断开目标
            to_file: 是否同时写入文件
        """
        msg = LogHelper.disconnect(target)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)
    
    def cache(self, action: str, target: str = "", details: str = "", to_file: bool = False) -> None:
        """
        记录缓存消息
        
        Args:
            action: 缓存操作
            target: 缓存目标
            details: 额外详情
            to_file: 是否同时写入文件
        """
        msg = LogHelper.cache(action, target, details)
        self.info(msg)
        if to_file:
            self._log_to_file(logging.INFO, msg)


# 注册智能日志器类
logging.setLoggerClass(SmartLogger)

def setup_logger(name: str, level: str = 'INFO', auto_file: bool = True) -> logging.Logger:
    """
    设置日志器
    
    Args:
        name: 日志器名称
        level: 日志级别
        auto_file: 是否自动关联文件日志器（支持 to_file 参数），默认True
        
    Returns:
        配置好的日志器实例
    """
    logger_key = f"{name}:console"
    if logger_key in logger_instances:
        return logger_instances[logger_key]
    
    # 创建 SmartLogger 实例
    logger = SmartLogger(name)
    logger.setLevel(get_log_level(level))
    logger.propagate = False  # 防止日志传播
    
    # 自动关联文件日志器
    if auto_file:
        file_logger = get_file_logger(name)
        logger.set_file_logger(file_logger)
    
    # 存储日志器实例
    logger_instances[logger_key] = logger
    
    return logger


class SmartFileHandler(logging.Handler):
    """智能文件处理器，根据日志级别选择对应文件
    
    日志级别与文件写入规则（受 LOG_LEVEL 控制，但 DEBUG/INFO 始终不写磁盘）：
    - DEBUG: 仅控制台输出，不写入任何文件
    - INFO: 仅控制台输出，不写入任何文件
    - WARNING: 写入 app.log
    - ERROR: 写入 app.log 和 error.log
    - CRITICAL: 写入 app.log 和 error.log
    """
    
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        # 只创建 error.log 的文件日志器（WARNING 及以上级别）
        self.default_logger = setup_file_logging(name, "app.log")  # app.log (WARNING及以上)
        self.default_logger.setLevel(logging.WARNING)
        self.error_logger = setup_file_logging(name, "error.log")  # error.log (ERROR及以上)
        self.error_logger.setLevel(logging.ERROR)
        # 不再创建 debug.log，因为 DEBUG 级别不写磁盘
    
    def emit(self, record):
        """根据日志级别选择对应文件
        
        重要：DEBUG 和 INFO 级别的日志永远不会写入磁盘文件，
        无论 LOG_LEVEL 环境变量设置为何值。这是为了防止日志体积过大。
        """
        # DEBUG 级别只输出到控制台，不写入任何文件
        if record.levelno == logging.DEBUG:
            pass  # 不写入任何文件
        # INFO 级别只输出到控制台，不写入任何文件
        elif record.levelno == logging.INFO:
            pass  # 不写入任何文件
        # WARNING 级别写入 app.log
        elif record.levelno == logging.WARNING:
            self.default_logger.handle(record)
        # ERROR/CRITICAL 级别同时写入 error.log 和 app.log
        elif record.levelno >= logging.ERROR:
            self.error_logger.handle(record)
            self.default_logger.handle(record)


def _create_smart_file_logger(name: str) -> logging.Logger:
    """
    创建智能文件日志器，根据日志级别自动选择文件
    
    Args:
        name: 日志器名称
        
    Returns:
        智能文件日志器实例
    """
    # 创建基础日志器
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    
    # 添加智能文件处理器
    smart_handler = SmartFileHandler(name)
    logger.addHandler(smart_handler)
    
    return logger


def get_file_logger(name: str) -> logging.Logger:
    """
    获取智能文件日志器，根据级别自动选择文件
    
    Args:
        name: 日志器名称
        
    Returns:
        配置好的智能文件日志器实例
    """
    # 创建智能文件日志器
    key = f"{name}:smart"
    if key in logger_instances:
        return logger_instances[key]
    
    logger = _create_smart_file_logger(name)
    logger_instances[key] = logger
    return logger


def get_logger(name: Optional[str] = None, level: str = 'INFO') -> logging.Logger:
    """
    获取统一的日志器
    
    Args:
        name: 日志器名称，默认使用调用模块的名称
        level: 日志级别，默认 'INFO'，可设置为 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        
    Returns:
        配置好的日志器实例
        
    Note:
        返回的日志器支持 to_file 参数，可控制是否同时写入文件：
        - console_log.fail(...)  # 默认 to_file=True，自动写入文件
        - console_log.success(...)  # 默认 to_file=False，仅控制台
        - console_log.success(..., to_file=True)  # 强制写入文件
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
    logger = setup_logger(name, level=level)
    
    return logger


def initialize_logging() -> None:
    """
    初始化日志系统
    """
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 移除默认处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 配置第三方库的日志级别，减少噪音
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('uvicorn.access').setLevel(logging.ERROR)
    logging.getLogger('pymysqlreplication').setLevel(logging.WARNING)
    # 启动文件日志监听器
    start_all_listeners()
    
    # 记录初始化信息
    logger = get_logger(__name__)
    logger.info("✅ 日志系统初始化完成")


def shutdown_logging() -> None:
    """
    关闭日志系统
    """
    # 关闭所有文件日志
    close_logging()
    
    # 清理日志器实例
    logger_instances.clear()
    
    # 记录关闭信息
    logger = get_logger(__name__)
    logger.info("✅ 日志系统已关闭")


# 便捷函数
def debug(msg: Any, *args: Any, **kwargs: Any) -> None:
    """
    记录 DEBUG 级别的日志
    """
    # 检查日志级别，只有当日志级别允许时才输出
    logger = get_logger()
    if not logger.isEnabledFor(logging.DEBUG):
        return
    
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
    
    # 5. 测试智能文件日志器
    print("\n5. 测试智能文件日志器:")
    file_logger = get_file_logger("file_test")
    file_logger.info("这是一条写入文件的 INFO 日志")
    file_logger.error("这是一条写入文件的 ERROR 日志")
    
    # 5.1 测试智能文件日志器
    print("\n5.1 测试智能文件日志器:")
    smart_logger = get_file_logger("smart_test")
    print("   ✅ 创建智能文件日志器")
    # 启动文件日志监听器（确保新创建的监听器被启动）
    start_all_listeners()
    print("   ✅ 启动文件日志监听器")
    # 测试不同级别的日志
    smart_logger.debug("这是一条智能 DEBUG 级别的日志")
    smart_logger.info("这是一条智能 INFO 级别的日志")
    smart_logger.warning("这是一条智能 WARNING 级别的日志")
    smart_logger.error("这是一条智能 ERROR 级别的日志")
    smart_logger.critical("这是一条智能 CRITICAL 级别的日志")
    # 等待日志写入
    import time
    time.sleep(0.5)
    print("   ✅ 智能文件日志器测试完成")
    
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
    print("\n智能文件日志器使用:")
    print("smart_logger = log_config.get_file_logger(__name__, smart=True)")
    print("smart_logger.info('智能文件日志内容')")