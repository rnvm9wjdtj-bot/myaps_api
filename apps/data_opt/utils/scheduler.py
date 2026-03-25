import os, asyncio, inspect, atexit
from fastapi import FastAPI

from typing import Dict, List, Callable, Any, Optional
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

from globalobjects import logger as log_config

# 获取统一日志器
logger = log_config.get_logger(__name__)

class TaskRegistry:
    """任务注册表，用于收集和管理所有定时任务"""
    
    def __init__(self):
        self.tasks: List[Dict[str, Any]] = []
    
    def register(self, func: Callable, trigger: str, **trigger_args):
        """注册定时任务"""
        task_info = {
            'func': func,
            'trigger': trigger,
            'trigger_args': trigger_args,
            'module': inspect.getmodule(func).__name__,
            'func_name': func.__name__
        }
        self.tasks.append(task_info)
        logger.success("定时任务注册", f"{task_info['module']}.{task_info['func_name']}", "")
        return func

# 全局任务注册表
task_registry = TaskRegistry()

class SchedulerManager:
    """调度器管理类"""
    
    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None
        self._initialized = False
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None
        
    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self.main_loop = loop
        logger.success("事件循环", "", "已设置主应用事件循环")
        
    def init_scheduler(self) -> bool:
        """初始化调度器并添加所有注册的任务"""
        try:
            # 配置调度器
            jobstores = {
                'default': MemoryJobStore()
            }
            executors = {
                'default': ThreadPoolExecutor(20),  # 增加线程数支持更多任务
            }
            job_defaults = {
                'coalesce': True,
                'max_instances': 3,
                'misfire_grace_time': 60
            }
            
            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='Asia/Shanghai'
            )
            
            # 添加事件监听
            self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
            
            # 添加所有注册的任务
            self._add_registered_jobs()
            
            self._initialized = True
            logger.success("调度器初始化", "", f"共注册{len(task_registry.tasks)}个定时任务")
            return True
            
        except Exception as e:
            logger.fail("调度器初始化", "", str(e))
            return False
    
    def _add_registered_jobs(self):
        """添加所有注册的任务到调度器"""
        if not self.scheduler:
            return
            
        for i, task_info in enumerate(task_registry.tasks):
            try:
                # 为每个任务创建唯一的ID
                job_id = f"{task_info['module']}_{task_info['func_name']}_{i}"
                
                # 包装函数，添加错误处理
                safe_func = self._create_safe_function(task_info['func'])
                
                self.scheduler.add_job(
                    func=safe_func,
                    trigger=task_info['trigger'],
                    id=job_id,
                    name=f"{task_info['module']}.{task_info['func_name']}",
                    replace_existing=True,
                    **task_info['trigger_args']
                )
                
                logger.success("定时任务添加", job_id, "")
                
            except Exception as e:
                logger.fail("定时任务添加", task_info['func_name'], str(e))
    
    def _create_safe_function(self, func: Callable) -> Callable:
        """创建安全的任务执行函数（包含异常处理）"""
        # 检查函数是否为异步函数
        is_async = inspect.iscoroutinefunction(func)
        if is_async:
            @wraps(func)
            async def async_wrapper():
                try:
                    logger.start(f"异步任务 {func.__module__}.{func.__name__}")
                    result = await func()
                    logger.success("异步任务执行", f"{func.__module__}.{func.__name__}", "")
                    return result
                except Exception as e:
                    logger.fail("异步任务执行", f"{func.__module__}.{func.__name__}", str(e))
                    return None
            # 为异步函数创建同步包装器
            @wraps(func)
            def wrapper():
                try:
                    # 优先使用已设置的主事件循环
                    if self.main_loop:
                        logger.debug("使用主应用事件循环执行异步任务")
                        # 直接传递coroutine对象给run_coroutine_threadsafe
                        return asyncio.run_coroutine_threadsafe(async_wrapper(), self.main_loop).result()
                    else:
                        # 尝试获取当前运行的事件循环
                        try:
                            loop = asyncio.get_running_loop()
                            logger.debug("使用当前运行的事件循环执行异步任务")
                            return loop.run_until_complete(async_wrapper())
                        except RuntimeError:
                            # 如果没有运行中的事件循环，才创建新的
                            logger.debug("使用新的事件循环执行异步任务")
                            return asyncio.run(async_wrapper())
                except Exception as e:
                    logger.fail("异步任务执行", "", str(e))
                    raise
            return wrapper
        else:
            # 原有的同步函数处理逻辑
            @wraps(func)
            def wrapper():
                try:
                    logger.start(f"任务 {func.__module__}.{func.__name__}")
                    result = func()
                    logger.success("任务执行", f"{func.__module__}.{func.__name__}", "")
                    return result
                except Exception as e:
                    logger.fail("任务执行", f"{func.__module__}.{func.__name__}", str(e))
                    return None
            return wrapper

    def _job_error_listener(self, event):
        if event.exception:
            logger.fail("任务执行异常", event.job_id, str(event.exception))
        else:
            logger.warning_msg("任务错过执行", event.job_id, "")
    
    def start(self) -> bool:
        if not self._initialized:
            logger.fail("调度器启动", "", "未初始化")
            return False
            
        try:
            if self.scheduler and not self.scheduler.running:
                self.scheduler.start()
                logger.success("调度器", "", "已启动")
                return True
            else:
                logger.success("调度器", "", "已在运行中")
                return True
        except Exception as e:
            logger.fail("调度器启动", "", str(e))
            return False
    
    def shutdown(self):
        try:
            if self.scheduler and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.success("调度器", "", "已关闭")
        except Exception as e:
            logger.fail("调度器关闭", "", str(e))
    
    def get_jobs_info(self) -> List[Dict]:
        """获取所有任务信息"""
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            # 尝试获取下一次运行时间，处理不同版本的 API
            next_run_time = None
            try:
                # 尝试使用 next_run_time 属性
                next_run_time = job.next_run_time
            except AttributeError:
                try:
                    # 尝试使用 _get_run_times 方法
                    run_times = job._get_run_times(None)
                    if run_times:
                        next_run_time = run_times[0]
                except Exception:
                    pass
            
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': next_run_time,
                'trigger': str(job.trigger)
            })
        return jobs

# 全局调度器实例
scheduler_manager = SchedulerManager()

# ============================================================================
# 装饰器定义
# ============================================================================

def cron_task(**trigger_args):
    """Cron类型的定时任务装饰器"""
    def decorator(func):
        return task_registry.register(func, 'cron', **trigger_args)
    return decorator

def interval_task(**trigger_args):
    """间隔执行任务装饰器"""
    def decorator(func):
        return task_registry.register(func, 'interval', **trigger_args)
    return decorator

def date_task(**trigger_args):
    """指定日期执行任务装饰器"""
    def decorator(func):
        return task_registry.register(func, 'date', **trigger_args)
    return decorator

# 常用快捷装饰器
def daily_task(hour: int = 0, minute: int = 0):
    """每日定时任务快捷装饰器"""
    return cron_task(hour=hour, minute=minute)

def hourly_task(minute: int = 0):
    """每小时定时任务快捷装饰器"""
    return cron_task(minute=minute)

def weekly_task(day_of_week: str = 'mon', hour: int = 0, minute: int = 0):
    """每周定时任务快捷装饰器"""
    return cron_task(day_of_week=day_of_week, hour=hour, minute=minute)

# ============================================================================
# 初始化函数
# ============================================================================

def initialize_scheduler():
    """初始化并启动调度器"""
    if scheduler_manager.init_scheduler():
        scheduler_manager.start()
        atexit.register(scheduler_manager.shutdown)
        logger.info("✅ 定时任务系统启动完成")
    else:
        logger.error("🚫 定时任务系统启动失败")


def get_scheduler_status() -> Dict:
    """获取调度器状态"""
    return {
        'initialized': scheduler_manager._initialized,
        'running': scheduler_manager.scheduler.running if scheduler_manager.scheduler else False,
        'job_count': len(scheduler_manager.scheduler.get_jobs()) if scheduler_manager.scheduler else 0,
        'jobs': scheduler_manager.get_jobs_info()
    }


if __name__ == "__main__":
    # 应用启动时自动初始化
    # initialize_scheduler()
    # 或者在模块导入后合适的时机调用

    # 在其他模块中使用装饰器：
    from apps.data_opt.utils.scheduler import daily_task, hourly_task, interval_task

    @daily_task(hour=9, minute=0)  # 每天9点执行
    def refresh_stock():
        """刷新库存数据"""
        print("执行库存刷新...")
        # 你的业务逻辑

    @hourly_task(minute=30)  # 每小时的30分执行
    def sync_inventory():
        """同步库存信息"""
        print("同步库存信息...")
        # 你的业务逻辑

    @interval_task(hours=2)  # 每2小时执行一次
    def cleanup_temp_data():
        """清理临时数据"""
        print("清理临时数据...")
        # 你的业务逻辑

    # 使用完整的cron表达式
    from apps.data_opt.utils.scheduler import cron_task

    @cron_task(hour='9,11,13,15,17', minute=0, day_of_week='mon-fri')
    def complex_stock_task():
        """复杂定时任务：工作日的9,11,13,15,17点执行"""
        print("执行复杂库存任务...")