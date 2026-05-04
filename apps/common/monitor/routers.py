"""
监控模块路由

提供监控相关的 API 端点
"""

import time
import json
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, List, Optional
from .service import monitor_service
from .log_stream_service import log_stream_service
from .storage import request_storage, outbound_request_storage, system_log_storage
from core.settings import TIMEZONE
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

# 导入定时任务模块，确保它们被注册
from . import tasks
from .schemas import (
    ResourceMetrics,
    DBMetrics,
    SchedulerMetrics,
    HealthStatus,
    MonitorOverview,
    EventMetrics,
)

router = APIRouter(prefix="/monitor/api", tags=["monitor"])


@router.get("/health", response_model=HealthStatus)
async def health_check():
    """
    健康检查端点

    返回系统整体健康状态和各组件检查详情
    """
    return await monitor_service.get_health_status()


@router.get("/resource", response_model=ResourceMetrics)
async def get_resource_metrics():
    """
    获取资源使用指标

    返回 CPU、内存、线程等系统资源使用情况
    """
    return monitor_service.get_resource_metrics()


@router.get("/database")
async def get_database_metrics():
    """
    获取数据库监控指标

    返回数据库连接状态和连接池信息
    """
    return await monitor_service.get_database_metrics()


@router.get("/scheduler", response_model=SchedulerMetrics)
async def get_scheduler_metrics():
    """
    获取定时任务监控指标

    返回调度器状态和任务列表
    """
    return monitor_service.get_scheduler_metrics()


@router.get("/overview")
async def get_monitor_overview():
    """
    获取监控总览

    返回所有监控指标的汇总信息
    """
    return await monitor_service.get_overview()


@router.get("/alerts")
async def get_alerts(limit: int = 10):
    """
    获取最近告警

    Args:
        limit: 返回告警数量限制

    Returns:
        告警列表
    """
    return {"alerts": monitor_service.get_recent_alerts(limit)}


@router.post("/alerts/clear")
async def clear_alerts():
    """
    清空告警列表

    Returns:
        操作结果
    """
    monitor_service.clear_alerts()
    return {"message": "告警已清空"}


@router.get("/system-info")
async def get_system_info():
    """
    获取系统信息

    返回操作系统、CPU、内存等基本信息
    """
    from .collectors import ResourceCollector
    collector = ResourceCollector()
    return collector.get_system_info()


@router.get("/http")
async def get_http_metrics():
    """
    获取 接收请求指标

    返回 HTTP 请求统计、状态码分布、路径统计等信息
    """
    return await monitor_service.get_http_metrics()


@router.get("/http/slow")
async def get_slow_requests(limit: int = 10):
    """
    获取慢请求列表

    Args:
        limit: 返回数量限制

    Returns:
        慢请求列表
    """
    return {"slow_requests": await monitor_service.http_collector.get_slow_requests(limit)}


@router.get("/http/errors")
async def get_error_requests(limit: int = 10):
    """
    获取错误请求列表

    Args:
        limit: 返回数量限制

    Returns:
        错误请求列表
    """
    return {"error_requests": await monitor_service.http_collector.get_error_requests(limit)}


@router.post("/http/reset")
async def reset_http_stats():
    """
    重置 HTTP 统计

    Returns:
        操作结果
    """
    monitor_service.http_collector.reset_stats()
    return {"message": "HTTP 统计已重置"}


@router.get("/http/requests")
async def get_requests_by_date(date: str, limit: int = 1000):
    """
    按日期获取请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        请求记录列表
    """
    requests = await monitor_service.http_collector.get_requests_by_date(date, limit)
    return {"requests": requests, "count": len(requests), "date": date}


@router.get("/http/slow/date")
async def get_slow_requests_by_date(date: str, limit: int = 100):
    """
    按日期获取慢请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        慢请求记录列表
    """
    slow_requests = await monitor_service.http_collector.get_slow_requests_by_date(date, limit)
    return {"slow_requests": slow_requests, "count": len(slow_requests), "date": date}


@router.get("/http/errors/date")
async def get_error_requests_by_date(date: str, limit: int = 100):
    """
    按日期获取错误请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        错误请求记录列表
    """
    error_requests = await monitor_service.http_collector.get_error_requests_by_date(date, limit)
    return {"error_requests": error_requests, "count": len(error_requests), "date": date}


# 对外 HTTP 请求端点
@router.get("/outbound-http")
async def get_outbound_http_metrics():
    """
    获取对外请求指标

    返回对外 HTTP 请求统计、状态码分布、URL 统计等信息
    """
    return monitor_service.get_outbound_http_metrics()


@router.get("/outbound-http/requests")
async def get_outbound_requests_by_date(date: str, limit: int = 1000):
    """
    按日期获取对外请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        对外请求记录列表
    """
    requests = await monitor_service.outbound_http_collector.get_requests_by_date(date, limit)
    return {"requests": requests, "count": len(requests), "date": date}


@router.get("/outbound-http/slow/date")
async def get_outbound_slow_requests_by_date(date: str, limit: int = 100):
    """
    按日期获取对外慢请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        对外慢请求记录列表
    """
    slow_requests = await monitor_service.outbound_http_collector.get_slow_requests_by_date(date, limit)
    return {"slow_requests": slow_requests, "count": len(slow_requests), "date": date}


@router.get("/outbound-http/errors/date")
async def get_outbound_error_requests_by_date(date: str, limit: int = 100):
    """
    按日期获取对外错误请求记录

    Args:
        date: 查询日期，格式：YYYY-MM-DD
        limit: 返回数量限制

    Returns:
        对外错误请求记录列表
    """
    error_requests = await monitor_service.outbound_http_collector.get_error_requests_by_date(date, limit)
    return {"error_requests": error_requests, "count": len(error_requests), "date": date}


@router.get("/logs")
async def get_recent_logs(limit: int = 50, level: str = None):
    """
    获取最近的日志

    Args:
        limit: 返回日志数量限制
        level: 日志级别过滤 (warning, error)

    Returns:
        日志列表
    """
    return {"logs": monitor_service.get_recent_logs(limit, level)}


# ========== 实时日志流端点 ==========


@router.get("/live-logs/stream")
async def live_logs_stream(level: Optional[str] = None):
    """
    SSE 实时日志流端点（独立于现有日志功能）

    Args:
        level: 日志级别过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）

    Returns:
        StreamingResponse: SSE 流
    """
    async def event_generator():
        queue = await log_stream_service.subscribe()
        try:
            while True:
                log_data = await queue.get()
                if log_data is None:
                    break

                # 级别过滤（前端请求级别的过滤）
                if level and log_data["level"] != level:
                    continue

                # 格式化 SSE 消息
                yield f'data: {json.dumps(log_data)}\n\n'
        finally:
            await log_stream_service.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.get("/live-logs/recent")
async def get_live_logs_recent(limit: int = 50, level: Optional[str] = None):
    """
    获取最近的实时日志（用于初始加载）

    Args:
        limit: 返回数量限制
        level: 日志级别过滤

    Returns:
        日志列表
    """
    logs = log_stream_service.get_recent_logs(limit)
    if level:
        logs = [log for log in logs if log["level"] == level]
    return {"logs": logs, "count": len(logs)}


@router.get("/live-logs/status")
async def get_live_logs_status():
    """
    获取日志流服务状态（调试用）
    """
    from apps.common.monitor.log_stream_service import _log_stream_manager
    return {
        "is_running": log_stream_service._is_running,
        "queue_size": len(log_stream_service._log_queue),
        "handler_count": len(_log_stream_manager.get_handlers()),
        "active_connections": len(log_stream_service._active_connections),
        "handler": log_stream_service._handler is not None,
    }


@router.get("/live-logs/test")
async def test_live_logs():
    """
    测试日志流（调试用）
    """
    from globalobjects.logger import debug, info, warning, error
    info("测试 INFO 日志")
    warning("测试 WARNING 日志")
    error("测试 ERROR 日志")
    debug("测试 DEBUG 日志")

    await asyncio.sleep(0.1)

    return {
        "message": "日志已触发",
        "queue_size": len(log_stream_service._log_queue),
    }


@router.get("/database/pool-leak-detection")
async def get_pool_leak_detection():
    """
    获取数据库连接池泄漏检测信息

    返回连接池使用情况和泄漏检测结果
    """
    from core.database import smart_pool_manager
    
    try:
        leak_stats = smart_pool_manager._leak_detector.get_all_stats()
        pool_stats = smart_pool_manager.get_pool_stats()
        
        return {
            "timestamp": time.time(),
            "leak_detection": leak_stats,
            "pool_stats": pool_stats,
            "summary": {
                "total_databases": len(leak_stats),
                "leaks_detected": sum(1 for stats in leak_stats.values() if stats.get('leak_detected', False)),
                "warning_threshold": smart_pool_manager._leak_detector._warning_threshold,
                "critical_threshold": smart_pool_manager._leak_detector._critical_threshold,
            }
        }
    except Exception as e:
        return {
            "error": str(e),
            "message": "获取连接池泄漏检测信息失败"
        }


@router.get("/env")
async def get_environment():
    """
    获取环境变量信息

    返回当前系统的环境变量配置
    """
    import os
    from core.settings import PROJECT_DIR, PROJECT_JSON
    
    return {
        "project_dir": PROJECT_DIR,
        "project_json": PROJECT_JSON
    }





@router.get("/outbound-http/all", response_model=List[Dict[str, Any]])
def get_all_outbound_http_requests():
    """获取所有对外 HTTP 请求"""
    from .collectors import outbound_http_collector
    return outbound_http_collector.get_all_requests()


@router.get("/outbound-http/slow", response_model=List[Dict[str, Any]])
def get_outbound_http_slow_requests(limit: int = 10):
    """获取对外 HTTP 慢请求"""
    from .collectors import outbound_http_collector
    return outbound_http_collector.get_slow_requests(limit)


@router.get("/outbound-http/error", response_model=List[Dict[str, Any]])
def get_outbound_http_error_requests(limit: int = 10):
    """获取对外 HTTP 错误请求"""
    from .collectors import outbound_http_collector
    return outbound_http_collector.get_error_requests(limit)


@router.post("/outbound-http/reset")
def reset_outbound_http_stats():
    """重置对外 HTTP 请求统计"""
    from .collectors import outbound_http_collector
    outbound_http_collector.reset_stats()
    return {"message": "对外 HTTP 请求统计已重置"}


@router.get("/events", response_model=EventMetrics)
def get_event_metrics():
    """
    获取事件监控指标

    返回各事件类型的统计信息、汇总信息
    """
    return monitor_service.get_event_metrics()


@router.post("/events/flush")
def flush_events_now(event_type: str = None):
    """
    立即刷新事件聚合器

    Args:
        event_type: 指定事件类型，不传则刷新所有

    Returns:
        操作结果
    """
    monitor_service.flush_events_now(event_type)
    return {"message": "事件聚合器已刷新"}


@router.post("/events/reset-stats")
@router.get("/events/reset-stats")
def reset_event_stats(event_type: str = None):
    """
    重置事件统计数据

    Args:
        event_type: 指定事件类型，不传则重置所有

    Returns:
        操作结果
    """
    monitor_service.reset_event_stats(event_type)
    return {"message": "事件统计已重置"}


@router.get("/event-helpers")
async def get_event_helpers_metrics():
    """
    获取事件辅助模块监控指标

    返回回调跟踪器、死信队列和事件去重器的监控数据
    """
    return monitor_service.get_event_helpers_metrics()


@router.get("/dead-letter")
async def get_dead_letter_events(limit: int = 50):
    """
    获取死信队列事件

    Args:
        limit: 返回事件数量限制

    Returns:
        死信事件列表和统计信息
    """
    return monitor_service.get_dead_letter_events(limit)


@router.post("/dead-letter/clear")
async def clear_dead_letters():
    """
    清空死信队列

    Returns:
        操作结果
    """
    return monitor_service.clear_dead_letters()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点，用于实时推送监控数据

    客户端可以通过此端点建立 WebSocket 连接，接收实时监控数据
    """
    await monitor_service.register_websocket(websocket)
    try:
        while True:
            # 接收客户端消息（如果有）
            await websocket.receive_text()
    except Exception as e:
        logger.error(f"WebSocket 连接异常: {e}")
    finally:
        monitor_service.unregister_websocket(websocket)


# ========== 时间范围查询端点（用于日志联动功能）==========

def local_to_utc(local_time_str: str, timezone_offset_minutes: int) -> datetime:
    """
    将本地时间转换为UTC时间
    
    Args:
        local_time_str: 本地时间字符串（ISO格式，如 "2024-01-15T18:30:00"）
        timezone_offset_minutes: 时区偏移分钟数（UTC+8 = 480分钟）
    
    Returns:
        UTC时间对象
    """
    try:
        # 解析本地时间
        if 'Z' in local_time_str:
            # ISO 8601 格式带 Z
            local_time = datetime.fromisoformat(local_time_str.replace('Z', '+00:00'))
        elif '+' in local_time_str or '-' in local_time_str[-6:]:
            # ISO 8601 格式带时区偏移
            local_time = datetime.fromisoformat(local_time_str)
        else:
            # 不带时区的本地时间
            local_time = datetime.fromisoformat(local_time_str)
            local_time = local_time.replace(tzinfo=None)
        
        # 计算UTC时间：本地时间 - 时区偏移
        utc_time = local_time - timedelta(minutes=timezone_offset_minutes)
        
        # 设置UTC时区
        return utc_time.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.error(f"时间转换失败: {e}")
        raise HTTPException(status_code=400, detail=f"无效的时间格式: {local_time_str}")


@router.get("/http/by-time-range")
async def get_http_requests_by_time_range(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    limit: int = 1000
):
    """
    按时间范围查询接收请求记录（用于联动查询）
    
    Args:
        start_time: 开始时间（本地时间，ISO格式，如 "2024-01-15T18:30:00"）
        end_time: 结束时间（本地时间，ISO格式，如 "2024-01-15T18:35:00"）
        timezone_offset: 时区偏移分钟数（默认从配置读取，UTC+8 = 480）
        limit: 返回数量限制
    
    Returns:
        请求记录列表
    """
    # 获取时区偏移（优先使用参数，否则使用配置）
    if timezone_offset is None:
        # 解析 TIMEZONE 配置，如 "+8" 转换为 480 分钟
        try:
            tz_hours = float(TIMEZONE)
            timezone_offset = int(tz_hours * 60)
        except ValueError:
            timezone_offset = 480  # 默认 UTC+8
    
    # 转换为UTC时间
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    # 查询数据库
    requests = await request_storage.get_requests_by_time_range(utc_start, utc_end, limit)
    
    # 转换为响应格式
    result = [{
        "id": req.id,
        "timestamp": req.timestamp.isoformat(),
        "method": req.method,
        "path": req.path,
        "query_params": req.query_params,
        "status_code": req.status_code,
        "response_time": req.response_time,
        "client_ip": req.client_ip,
        "user_agent": req.user_agent,
        "is_slow": req.is_slow,
        "is_error": req.is_error,
        "error_message": req.error_message
    } for req in requests]
    
    return {
        "requests": result,
        "count": len(result),
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat(), "end": utc_end.isoformat()}
        }
    }


@router.get("/outbound-http/by-time-range")
async def get_outbound_http_requests_by_time_range(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    limit: int = 1000
):
    """
    按时间范围查询发送请求记录（用于联动查询）
    
    Args:
        start_time: 开始时间（本地时间，ISO格式）
        end_time: 结束时间（本地时间，ISO格式）
        timezone_offset: 时区偏移分钟数（默认从配置读取）
        limit: 返回数量限制
    
    Returns:
        发送请求记录列表
    """
    # 获取时区偏移
    if timezone_offset is None:
        try:
            tz_hours = float(TIMEZONE)
            timezone_offset = int(tz_hours * 60)
        except ValueError:
            timezone_offset = 480
    
    # 转换为UTC时间
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    # 查询数据库
    requests = await outbound_request_storage.get_requests_by_time_range(utc_start, utc_end, limit)
    
    # 转换为响应格式
    result = [{
        "id": req.id,
        "timestamp": req.timestamp.isoformat(),
        "method": req.method,
        "url": req.url,
        "status_code": req.status_code,
        "duration": req.duration,
        "module": req.module,
        "is_slow": req.is_slow,
        "is_error": req.is_error,
        "error_message": req.error_message
    } for req in requests]
    
    return {
        "requests": result,
        "count": len(result),
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat(), "end": utc_end.isoformat()}
        }
    }


@router.get("/logs/by-time-range")
async def get_logs_by_time_range(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    level: str = None,
    limit: int = 1000
):
    """
    按时间范围查询系统日志（用于联动查询）
    
    Args:
        start_time: 开始时间（本地时间，ISO格式）
        end_time: 结束时间（本地时间，ISO格式）
        timezone_offset: 时区偏移分钟数（默认从配置读取）
        level: 日志级别过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        limit: 返回数量限制
    
    Returns:
        日志记录列表
    """
    # 获取时区偏移
    if timezone_offset is None:
        try:
            tz_hours = float(TIMEZONE)
            timezone_offset = int(tz_hours * 60)
        except ValueError:
            timezone_offset = 480
    
    # 转换为UTC时间
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    # 查询数据库
    logs = await system_log_storage.get_logs_by_time_range(utc_start, utc_end, level, limit)
    
    # 转换为响应格式
    result = [{
        "id": log.id,
        "timestamp": log.timestamp.isoformat(),
        "level": log.level,
        "module": log.module,
        "function": log.function,
        "line_number": log.line_number,
        "message": log.message
    } for log in logs]
    
    return {
        "logs": result,
        "count": len(result),
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat(), "end": utc_end.isoformat()}
        }
    }


@router.get("/history/query")
async def get_history_by_time_range(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    level: str = None,
    type: str = None,
    limit: int = 1000
):
    """
    统一的历史查询端点（用于日志联动功能）
    
    按时间范围查询接收请求、发送请求和系统日志，并支持数据类型过滤
    
    Args:
        start_time: 开始时间（本地时间，ISO格式，如 "2024-01-15T18:30:00"）
        end_time: 结束时间（本地时间，ISO格式，如 "2024-01-15T18:35:00"）
        timezone_offset: 时区偏移分钟数（默认从配置读取，UTC+8 = 480）
        level: 日志级别过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        type: 数据类型过滤（http/outbound/logs，不传则返回全部）
        limit: 每种数据类型返回数量限制
    
    Returns:
        包含接收请求、发送请求和系统日志的查询结果
    """
    # 获取时区偏移 - 添加防御性检查
    if timezone_offset is None or timezone_offset == 0:
        try:
            # 移除可能的符号前缀（如 "+8" 或 "-5"）
            tz_str = str(TIMEZONE).strip()
            if tz_str.startswith(('+', '-')):
                tz_hours = float(tz_str)
            else:
                tz_hours = float(tz_str)
            timezone_offset = int(tz_hours * 60)
        except (ValueError, TypeError):
            timezone_offset = 480  # 默认 UTC+8
    
    # 转换为UTC时间
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    result = {
        "http_requests": [],
        "outbound_requests": [],
        "logs": [],
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat(), "end": utc_end.isoformat()}
        }
    }
    
    # 根据类型参数决定查询哪些数据
    should_query_http = type is None or type == 'http' or type == 'all'
    should_query_outbound = type is None or type == 'outbound' or type == 'all'
    should_query_logs = type is None or type == 'logs' or type == 'all'
    
    # 查询接收请求
    if should_query_http:
        http_requests = await request_storage.get_requests_by_time_range(utc_start, utc_end, limit)
        result["http_requests"] = [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "path": req.path,
            "query_params": req.query_params,
            "status_code": req.status_code,
            "duration": req.response_time,
            "client_ip": req.client_ip,
            "user_agent": req.user_agent,
            "is_slow": req.is_slow,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "request_headers": getattr(req, 'request_headers', None),
            "response_headers": getattr(req, 'response_headers', None)
        } for req in http_requests]
    
    # 查询发送请求
    if should_query_outbound:
        outbound_requests = await outbound_request_storage.get_requests_by_time_range(utc_start, utc_end, limit)
        result["outbound_requests"] = [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration,
            "module": req.module,
            "is_slow": req.is_slow,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "request_headers": req.request_headers,
            "response_headers": req.response_headers
        } for req in outbound_requests]
    
    # 查询系统日志
    if should_query_logs:
        logs = await system_log_storage.get_logs_by_time_range(utc_start, utc_end, level, limit)
        result["logs"] = [{
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "module": log.module,
            "function": log.function,
            "line_number": log.line_number,
            "message": log.message,
            "stack_trace": log.stack_trace
        } for log in logs]
    
    return result
