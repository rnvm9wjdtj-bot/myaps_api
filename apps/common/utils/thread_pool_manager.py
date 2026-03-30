import os, threading, concurrent.futures
from globalobjects import logger as log_config

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)

class GlobalThreadPoolManager:
    """全局线程池管理器"""
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        """初始化线程池管理器"""
        self._pools = {}
        self._lock = threading.RLock()
        self._default_config = {
            'min_workers': 5,
            'max_workers': 20,
            'thread_name_prefix': 'global-'
        }
    
    def get_pool(self, name, max_workers=None, min_workers=None, thread_name_prefix=None):
        """获取或创建线程池
        
        Args:
            name: 线程池名称
            max_workers: 最大线程数
            min_workers: 最小线程数
            thread_name_prefix: 线程名称前缀
            
        Returns:
            ThreadPoolExecutor: 线程池实例
        """
        with self._lock:
            if name not in self._pools:
                # 使用默认配置或传入的配置
                config = self._default_config.copy()
                if max_workers is not None:
                    config['max_workers'] = max_workers
                if min_workers is not None:
                    config['min_workers'] = min_workers
                if thread_name_prefix is not None:
                    config['thread_name_prefix'] = thread_name_prefix
                else:
                    config['thread_name_prefix'] = f"{name}-"
                
                # 创建线程池
                self._pools[name] = {
                    'pool': concurrent.futures.ThreadPoolExecutor(
                        max_workers=config['max_workers'],
                        thread_name_prefix=config['thread_name_prefix']
                    ),
                    'config': config
                }
                logger.success("线程池创建", name, f"max_workers={config['max_workers']}")
            
            return self._pools[name]['pool']
    
    def shutdown_pool(self, name, wait=True, cancel_futures=False):
        """关闭指定线程池
        
        Args:
            name: 线程池名称
            wait: 是否等待任务完成
            cancel_futures: 是否取消未完成的任务
        """
        with self._lock:
            if name in self._pools:
                try:
                    self._pools[name]['pool'].shutdown(wait=wait, cancel_futures=cancel_futures)
                    del self._pools[name]
                    logger.success("线程池关闭", name, "")
                except Exception as e:
                    logger.fail("线程池关闭", name, str(e))
            else:
                logger.warning(f"线程池 {name} 不存在")
    
    def shutdown_all(self, wait=True, cancel_futures=False):
        """关闭所有线程池
        
        Args:
            wait: 是否等待任务完成
            cancel_futures: 是否取消未完成的任务
        """
        with self._lock:
            for name in list(self._pools.keys()):
                self.shutdown_pool(name, wait=wait, cancel_futures=cancel_futures)
        logger.success("线程池管理器", "", "所有线程池已关闭")
    
    def get_pool_info(self):
        """获取所有线程池信息
        
        Returns:
            dict: 线程池信息
        """
        with self._lock:
            info = {}
            for name, pool_data in self._pools.items():
                pool = pool_data['pool']
                info[name] = {
                    'config': pool_data['config'],
                    'running': not getattr(pool, '_shutdown', False)
                }
            return info

# 全局线程池管理器实例
global_pool_manager = GlobalThreadPoolManager()

# 应用退出时关闭所有线程池
import atexit
def _cleanup_thread_pools():
    try:
        global_pool_manager.shutdown_all()
    except Exception as e:
        logger.fail("线程池清理", "", str(e))

atexit.register(_cleanup_thread_pools)