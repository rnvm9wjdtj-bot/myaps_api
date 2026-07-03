"""
定时任务指标采集器

采集定时任务状态、执行历史等信息
"""

import time
from typing import Dict, Any, List, Optional
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status

logger = log_config.get_logger(__name__)


class SchedulerCollector:
    """定时任务指标采集器"""

    def __init__(self):
        pass

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        获取调度器状态

        Returns:
            Dict: 调度器运行状态
        """
        try:
            status = get_scheduler_status()
            return {
                "timestamp": time.time(),
                "running": status.get("running", False),
                "initialized": scheduler_manager._initialized,
            }
        except Exception as e:
            logger.error(f"获取调度器状态失败: {e}")
            return {
                "timestamp": time.time(),
                "running": False,
                "error": str(e),
            }

    def get_jobs(self) -> List[Dict[str, Any]]:
        """
        获取所有定时任务列表

        Returns:
            List: 任务信息列表
        """
        jobs = []
        try:
            if scheduler_manager.scheduler:
                # 直接使用scheduler_manager的get_jobs_info方法，它已经包含了last_error字段
                jobs_info = scheduler_manager.get_jobs_info()
                for job_info in jobs_info:
                    # 转换执行历史记录中的时间格式为ISO字符串
                    execution_history = []
                    if 'execution_history' in job_info:
                        for record in job_info['execution_history']:
                            execution_history.append({
                                'time': record['time'].isoformat() if hasattr(record['time'], 'isoformat') else record['time'],
                                'error': record['error']
                            })
                    
                    # 转换时间格式为ISO字符串
                    job_dict = {
                        "id": job_info['id'],
                        "name": job_info['name'],
                        "trigger": job_info['trigger'],
                        "next_run_time": job_info['next_run_time'].isoformat() if hasattr(job_info['next_run_time'], 'isoformat') else job_info['next_run_time'],
                        "last_run_time": job_info['last_run_time'].isoformat() if hasattr(job_info['last_run_time'], 'isoformat') else job_info['last_run_time'],
                        "last_error": job_info['last_error'],
                        "execution_history": execution_history,  # 包含执行历史记录
                        "pending": False  # 暂不支持pending状态
                    }
                    # logger.debug(f"任务信息: {job_dict}")
                    jobs.append(job_dict)
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")

        # logger.debug(f"返回的任务列表: {jobs}")
        return jobs

    def get_all_metrics(self) -> Dict[str, Any]:
        """
        获取所有定时任务相关指标

        Returns:
            Dict: 完整的定时任务监控指标
        """
        try:
            # 直接使用get_scheduler_status函数，它已经包含了完整的任务信息
            status = get_scheduler_status()
            jobs = []
            # logger.debug(f"get_scheduler_status返回的状态: {status}")
            
            for job_info in status.get('jobs', []):
                # 转换执行历史记录中的时间格式为ISO字符串
                execution_history = []
                if 'execution_history' in job_info:
                    for record in job_info['execution_history']:
                        execution_history.append({
                            'time': record['time'].isoformat() if hasattr(record['time'], 'isoformat') else record['time'],
                            'error': record['error']
                        })
                
                # 转换时间格式为ISO字符串
                job_dict = {
                    "id": job_info['id'],
                    "name": job_info['name'],
                    "description": job_info.get('description'),
                    "trigger": job_info['trigger'],
                    "next_run_time": job_info['next_run_time'].isoformat() if hasattr(job_info['next_run_time'], 'isoformat') else job_info['next_run_time'],
                    "last_run_time": job_info['last_run_time'].isoformat() if hasattr(job_info['last_run_time'], 'isoformat') else job_info['last_run_time'],
                    "last_error": job_info['last_error'],
                    "execution_history": execution_history,  # 包含执行历史记录
                    "pending": False  # 暂不支持pending状态
                }
                # logger.debug(f"转换后的任务信息: {job_dict}")
                jobs.append(job_dict)
            
            result = {
                "timestamp": time.time(),
                "scheduler": {
                    "timestamp": time.time(),
                    "running": status.get("running", False),
                    "initialized": status.get("initialized", False),
                    "error": None
                },
                "jobs": jobs,
                "job_count": status.get("job_count", 0),
            }
            # logger.debug(f"返回的监控指标: {result}")
            return result
        except Exception as e:
            logger.error(f"获取定时任务指标失败: {e}")
            return {
                "timestamp": time.time(),
                "scheduler": {
                    "timestamp": time.time(),
                    "running": False,
                    "initialized": False,
                    "error": str(e)
                },
                "jobs": [],
                "job_count": 0,
            }
