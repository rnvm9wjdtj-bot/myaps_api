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
                for job in scheduler_manager.scheduler.get_jobs():
                    # 尝试获取下一次运行时间，处理不同版本的 API
                    next_run_time = None
                    try:
                        next_run_time = job.next_run_time
                    except AttributeError:
                        try:
                            run_times = job._get_run_times(None)
                            if run_times:
                                next_run_time = run_times[0]
                        except Exception:
                            pass
                    
                    # 尝试获取上次运行时间，处理不同版本的 API
                    last_run_time = None
                    try:
                        # 尝试使用 last_run_time 属性
                        last_run_time = job.last_run_time
                    except AttributeError:
                        try:
                            # 尝试使用 _last_run 属性（某些版本的 APScheduler）
                            last_run_time = job._last_run
                        except Exception:
                            try:
                                # 尝试使用 _last_run_time 属性（另一种可能的属性名）
                                last_run_time = job._last_run_time
                            except Exception:
                                pass
                    
                    # 打印调试信息
                    logger.debug(f"任务 {job.name} 的上次执行时间: {last_run_time}")
                    
                    jobs.append({
                        "id": job.id,
                        "name": job.name,
                        "trigger": str(job.trigger),
                        "next_run_time": next_run_time.isoformat() if next_run_time else None,
                        "last_run_time": last_run_time.isoformat() if last_run_time else None,
                        "pending": job.pending,
                    })
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")

        logger.debug(f"返回的任务列表: {jobs}")
        return jobs

    def get_all_metrics(self) -> Dict[str, Any]:
        """
        获取所有定时任务相关指标

        Returns:
            Dict: 完整的定时任务监控指标
        """
        return {
            "timestamp": time.time(),
            "scheduler": self.get_scheduler_status(),
            "jobs": self.get_jobs(),
            "job_count": len(self.get_jobs()),
        }
