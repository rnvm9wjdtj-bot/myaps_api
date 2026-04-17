from typing import List, Dict, Any
from datetime import datetime
from .models import APIRequest, OutboundAPIRequest


class RequestStorage:
    """请求数据存储服务"""

    async def save_request(self, request_data: Dict[str, Any]) -> APIRequest:
        """保存单个请求数据"""
        request = await APIRequest.create(**request_data)
        return request

    async def save_requests(self, requests_data: List[Dict[str, Any]]) -> List[APIRequest]:
        """批量保存请求数据"""
        if not requests_data:
            return []
        requests = await APIRequest.bulk_create(
            [APIRequest(**data) for data in requests_data]
        )
        return requests

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

    async def clean_old_data(self, days: int = 7):
        """清理指定天数前的数据"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # 直接删除主表数据
        await APIRequest.filter(timestamp__lt=cutoff_date).delete()


class OutboundRequestStorage:
    """对外请求数据存储服务"""

    async def save_request(self, request_data: Dict[str, Any]) -> OutboundAPIRequest:
        """保存单个对外请求数据"""
        request = await OutboundAPIRequest.create(**request_data)
        return request

    async def save_requests(self, requests_data: List[Dict[str, Any]]) -> List[OutboundAPIRequest]:
        """批量保存对外请求数据"""
        if not requests_data:
            return []
        requests = await OutboundAPIRequest.bulk_create(
            [OutboundAPIRequest(**data) for data in requests_data]
        )
        return requests

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

    async def clean_old_data(self, days: int = 7):
        """清理指定天数前的对外请求数据"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        await OutboundAPIRequest.filter(timestamp__lt=cutoff_date).delete()


# 全局存储实例
request_storage = RequestStorage()
outbound_request_storage = OutboundRequestStorage()


async def clean_all_old_data(days: int = 30):
    """统一清理所有旧的请求数据
    
    Args:
        days: 保留多少天的数据，默认30天
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
    
    logger.success("清理旧请求记录", "任务完成")
