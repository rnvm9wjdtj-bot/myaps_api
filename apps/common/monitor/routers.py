"""
监控模块路由

提供监控相关的 API 端点
"""

import time
import hmac
import json
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, WebSocket, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, List, Optional
from tortoise import Tortoise
from .service import monitor_service
from .log_stream_service import log_stream_service
from .storage import request_storage, outbound_request_storage, system_log_storage
from .models import APIRequest, OutboundAPIRequest, SystemLog
from core.settings import TIMEZONE, SQLITE_FILE
from apps.common.utils.redis_pool_manager import get_redis_client
from globalobjects import logger as log_config
import time
import json
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, WebSocket, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, List, Optional
from tortoise import Tortoise
from .service import monitor_service
from .log_stream_service import log_stream_service
from .storage import request_storage, outbound_request_storage, system_log_storage
from .models import APIRequest, OutboundAPIRequest, SystemLog
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


@router.get("/health/database")
async def check_database_health() -> Dict[str, Any]:
    """
    检查所有数据库连接状态
    
    Returns:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "connections": {...},
            "tortoise_initialized": bool
        }
    """
    result = {
        "status": "healthy",
        "connections": {},
        "tortoise_initialized": Tortoise._inited
    }
    
    if not Tortoise._inited:
        result["status"] = "unhealthy"
        result["error"] = "Tortoise ORM 未初始化"
        return result
    
    unhealthy_count = 0
    for db_name in Tortoise._connections.keys():
        try:
            conn = Tortoise.get_connection(db_name)
            start_time = time.time()
            
            await conn.execute_query("SELECT 1")
            
            response_time_ms = (time.time() - start_time) * 1000
            
            result["connections"][db_name] = {
                "status": "healthy",
                "response_time_ms": round(response_time_ms, 2),
                "error": None
            }
            
        except Exception as e:
            unhealthy_count += 1
            result["connections"][db_name] = {
                "status": "unhealthy",
                "response_time_ms": None,
                "error": str(e)
            }
    
    total = len(result["connections"])
    if total == 0:
        result["status"] = "unhealthy"
        result["error"] = "无可用连接"
    elif unhealthy_count == total:
        result["status"] = "unhealthy"
    elif unhealthy_count > 0:
        result["status"] = "degraded"
    
    return result


@router.get("/health/database/{db_name}")
async def check_specific_database(db_name: str) -> Dict[str, Any]:
    """检查指定数据库连接状态"""
    if not Tortoise._inited:
        raise HTTPException(status_code=503, detail="数据库服务初始化中")
    
    try:
        conn = Tortoise.get_connection(db_name)
        start_time = time.time()
        
        await conn.execute_query("SELECT 1")
        
        response_time_ms = (time.time() - start_time) * 1000
        
        return {
            "db_name": db_name,
            "status": "healthy",
            "response_time_ms": round(response_time_ms, 2)
        }
        
    except KeyError:
        raise HTTPException(status_code=404, detail=f"连接 '{db_name}' 不存在")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库连接失败: {e}")


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


@router.get("/network")
async def get_network_metrics():
    """
    获取网络 I/O 指标

    返回各网络接口的发送/接收字节数、数据包数等累计指标
    """
    from .collectors import ResourceCollector
    collector = ResourceCollector()
    return collector.get_network_metrics()


@router.get("/network/bandwidth")
async def get_network_bandwidth():
    """
    获取实时网络带宽

    返回各网络接口的上传/下载带宽（字节/秒、数据包/秒）
    注：首次调用会返回"首次采样，等待下一次"，需要连续调用才能获取实际带宽值
    """
    from .collectors import ResourceCollector
    collector = ResourceCollector()
    return collector.get_network_bandwidth()


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
                try:
                    # 使用超时等待，定期发送心跳
                    log_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if log_data is None:
                        break

                    # 级别过滤（前端请求级别的过滤）
                    if level and log_data["level"] != level:
                        continue

                    # 格式化 SSE 消息
                    yield f'data: {json.dumps(log_data)}\n\n'
                except asyncio.TimeoutError:
                    # 发送心跳消息，保持连接活跃
                    yield 'data: heartbeat\n\n'
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
    from globalobjects.logger.handlers import _log_stream_manager
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
    from globalobjects.logger import debug, info, warning, error, critical
    debug("测试 DEBUG 日志")
    info("测试 INFO 日志")
    warning("测试 WARNING 日志")
    error("测试 ERROR 日志")
    critical("测试 CRITICAL 日志")

    await asyncio.sleep(0.1)

    return {
        "message": "所有级别日志已触发",
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

    返回回调跟踪器、DeadLetter队列和事件去重器的监控数据
    """
    return monitor_service.get_event_helpers_metrics()


@router.get("/binlog-listener")
async def get_binlog_listener_status():
    """
    获取binlog listener状态

    返回binlog listener的运行状态、健康状态、待处理事件数、背压状态等信息
    """
    return monitor_service.get_binlog_listener_status()


@router.get("/dead-letter")
async def get_dead_letter_events(limit: int = 50):
    """
    获取DeadLetter队列事件

    Args:
        limit: 返回事件数量限制

    Returns:
        DeadLetter事件列表和统计信息
    """
    return monitor_service.get_dead_letter_events(limit)


@router.post("/dead-letter/clear")
async def clear_dead_letters():
    """
    清空DeadLetter队列

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
        "duration": req.duration * 1000,  # 转换为毫秒
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
    start_time: str = None,
    end_time: str = None,
    timezone_offset: int = None,
    level: str = None,
    type: str = None,
    limit: int = 1000,
    module: str = None,
    keyword: str = None,
    status_code_min: int = None,
    status_code_max: int = None,
    duration_min: float = None,
    duration_max: float = None,
    client_ip: str = None,
    method: str = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = None,
    sort_order: str = "asc"
):
    """
    统一的历史查询端点（用于日志联动功能）
    
    按时间范围查询接收请求、发送请求和系统日志，并支持数据类型过滤和高级过滤条件
    
    Args:
        start_time: 开始时间（本地时间，ISO格式，如 "2024-01-15T18:30:00"），不传则查询全部
        end_time: 结束时间（本地时间，ISO格式，如 "2024-01-15T18:35:00"），不传则查询全部
        timezone_offset: 时区偏移分钟数（默认从配置读取，UTC+8 = 480）
        level: 日志级别过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        type: 数据类型过滤（http/outbound/logs，不传则返回全部）
        limit: 每种数据类型返回数量限制（用于无分页场景）
        module: 模块名过滤（支持多选，逗号分隔，如 "order_service,payment"）
        keyword: 关键词全文搜索（匹配message、path、url等文本字段）
        status_code_min: 状态码范围下限
        status_code_max: 状态码范围上限
        duration_min: 响应时间范围下限（毫秒）
        duration_max: 响应时间范围上限（毫秒）
        client_ip: 客户端IP过滤
        method: HTTP请求方法过滤（GET/POST/PUT/DELETE等）
        page: 页码（从1开始）
        page_size: 每页条数（50/100/200/500）
        sort_by: 排序字段（timestamp/duration/status_code）
        sort_order: 排序方向（asc/desc）
    
    Returns:
        包含接收请求、发送请求和系统日志的查询结果
    """
    # 获取时区偏移 - 添加防御性检查
    if timezone_offset is None:
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
    
    # 转换为UTC时间（如果提供了时间范围）
    utc_start = local_to_utc(start_time, timezone_offset) if start_time else None
    utc_end = local_to_utc(end_time, timezone_offset) if end_time else None
    
    # 参数验证
    if status_code_min is not None and status_code_max is not None and status_code_min > status_code_max:
        raise HTTPException(status_code=400, detail="status_code_min 不能大于 status_code_max")
    
    if duration_min is not None and duration_max is not None and duration_min > duration_max:
        raise HTTPException(status_code=400, detail="duration_min 不能大于 duration_max")
    
    if status_code_min is not None and (status_code_min < 100 or status_code_min > 599):
        raise HTTPException(status_code=400, detail="status_code_min 必须在 100-599 范围内")
    
    if status_code_max is not None and (status_code_max < 100 or status_code_max > 599):
        raise HTTPException(status_code=400, detail="status_code_max 必须在 100-599 范围内")
    
    if duration_min is not None and duration_min < 0:
        raise HTTPException(status_code=400, detail="duration_min 不能为负数")
    
    if duration_max is not None and duration_max < 0:
        raise HTTPException(status_code=400, detail="duration_max 不能为负数")
    
    # 分页参数验证
    if page < 1:
        raise HTTPException(status_code=400, detail="page 必须 >= 1")
    
    valid_page_sizes = [50, 100, 200, 500]
    if page_size not in valid_page_sizes:
        raise HTTPException(status_code=400, detail=f"page_size 必须是 {valid_page_sizes} 之一")
    
    if sort_order not in ["asc", "desc"]:
        raise HTTPException(status_code=400, detail="sort_order 必须是 asc 或 desc")
    
    if sort_by and sort_by not in ["timestamp", "duration", "status_code"]:
        raise HTTPException(status_code=400, detail="sort_by 必须是 timestamp/duration/status_code 之一")
    
    # 构建过滤条件字典（传递给storage层）
    filter_params = {
        "module": module.split(',') if module else None,
        "keyword": keyword,
        "status_code_min": status_code_min,
        "status_code_max": status_code_max,
        "duration_min": duration_min,
        "duration_max": duration_max,
        "client_ip": client_ip,
        "method": method,
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_order": sort_order
    }
    
    result = {
        "http_requests": [],
        "outbound_requests": [],
        "logs": [],
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat() if utc_start else None, "end": utc_end.isoformat() if utc_end else None}
        },
        "filter_params": {k: v for k, v in filter_params.items() if v is not None}
    }
    
    # 根据类型参数决定查询哪些数据
    should_query_http = type is None or type == 'http' or type == 'all'
    should_query_outbound = type is None or type == 'outbound' or type == 'all'
    should_query_logs = type is None or type == 'logs' or type == 'all'
    
    # 查询接收请求
    if should_query_http:
        http_requests = await request_storage.get_requests_with_filters(
            utc_start, utc_end, limit, filter_params
        )

        # 列表查询只返回基本字段，不返回request_body/response_body大字段（详情时懒加载）
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
            "error_message": req.error_message
            # 不返回: request_body, response_body, request_headers, response_headers
        } for req in http_requests]
    
    # 查询发送请求
    if should_query_outbound:
        outbound_requests = await outbound_request_storage.get_requests_with_filters(
            utc_start, utc_end, limit, filter_params
        )

        # 列表查询只返回基本字段，不返回request_body/response_body大字段
        result["outbound_requests"] = [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration * 1000,  # 转换为毫秒
            "module": req.module,
            "is_slow": req.is_slow,
            "is_error": req.is_error,
            "error_message": req.error_message
            # 不返回: request_body, response_body, request_headers, response_headers
        } for req in outbound_requests]
    
    # 查询系统日志
    if should_query_logs:
        logs = await system_log_storage.get_logs_with_filters(
            utc_start, utc_end, level, limit, filter_params
        )

        # 列表查询不返回stack_trace大字段（详情时懒加载）
        result["logs"] = [{
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "module": log.module,
            "function": log.function,
            "line_number": log.line_number,
            "message": log.message[:500] if log.message else None  # 截断message，避免超长日志
            # 不返回: stack_trace
        } for log in logs]
    
    # 统计总数（用于结果摘要显示）- 只执行一次count
    result["stats"] = {
        "http_count": await request_storage.count_requests_with_filters(utc_start, utc_end, filter_params) if should_query_http else 0,
        "outbound_count": await outbound_request_storage.count_requests_with_filters(utc_start, utc_end, filter_params) if should_query_outbound else 0,
        "logs_count": await system_log_storage.count_logs_with_filters(utc_start, utc_end, level, filter_params) if should_query_logs else 0
    }
    
    # 计算分页元数据（为每种数据类型独立计算）
    result["pagination"] = {}

    if should_query_http:
        http_count = result["stats"]["http_count"]
        if http_count > 0:
            http_pages = (http_count + page_size - 1) // page_size
            result["pagination"]["http"] = {
                "page": page,
                "page_size": page_size,
                "total_count": http_count,
                "total_pages": http_pages,
                "has_next": page < http_pages,
                "has_prev": page > 1,
                "start_index": (page - 1) * page_size + 1,
                "end_index": min(page * page_size, http_count)
            }

    if should_query_outbound:
        outbound_count = result["stats"]["outbound_count"]
        if outbound_count > 0:
            outbound_pages = (outbound_count + page_size - 1) // page_size
            result["pagination"]["outbound"] = {
                "page": page,
                "page_size": page_size,
                "total_count": outbound_count,
                "total_pages": outbound_pages,
                "has_next": page < outbound_pages,
                "has_prev": page > 1,
                "start_index": (page - 1) * page_size + 1,
                "end_index": min(page * page_size, outbound_count)
            }

    if should_query_logs:
        logs_count = result["stats"]["logs_count"]
        if logs_count > 0:
            logs_pages = (logs_count + page_size - 1) // page_size
            result["pagination"]["logs"] = {
                "page": page,
                "page_size": page_size,
                "total_count": logs_count,
                "total_pages": logs_pages,
                "has_next": page < logs_pages,
                "has_prev": page > 1,
                "start_index": (page - 1) * page_size + 1,
                "end_index": min(page * page_size, logs_count)
            }
    
    # 统计日志级别分布（仅查询系统日志时）- 优化：使用GROUP BY聚合，避免查询所有记录
    if should_query_logs and result["stats"]["logs_count"] > 0:
        try:
            # 使用原生SQL的GROUP BY聚合，性能最优
            from .models import SystemLog
            from tortoise import connections
            
            conn = connections.get(SQLITE_FILE)
            
            # 构建SQL查询
            sql = "SELECT level, COUNT(*) as count FROM system_logs WHERE 1=1"
            params = []
            
            if utc_start and utc_end:
                sql += " AND timestamp >= ? AND timestamp <= ?"
                params.extend([utc_start, utc_end])
            
            if filter_params and filter_params.get('module'):
                sql += f" AND module IN ({','.join(['?' for _ in filter_params['module']])})"
                params.extend(filter_params['module'])
            
            sql += " GROUP BY level"
            
            # 执行查询
            rows = await conn.execute_query(sql, params)
            level_stats = {}
            if rows and len(rows) > 1 and rows[1]:
                for row in rows[1]:
                    # SQLite返回sqlite3.Row对象，支持索引访问
                    if isinstance(row, (tuple, list)) and len(row) >= 2:
                        level_stats[row[0]] = row[1]
                    elif hasattr(row, '__getitem__'):
                        try:
                            level_stats[row['level']] = row['count']
                        except (KeyError, TypeError):
                            pass
            result["stats"]["level_distribution"] = level_stats
        except Exception as e:
            print(f"统计级别分布失败: {e}")
            result["stats"]["level_distribution"] = {}
    
    return result


# ========== 统计数据端点 ==========

@router.get("/history/stats")
async def get_history_stats(
    start_time: str,
    end_time: str,
    timezone_offset: int = None
):
    """
    统计数据端点 - 用于图表分析
    
    Returns:
        - 时序趋势数据
        - 日志级别分布
        - 状态码分布
        - 慢请求TOP10
    """
    if timezone_offset is None:
        try:
            tz_str = str(TIMEZONE).strip()
            tz_hours = float(tz_str) if tz_str.startswith(('+', '-')) else float(tz_str)
            timezone_offset = int(tz_hours * 60)
        except (ValueError, TypeError):
            timezone_offset = 480
    
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    # 统计日志级别分布
    logs = await system_log_storage.get_logs_by_time_range(utc_start, utc_end, None, 10000)
    level_dist = {}
    for log in logs:
        level = log.level or "INFO"
        level_dist[level] = level_dist.get(level, 0) + 1
    
    # 统计HTTP状态码分布
    http_requests = await request_storage.get_requests_by_time_range(utc_start, utc_end, 10000)
    status_dist = {}
    slow_requests = []
    for req in http_requests:
        code_range = f"{req.status_code // 100}xx"
        status_dist[code_range] = status_dist.get(code_range, 0) + 1
        if req.is_slow:
            slow_requests.append({
                "path": req.path,
                "method": req.method,
                "duration": req.response_time
            })
    
    slow_requests.sort(key=lambda x: x["duration"], reverse=True)
    slow_top10 = slow_requests[:10]
    
    from collections import defaultdict
    hourly_counts = defaultdict(lambda: {"requests": 0, "errors": 0})
    
    for req in http_requests:
        hour = req.timestamp.strftime("%Y-%m-%d %H:00")
        hourly_counts[hour]["requests"] += 1
        if req.is_error:
            hourly_counts[hour]["errors"] += 1
    
    trend_data = [
        {"time": k, "requests": v["requests"], "errors": v["errors"]}
        for k, v in sorted(hourly_counts.items())
    ]
    
    return {
        "trend": trend_data,
        "level_distribution": level_dist,
        "status_distribution": status_dist,
        "slow_requests": slow_top10,
        "summary": {
            "total_logs": len(logs),
            "total_requests": len(http_requests),
            "error_count": sum(1 for r in http_requests if r.is_error),
            "slow_count": len(slow_requests)
        }
    }


# ========== 时间线端点 ==========

@router.get("/history/timeline")
async def get_history_timeline(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    level: str = None,
    limit: int = 500,
    module: str = None,
    keyword: str = None,
    status_code_min: int = None,
    status_code_max: int = None,
    duration_min: float = None,
    duration_max: float = None,
    client_ip: str = None,
    method: str = None
):
    """
    时间线查询端点 - 合并三源数据并按时间排序
    
    Args:
        start_time: 开始时间（本地时间）
        end_time: 结束时间（本地时间）
        timezone_offset: 时区偏移分钟数
        level: 日志级别过滤
        limit: 返回数量限制
        其他过滤参数同history/query
    
    Returns:
        按时间排序的混合事件列表
    """
    # 时区处理
    if timezone_offset is None:
        try:
            tz_str = str(TIMEZONE).strip()
            if tz_str.startswith(('+', '-')):
                tz_hours = float(tz_str)
            else:
                tz_hours = float(tz_str)
            timezone_offset = int(tz_hours * 60)
        except (ValueError, TypeError):
            timezone_offset = 480
    
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    filter_params = {
        "module": module.split(',') if module else None,
        "keyword": keyword,
        "status_code_min": status_code_min,
        "status_code_max": status_code_max,
        "duration_min": duration_min,
        "duration_max": duration_max,
        "client_ip": client_ip,
        "method": method
    }
    
    # 并发查询三源数据
    http_task = request_storage.get_requests_with_filters(utc_start, utc_end, limit, filter_params)
    outbound_task = outbound_request_storage.get_requests_with_filters(utc_start, utc_end, limit, filter_params)
    logs_task = system_log_storage.get_logs_with_filters(utc_start, utc_end, level, limit, filter_params)
    
    http_requests, outbound_requests, logs = await asyncio.gather(
        http_task, outbound_task, logs_task
    )
    
    # 转换为统一事件格式
    events = []
    
    # HTTP请求事件
    for req in http_requests:
        events.append({
            "id": f"http_{req.id}",
            "timestamp": req.timestamp.isoformat(),
            "type": "http",
            "icon": "📥",
            "level": "INFO" if req.status_code < 400 else "ERROR",
            "summary": f"{req.method} {req.path}",
            "detail": {
                "method": req.method,
                "path": req.path,
                "status_code": req.status_code,
                "duration": req.response_time,
                "client_ip": req.client_ip,
                "is_error": req.is_error,
                "is_slow": req.is_slow
            }
        })
    
    # 发送请求事件
    for req in outbound_requests:
        events.append({
            "id": f"outbound_{req.id}",
            "timestamp": req.timestamp.isoformat(),
            "type": "outbound",
            "icon": "📤",
            "level": "INFO" if req.status_code < 400 else "ERROR",
            "summary": f"{req.method} {req.url[:80]}",
            "detail": {
                "method": req.method,
                "url": req.url,
                "status_code": req.status_code,
                "duration": req.duration * 1000,
                "module": req.module,
                "is_error": req.is_error,
                "is_slow": req.is_slow
            }
        })
    
    # 系统日志事件
    for log in logs:
        icon_map = {
            "DEBUG": "🔍",
            "INFO": "📝",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🔥"
        }
        events.append({
            "id": f"log_{log.id}",
            "timestamp": log.timestamp.isoformat(),
            "type": "log",
            "icon": icon_map.get(log.level, "📝"),
            "level": log.level,
            "summary": log.message[:100] if log.message else "",
            "detail": {
                "level": log.level,
                "module": log.module,
                "function": log.function,
                "line_number": log.line_number,
                "message": log.message,
                "stack_trace": log.stack_trace
            }
        })
    
    # 按时间戳排序（降序）
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # 应用限制
    if len(events) > limit:
        events = events[:limit]
    
    return {
        "events": events,
        "count": len(events),
        "time_range": {
            "original": {"start": start_time, "end": end_time},
            "converted": {"start": utc_start.isoformat(), "end": utc_end.isoformat()}
        }
    }


# ========== 增量拉取端点 ==========

@router.get("/history/recent")
async def get_recent_data(
    since_timestamp: str = None,
    data_type: str = "logs",
    limit: int = 100
):
    """
    增量拉取端点 - 用于实时追踪
    
    Args:
        since_timestamp: 上次拉取的时间戳（ISO格式），拉取此时间之后的数据
        data_type: 数据类型（http/outbound/logs）
        limit: 返回数量限制
    
    Returns:
        新增数据和最新时间戳
    """
    if not since_timestamp:
        # 无时间戳时返回最近数据
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
    else:
        since = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
    
    latest_timestamp = since.isoformat()
    
    result = {"events": [], "latest_timestamp": latest_timestamp}
    
    if data_type == "logs":
        logs = await SystemLog.filter(timestamp__gt=since).limit(limit).order_by('-timestamp').all()
        if logs:
            latest_timestamp = logs[0].timestamp.isoformat()
        result["events"] = [{
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "module": log.module,
            "message": log.message
        } for log in logs]
    
    elif data_type == "http":
        requests = await APIRequest.filter(timestamp__gt=since).limit(limit).order_by('-timestamp').all()
        if requests:
            latest_timestamp = requests[0].timestamp.isoformat()
        result["events"] = [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "path": req.path,
            "status_code": req.status_code,
            "duration": req.response_time
        } for req in requests]
    
    elif data_type == "outbound":
        requests = await OutboundAPIRequest.filter(timestamp__gt=since).limit(limit).order_by('-timestamp').all()
        if requests:
            latest_timestamp = requests[0].timestamp.isoformat()
        result["events"] = [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration * 1000
        } for req in requests]
    
    result["latest_timestamp"] = latest_timestamp
    result["count"] = len(result["events"])
    
    return result


# ========== 导出端点 ==========

import csv
import io


@router.get("/history/export")
async def export_history_data(
    start_time: str,
    end_time: str,
    timezone_offset: int = None,
    level: str = None,
    type: str = "logs",
    format: str = "csv",
    module: str = None,
    keyword: str = None,
    status_code_min: int = None,
    status_code_max: int = None,
    duration_min: float = None,
    duration_max: float = None,
    client_ip: str = None,
    method: str = None
):
    """
    导出历史查询数据（CSV或JSON格式）
    
    Args:
        start_time: 开始时间
        end_time: 结束时间
        timezone_offset: 时区偏移
        level: 日志级别
        type: 数据类型（http/outbound/logs）
        format: 导出格式（csv/json）
        其他过滤参数同查询接口
    
    Returns:
        StreamingResponse: 文件流
    """
    # 时区处理
    if timezone_offset is None:
        try:
            tz_str = str(TIMEZONE).strip()
            if tz_str.startswith(('+', '-')):
                tz_hours = float(tz_str)
            else:
                tz_hours = float(tz_str)
            timezone_offset = int(tz_hours * 60)
        except (ValueError, TypeError):
            timezone_offset = 480
    
    utc_start = local_to_utc(start_time, timezone_offset)
    utc_end = local_to_utc(end_time, timezone_offset)
    
    filter_params = {
        "module": module.split(',') if module else None,
        "keyword": keyword,
        "status_code_min": status_code_min,
        "status_code_max": status_code_max,
        "duration_min": duration_min,
        "duration_max": duration_max,
        "client_ip": client_ip,
        "method": method
    }
    
    limit = 10000  # 导出最大条数
    
    # 查询数据
    if type == "http":
        data = await request_storage.get_requests_with_filters(utc_start, utc_end, limit, filter_params)
        records = [{
            "时间": req.timestamp.isoformat(),
            "方法": req.method,
            "路径": req.path,
            "状态码": req.status_code,
            "响应时间(ms)": req.response_time,
            "客户端IP": req.client_ip or "",
            "是否慢请求": "是" if req.is_slow else "否",
            "是否错误": "是" if req.is_error else "否",
            "错误信息": req.error_message or ""
        } for req in data]
        filename_prefix = "http_requests"
        
    elif type == "outbound":
        data = await outbound_request_storage.get_requests_with_filters(utc_start, utc_end, limit, filter_params)
        records = [{
            "时间": req.timestamp.isoformat(),
            "方法": req.method,
            "URL": req.url,
            "状态码": req.status_code,
            "响应时间(ms)": req.duration * 1000,
            "模块": req.module or "",
            "是否慢请求": "是" if req.is_slow else "否",
            "是否错误": "是" if req.is_error else "否",
            "错误信息": req.error_message or ""
        } for req in data]
        filename_prefix = "outbound_requests"
        
    else:  # logs
        data = await system_log_storage.get_logs_with_filters(utc_start, utc_end, level, limit, filter_params)
        records = [{
            "时间": log.timestamp.isoformat(),
            "级别": log.level,
            "模块": log.module,
            "函数": log.function,
            "行号": log.line_number,
            "消息": log.message
        } for log in data]
        filename_prefix = "system_logs"
    
    if not records:
        raise HTTPException(status_code=404, detail="无数据可导出")
    
    # 生成文件名
    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{time_str}.{format}"
    
    # 流式生成响应
    if format == "csv":
        async def generate_csv():
            output = io.StringIO()
            if records:
                writer = csv.DictWriter(output, fieldnames=records[0].keys())
                writer.writeheader()
                for record in records:
                    writer.writerow(record)
            yield output.getvalue()
        
        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    else:  # json
        async def generate_json():
            yield json.dumps(records, ensure_ascii=False, indent=2)
        
        return StreamingResponse(
            generate_json(),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


# ========== 详情懒加载端点 ==========

@router.get("/history/outbound/{request_id}")
async def get_outbound_request_detail(request_id: int):
    """
    获取发送请求详情（懒加载，包含request_body、response_body等大字段）
    """
    try:
        req = await OutboundAPIRequest.get_or_none(id=request_id)
        if not req:
            raise HTTPException(status_code=404, detail="请求不存在")
        
        return {
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration * 1000,
            "module": req.module,
            "is_slow": req.is_slow,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "request_headers": req.request_headers,
            "response_headers": req.response_headers
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询详情失败: {str(e)}")


@router.get("/history/http/{request_id}")
async def get_http_request_detail(request_id: int):
    """
    获取HTTP请求详情（懒加载，包含request_body、response_body等大字段）
    """
    try:
        req = await APIRequest.get_or_none(id=request_id)
        if not req:
            raise HTTPException(status_code=404, detail="请求不存在")
        
        return {
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
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询详情失败: {str(e)}")


@router.get("/history/http/by-request-id/{request_id}")
async def get_http_request_by_request_id(request_id: str):
    """
    根据request_id（UUID）获取HTTP请求详情（包含完整的request_body、response_body）
    用于前端复制功能获取完整数据
    """
    try:
        req = await APIRequest.get_or_none(request_id=request_id)
        if not req:
            raise HTTPException(status_code=404, detail="请求不存在")
        
        return {
            "id": req.id,
            "request_id": req.request_id,
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
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询详情失败: {str(e)}")


@router.get("/history/log/{log_id}")
async def get_log_detail(log_id: int):
    """
    获取系统日志详情（懒加载，包含stack_trace等大字段）
    """
    try:
        log = await SystemLog.get_or_none(id=log_id)
        if not log:
            raise HTTPException(status_code=404, detail="日志不存在")
        
        return {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "module": log.module,
            "function": log.function,
            "line_number": log.line_number,
            "message": log.message,
            "stack_trace": log.stack_trace
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询详情失败: {str(e)}")


@router.get("/deadlock/stats")
async def get_deadlock_stats():
    """
    获取死锁监控统计信息
    
    Returns:
        {
            "timestamp": "2026-07-20T12:00:00",
            "databases": {
                "haida1": {
                    "state": "closed",
                    "deadlock_count": 3,
                    "is_circuit_open": false,
                    "alert_level": "normal"
                }
            },
            "summary": {
                "total_deadlocks": 5,
                "circuit_open_count": 0,
                "high_risk_databases": []
            },
            "alerts": []
        }
    """
    from apps.common.utils.redis_pool_manager import get_redis_client
    from core.settings import MYAPS_DBSET_LIST
    
    stats = {}
    redis_client = get_redis_client()
    
    if redis_client:
        try:
            for db_name in MYAPS_DBSET_LIST:
                prefix = f"myaps:circuitbreaker:{db_name}"
                
                state = redis_client.get(f"{prefix}:state")
                deadlock_count = redis_client.get(f"{prefix}:deadlock_count")
                window_start = redis_client.get(f"{prefix}:window_start")
                open_time = redis_client.get(f"{prefix}:open_time")
                half_open_success = redis_client.get(f"{prefix}:half_open_success")
                half_open_failure = redis_client.get(f"{prefix}:half_open_failure")
                
                state_str = state.decode('utf-8') if state else 'closed'
                deadlock_count_int = int(deadlock_count) if deadlock_count else 0
                
                stats[db_name] = {
                    'state': state_str,
                    'deadlock_count': deadlock_count_int,
                    'window_start': float(window_start) if window_start else time.time(),
                    'open_time': float(open_time) if open_time else None,
                    'is_circuit_open': state_str == 'open',
                    'half_open_success': int(half_open_success) if half_open_success else 0,
                    'half_open_failure': int(half_open_failure) if half_open_failure else 0,
                    'alert_level': 'normal'
                }
        except Exception as e:
            logger.error(f"获取熔断器统计信息失败: {e}")
    else:
        for db_name in MYAPS_DBSET_LIST:
            stats[db_name] = {
                'state': 'unknown',
                'deadlock_count': 0,
                'is_circuit_open': False,
                'alert_level': 'normal'
            }
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'databases': {},
        'alerts': [],
        'summary': {
            'total_deadlocks': 0,
            'circuit_open_count': 0,
            'high_risk_databases': []
        }
    }
    
    alert_threshold = 5
    
    for db_name, db_stats in stats.items():
        deadlock_count = db_stats['deadlock_count']
        is_circuit_open = db_stats['is_circuit_open']
        
        report['databases'][db_name] = {
            'deadlock_count': deadlock_count,
            'state': db_stats['state'],
            'is_circuit_open': is_circuit_open,
            'alert_level': 'normal',
            'half_open_success': db_stats.get('half_open_success', 0),
            'half_open_failure': db_stats.get('half_open_failure', 0)
        }
        
        report['summary']['total_deadlocks'] += deadlock_count
        
        if is_circuit_open:
            report['summary']['circuit_open_count'] += 1
            report['databases'][db_name]['alert_level'] = 'critical'
            report['alerts'].append({
                'database': db_name,
                'level': 'critical',
                'message': f"数据库 {db_name} 熔断器已触发，死锁次数: {deadlock_count}"
            })
        elif deadlock_count >= alert_threshold:
            report['summary']['high_risk_databases'].append(db_name)
            report['databases'][db_name]['alert_level'] = 'warning'
            report['alerts'].append({
                'database': db_name,
                'level': 'warning',
                'message': f"数据库 {db_name} 死锁次数较高: {deadlock_count}（阈值: {alert_threshold}）"
            })
    
    return report


@router.get("/deadlock/history")
async def get_deadlock_history(hours: int = 24):
    """
    获取死锁历史趋势数据（用于图表展示）
    
    Args:
        hours: 查询最近多少小时的数据，默认24小时
    
    Returns:
        {
            "timeline": [...],
            "deadlocks": [...],
            "circuit_opens": [...]
        }
    """
    from apps.common.utils.redis_pool_manager import get_redis_client
    
    redis_client = get_redis_client()
    
    if not redis_client:
        return {
            "timeline": [],
            "deadlocks": [],
            "circuit_opens": []
        }
    
    try:
        history_key = "myaps:deadlock:history"
        history_data = redis_client.lrange(history_key, 0, -1)
        
        if not history_data:
            return {
                "timeline": [],
                "deadlocks": [],
                "circuit_opens": []
            }
        
        timeline = []
        deadlocks = []
        circuit_opens = []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for item in history_data:
            try:
                data = json.loads(item.decode('utf-8'))
                timestamp = datetime.fromisoformat(data['timestamp'])
                
                if timestamp >= cutoff_time:
                    timeline.append(data['timestamp'])
                    deadlocks.append(data.get('total_deadlocks', 0))
                    circuit_opens.append(data.get('circuit_open_count', 0))
            except Exception as e:
                logger.debug(f"解析死锁历史数据失败: {e}")
                continue
        
        return {
            "timeline": timeline,
            "deadlocks": deadlocks,
            "circuit_opens": circuit_opens
        }
    except Exception as e:
        logger.error(f"获取死锁历史数据失败: {e}")
        return {
            "timeline": [],
            "deadlocks": [],
            "circuit_opens": []
        }


# ========== 服务管理端点 ==========

_RESTART_COOLDOWN = 43200
_RESTART_COOLDOWN_KEY = "myaps:restart:cooldown"
_RESTART_FAIL_PREFIX = "myaps:restart:fail:"
_RESTART_FAIL_LIMIT = 10
_RESTART_FAIL_WINDOW = 300

_last_restart_time = 0.0  # Redis 不可用时的内存降级
_last_fail_count = 0
_last_fail_window_start = 0.0


def _get_cooldown_remaining(now: float) -> int:
    """获取重启冷却剩余秒数，优先 Redis，不可用时回退内存"""
    try:
        client = get_redis_client()
        if client is not None:
            ttl = client.ttl(_RESTART_COOLDOWN_KEY)
            if ttl is not None and ttl > 0:
                return int(ttl)
    except Exception:
        pass
    return max(0, int(_RESTART_COOLDOWN - (now - _last_restart_time)))


def _set_cooldown(now: float) -> None:
    """记录重启时间，写入 Redis 并设置 TTL，同时更新内存降级值"""
    global _last_restart_time
    _last_restart_time = now
    try:
        client = get_redis_client()
        if client is not None:
            client.setex(_RESTART_COOLDOWN_KEY, _RESTART_COOLDOWN, int(now))
    except Exception:
        pass


def _restart_fail_key(ip: str) -> str:
    """失败计数 Redis 键名（按客户端 IP 隔离）"""
    return f"{_RESTART_FAIL_PREFIX}{ip}"


def _is_fail_blocked(ip: str) -> bool:
    """判断是否已触发失败锁定"""
    try:
        client = get_redis_client()
        if client is not None:
            count = client.get(_restart_fail_key(ip))
            return count is not None and int(count) > _RESTART_FAIL_LIMIT
    except Exception:
        pass
    return _last_fail_count > _RESTART_FAIL_LIMIT


def _record_fail(ip: str, now: float) -> None:
    """记录一次密码校验失败（窗口内计数，超时自动清零）"""
    global _last_fail_count, _last_fail_window_start
    try:
        client = get_redis_client()
        if client is not None:
            key = _restart_fail_key(ip)
            count = client.incr(key)
            if count == 1:
                client.expire(key, _RESTART_FAIL_WINDOW)
            return
    except Exception:
        pass
    if now - _last_fail_window_start > _RESTART_FAIL_WINDOW:
        _last_fail_count = 0
        _last_fail_window_start = now
    _last_fail_count += 1


def _reset_fail(ip: str) -> None:
    """校验成功后清零失败计数"""
    global _last_fail_count
    _last_fail_count = 0
    try:
        client = get_redis_client()
        if client is not None:
            client.delete(_restart_fail_key(ip))
    except Exception:
        pass


@router.get("/admin-enabled")
async def check_admin_enabled():
    """
    检查管理员功能是否启用

    当 ADMIN_PASSWORD 环境变量已配置时返回 enabled=True
    """
    from core.settings import ADMIN_PASSWORD
    now = time.time()
    remaining = _get_cooldown_remaining(now)
    return {"enabled": bool(ADMIN_PASSWORD), "cooldown_remaining": remaining}


@router.post("/restart")
async def restart_service(request: Request):
    """
    重启服务

    需要提供正确的管理员密码（ADMIN_PASSWORD 环境变量配置）
    进程退出后由 Docker restart: unless-stopped 策略自动拉起
    """
    import os as _os
    from core.settings import ADMIN_PASSWORD

    try:
        body = await request.json()
        password = body.get("password", "")
    except Exception:
        password = ""

    if not ADMIN_PASSWORD:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": "restart_not_enabled"}
        )

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # 失败次数锁定：超过阈值直接拒绝，防止暴力破解
    if _is_fail_blocked(client_ip):
        return JSONResponse(
            status_code=429,
            content={"success": False, "error": "too_many_attempts"}
        )

    if not hmac.compare_digest(password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
        _record_fail(client_ip, now)
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "wrong_password"}
        )

    _reset_fail(client_ip)

    remaining = _get_cooldown_remaining(now)
    if remaining > 0:
        return JSONResponse(
            status_code=429,
            content={"success": False, "error": "cooldown", "remaining_seconds": remaining}
        )

    _set_cooldown(now)

    logger.warning("服务重启", "管理员触发", "正在执行优雅关闭...")

    try:
        from apps.common.utils.event_helpers import shutdown_event_helpers
        shutdown_event_helpers()
    except Exception as e:
        logger.fail("重启清理", "event_helpers", str(e))

    try:
        from apps.common.utils.thread_pool_manager import global_pool_manager
        global_pool_manager.shutdown_all(wait=False, cancel_futures=True)
    except Exception as e:
        logger.fail("重启清理", "thread_pool", str(e))

    try:
        from apps.common.utils.resource_monitor import resource_monitor
        resource_monitor.stop_monitoring()
    except Exception as e:
        logger.fail("重启清理", "resource_monitor", str(e))

    logger.warning("服务重启", "优雅关闭完成", "进程即将退出")

    # 先返回响应，再由后台任务触发进程退出，避免 HTTP 响应未发送即被终止
    async def _trigger_exit():
        await asyncio.sleep(0.5)
        _os._exit(0)

    asyncio.create_task(_trigger_exit())
    return JSONResponse(
        status_code=200,
        content={"success": True, "cooldown_seconds": _RESTART_COOLDOWN}
    )

