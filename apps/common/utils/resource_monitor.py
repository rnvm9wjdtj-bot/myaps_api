import os, time, threading, gc
from globalobjects import logger as log_config
from globalobjects import EVENT_AGGREGATOR
from globalobjects.db_manager import get_db_managers

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)

class ResourceMonitor:
    """系统资源监控器"""
    
    def __init__(self):
        """初始化资源监控器"""
        self._metrics = {}
        self._last_check = time.time()
        self._last_cleanup = time.time()
        self._running = False
        self._monitor_thread = None
        
        # 从settings.py加载阈值
        from core.settings import MONITOR_THRESHOLDS, RESOURCE_CLEANUP_CONFIG
        
        resource_thresholds = MONITOR_THRESHOLDS.get('resource', {})
        self._thresholds = {
            'cpu': resource_thresholds.get('cpu', 80.0),
            'memory': resource_thresholds.get('memory', 80.0),  # 内存使用率阈值（百分比）
            'threads': resource_thresholds.get('threads', 200)
        }
        
        self._cleanup_interval = RESOURCE_CLEANUP_CONFIG.get('interval', 300)
        self._cleanup_thresholds = {
            'memory': RESOURCE_CLEANUP_CONFIG.get('memory_threshold', 600.0)
        }
    
    def get_resource_usage(self):
        """获取系统资源使用情况
        
        Returns:
            dict: 资源使用情况
        """
        try:
            import psutil
            process = psutil.Process()
            memory = process.memory_info()
            # 获取系统CPU使用率
            system_cpu = psutil.cpu_percent(interval=0.1)
            # 获取进程CPU使用率（相对于所有核心）
            process_cpu = process.cpu_percent(interval=0.0)
            threads = process.num_threads()
            # 获取CPU核心数
            cpu_count = psutil.cpu_count()
            # 计算进程CPU使用率（相对于系统总CPU）
            process_cpu_system_percent = process_cpu / cpu_count
            
            # 添加详细日志
            logger.debug(f"CPU使用率调试: 系统CPU={system_cpu}%, 进程CPU={process_cpu}%, 核心数={cpu_count}, 进程相对系统={process_cpu_system_percent:.2f}%")
            
            return {
                'timestamp': time.time(),
                'memory': {
                    'rss': memory.rss / 1024 / 1024,  # MB
                    'vms': memory.vms / 1024 / 1024,  # MB
                },
                'cpu': {
                    'process': process_cpu,  # 进程CPU使用率（相对于单个核心）
                    'process_system_percent': process_cpu_system_percent,  # 进程CPU使用率（相对于系统）
                    'system': system_cpu  # 系统CPU使用率
                },
                'threads': threads,
                'cpu_count': cpu_count,
                'uptime': time.time() - process.create_time()
            }
        except ImportError:
            logger.warning("psutil not installed, resource monitoring disabled")
            return {
                'timestamp': time.time(),
                'error': 'psutil not installed'
            }
        except Exception as e:
            logger.fail("资源监控", "", str(e))
            return {
                'timestamp': time.time(),
                'error': str(e)
            }
    
    def check_thresholds(self, usage=None, thresholds=None):
        """检查资源使用是否超过阈值
        
        Args:
            usage: 资源使用情况，如果为None则自动获取
            thresholds: 自定义阈值
            
        Returns:
            list: 告警信息列表
        """
        if usage is None:
            usage = self.get_resource_usage()
        alerts = []
        
        check_thresholds = thresholds or self._thresholds
        
        # 检查系统CPU使用率
        if 'cpu' in check_thresholds:
            if isinstance(usage.get('cpu'), dict):
                if usage['cpu'].get('system', 0) > check_thresholds['cpu']:
                    alerts.append(f"CPU usage ({usage['cpu']['system']}%) exceeds threshold ({check_thresholds['cpu']}%)")
            else:
                if usage.get('cpu', 0) > check_thresholds['cpu']:
                    alerts.append(f"CPU usage ({usage.get('cpu', 0)}%) exceeds threshold ({check_thresholds['cpu']}%)")
        
        if 'memory' in check_thresholds:
            import psutil
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > check_thresholds['memory']:
                alerts.append(f"Memory usage ({memory_percent:.2f}%) exceeds threshold ({check_thresholds['memory']}%)")
        
        if 'threads' in check_thresholds and usage.get('threads', 0) > check_thresholds['threads']:
            alerts.append(f"Thread count ({usage['threads']}) exceeds threshold ({check_thresholds['threads']})")
        
        return alerts
    
    def start_monitoring(self, interval=60):
        """开始资源监控
        
        Args:
            interval: 监控间隔（秒）
        """
        if not self._running:
            self._running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, 
                args=(interval,),
                daemon=True,
                name='resource-monitor'
            )
            self._monitor_thread.start()
            logger.info("✅ 资源监控已启动")
        else:
            logger.info("⚠️ 资源监控已经在运行")
    
    def _cleanup_resources(self):
        """清理系统资源"""
        try:
            logger.debug("开始资源清理...")
            
            # 1. 清理事件缓冲区
            if EVENT_AGGREGATOR:
                try:
                    # 遍历所有事件聚合器并刷新
                    for event_type, aggregator in getattr(EVENT_AGGREGATOR, "_aggregators", {}).items():
                        if hasattr(aggregator, "flush_now"):
                            aggregator.flush_now()
                    logger.debug("事件缓冲区清理完成")
                except Exception as e:
                    logger.error(f"清理事件缓冲区异常: {e}")
            
            # 2. 触发垃圾回收
            collected = gc.collect()
            logger.info(f"垃圾回收完成，回收对象数: {collected}")
            
            # 3. 检查并清理其他资源
            # 这里可以添加其他资源清理逻辑
            
            self._last_cleanup = time.time()
            logger.debug("资源清理完成")
        except Exception as e:
            logger.error(f"资源清理异常: {e}")
    
    def _monitor_loop(self, interval):
        """监控循环"""
        while self._running:
            try:
                usage = self.get_resource_usage()
                alerts = self.check_thresholds(usage=usage)
                
                # 记录资源使用情况
                if 'error' not in usage:
                    if isinstance(usage.get('cpu'), dict):
                        logger.debug(f"资源使用: 系统CPU={usage['cpu']['system']}%, 进程CPU={usage['cpu']['process_system_percent']:.2f}%, 内存={usage['memory']['rss']:.2f}MB, 线程={usage['threads']}, CPU核心数={usage.get('cpu_count', 'N/A')}")
                    else:
                        logger.debug(f"资源使用: CPU={usage.get('cpu', 0)}%, 内存={usage['memory']['rss']:.2f}MB, 线程={usage['threads']}")
                
                # 处理告警
                for alert in alerts:
                    logger.warning(f"资源告警: {alert}")
                
                # 检查是否需要进行资源清理
                current_time = time.time()
                if (current_time - self._last_cleanup >= self._cleanup_interval) or \
                   (not 'error' in usage and usage.get('memory', {}).get('rss', 0) >= self._cleanup_thresholds['memory']):
                    # 执行资源清理
                    try:
                        # 直接执行同步清理操作
                        self._cleanup_resources()
                    except Exception as e:
                        logger.error(f"执行资源清理异常: {e}")
            except Exception as e:
                logger.fail("资源监控", "", str(e))
            
            # 等待下一次检查
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)
    
    def stop_monitoring(self):
        """停止资源监控"""
        if self._running:
            self._running = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5)
            logger.info("✅ 资源监控已停止")
        else:
            logger.info("⚠️ 资源监控已经停止")
    
    def set_thresholds(self, **thresholds):
        """设置资源阈值
        
        Args:
            thresholds: 阈值参数
        """
        self._thresholds.update(thresholds)
        logger.info(f"资源阈值已更新: {self._thresholds}")
    
    def get_status(self):
        """获取监控状态
        
        Returns:
            dict: 监控状态
        """
        return {
            'running': self._running,
            'thresholds': self._thresholds,
            'last_check': self._last_check,
            'current_usage': self.get_resource_usage()
        }

# 全局资源监控器实例
resource_monitor = ResourceMonitor()

# 应用退出时停止监控
import atexit
def _cleanup_resource_monitor():
    try:
        resource_monitor.stop_monitoring()
    except Exception as e:
        logger.fail("资源监控清理", "", str(e))

atexit.register(_cleanup_resource_monitor)