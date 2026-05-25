"""
后台任务管理器
统一管理所有后台任务的生命周期
"""
import asyncio
from typing import Dict, Set, Optional, Any
from globalobjects import logger as log_config


class BackgroundTaskManager:
    """
    后台任务统一管理器
    
    功能：
    1. 统一注册所有后台任务
    2. 提供优雅关闭机制
    3. 确保关闭顺序正确（先取消任务，再释放资源）
    """
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_timeout: float = 10.0
        
    def register(self, name: str, task: asyncio.Task) -> asyncio.Task:
        """
        注册后台任务
        
        Args:
            name: 任务名称（用于日志和调试）
            task: asyncio.Task实例
            
        Returns:
            返回传入的task，方便链式调用
        """
        self._tasks[name] = task
        log_config.debug(f"后台任务已注册: {name}")
        
        # 添加完成回调，自动清理
        def _on_task_done(t: asyncio.Task):
            task_name = None
            for k, v in self._tasks.items():
                if v == t:
                    task_name = k
                    break
            if task_name:
                self._tasks.pop(task_name, None)
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        log_config.error(f"后台任务异常退出: {task_name}", exc_info=exc)
                    else:
                        log_config.debug(f"后台任务正常完成: {task_name}")
        
        task.add_done_callback(_on_task_done)
        return task
    
    def create_and_register(
        self, 
        name: str, 
        coro, 
        *,
        delay: float = 0.0
    ) -> asyncio.Task:
        """
        创建并注册后台任务
        
        Args:
            name: 任务名称
            coro: 协程对象
            delay: 启动延迟（秒）
            
        Returns:
            创建的Task实例
        """
        async def _wrapped_coro():
            if delay > 0:
                await asyncio.sleep(delay)
            await coro
        
        task = asyncio.create_task(_wrapped_coro())
        return self.register(name, task)
    
    async def cancel_all(self, timeout: Optional[float] = None) -> Dict[str, bool]:
        """
        取消所有后台任务
        
        Args:
            timeout: 超时时间（秒），None使用默认值
            
        Returns:
            任务取消结果字典 {任务名: 是否成功}
        """
        if not self._tasks:
            return {}
        
        timeout = timeout or self._shutdown_timeout
        results = {}
        
        log_config.info(f"开始取消 {len(self._tasks)} 个后台任务...")
        
        # 第一阶段：发送取消信号
        for name, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                log_config.debug(f"已发送取消信号: {name}")
        
        # 第二阶段：等待任务完成
        async def wait_for_task(name: str, task: asyncio.Task) -> bool:
            try:
                await asyncio.wait_for(task, timeout=timeout)
                return True
            except asyncio.CancelledError:
                return True  # 正常取消
            except asyncio.TimeoutError:
                log_config.warning(f"任务取消超时: {name}")
                return False
            except Exception as e:
                log_config.error(f"任务取消异常: {name}, {e}")
                return False
        
        # 并行等待所有任务
        wait_tasks = {
            name: asyncio.create_task(wait_for_task(name, task))
            for name, task in list(self._tasks.items())
        }
        
        # 等待所有等待任务完成
        for name, wait_task in wait_tasks.items():
            try:
                results[name] = await wait_task
            except Exception as e:
                log_config.error(f"等待任务完成失败: {name}, {e}")
                results[name] = False
        
        # 清理已完成的任务
        self._tasks.clear()
        
        # 统计结果
        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count
        
        if fail_count > 0:
            log_config.warning(f"任务取消完成: 成功 {success_count}, 失败 {fail_count}")
        else:
            log_config.info(f"所有 {success_count} 个后台任务已成功取消")
        
        return results
    
    def get_task_names(self) -> Set[str]:
        """获取所有已注册任务名称"""
        return set(self._tasks.keys())
    
    def get_task_count(self) -> int:
        """获取已注册任务数量"""
        return len(self._tasks)
    
    def has_task(self, name: str) -> bool:
        """检查任务是否已注册"""
        return name in self._tasks
    
    def set_shutdown_timeout(self, timeout: float):
        """设置关闭超时时间"""
        self._shutdown_timeout = timeout


# 全局任务管理器实例
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取全局任务管理器"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager


def reset_task_manager():
    """重置任务管理器（用于测试）"""
    global _task_manager
    _task_manager = None
