from apps.data_opt.utils.scheduler import cron_task
from apps.common.monitor.storage import clean_all_old_data
from globalobjects import logger as log_config

LOG_LEVEL = "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


@cron_task(hour="*", minute=30, description="每小时清理旧的收发请求及系统日志数据库记录")
async def task_clean_old_requests():
    """定时任务：每小时清理旧的收发请求及系统日志数据库记录"""
    try:
        # 调用统一的清理方法，默认使用 MONITOR_RETENTION_DAYS
        await clean_all_old_data()
    except Exception as e:
        logger.fail("定时任务执行", "清理旧请求记录", f"任务失败: {str(e)}")
        # 不抛出异常，避免影响其他任务
