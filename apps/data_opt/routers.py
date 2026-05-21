# from datetime import datetime
import os#, importlib#, uuid
from pathlib import Path
from typing import Optional#, Dict, Any
# from datetime import datetime


import pandas as pd
from fastapi import APIRouter, Query, Body, Header, File, UploadFile#, HTTPException
from fastapi.responses import HTMLResponse#, StreamingResponse

from core.settings import BASE_DIR
from project_files import  project_client, hap_conn
# from .schemas import SupplyOperationBody, SupplyAction
# from apps.io_api.models import TSupply
from .utils.barcode_qrcode_generator import generate_qrcode, generate_barcode
from apps.io_api.utils.common import standard_response
from apps.data_opt.utils.bomchecker import BOMChecker
from apps.data_opt.utils.routechecker import RouteChecker



# 创建路由器实例
rt = APIRouter()


@rt.post("/generate/qrcode",
    tags=["数据操作 - 二维码生成"],
    summary="生成二维码",
    description="生成二维码并返回BASE64格式数据"
)
async def generate_qrcode_api(
    content: str = Body(..., description="二维码内容"),
    version: Optional[int] = Body(1, ge=1, le=40, description="二维码版本，1-40"),
    box_size: Optional[int] = Body(10, ge=1, description="二维码每个小方格的像素大小"),
    border: Optional[int] = Body(4, ge=1, description="二维码边框的小方格数"),
    error_correction: Optional[str] = Body("H", pattern="^(L|M|Q|H)$", description="纠错级别：L(7%), M(15%), Q(25%), H(30%)"),
    back_color: Optional[str] = Body("#FFFFFF", pattern="^#[0-9A-Fa-f]{6}$", description="背景颜色，十六进制颜色码"),
    fill_color: Optional[str] = Body("#000000", pattern="^#[0-9A-Fa-f]{6}$", description="填充颜色，十六进制颜色码"),
    image_format: Optional[str] = Body("SVG", pattern="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(12, ge=8, description="内容文字大小"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        result = generate_qrcode(
            content=content,
            version=version,
            box_size=box_size,
            border=border,
            error_correction=error_correction,
            back_color=back_color,
            fill_color=fill_color,
            image_format=image_format,
            show_content=show_content,
            content_font_size=content_font_size,
            output_type="BASE64"
        )
        return standard_response(
            data={
                "base64": result["base64"],
                "content": content,
                "image_format": image_format
            }
        )
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )


# ========== Binlog Listener HA Enhancement ==========
# 以下接口为 Binlog 监听器高可用增强模块新增
# 与现有监控模块 (apps.common.monitor) 接口互不影响，向后兼容

from apps.data_opt.utils.binlog_ha import (
    prometheus_metrics,
    health_checker,
    HealthResponse,
    backpressure_controller,
    event_deduplicator,
    config_manager,
    failover_manager,
)


@rt.get("/metrics",
    tags=["Binlog HA - 监控指标"],
    summary="Prometheus 指标暴露",
    description="返回 Prometheus 格式的监控指标，支持 Counter、Gauge、Histogram 类型"
)
async def prometheus_metrics_endpoint():
    """
    Prometheus 指标暴露端点
    
    指标类型：
    - binlog_events_processed_total: 已处理事件总数 (Counter)
    - binlog_queue_size: 当前队列大小 (Gauge)
    - binlog_processing_delay_seconds: 处理延迟分布 (Histogram)
    - binlog_listener_role: 监听器角色 (Gauge: 1=master, 2=slave, 3=standalone)
    """
    return await prometheus_metrics.expose_endpoint()


@rt.get("/health",
    tags=["Binlog HA - 健康检查"],
    summary="增强健康检查",
    description="返回全面的健康检查结果，包含 MySQL、Redis、Binlog 位置、背压状态等",
    response_model=HealthResponse
)
async def health_check_endpoint():
    """
    增强健康检查端点
    
    检查项：
    - mysql_connection: MySQL 连接状态
    - redis_connection: Redis 连接状态
    - binlog_position: Binlog 位置同步状态
    - listener_role: 监听器角色状态
    - backpressure: 背压状态
    - event_loop: 事件循环状态
    - connection_pool: 连接池状态
    
    响应状态：
    - healthy: 所有检查项通过
    - degraded: 存在警告项
    - unhealthy: 存在失败项
    """
    return await health_checker.check_all()


@rt.get("/binlog/status",
    tags=["Binlog HA - 状态查询"],
    summary="Binlog 监听器状态查询（增强）",
    description="返回监听器详细状态，包含角色、背压、故障转移等信息"
)
async def binlog_status_endpoint():
    """
    Binlog 监听器状态查询（增强版）
    
    说明：
    - 此接口为新增接口，与现有 /monitor/binlog-listener 接口并存
    - /monitor/binlog-listener 保持原有实现，向后兼容
    - 本接口提供增强的状态信息
    
    返回字段：
    - 基础状态：is_running, connection_status, current_position
    - 性能指标：events_processed, queue_size
    - 高可用信息：role, failover_count, backpressure
    """
    from apps.data_opt.utils.binlog_listener import binlog_listener
    
    try:
        status = binlog_listener.get_status()
        
        return {
            "success": True,
            "data": {
                "is_running": status.get("running", False),
                "connection_status": "connected" if status.get("healthy") else "disconnected",
                "current_position": status.get("current_position"),
                "events_processed": status.get("pending_events", 0),
                "role": status.get("role", "standalone"),
                "failover_count": status.get("failover_count", 0),
                "backpressure": {
                    "state": "normal",
                    "queue_size": status.get("pending_events", 0),
                    "throttle_count": 0,
                    "threshold": status.get("backpressure_threshold", 10000),
                    "percent": status.get("backpressure_percent", 0),
                },
                "event_loop_healthy": status.get("event_loop_healthy", None),
                "consecutive_errors": status.get("consecutive_errors", 0),
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


@rt.get("/binlog/backpressure/status",
    tags=["Binlog HA - 背压控制"],
    summary="背压状态查询",
    description="返回当前背压状态、队列指标、限流统计"
)
async def backpressure_status_endpoint():
    """
    背压状态查询端点
    
    返回字段：
    - state: 背压状态 (normal/warning/critical)
    - queue_size: 当前队列大小
    - queue_capacity: 队列容量（限流阈值）
    - processing_delay_avg: 平均处理延迟
    - processing_delay_max: 最大处理延迟
    - throttle_count: 限流次数累计
    - throttle_duration_total: 限流总时长
    """
    try:
        metrics = backpressure_controller.get_queue_metrics()
        state = backpressure_controller.get_state()
        
        return {
            "success": True,
            "data": {
                "state": state.value,
                "queue_size": metrics.current_size,
                "queue_capacity": backpressure_controller.limit_threshold,
                "processing_delay_avg": metrics.avg_delay,
                "processing_delay_max": metrics.max_delay,
                "throttle_count": metrics.throttle_count,
                "throttle_duration_total": metrics.throttle_duration_total,
                "warning_threshold": backpressure_controller.warning_threshold,
                "limit_threshold": backpressure_controller.limit_threshold,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


@rt.post("/binlog/config/update",
    tags=["Binlog HA - 配置管理"],
    summary="配置热更新",
    description="更新 Binlog 监听器配置，支持热更新和需重启项区分"
)
async def config_update_endpoint(
    config: dict = Body(..., description="配置项字典"),
    operator: str = Body(..., description="操作者"),
    reason: str = Body(None, description="操作原因")
):
    """
    配置热更新端点
    
    热更新配置项（立即生效）：
    - max_retry_attempts: 最大重试次数
    - base_retry_delay_seconds: 基础重试延迟
    - heartbeat_interval_seconds: 心跳间隔
    - backpressure_warning_threshold: 背压告警阈值
    - backpressure_limit_threshold: 背压限流阈值
    - dedup_ttl_hours: 去重TTL
    
    需重启配置项：
    - turnon_binlog_listener: 监听器开关
    - enable_binlog_position: 位置持久化开关
    - redis_host, redis_port: Redis连接配置
    
    返回字段：
    - applied: 已应用的配置项
    - requires_restart: 需重启才能生效的配置项
    - audit_id: 审计ID
    """
    result = config_manager.apply_config(config, operator, reason)
    return result


@rt.get("/binlog/config/audit",
    tags=["Binlog HA - 配置管理"],
    summary="获取审计日志",
    description="返回配置变更审计日志"
)
async def config_audit_endpoint(
    limit: int = Query(100, ge=1, le=1000, description="返回条数限制")
):
    """
    审计日志查询端点
    
    返回字段：
    - audit_id: 审计ID
    - timestamp: 操作时间
    - operator: 操作者
    - action: 操作类型
    - changes: 变更内容
    - result: 操作结果
    - reason: 操作原因
    """
    entries = config_manager.get_audit_log(limit)
    
    return {
        "success": True,
        "data": [entry.model_dump() for entry in entries],
        "total_count": len(entries)
    }


@rt.get("/binlog/dedup/stats",
    tags=["Binlog HA - 事件去重"],
    summary="去重统计信息",
    description="返回事件去重统计信息"
)
async def dedup_stats_endpoint():
    """
    去重统计信息端点
    
    返回字段：
    - total_checked: 检查总数
    - total_duplicates: 重复事件数
    - duplicate_rate: 重复率 (%)
    - ttl_hours: TTL时长
    - use_redis: 是否使用Redis
    """
    stats = event_deduplicator.get_stats()
    
    return {
        "success": True,
        "data": stats
    }


@rt.get("/binlog/failover/status",
    tags=["Binlog HA - 主备故障转移"],
    summary="主备状态查询",
    description="返回主备角色、心跳信息、故障转移统计"
)
async def failover_status_endpoint():
    """
    主备状态查询端点
    
    返回字段：
    - role: 当前角色 (master/slave/standalone)
    - master_info: 主节点信息（备节点视角）
    - failover_count: 故障转移次数
    - last_failover_time: 上次故障转移时间
    """
    try:
        role = failover_manager.get_role()
        failover_count = failover_manager.get_failover_count()
        
        master_info = None
        if role.value == "slave":
            master_info = failover_manager.get_master_info()
        
        return {
            "success": True,
            "data": {
                "role": role.value,
                "master_info": master_info,
                "failover_count": failover_count,
                "last_failover_time": failover_manager._promoted_time,
                "heartbeat_interval": failover_manager.heartbeat_interval,
                "heartbeat_timeout": failover_manager.heartbeat_timeout,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


@rt.post("/generate/barcode",
    tags=["数据操作 - 条形码生成"],
    summary="生成条形码",
    description="生成条形码并返回BASE64格式数据"
)
async def generate_barcode_api(
    content: str = Body(..., description="条形码内容"),
    barcode_type: Optional[str] = Body("code128", description="条形码类型"),
    width: Optional[int] = Body(500, ge=50, description="条形码宽度(像素)", examples=[200]),
    height: Optional[int] = Body(150, ge=30, description="条形码高度(像素)", examples=[100]),
    margin: Optional[int] = Body(20, ge=0, description="条形码边距(像素)", examples=[10]),
    font_size: Optional[int] = Body(14, ge=6, description="条形码文字大小", examples=[10]),
    add_text: Optional[bool] = Body(True, description="是否在条形码下方添加文字"),
    fill_color: Optional[str] = Body("#000000", pattern="^#[0-9A-Fa-f]{6}$", description="条形码颜色"),
    back_color: Optional[str] = Body("#FFFFFF", pattern="^#[0-9A-Fa-f]{6}$", description="条形码背景颜色"),
    image_format: Optional[str] = Body("SVG", pattern="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(20, ge=8, description="内容文字大小"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        result = generate_barcode(
            content=content,
            barcode_type=barcode_type,
            width=width,
            height=height,
            margin=margin,
            font_size=font_size,
            add_text=add_text,
            fill_color=fill_color,
            back_color=back_color,
            image_format=image_format,
            show_content=show_content,
            content_font_size=content_font_size,
            output_type="BASE64"
        )
        return standard_response(
            data={
                "base64": result["base64"],
                "content": content,
                "barcode_type": barcode_type,
                "image_format": image_format
            }
        )

    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"条形码生成失败: {str(e)}"
        )


@rt.post("/check/bom",
    tags=["数据操作 - 校验BOM"],
    summary="校验BOM",
    description="校验传入的 BOM excel，结果输出至 新的 excel 文件"
)
async def check_bom_excel(
    file: UploadFile = File(..., description="BOM excel 文件，必须为 xlsx 格式"),
    parentversion_col: str = Query(None, example="MatVer", description="版本号"),
    parent_col: str = Query(..., example="ProductNo", description="父料号"),
    child_col: str = Query(..., example="MaterialNo", description="子料号"),
    numerator_col: str = Query(..., example="Qty", description="数量"),
    denominator_col: str = Query(None, example=None, description="分母"),
    parentunit_col: str = Query(None, example=None, description="父单位"),
    childunit_col: str = Query(None, example=None, description="子单位"),
    x_api_key: str = Header(None, description="API密钥")
):

    try:
        # 验证文件格式是否为 xlsx
        if not file.filename.lower().endswith('.xlsx'):
            return standard_response(
                status_code=400,
                success=0,
                message="文件格式错误：请上传 xlsx 格式的 Excel 文件"
            )
        bom_df = pd.read_excel(file.file)
        checker = BOMChecker(
            numerator_col=numerator_col,
            denominator_col=denominator_col,
            parent_col=parent_col,
            child_col=child_col,
            parentversion_col=parentversion_col,
            parentunit_col=parentunit_col,
            childunit_col=childunit_col,
            # dtofield_mapper=dtofield_mapper,
        )
        checker.start_check(bom_df)
        return checker.export_results_as_excel()
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )


@rt.get("/tools", tags=["数据操作 - 校验工具页面"])
async def bom_check_page():
    """
    校验工具页面
    提供用户友好的Web界面来上传Excel文件并进行BOM和工序数据校验
    """
    html_path = os.path.join(BASE_DIR, "static", "tools.html")
    if os.path.exists(html_path):
        html_content = open(html_path, 'r', encoding='utf-8').read()
        status_code = 200
    else:
        html_content = """
        <html>
            <body>
                <h1>BOM校验页面未找到</h1>
                <p>请确保static/tools.html文件存在</p>
                <a href="/">返回首页</a>
            </body>
        </html>
        """
        status_code = 404
    return HTMLResponse(content=html_content, status_code=status_code)


@rt.get("/check/bom",
    tags=["数据操作 - 校验BOM"],
    summary="获取校验BOM结果",
    description="校验三方系统的BOM，结果输出至 excel 文件 或 HAP"
)
async def get_bom_check_result_api(
    output_method: str = Query(..., example="EXCEL", enum=["EXCEL", "HAP"], description="输出方式"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        bom_json_data = await project_client.ScheduleTasks.get_bom()

        mainfield_mapper = {
            "id": None,
            "pn": "matnr",   # 产品料号
            "pu": "bmein",   # 产品单位
            "cn": "idnrk",   # 物料料号
            "cu": "meins",   # 物料单位
            "n": "menge",   # 数量
            "d": "bmeng",   # 分母
            "pv": "stlal"      # 产品版本号
        }

        dtofield_mapper = {
            "productno": "matnr",
            "materialno": "idnrk",
            "matver": "stlal",
        }

        checker = BOMChecker(
            mainfield_mapper=mainfield_mapper,
            dtofield_mapper=dtofield_mapper,
        )

        checker.start_check(bom_json_data)

        output_method = output_method.strip().upper()
        if output_method == "EXCEL":
            return checker.export_results_as_excel()
        elif output_method == "HAP":
            if hap_conn is None:
                return standard_response(
                    status_code=500,
                    success=0,
                    message="HAP 配置未完成，无法连接"
                )
            return standard_response(**checker.output_results_to_hap(hap_conn))
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"BOM校验失败: {str(e)}"
        )


@rt.post("/check/route",
    tags=["数据操作 - 校验工艺路线"],
    summary="校验工艺路线问题",
    description="校验传入的 工艺路线 excel，返回问题列表"
)
def check_route_excel(
    file: UploadFile = File(..., description="工艺路线 excel 文件，必须为 xlsx 格式"),
    product_col: str = Query(..., example="MaterialNo", description="产品料号"),
    productversion_col: str = Query(None, example="MatVer", description="产品版本号"),
    sortno_col: str = Query(..., example="SortNo", description="顺序号"),
    itemno_col: str = Query(..., example="ItemNo", description="工序项"),
    workcenter_col: str = Query(None, example="WorkCenter", description="工作中心"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        # 验证文件格式是否为 xlsx
        if not file.filename.lower().endswith('.xlsx'):
            return standard_response(
                status_code=400,
                success=0,
                message="文件格式错误：请上传 xlsx 格式的 Excel 文件"
            )
        route_df = pd.read_excel(file.file)
        checker = RouteChecker(
            product_col=product_col,
            productversion_col=productversion_col,
            sortno_col=sortno_col,
            itemno_col=itemno_col,
            workcenter_col=workcenter_col,
        )
        checker.start_check(route_df)
        return checker.export_results_as_excel()
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )