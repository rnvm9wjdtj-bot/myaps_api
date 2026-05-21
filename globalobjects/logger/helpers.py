"""
统一日志系统 - 辅助工具

包含EmojiManager、LogHelper和SensitiveDataMasker等工具类
"""

import os
import sys
import re
import platform
from typing import Optional, Dict, Any, List


class EmojiManager:
    """
    Emoji管理类，根据终端支持情况提供相应的图标
    
    自动检测终端是否支持emoji显示，不支持时使用文本替代
    """
    
    def __init__(self):
        self._supported = self._detect_emoji_support()
        self._emojis = self._build_emoji_map()
    
    def _build_emoji_map(self) -> Dict[str, str]:
        """构建emoji映射表"""
        emoji_pairs = {
            'SUCCESS': ('✅', '[OK]'),
            'FAIL': ('❌', '[FAIL]'),
            'ERROR': ('🚫', '[ERROR]'),
            'WARNING': ('⚠️', '[WARN]'),
            'CRITICAL': ('💥', '[CRIT]'),
            'START': ('⏰', '[START]'),
            'STOP': ('🛑', '[STOP]'),
            'INSERT': ('📥', '[INSERT]'),
            'UPDATE': ('🔄', '[UPDATE]'),
            'DELETE': ('🗑️', '[DELETE]'),
            'QUERY': ('🔍', '[QUERY]'),
            'CONNECT': ('🔗', '[CONNECT]'),
            'DISCONNECT': ('🔌', '[DISCONNECT]'),
            'CACHE': ('💾', '[CACHE]'),
            'TIMER': ('⏱️', '[TIMER]'),
            'SYNC': ('🔄', '[SYNC]'),
            'DEBUG': ('🔍', '[DEBUG]'),
            'INFO': ('ℹ️', '[INFO]')
        }
        
        return {
            name: emoji if self._supported else text
            for name, (emoji, text) in emoji_pairs.items()
        }
    
    def _detect_emoji_support(self) -> bool:
        """
        检测当前终端是否支持emoji显示
        
        Returns:
            bool: 支持返回True，否则返回False
        """
        if platform.system() != 'Windows':
            return True
        
        try:
            windows_version = platform.version()
            parts = windows_version.split('.')
            if len(parts) >= 3:
                major = int(parts[0])
                build = int(parts[2])
                
                if major >= 10 and build >= 17763:
                    if 'WT_SESSION' in os.environ:
                        return True
                    if 'VSCODE_INTEGRATED_TERMINAL' in os.environ:
                        return True
                    
                    terminal = os.environ.get('TERM', '')
                    if any(t in terminal for t in ['conemu', 'cmder', 'mintty']):
                        return True
                    
                    return True
        except Exception:
            pass
        
        return False
    
    @property
    def supported(self) -> bool:
        """是否支持emoji"""
        return self._supported
    
    def get(self, name: str) -> str:
        """获取指定名称的emoji或替代文本"""
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


emoji_manager = EmojiManager()


class LogHelper:
    """
    统一日志格式化工具类
    
    提供标准化的日志消息格式，确保项目中所有日志输出风格一致
    
    使用示例:
        >>> LogHelper.success("推送采购申请", "单号PR001", "共5条")
        '✅ 推送采购申请成功：单号PR001，共5条'
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
        """格式化成功消息"""
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
        """格式化失败消息"""
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
        """格式化错误消息"""
        if reason:
            return f"{LogHelper.Emoji.ERROR} {action}失败：{subject} - {reason}"
        return f"{LogHelper.Emoji.ERROR} {action}失败：{subject}"
    
    @staticmethod
    def start(action: str, subject: str = "") -> str:
        """格式化开始消息"""
        if subject:
            return LogHelper.Template.START.format(
                emoji=LogHelper.Emoji.START,
                action=action,
                subject=subject
            )
        return f"{LogHelper.Emoji.START} 开始{action}"
    
    @staticmethod
    def stop(action: str, subject: str = "") -> str:
        """格式化结束消息"""
        if subject:
            return LogHelper.Template.STOP.format(
                emoji=LogHelper.Emoji.STOP,
                action=action,
                subject=subject
            )
        return f"{LogHelper.Emoji.STOP} 结束{action}"
    
    @staticmethod
    def status_change(subject: str, old_status: str, new_status: str) -> str:
        """格式化状态变更消息"""
        return LogHelper.Template.STATUS_CHANGE.format(
            emoji=LogHelper.Emoji.UPDATE,
            subject=subject,
            old_status=old_status,
            new_status=new_status
        )
    
    @staticmethod
    def api_response(api_name: str, status_code: int, details: str = "") -> str:
        """格式化API响应消息"""
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
        """格式化查询消息"""
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
        """格式化插入消息"""
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
        """格式化更新消息"""
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
        """格式化删除消息"""
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
        """格式化警告消息"""
        return LogHelper.Template.WARNING.format(
            emoji=LogHelper.Emoji.WARNING,
            subject=subject,
            message=message
        )
    
    @staticmethod
    def sync(action: str, subject: str = "", details: str = "") -> str:
        """格式化同步消息"""
        if details:
            return f"{LogHelper.Emoji.SYNC} {action}：{subject}，{details}"
        if subject:
            return f"{LogHelper.Emoji.SYNC} {action}：{subject}"
        return f"{LogHelper.Emoji.SYNC} {action}"
    
    @staticmethod
    def connect(target: str, status: str = "成功") -> str:
        """格式化连接消息"""
        emoji = LogHelper.Emoji.CONNECT if status == "成功" else LogHelper.Emoji.ERROR
        return f"{emoji} 连接{target}{status}"
    
    @staticmethod
    def disconnect(target: str) -> str:
        """格式化断开连接消息"""
        return f"{LogHelper.Emoji.DISCONNECT} 断开{target}连接"
    
    @staticmethod
    def cache(action: str, target: str = "", details: str = "") -> str:
        """格式化缓存消息"""
        if details:
            return f"{LogHelper.Emoji.CACHE} {action}缓存：{target}，{details}"
        if target:
            return f"{LogHelper.Emoji.CACHE} {action}缓存：{target}"
        return f"{LogHelper.Emoji.CACHE} {action}缓存"


class SensitiveDataMasker:
    """
    敏感信息脱敏器
    
    自动检测并屏蔽日志中的敏感信息（如密码、token等）
    """
    
    DEFAULT_SENSITIVE_FIELDS = [
        'password', 'passwd', 'pwd',
        'token', 'access_token', 'refresh_token', 'auth_token',
        'secret', 'secret_key', 'api_key', 'key',
        'credential', 'auth', 'authorization'
    ]
    
    def __init__(self, sensitive_fields: Optional[List[str]] = None):
        """
        初始化脱敏器
        
        Args:
            sensitive_fields: 自定义敏感字段列表
        """
        self._fields = sensitive_fields or self.DEFAULT_SENSITIVE_FIELDS
        self._patterns = self._build_patterns()
    
    def _build_patterns(self) -> List[re.Pattern]:
        """构建正则表达式模式"""
        fields_pattern = '|'.join(self._fields)
        
        return [
            re.compile(
                rf'({fields_pattern})\s*[:=]\s*\S+',
                re.IGNORECASE
            ),
            re.compile(
                rf'"({fields_pattern})"\s*:\s*"[^"]*"',
                re.IGNORECASE
            ),
            re.compile(
                rf"'({fields_pattern})'\s*:\s*'[^']*'",
                re.IGNORECASE
            )
        ]
    
    def mask(self, message: str) -> str:
        """
        脱敏日志消息
        
        Args:
            message: 原始消息
            
        Returns:
            str: 脱敏后的消息
        """
        if not message:
            return message
        
        for pattern in self._patterns:
            message = pattern.sub(self._replace_sensitive, message)
        
        return message
    
    def _replace_sensitive(self, match: re.Match) -> str:
        """替换敏感信息"""
        original = match.group(0)
        
        if ':' in original:
            idx = original.index(':')
            return original[:idx + 1] + ' ***'
        elif '=' in original:
            idx = original.index('=')
            return original[:idx + 1] + ' ***'
        
        return original
    
    def add_field(self, field: str) -> None:
        """添加敏感字段"""
        if field.lower() not in [f.lower() for f in self._fields]:
            self._fields.append(field.lower())
            self._patterns = self._build_patterns()
    
    def remove_field(self, field: str) -> None:
        """移除敏感字段"""
        self._fields = [f for f in self._fields if f.lower() != field.lower()]
        self._patterns = self._build_patterns()


sensitive_masker = SensitiveDataMasker()


def is_terminal_supports_ansi() -> bool:
    """
    检测终端是否支持ANSI颜色
    
    Returns:
        bool: 支持返回True，否则返回False
    """
    if platform.system() == 'Windows':
        try:
            import ctypes
            hConsole = ctypes.windll.kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetConsoleMode(hConsole, ctypes.byref(mode)):
                new_mode = mode.value | 0x0004
                if ctypes.windll.kernel32.SetConsoleMode(hConsole, new_mode):
                    return True
        except Exception:
            pass
        return False
    else:
        return sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else True


TERMINAL_SUPPORTS_ANSI = is_terminal_supports_ansi()


ANSI_COLORS = {
    'DEBUG': '\033[36m',
    'INFO': '\033[32m',
    'WARNING': '\033[33m',
    'ERROR': '\033[31m',
    'CRITICAL': '\033[31m',
    'RESET': '\033[0m',
}
