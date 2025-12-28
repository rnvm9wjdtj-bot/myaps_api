import threading, functools

from apps.data_opt.utils.common import get_session


def timed_execution(interval_seconds: int = 300):
    """
    装饰器：为类方法添加定时执行功能
    interval_seconds: 执行间隔时间（秒），默认5分钟
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 如果是第一次调用，创建定时器
            if not hasattr(self, f'_timer_{func.__name__}'):
                timer = threading.Timer(interval_seconds, self._execute_timed_method, args=[func.__name__] + list(args), kwargs=kwargs)
                setattr(self, f'_timer_{func.__name__}', timer)
                timer.start()
            return func(self, *args, **kwargs)
        return wrapper
    
    return decorator


class TimedExecutionMixin:
    """
    混入类：为任何类添加定时执行方法的功能
    """
    def _execute_timed_method(self, method_name: str, *args, **kwargs):
        """执行定时方法"""
        try:
            method = getattr(self, method_name)
            method(*args, **kwargs)
        except Exception as e:
            print(f"定时执行方法 {method_name} 出错: {e}")
    
    def start_timed_execution(self, method_name: str, interval_seconds: int = 300):
        """启动指定方法的定时执行"""
        if hasattr(self, method_name):
            timer_name = f'_timer_{method_name}'
            # 停止现有定时器
            if hasattr(self, timer_name):
                getattr(self, timer_name).cancel()
            
            # 创建新的定时器
            timer = threading.Timer(interval_seconds, self._execute_timed_method, args=[method_name])
            setattr(self, timer_name, timer)
            timer.start()
            print(f"方法 {method_name} 已启动定时执行，间隔 {interval_seconds} 秒")
        else:
            print(f"方法 {method_name} 不存在")
    
    def stop_timed_execution(self, method_name: str):
        """停止指定方法的定时执行"""
        timer_name = f'_timer_{method_name}'
        if hasattr(self, timer_name):
            getattr(self, timer_name).cancel()
            delattr(self, timer_name)
            print(f"方法 {method_name} 的定时执行已停止")
        else:
            print(f"方法 {method_name} 没有活跃的定时器")