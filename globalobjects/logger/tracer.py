"""
统一日志系统 - 调用栈追踪器

高性能捕获日志调用位置的上下文信息
"""

import sys
from typing import Optional, Dict, Any, Set
from functools import lru_cache


class StackTraceTracer:
    """
    调用栈追踪器
    
    特性：
    - 可选启用，默认关闭减少开销
    - 使用sys._getframe替代inspect.stack提升性能
    - 显式清理帧对象防止内存泄漏
    - LRU缓存优化
    """
    
    DEFAULT_SKIP_MODULES: Set[str] = {
        'asyncio', 'asyncio.events', 'asyncio.tasks', 'asyncio.runners',
        'logging', 'uvicorn', 'uvicorn.server', 'uvicorn.protocols',
        'starlette', 'starlette.requests', 'starlette.responses',
        'fastapi', 'fastapi.routing',
        'globalobjects.logger', 'globalobjects.logger.queue',
        'globalobjects.logger.router', 'globalobjects.logger.tracer',
        'globalobjects.logger.core'
    }
    
    DEFAULT_SKIP_FUNCTIONS: Set[str] = {
        '_log', '_run', '_consume_loop', '_flush_batch',
        'debug', 'info', 'warning', 'error', 'critical', 'exception',
        'success', 'fail', 'start', 'stop', 'route',
        'run', 'serve', 'handle', 'emit'
    }
    
    def __init__(
        self,
        enabled: bool = False,
        skip_modules: Optional[Set[str]] = None,
        skip_functions: Optional[Set[str]] = None
    ):
        """
        初始化追踪器
        
        Args:
            enabled: 是否启用追踪
            skip_modules: 要跳过的模块名集合
            skip_functions: 要跳过的函数名集合
        """
        self._enabled = enabled
        self._skip_modules = skip_modules or self.DEFAULT_SKIP_MODULES
        self._skip_functions = skip_functions or self.DEFAULT_SKIP_FUNCTIONS
        
        self._stats = {
            'total_calls': 0,
            'cache_hits': 0
        }
    
    def enable(self) -> None:
        """启用追踪"""
        self._enabled = True
    
    def disable(self) -> None:
        """禁用追踪"""
        self._enabled = False
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._enabled
    
    def get_caller_info(self, skip_frames: int = 2) -> Optional[Dict[str, Any]]:
        """
        获取调用者信息
        
        Args:
            skip_frames: 要跳过的栈帧数量
            
        Returns:
            Dict包含module、function、line_number，或None
        """
        if not self._enabled:
            return None
        
        self._stats['total_calls'] += 1
        
        try:
            frame = sys._getframe(skip_frames)
            
            while frame is not None:
                module_name = frame.f_globals.get('__name__', '')
                function_name = frame.f_code.co_name
                
                if self._is_internal(module_name, function_name, frame):
                    frame = frame.f_back
                    continue
                
                info = {
                    'module': module_name,
                    'function': function_name,
                    'line_number': frame.f_lineno,
                    'file': frame.f_code.co_filename
                }
                
                frame = frame.f_back
                return info
            
        except Exception:
            pass
        finally:
            try:
                del frame
            except Exception:
                pass
        
        return None
    
    def _is_internal(self, module_name: str, function_name: str, frame: Any) -> bool:
        """
        判断是否为内部调用
        
        Args:
            module_name: 模块名
            function_name: 函数名
            frame: 栈帧
            
        Returns:
            bool: 是内部调用返回True
        """
        if 'self' in frame.f_locals:
            try:
                class_name = frame.f_locals['self'].__class__.__name__
                if class_name == 'SmartLogger':
                    return True
            except Exception:
                pass
        
        if module_name in self._skip_modules:
            return True
        
        for skip_module in self._skip_modules:
            if module_name.startswith(skip_module + '.'):
                return True
        
        if function_name in self._skip_functions:
            return True
        
        return False
    
    def get_caller_info_fast(self, skip_frames: int = 2) -> Optional[Dict[str, Any]]:
        """
        快速获取调用者信息（无类检查，性能更高）
        
        Args:
            skip_frames: 要跳过的栈帧数量
            
        Returns:
            Dict或None
        """
        if not self._enabled:
            return None
        
        try:
            frame = sys._getframe(skip_frames)
            
            while frame is not None:
                module_name = frame.f_globals.get('__name__', '')
                
                is_internal = False
                for skip_module in self._skip_modules:
                    if module_name == skip_module or module_name.startswith(skip_module + '.'):
                        is_internal = True
                        break
                
                if not is_internal:
                    info = {
                        'module': module_name,
                        'function': frame.f_code.co_name,
                        'line_number': frame.f_lineno
                    }
                    frame = frame.f_back
                    return info
                
                frame = frame.f_back
            
        except Exception:
            pass
        finally:
            try:
                del frame
            except Exception:
                pass
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            'enabled': self._enabled,
            'hit_rate': self._stats['cache_hits'] / max(1, self._stats['total_calls'])
        }


@lru_cache(maxsize=1024)
def _get_cached_code_info(code_obj_id: int, filename: str, name: str, first_lineno: int) -> Dict[str, Any]:
    """
    缓存代码对象信息
    
    Args:
        code_obj_id: 代码对象ID
        filename: 文件名
        name: 函数名
        first_lineno: 首行号
        
    Returns:
        Dict包含代码信息
    """
    return {
        'file': filename,
        'function': name,
        'line': first_lineno
    }


def get_caller_info_cached(skip_frames: int = 2) -> Optional[Dict[str, Any]]:
    """
    使用缓存获取调用者信息（性能最高）
    
    Args:
        skip_frames: 要跳过的栈帧数量
        
    Returns:
        Dict或None
    """
    try:
        frame = sys._getframe(skip_frames)
        
        code = frame.f_code
        info = _get_cached_code_info(
            id(code),
            code.co_filename,
            code.co_name,
            frame.f_lineno
        )
        
        frame = frame.f_back
        return info
        
    except Exception:
        pass
    finally:
        try:
            del frame
        except Exception:
            pass
    
    return None
