import json
from datetime import datetime, timedelta
from typing import List

from globalobjects import AlertType, alert_manager
from apps.common.monitor.models import FailedOperation
from apps.io_api.utils.db_operation import (
    db_exec_sql,
    db_query,
    db_supsert,
    db_bupsert,
    db_delete,
    call_dbprocdure,
    db_update_by_index
)
from globalobjects import logger as log_config
from core.settings import LOG_LEVEL


# 获取日志器
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


# 函数映射表
FUNCTION_MAP = {
    "db_exec_sql": db_exec_sql,
    "db_query": db_query,
    "db_supsert": db_supsert,
    "db_bupsert": db_bupsert,
    "db_delete": db_delete,
    "call_dbprocdure": call_dbprocdure,
    "db_update_by_index": db_update_by_index,
}


class FailedOperationRecovery:
    """失败操作恢复管理器"""
    
    @staticmethod
    async def process_pending_operations() -> int:
        """
        处理待重试的失败操作
        
        Returns:
            int: 处理的操作数量
        """
        # 查询待重试且已到重试时间的操作，每次最多处理100个
        pending_ops = await FailedOperation.filter(
            status="pending",
            next_retry_time__lte=datetime.now()
        ).limit(100).order_by("timestamp")
        
        processed_count = 0
        
        for op in pending_ops:
            try:
                await FailedOperationRecovery._retry_operation(op)
                processed_count += 1
            except Exception as e:
                logger.error(
                    f"处理失败操作出错",
                    f"operation_id={op.operation_id}",
                    str(e)
                )
        
        if processed_count > 0:
            logger.info(
                f"已处理失败操作",
                f"count={processed_count}",
                "complete"
            )
        
        return processed_count
    
    @staticmethod
    async def _retry_operation(op: FailedOperation) -> None:
        """
        重试单个失败操作
        
        Args:
            op: 失败操作记录
        """
        try:
            # 更新状态为处理中
            op.status = "processing"
            op.last_retry_time = datetime.now()
            await op.save()
            
            # 获取函数
            func = FUNCTION_MAP.get(op.function_name)
            if not func:
                raise ValueError(f"未知函数: {op.function_name}")
            
            # 反序列化参数
            try:
                args = json.loads(op.args_json)
                # 尝试反序列化内层json
                for i in range(len(args)):
                    try:
                        args[i] = json.loads(args[i])
                    except (json.JSONDecodeError, TypeError):
                        pass
            except (json.JSONDecodeError, TypeError):
                args = []
            
            try:
                kwargs = json.loads(op.kwargs_json)
                # 尝试反序列化内层json
                for k, v in kwargs.items():
                    try:
                        kwargs[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        pass
            except (json.JSONDecodeError, TypeError):
                kwargs = {}
            
            # 执行重试（不使用装饰器，因为我们已经在装饰器的失败流程中）
            await func(*args, **kwargs)
            
            # 标记成功
            op.status = "completed"
            await op.save()
            
            logger.info(
                f"失败操作重试成功",
                f"operation_id={op.operation_id}",
                f"{op.db_name}/{op.function_name}"
            )
            
        except Exception as e:
            # 更新失败状态
            op.retry_count += 1
            
            if op.retry_count >= op.max_retries:
                # 达到最大重试次数
                op.status = "failed"
                
                # 触发最终告警
                await alert_manager.trigger_remind(
                    AlertType.DB_CONNECTION,
                    {
                        "operation_id": op.operation_id,
                        "db_name": op.db_name,
                        "function": op.function_name,
                        "status": "最终失败",
                        "retry_count": op.retry_count,
                        "max_retries": op.max_retries,
                        "error": str(e)
                    }
                )
                
                logger.error(
                    f"失败操作已达到最大重试次数",
                    f"operation_id={op.operation_id}",
                    f"retry_count={op.retry_count}"
                )
            else:
                # 继续等待下次重试，指数退避
                op.status = "pending"
                retry_interval = min(5 * (op.retry_count + 1), 60)
                op.next_retry_time = datetime.now() + timedelta(minutes=retry_interval)
                
                logger.warning(
                    f"失败操作重试失败，等待下次重试",
                    f"operation_id={op.operation_id}",
                    f"next_retry={retry_interval}分钟后"
                )
            
            await op.save()
    
    @staticmethod
    async def cleanup_completed_operations(days: int = 7) -> int:
        """
        清理已完成的旧记录
        
        Args:
            days: 保留天数
            
        Returns:
            int: 删除的记录数
        """
        cutoff = datetime.now() - timedelta(days=days)
        deleted = await FailedOperation.filter(
            status="completed",
            timestamp__lt=cutoff
        ).delete()
        
        count = deleted if isinstance(deleted, int) else deleted[0]
        
        if count > 0:
            logger.info(
                f"已清理旧的完成记录",
                f"count={count}",
                f"older_than={days}天"
            )
        
        return count
    
    @staticmethod
    async def get_pending_count() -> int:
        """
        获取待处理操作数量
        
        Returns:
            int: 待处理数量
        """
        return await FailedOperation.filter(status="pending").count()
    
    @staticmethod
    async def get_failed_count() -> int:
        """
        获取最终失败的操作数量
        
        Returns:
            int: 失败数量
        """
        return await FailedOperation.filter(status="failed").count()
    
    @staticmethod
    async def get_recent_failed_operations(limit: int = 20) -> List[FailedOperation]:
        """
        获取最近失败的操作
        
        Args:
            limit: 返回数量
            
        Returns:
            List[FailedOperation]: 失败操作列表
        """
        return await FailedOperation.filter(
            status__in=["pending", "failed"]
        ).order_by("-timestamp").limit(limit)
