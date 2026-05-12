"""
数据清洗API路由
提供缓冲表数据接收、校验、审批、同步等接口
"""
from typing import List, Dict, Optional, Literal
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Body, HTTPException, status, Request, UploadFile, File

from apps.data_opt.staging_models import (
    StagingStatus, STAGING_MODEL_MAPPING,
    TMaterialStaging, TWorkcenterStaging, TMatVerStaging,
    TMatWcStaging, TMatWcBomStaging, TMoldStaging, TMatWcMoldStaging,
    ValidationError, TransformRule
)
from apps.data_opt.staging_cleaner import StagingProcessor, DataTransformer
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_bupsert
from core.settings import MYAPS_MAIN_DB, THIS_DB_NAME
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

rt = APIRouter(prefix="/mds", tags=["数据清洗"])


def ensure_timezone_aware(dt: datetime) -> datetime:
    """确保datetime对象是时区感知的"""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def insert_to_staging_table(
    model_class,
    table_name: str,
    data_list: List[Dict],
    source_system: str,
    exclude_fields: List[str] = None
) -> int:
    """
    通用缓冲表SQL插入函数
    
    Args:
        model_class: Tortoise ORM 模型类
        table_name: 目标表名
        data_list: 数据列表（字段名使用小写格式，如materialno）
        source_system: 来源系统
        exclude_fields: 排除的字段列表（如 datetime 字段）
    
    Returns:
        插入记录数
    """
    from tortoise import Tortoise
    
    if exclude_fields is None:
        exclude_fields = ['_createtime', '_updatetime', 'sys_date', 'sys_stamp', 'sys_date']
    
    conn = Tortoise.get_connection(THIS_DB_NAME)
    
    # 获取字段映射：Python字段名(小写) -> 数据库字段名(大驼峰)
    field_map = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        field_map[field.model_field_name] = db_col_name
    
    count = 0
    for item in data_list:
        columns = ["_source_system", "_status"]
        values = [source_system, "pending"]
        
        for key, value in item.items():
            if value is not None and key not in exclude_fields:
                # key是传入的小写字段名，通过field_map映射到数据库字段名
                db_column = field_map.get(key, key)
                columns.append(db_column)
                values.append(value)
        
        placeholders = ", ".join(["$" + str(i+1) for i in range(len(values))])
        column_list = ", ".join([f'"{col}"' for col in columns])
        
        query = f'INSERT INTO "{table_name}" ({column_list}) VALUES ({placeholders})'
        
        await conn.execute_query(query, tuple(values))
        count += 1
    
    return count


# APS系统内部使用字段，不对外暴露
INTERNAL_FIELDS = {'memo', 'sys_user', 'sys_date', 'sys_stamp'}


def convert_record_to_lowercase(record_dict: Dict, model_class) -> Dict:
    """
    将记录的字段名从数据库格式(大驼峰)转换为API格式(小写)
    同时过滤掉APS系统内部使用的字段
    
    Args:
        record_dict: 记录字典
        model_class: 模型类
    
    Returns:
        转换后的字典（字段名为小写，已过滤内部字段）
    """
    # 构建反向映射：数据库字段名 -> Python字段名(小写)
    reverse_field_map = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        reverse_field_map[db_col_name] = field.model_field_name
    
    result = {}
    for key, value in record_dict.items():
        # 将数据库字段名转换为Python字段名(小写)
        python_field = reverse_field_map.get(key, key)
        # 过滤掉内部使用字段
        if python_field in INTERNAL_FIELDS:
            continue
        result[python_field] = value
    
    return result


@rt.post("/t_material", summary="接收物料数据到缓冲表")
async def staging_material(
    request: Request,
    data: List[Dict] = Body(..., description="物料数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的物料数据，写入缓冲表"""
    try:
        count = await insert_to_staging_table(
            TMaterialStaging, "t_material_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条物料数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收物料数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_workcenter", summary="接收工作中心数据到缓冲表")
async def staging_workcenter(
    request: Request,
    data: List[Dict] = Body(..., description="工作中心数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的工作中心数据"""
    try:
        count = await insert_to_staging_table(
            TWorkcenterStaging, "t_workcenter_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条工作中心数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收工作中心数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_mat_ver", summary="接收产线版本数据到缓冲表")
async def staging_mat_ver(
    request: Request,
    data: List[Dict] = Body(..., description="产线版本数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的产线版本数据"""
    try:
        count = await insert_to_staging_table(
            TMatVerStaging, "t_mat_ver_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条产线版本数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收产线版本数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_mat_wc", summary="接收工艺路线数据到缓冲表")
async def staging_mat_wc(
    request: Request,
    data: List[Dict] = Body(..., description="工艺路线数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的工艺路线数据"""
    try:
        count = await insert_to_staging_table(
            TMatWcStaging, "t_mat_wc_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条工艺路线数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收工艺路线数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_mat_wc_bom", summary="接收BOM数据到缓冲表")
async def staging_mat_wc_bom(
    request: Request,
    data: List[Dict] = Body(..., description="BOM数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的BOM数据"""
    try:
        count = await insert_to_staging_table(
            TMatWcBomStaging, "t_mat_wc_bom_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条BOM数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收BOM数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_mold", summary="接收模具数据到缓冲表")
async def staging_mold(
    request: Request,
    data: List[Dict] = Body(..., description="模具数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的模具数据"""
    try:
        count = await insert_to_staging_table(
            TMoldStaging, "t_mold_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条模具数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收模具数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/t_mat_wc_mold", summary="接收机台模具关联数据到缓冲表")
async def staging_mat_wc_mold(
    request: Request,
    data: List[Dict] = Body(..., description="机台模具关联数据列表"),
    source_system: str = Query("unknown", description="来源系统"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """接收外部系统的机台模具关联数据"""
    try:
        count = await insert_to_staging_table(
            TMatWcMoldStaging, "t_mat_wc_mold_staging", data, source_system
        )
        return standard_response(
            success=1,
            message=f"成功接收 {count} 条机台模具关联数据到缓冲表",
            data={"count": count}
        )
    except Exception as e:
        import traceback
        logger.error(f"接收机台模具关联数据失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.post("/validate/{table_name}", summary="校验缓冲表数据")
async def validate_staging(
    request: Request,
    table_name: str,
    batch_size: int = Query(100, description="每批处理数量"),
    db_name: str = Query(THIS_DB_NAME, description="账套")
):
    """校验指定缓冲表中的待处理数据"""
    try:
        processor = StagingProcessor(db_name)
        stats = await processor.process_staging(table_name, batch_size)
        
        return standard_response(
            success=1,
            message=f"校验完成",
            data=stats
        )
    except Exception as e:
        logger.error(f"校验失败 [{table_name}]: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/validate_all", summary="校验所有缓冲表数据")
async def validate_all_staging(
    request: Request,
    batch_size: int = Query(100, description="每批处理数量"),
    db_name: str = Query(THIS_DB_NAME, description="账套")
):
    """按依赖顺序校验所有缓冲表数据"""
    table_order = [
        "t_material",
        "t_workcenter",
        "t_mold",
        "t_mat_ver",
        "t_mat_wc",
        "t_mat_wc_bom",
        "t_mat_wc_mold",
    ]
    
    try:
        processor = StagingProcessor(db_name)
        all_stats = {}
        
        for table_name in table_order:
            stats = await processor.process_staging(table_name, batch_size)
            all_stats[table_name] = stats
        
        return standard_response(
            success=1,
            message="所有缓冲表校验完成",
            data=all_stats
        )
    except Exception as e:
        logger.error(f"批量校验失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/sync/{table_name}", summary="同步缓冲表数据到正式表")
async def sync_to_production(
    request: Request,
    table_name: str,
    batch_size: int = Query(100, description="每批同步数量"),
    max_retries: int = Query(3, description="最大重试次数"),
    db_name: str = Query(THIS_DB_NAME, description="账套")
):
    """将校验通过的缓冲表数据同步到正式表"""
    try:
        processor = StagingProcessor(db_name)
        stats = await processor.sync_to_production(table_name, batch_size, max_retries)
        
        return standard_response(
            success=1,
            message=f"同步完成",
            data=stats
        )
    except Exception as e:
        logger.error(f"同步失败 [{table_name}]: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/sync_all", summary="同步所有缓冲表数据到正式表")
async def sync_all_to_production(
    request: Request,
    batch_size: int = Query(100, description="每批同步数量"),
    max_retries: int = Query(3, description="最大重试次数"),
    db_name: str = Query(THIS_DB_NAME, description="账套")
):
    """按依赖顺序同步所有缓冲表数据到正式表"""
    table_order = [
        "t_material",
        "t_workcenter",
        "t_mold",
        "t_mat_ver",
        "t_mat_wc",
        "t_mat_wc_bom",
        "t_mat_wc_mold",
    ]
    
    try:
        processor = StagingProcessor(db_name)
        all_stats = {}
        
        for table_name in table_order:
            stats = await processor.sync_to_production(table_name, batch_size, max_retries)
            all_stats[table_name] = stats
        
        return standard_response(
            success=1,
            message="所有缓冲表同步完成",
            data=all_stats
        )
    except Exception as e:
        logger.error(f"批量同步失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/errors/{table_name}", summary="获取校验错误列表")
async def get_validation_errors(
    request: Request,
    table_name: str,
    staging_id: Optional[int] = Query(None, description="缓冲记录ID"),
    error_type: Optional[str] = Query(None, description="错误类型"),
    limit: int = Query(100, description="返回数量限制")
):
    """查询缓冲表的校验错误记录"""
    try:
        query = ValidationError.filter(staging_table=table_name)
        
        if staging_id:
            query = query.filter(staging_id=staging_id)
        if error_type:
            query = query.filter(error_type=error_type)
        
        errors = await query.order_by("-createtime").limit(limit)
        
        data = [{
            "id": e.id,
            "staging_id": e.staging_id,
            "error_type": e.error_type,
            "error_field": e.error_field,
            "error_value": e.error_value,
            "error_message": e.error_message,
            "suggestion": e.suggestion,
            "createtime": e.createtime.isoformat()
        } for e in errors]
        
        return standard_response(
            success=1,
            message=f"查询到 {len(data)} 条错误记录",
            data=data
        )
    except Exception as e:
        logger.error(f"查询错误记录失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/status/{table_name}", summary="获取缓冲表状态统计")
async def get_staging_status(
    request: Request,
    table_name: str
):
    """获取指定缓冲表的状态统计"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        stats = {}
        for status in StagingStatus:
            count = await staging_model.filter(_status=status).count()
            stats[status.value] = count
        
        stats["total"] = sum(stats.values())
        
        return standard_response(
            success=1,
            message="查询成功",
            data=stats
        )
    except Exception as e:
        logger.error(f"查询状态统计失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.patch("/approve/{table_name}/{staging_id}", summary="审批缓冲表数据")
async def approve_staging(
    request: Request,
    table_name: str,
    staging_id: int,
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """手动审批通过缓冲表记录"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        record = await staging_model.get(_staging_id=staging_id)
        record._status = StagingStatus.APPROVED
        await record.save()
        
        return standard_response(success=1, message="审批通过")
    except Exception as e:
        logger.error(f"审批失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.patch("/reject/{table_name}/{staging_id}", summary="拒绝缓冲表数据")
async def reject_staging(
    request: Request,
    table_name: str,
    staging_id: int,
    reason: str = Query(..., description="拒绝原因"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """手动拒绝缓冲表记录"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        record = await staging_model.get(_staging_id=staging_id)
        record._status = StagingStatus.REJECTED
        record._error_msg = reason
        await record.save()
        
        return standard_response(success=1, message="已拒绝")
    except Exception as e:
        logger.error(f"拒绝操作失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.delete("/clear/{table_name}", summary="清空缓冲表")
async def clear_staging(
    request: Request,
    table_name: str,
    status_filter: Optional[StagingStatus] = Query(None, description="按状态过滤")
):
    """清空缓冲表数据"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        if status_filter:
            deleted = await staging_model.filter(_status=status_filter).delete()
        else:
            deleted = await staging_model.all().delete()
        
        return standard_response(
            success=1,
            message=f"已删除 {deleted} 条记录"
        )
    except Exception as e:
        logger.error(f"清空缓冲表失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/monitor/summary", summary="获取所有缓冲表监控数据")
async def get_monitor_summary(request: Request):
    """获取所有缓冲表的数据量统计"""
    try:
        from tortoise import Tortoise
        from core.settings import THIS_DB_NAME
        
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        tables = [
            "t_material_staging",
            "t_workcenter_staging",
            "t_mat_ver_staging",
            "t_mat_wc_staging",
            "t_mat_wc_bom_staging",
            "t_mold_staging",
            "t_mat_wc_mold_staging",
        ]
        
        summary = []
        for table in tables:
            query = f'''
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE "_status" = 'pending') as pending,
                    COUNT(*) FILTER (WHERE "_status" = 'validated') as validated,
                    COUNT(*) FILTER (WHERE "_status" = 'rejected') as rejected,
                    COUNT(*) FILTER (WHERE "_status" = 'synced') as synced,
                    MAX("_createtime") as last_created,
                    MAX("_synced_time") as last_synced
                FROM "{table}"
            '''
            result = await conn.execute_query(query)
            row = result[1][0] if result[1] else {}
            
            summary.append({
                "table": table,
                "total": row.get("total", 0),
                "pending": row.get("pending", 0),
                "validated": row.get("validated", 0),
                "rejected": row.get("rejected", 0),
                "synced": row.get("synced", 0),
                "last_created": row.get("last_created").isoformat() if row.get("last_created") else None,
                "last_synced": row.get("last_synced").isoformat() if row.get("last_synced") else None,
            })
        
        return standard_response(
            success=1,
            message="查询成功",
            data=summary
        )
    except Exception as e:
        logger.error(f"获取监控数据失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/cleanup/old_data", summary="清理历史数据")
async def cleanup_old_data(
    request: Request,
    days: int = Query(30, description="保留最近N天的数据"),
    status_filter: Optional[StagingStatus] = Query(StagingStatus.SYNCED, description="清理的状态类型"),
    dry_run: bool = Query(True, description="仅统计不删除")
):
    """清理已同步的历史数据"""
    try:
        from tortoise import Tortoise
        from datetime import timedelta
        from core.settings import THIS_DB_NAME
        
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        tables = [
            "t_material_staging",
            "t_workcenter_staging",
            "t_mat_ver_staging",
            "t_mat_wc_staging",
            "t_mat_wc_bom_staging",
            "t_mold_staging",
            "t_mat_wc_mold_staging",
        ]
        
        results = []
        for table in tables:
            count_query = f'''
                SELECT COUNT(*) as cnt FROM "{table}"
                WHERE "_status" = $1 AND "_synced_time" < $2
            '''
            result = await conn.execute_query(count_query, (status_filter.value, cutoff_date))
            count = result[1][0]['cnt'] if result[1] else 0
            
            if not dry_run and count > 0:
                delete_query = f'''
                    DELETE FROM "{table}"
                    WHERE "_status" = $1 AND "_synced_time" < $2
                '''
                await conn.execute_query(delete_query, (status_filter.value, cutoff_date))
            
            results.append({
                "table": table,
                "would_delete": count,
                "deleted": count if not dry_run else 0
            })
        
        return standard_response(
            success=1,
            message=f"{'统计完成（未删除）' if dry_run else '清理完成'}",
            data={
                "cutoff_date": cutoff_date.isoformat(),
                "dry_run": dry_run,
                "tables": results
            }
        )
    except Exception as e:
        logger.error(f"清理历史数据失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/retry_failed/{table_name}", summary="重试失败的记录")
async def retry_failed_records(
    request: Request,
    table_name: str,
    max_retry: int = Query(3, description="最大重试次数"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """重试同步失败的记录"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        records = await staging_model.filter(
            _status=StagingStatus.REJECTED,
            _retry_count__lt=max_retry
        )
        
        reset_count = 0
        for record in records:
            record._status = StagingStatus.VALIDATED
            record._retry_count = 0
            record._error_msg = None
            await record.save()
            reset_count += 1
        
        return standard_response(
            success=1,
            message=f"已重置 {reset_count} 条失败记录待重试",
            data={"reset_count": reset_count}
        )
    except Exception as e:
        logger.error(f"重试失败记录失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/upload/{table_name}", summary="Excel文件上传")
async def upload_excel(
    request: Request,
    table_name: str,
    file: UploadFile = File(..., description="Excel文件"),
    source_system: str = Query("excel", description="来源系统"),
    dedup_strategy: str = Query("skip", description="去重策略: overwrite/skip/reject"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """上传Excel文件并导入缓冲表，支持去重"""
    try:
        from apps.data_opt.utils.excel_parser import get_parser_for_table
        from apps.data_opt.utils.duplicate_checker import apply_dedup_strategy, DedupStrategy
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        file_bytes = await file.read()
        parser = get_parser_for_table(table_name)
        data_list, parse_errors = parser.parse(file_bytes)
        
        if parse_errors and not data_list:
            return standard_response(
                success=0,
                message="Excel解析失败",
                data={"errors": parse_errors[:10]}
            )
        
        strategy = DedupStrategy(dedup_strategy)
        processed_data, handled_data = await apply_dedup_strategy(
            table_name, data_list, strategy
        )
        
        table_name_staging = f"{table_name}_staging"
        inserted_count = 0
        if processed_data:
            inserted_count = await insert_to_staging_table(
                staging_model, table_name_staging, processed_data, source_system
            )
        
        return standard_response(
            success=1,
            message=f"Excel导入完成: 成功{inserted_count}条, 跳过{len(handled_data)}条",
            data={
                "total": len(data_list),
                "inserted": inserted_count,
                "skipped": len(handled_data),
                "parse_errors": len(parse_errors),
                "handled_details": handled_data[:20]
            }
        )
    except Exception as e:
        import traceback
        logger.error(f"Excel上传失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@rt.get("/list/{table_name}", summary="查询缓冲表列表")
async def list_staging(
    request: Request,
    table_name: str,
    _status: Optional[str] = Query(None, description="状态筛选"),
    source_system: Optional[str] = Query(None, description="来源系统"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    advanced_filters: Optional[str] = Query(None, description="精准筛选条件JSON"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(20, description="每页数量"),
    sort_field: str = Query("_createtime", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向: asc/desc")
):
    """分页查询缓冲表数据"""
    try:
        from tortoise import Tortoise
        import json
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        conditions = []
        params = []
        param_idx = 1
        
        if _status:
            conditions.append(f'"_status" = ${param_idx}')
            params.append(_status)
            param_idx += 1
        
        if source_system:
            conditions.append(f'"_source_system" = ${param_idx}')
            params.append(source_system)
            param_idx += 1
        
        if keyword:
            conditions.append(f'("MaterialNo" LIKE ${param_idx} OR "Description" LIKE ${param_idx})')
            params.append(f"%{keyword}%")
            param_idx += 1
        
        if advanced_filters:
            try:
                filters = json.loads(advanced_filters)
                for f in filters:
                    field = f.get('field')
                    operator = f.get('operator')
                    value = f.get('value')
                    
                    if not field:
                        continue
                    
                    if operator == 'null':
                        conditions.append(f'"{field}" IS NULL')
                    elif operator == 'not_null':
                        conditions.append(f'"{field}" IS NOT NULL')
                    elif operator == 'eq' and value:
                        conditions.append(f'"{field}" = ${param_idx}')
                        params.append(value)
                        param_idx += 1
                    elif operator == 'ne' and value:
                        conditions.append(f'"{field}" != ${param_idx}')
                        params.append(value)
                        param_idx += 1
                    elif operator == 'gt' and value:
                        conditions.append(f'"{field}" > ${param_idx}')
                        params.append(float(value))
                        param_idx += 1
                    elif operator == 'gte' and value:
                        conditions.append(f'"{field}" >= ${param_idx}')
                        params.append(float(value))
                        param_idx += 1
                    elif operator == 'lt' and value:
                        conditions.append(f'"{field}" < ${param_idx}')
                        params.append(float(value))
                        param_idx += 1
                    elif operator == 'lte' and value:
                        conditions.append(f'"{field}" <= ${param_idx}')
                        params.append(float(value))
                        param_idx += 1
                    elif operator == 'like' and value:
                        conditions.append(f'"{field}" LIKE ${param_idx}')
                        params.append(f"%{value}%")
                        param_idx += 1
                    elif operator == 'not_like' and value:
                        conditions.append(f'"{field}" NOT LIKE ${param_idx}')
                        params.append(f"%{value}%")
                        param_idx += 1
                    elif operator == 'starts' and value:
                        conditions.append(f'"{field}" LIKE ${param_idx}')
                        params.append(f"{value}%")
                        param_idx += 1
                    elif operator == 'ends' and value:
                        conditions.append(f'"{field}" LIKE ${param_idx}')
                        params.append(f"%{value}")
                        param_idx += 1
            except Exception as e:
                logger.warning(f"解析精准筛选条件失败: {e}")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        count_query = f'SELECT COUNT(*) as cnt FROM "{table_name_staging}" {where_clause}'
        count_result = await conn.execute_query(count_query, tuple(params) if params else None)
        total = count_result[1][0]['cnt'] if count_result[1] else 0
        
        offset = (page - 1) * page_size
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        
        sort_field_mapping = {
            '_createtime': '_createtime',
            '_updatetime': '_updatetime',
            'materialno': 'MaterialNo'
        }
        db_sort_field = sort_field_mapping.get(sort_field, sort_field)
        
        data_query = f'''
            SELECT * FROM "{table_name_staging}"
            {where_clause}
            ORDER BY "{db_sort_field}" {sort_direction}
            LIMIT {page_size} OFFSET {offset}
        '''
        data_result = await conn.execute_query(data_query, tuple(params) if params else None)
        raw_records = data_result[1] if data_result[1] else []
        
        records = []
        for record in raw_records:
            record_dict = dict(record)
            # 转换字段名为小写
            record_dict = convert_record_to_lowercase(record_dict, staging_model)
            for key, value in record_dict.items():
                if isinstance(value, datetime):
                    record_dict[key] = value.isoformat()
            records.append(record_dict)
        
        return standard_response(
            success=1,
            message=f"查询成功，共{total}条",
            data={
                "total": total,
                "page": page,
                "page_size": page_size,
                "records": records
            }
        )
    except Exception as e:
        logger.error(f"查询列表失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/batch_update/{table_name}", summary="批量更新记录")
async def batch_update_staging(
    request: Request,
    table_name: str,
    data: dict = Body(...)
):
    """批量更新缓冲表记录"""
    try:
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        ids = data.get('ids', [])
        updates = data.get('updates', {})
        
        if not ids or not updates:
            raise ValueError("缺少必要参数: ids或updates")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        field_mapping = {}
        for field in staging_model._meta.fields_map.values():
            db_col_name = field.source_field if field.source_field else field.model_field_name
            field_mapping[field.model_field_name] = db_col_name
        
        set_clauses = []
        params = []
        param_idx = 1
        
        for python_field, value in updates.items():
            db_field = field_mapping.get(python_field, python_field)
            if value is None:
                set_clauses.append(f'"{db_field}" = NULL')
            else:
                set_clauses.append(f'"{db_field}" = ${param_idx}')
                params.append(value)
                param_idx += 1
        
        params.append(ids)
        
        update_query = f'''
            UPDATE "{table_name_staging}"
            SET {', '.join(set_clauses)}, "_updatetime" = NOW(), "_status" = 'pending', "_error_msg" = NULL
            WHERE "_staging_id" = ANY(${param_idx})
        '''
        
        await conn.execute_query(update_query, tuple(params))
        
        return standard_response(
            success=1,
            message=f"成功更新{len(ids)}条记录，状态已重置为待处理"
        )
    except Exception as e:
        logger.error(f"批量更新失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/detail/{table_name}/{staging_id}", summary="查询单条记录")
async def get_staging_detail(
    request: Request,
    table_name: str,
    staging_id: int
):
    """查询单条缓冲表记录详情"""
    try:
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        query = f'SELECT * FROM "{table_name_staging}" WHERE "_staging_id" = $1'
        result = await conn.execute_query(query, (staging_id,))
        
        if not result[1]:
            raise ValueError(f"记录不存在: staging_id={staging_id}")
        
        raw_record = result[1][0]
        record = dict(raw_record)
        # 转换字段名为小写
        record = convert_record_to_lowercase(record, staging_model)
        for key, value in record.items():
            if isinstance(value, datetime):
                record[key] = value.isoformat()
        
        return standard_response(
            success=1,
            message="查询成功",
            data=record
        )
    except Exception as e:
        logger.error(f"查询详情失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.patch("/update/{table_name}/{staging_id}", summary="更新单条记录")
async def update_staging(
    request: Request,
    table_name: str,
    staging_id: int,
    data: Dict = Body(..., description="更新数据"),
    db_name: str = Query(MYAPS_MAIN_DB, description="账套")
):
    """更新单条缓冲表记录"""
    try:
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        field_map = {}
        for field in staging_model._meta.fields_map.values():
            db_col_name = field.source_field if field.source_field else field.model_field_name
            field_map[field.model_field_name] = db_col_name
        
        set_parts = []
        values = []
        param_idx = 1
        
        exclude_fields = ['_staging_id', '_createtime', '_updatetime']
        for key, value in data.items():
            if key not in exclude_fields:
                db_col = field_map.get(key, key)
                if value is None or value == '':
                    set_parts.append(f'"{db_col}" = NULL')
                else:
                    set_parts.append(f'"{db_col}" = ${param_idx}')
                    values.append(value)
                    param_idx += 1
        
        if not set_parts:
            raise ValueError("没有可更新的字段")
        
        set_parts.append('"_status" = $' + str(param_idx))
        values.append('pending')
        param_idx += 1
        
        set_parts.append('"_error_msg" = NULL')
        
        values.append(staging_id)
        update_query = f'UPDATE "{table_name_staging}" SET {", ".join(set_parts)}, "_updatetime" = NOW() WHERE "_staging_id" = ${param_idx}'
        
        await conn.execute_query(update_query, tuple(values))
        
        return standard_response(success=1, message="更新成功，状态已重置为待处理")
    except Exception as e:
        logger.error(f"更新记录失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.delete("/delete/{table_name}/{staging_id}", summary="删除单条记录")
async def delete_staging(
    request: Request,
    table_name: str,
    staging_id: int
):
    """删除单条缓冲表记录"""
    try:
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        query = f'DELETE FROM "{table_name_staging}" WHERE "_staging_id" = $1'
        await conn.execute_query(query, (staging_id,))
        
        return standard_response(success=1, message="删除成功")
    except Exception as e:
        logger.error(f"删除记录失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.post("/batch_delete/{table_name}", summary="批量删除记录")
async def batch_delete_staging(
    request: Request,
    table_name: str,
    staging_ids: List[int] = Body(..., description="staging_id列表")
):
    """批量删除缓冲表记录"""
    try:
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        if not staging_ids:
            raise ValueError("staging_ids不能为空")
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(THIS_DB_NAME)
        
        placeholders = ", ".join([f"${i+1}" for i in range(len(staging_ids))])
        query = f'DELETE FROM "{table_name_staging}" WHERE "_staging_id" IN ({placeholders})'
        
        await conn.execute_query(query, tuple(staging_ids))
        
        return standard_response(
            success=1,
            message=f"成功删除 {len(staging_ids)} 条记录"
        )
    except Exception as e:
        logger.error(f"批量删除失败: {str(e)}")
        return standard_response(success=0, message=str(e))
