from typing import List, Dict, Any
from datetime import datetime
from core.settings import LOG_RETENTION, LOG_LEVEL
from .models import APIRequest, OutboundAPIRequest, SystemLog

# 日志级别优先级映射
LOG_LEVEL_PRIORITY = {
    'DEBUG': 10,
    'INFO': 20,
    'WARNING': 30,
    'ERROR': 40,
    'CRITICAL': 50
}

# 获取当前 LOG_LEVEL 的优先级
CURRENT_LOG_LEVEL_PRIORITY = LOG_LEVEL_PRIORITY.get(LOG_LEVEL.upper(), 20)


def should_record_to_db(required_level: str) -> bool:
    """
    判断是否应该记录到数据库
    
    Args:
        required_level: 需要的最低日志级别
        
    Returns:
        bool: 是否应该记录
    """
    required_priority = LOG_LEVEL_PRIORITY.get(required_level.upper(), 20)
    return CURRENT_LOG_LEVEL_PRIORITY <= required_priority


class RequestStorage:
    """请求数据存储服务"""

    async def get_requests_by_time_range(self, start_time: datetime, end_time: datetime, limit: int = 1000) -> List[APIRequest]:
        """
        按时间范围查询请求记录
        
        Args:
            start_time: 开始时间（UTC datetime）
            end_time: 结束时间（UTC datetime）
            limit: 返回数量限制
            
        Returns:
            请求记录列表
        """
        try:
            requests = await APIRequest.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).limit(limit).order_by('-timestamp').all()
            return requests
        except Exception as e:
            print(f"按时间范围获取请求数据失败: {e}")
            return []

    async def save_request(self, request_data: Dict[str, Any]) -> APIRequest:
        """
        保存单个请求数据
        - 普通请求：INFO 级别
        - 错误请求/慢请求：WARNING 级别（总是记录）
        """
        is_error = request_data.get('is_error', False)
        is_slow = request_data.get('is_slow', False)
        
        # 错误请求和慢请求总是记录
        if is_error or is_slow:
            request = await APIRequest.create(**request_data)
            return request
        
        # 普通请求根据 LOG_LEVEL 决定是否记录
        if should_record_to_db('INFO'):
            request = await APIRequest.create(**request_data)
            return request
        return None

    async def save_requests(self, requests_data: List[Dict[str, Any]]) -> List[APIRequest]:
        """批量保存请求数据"""
        if not requests_data:
            return []
        
        # 过滤需要保存的请求
        requests_to_save = []
        for data in requests_data:
            is_error = data.get('is_error', False)
            is_slow = data.get('is_slow', False)
            if is_error or is_slow or should_record_to_db('INFO'):
                requests_to_save.append(data)
        
        if requests_to_save:
            requests = await APIRequest.bulk_create(
                [APIRequest(**data) for data in requests_to_save]
            )
            return requests
        return []

    async def get_request_by_timestamp_and_path(self, timestamp: float, path: str) -> APIRequest:
        """通过时间戳和路径获取请求记录"""
        from datetime import datetime, timedelta
        # 转换时间戳为 datetime
        timestamp_dt = datetime.fromtimestamp(timestamp)
        
        # 使用时间范围查询，避免时间戳精度问题
        return await APIRequest.filter(
            timestamp__gte=timestamp_dt - timedelta(seconds=0.1),
            timestamp__lte=timestamp_dt + timedelta(seconds=0.1),
            path=path
        ).first()

    async def get_requests_by_date(self, date: str, limit: int = 1000) -> List[APIRequest]:
        """按日期获取请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            requests = await APIRequest.filter(
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-timestamp').all()
            return requests
        except Exception as e:
            print(f"获取请求数据失败: {e}")
            return []

    async def get_slow_requests_by_date(self, date: str, limit: int = 100) -> List[APIRequest]:
        """按日期获取慢请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            slow_requests = await APIRequest.filter(
                is_slow=True,
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-response_time').all()
            return slow_requests
        except Exception as e:
            print(f"获取慢请求数据失败: {e}")
            return []

    async def get_error_requests_by_date(self, date: str, limit: int = 100) -> List[APIRequest]:
        """按日期获取错误请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            error_requests = await APIRequest.filter(
                is_error=True,
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-timestamp').all()
            return error_requests
        except Exception as e:
            print(f"获取错误请求数据失败: {e}")
            return []

    async def get_slow_requests_by_threshold(self, threshold: float, limit: int = 100) -> List[APIRequest]:
        """按阈值获取慢请求记录"""
        slow_requests = await APIRequest.filter(
            is_slow=True,
            slow_threshold__gte=threshold
        ).limit(limit).order_by('-slow_threshold').all()
        return slow_requests

    async def get_error_requests_by_status(self, status_code: int, limit: int = 100) -> List[APIRequest]:
        """按状态码获取错误请求记录"""
        error_requests = await APIRequest.filter(
            is_error=True,
            status_code=status_code
        ).limit(limit).order_by('-timestamp').all()
        return error_requests

    async def clean_old_data(self, days: int = LOG_RETENTION):
        """清理指定天数前的数据"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # 直接删除主表数据
        await APIRequest.filter(timestamp__lt=cutoff_date).delete()


class OutboundRequestStorage:
    """对外请求数据存储服务"""

    async def get_requests_by_time_range(self, start_time: datetime, end_time: datetime, limit: int = 1000) -> List[OutboundAPIRequest]:
        """
        按时间范围查询对外请求记录
        
        Args:
            start_time: 开始时间（UTC datetime）
            end_time: 结束时间（UTC datetime）
            limit: 返回数量限制
            
        Returns:
            对外请求记录列表
        """
        try:
            requests = await OutboundAPIRequest.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).limit(limit).order_by('-timestamp').all()
            return requests
        except Exception as e:
            print(f"按时间范围获取对外请求数据失败: {e}")
            return []

    async def save_request(self, request_data: Dict[str, Any]) -> OutboundAPIRequest:
        """
        保存单个对外请求数据
        - 普通请求：INFO 级别
        - 错误请求/慢请求：WARNING 级别（总是记录）
        """
        is_error = request_data.get('is_error', False)
        is_slow = request_data.get('is_slow', False)
        
        # 错误请求和慢请求总是记录
        if is_error or is_slow:
            request = await OutboundAPIRequest.create(**request_data)
            return request
        
        # 普通请求根据 LOG_LEVEL 决定是否记录
        if should_record_to_db('INFO'):
            request = await OutboundAPIRequest.create(**request_data)
            return request
        return None

    async def save_requests(self, requests_data: List[Dict[str, Any]]) -> List[OutboundAPIRequest]:
        """批量保存对外请求数据"""
        if not requests_data:
            return []
        
        # 过滤需要保存的请求
        requests_to_save = []
        for data in requests_data:
            is_error = data.get('is_error', False)
            is_slow = data.get('is_slow', False)
            if is_error or is_slow or should_record_to_db('INFO'):
                requests_to_save.append(data)
        
        if requests_to_save:
            requests = await OutboundAPIRequest.bulk_create(
                [OutboundAPIRequest(**data) for data in requests_to_save]
            )
            return requests
        return []

    async def get_requests_by_date(self, date: str, limit: int = 1000) -> List[OutboundAPIRequest]:
        """按日期获取对外请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            requests = await OutboundAPIRequest.filter(
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-timestamp').all()
            return requests
        except Exception as e:
            print(f"获取对外请求数据失败: {e}")
            return []

    async def get_slow_requests_by_date(self, date: str, limit: int = 100) -> List[OutboundAPIRequest]:
        """按日期获取对外慢请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            requests = await OutboundAPIRequest.filter(
                is_slow=True,
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-duration').all()
            return requests
        except Exception as e:
            print(f"获取对外慢请求数据失败: {e}")
            return []

    async def get_error_requests_by_date(self, date: str, limit: int = 100) -> List[OutboundAPIRequest]:
        """按日期获取对外错误请求记录"""
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            next_day = date_obj.replace(day=date_obj.day + 1)
            requests = await OutboundAPIRequest.filter(
                is_error=True,
                timestamp__gte=date_obj,
                timestamp__lt=next_day
            ).limit(limit).order_by('-timestamp').all()
            return requests
        except Exception as e:
            print(f"获取对外错误请求数据失败: {e}")
            return []

    async def get_requests_by_module(self, module: str, limit: int = 100) -> List[OutboundAPIRequest]:
        """按模块获取对外请求记录"""
        requests = await OutboundAPIRequest.filter(
            module=module
        ).limit(limit).order_by('-timestamp').all()
        return requests

    async def clean_old_data(self, days: int = LOG_RETENTION):
        """清理指定天数前的对外请求数据"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        await OutboundAPIRequest.filter(timestamp__lt=cutoff_date).delete()


class SystemLogStorage:
    """系统日志存储服务"""
    
    async def get_logs_by_time_range(self, start_time: datetime, end_time: datetime, level: str = None, limit: int = 1000) -> List[SystemLog]:
        """
        按时间范围查询系统日志记录
        
        Args:
            start_time: 开始时间（UTC datetime）
            end_time: 结束时间（UTC datetime）
            level: 日志级别过滤（可选）
            limit: 返回数量限制
            
        Returns:
            系统日志记录列表
        """
        try:
            query = SystemLog.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time
            )
            
            if level:
                query = query.filter(level=level.upper())
            
            logs = await query.limit(limit).order_by('-timestamp').all()
            return logs
        except Exception as e:
            print(f"按时间范围获取系统日志数据失败: {e}")
            return []
    
    async def clean_old_data(self, days: int = LOG_RETENTION):
        """清理指定天数前的系统日志数据"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        await SystemLog.filter(timestamp__lt=cutoff_date).delete()


# 全局存储实例
request_storage = RequestStorage()
outbound_request_storage = OutboundRequestStorage()
system_log_storage = SystemLogStorage()


async def clean_all_old_data(days: int = LOG_RETENTION):
    """统一清理所有旧的请求数据
    
    Args:
        days: 保留多少天的数据，默认使用配置文件中的 LOG_RETENTION
    """
    from globalobjects import logger as log_config
    logger = log_config.get_logger(__name__)
    
    logger.start("清理旧请求记录")
    
    # 清理接收请求记录
    try:
        logger.info("开始清理接收请求记录...")
        await request_storage.clean_old_data(days=days)
        logger.success("接收请求记录清理完成")
    except Exception as e:
        logger.fail("接收请求记录清理", "", str(e))
    
    # 清理发送请求记录
    try:
        logger.info("开始清理发送请求记录...")
        await outbound_request_storage.clean_old_data(days=days)
        logger.success("发送请求记录清理完成")
    except Exception as e:
        logger.fail("发送请求记录清理", "", str(e))
    
    # 清理系统日志记录
    try:
        logger.info("开始清理系统日志记录...")
        await system_log_storage.clean_old_data(days=days)
        logger.success("系统日志记录清理完成")
    except Exception as e:
        logger.fail("系统日志记录清理", "", str(e))
    
    logger.success("清理旧请求记录", "任务完成")
