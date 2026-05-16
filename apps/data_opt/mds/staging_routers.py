"""
数据清洗API路由
提供缓冲表数据接收、校验、审批、同步等接口
"""
import json
from typing import List, Dict, Optional, Literal
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException, status, Request, UploadFile, File

from ._base import StagingStatus, INTERNAL_FIELDS, EXCLUDE_FIELDS, convert_record_to_lowercase, generate_validation_rules_doc
from .staging_models import (
    TMaterialStaging, TWorkcenterStaging, TMatVerStaging,
    TMatWcStaging, TMatWcBomStaging, TMoldStaging, TMatWcMoldStaging,
    ValidationError, TransformRule
)
from .staging_cleaner import StagingProcessor, DataTransformer, STAGING_TABLE_CONFIG, STAGING_MODEL_MAPPING, ensure_config_initialized
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_bupsert
from core.settings import MYAPS_MAIN_DB, THIS_DB_NAME, MYAPS_DBSET_LIST
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

# ==============================================
# 监控统计字段常量（P1优化）
# ==============================================
MONITOR_STATUS_FIELDS = (
    StagingStatus.PENDING.value,
    StagingStatus.COMPLIANCE_PASS.value,
    StagingStatus.COMPLIANCE_ERROR.value,
    StagingStatus.RELATION_PASS.value,
    StagingStatus.RELATION_ERROR.value,
    StagingStatus.SYNCED.value,
)

MONITOR_TIME_FIELDS = ("last_created", "last_synced")

rt = APIRouter(prefix="/mds", tags=["数据清洗"])


def create_staging_endpoint(table_key: str, config: Dict):
    """创建数据接收路由端点"""
    @rt.post(f"/{table_key}", summary=f"接收{config['display_name']}数据到缓冲表")
    async def staging_endpoint(
        request: Request,
        data: List[Dict] = Body(..., description=f"{config['display_name']}数据列表"),
        source_system: str = Query("unknown", description="来源系统"),
        dedup_strategy: str = Query("overwrite", description="去重策略: overwrite/skip/reject"),
    ):
        """接收外部系统的{config['display_name']}数据，支持去重"""
        try:
            from apps.data_opt.utils.duplicate_checker import apply_dedup_strategy, DedupStrategy
            
            # 应用去重策略
            strategy = DedupStrategy(dedup_strategy)
            processed_data, handled_data = await apply_dedup_strategy(
                table_key, data, strategy
            )
            
            inserted_count = 0
            
            if processed_data:
                # OVERWRITE策略：先删除已存在的记录
                if strategy == DedupStrategy.OVERWRITE:
                    overwrite_records = [h for h in handled_data if h.get("action") == "overwrite"]
                    if overwrite_records:
                        await delete_existing_records(config['model'], config['table_name'], overwrite_records)
                
                inserted_count = await insert_to_staging_table(
                    config['model'], config['table_name'], processed_data, source_system
                )
            
            # 统计
            overwrite_count = len([h for h in handled_data if h.get("action") == "overwrite"])
            skip_count = len(handled_data) - overwrite_count
            
            return standard_response(
                success=1,
                message=f"导入完成: 新增{inserted_count - overwrite_count}条, 覆盖{overwrite_count}条, 跳过{skip_count}条",
                data={
                    "total": len(data),
                    "inserted": inserted_count,
                    "overwritten": overwrite_count,
                    "skipped": skip_count,
                    "handled_details": handled_data[:20]
                }
            )
        except Exception as e:
            import traceback
            logger.error(f"接收{config['display_name']}数据失败: {str(e)}")
            logger.error(traceback.format_exc())
            return standard_response(success=0, message=str(e))
    
    return staging_endpoint


for table_key, config in STAGING_TABLE_CONFIG.items():
    create_staging_endpoint(table_key, config)


async def delete_existing_records(model_class, table_name: str, records: List[Dict]) -> int:
    """
    删除缓冲表中已存在的记录（用于OVERWRITE策略）
    
    Args:
        model_class: Tortoise ORM 模型类
        table_name: 表名
        records: 要删除的记录列表（包含 pk_value）
    
    Returns:
        删除的记录数
    """
    base_table_name = table_name.replace('_staging', '')
    pk_fields = STAGING_TABLE_CONFIG.get(base_table_name, {}).get("business_keys", [])
    
    if not pk_fields:
        return 0
    
    count = 0
    for record in records:
        data = record.get("data", {})
        conditions = {}
        for pk in pk_fields:
            value = data.get(pk)
            if value is not None:
                conditions[pk] = value
        
        if conditions:
            deleted = await model_class.filter(**conditions).delete()
            count += deleted
    
    return count


async def insert_to_staging_table(
    model_class,
    table_name: str,
    data_list: List[Dict],
    source_system: str,
    exclude_fields: List[str] = None
) -> int:
    """
    通用缓冲表UPSERT函数（INSERT ON CONFLICT UPDATE）
    
    Args:
        model_class: Tortoise ORM 模型类
        table_name: 目标表名（如 t_material_staging）
        data_list: 数据列表（字段名使用小写格式，如materialno）
        source_system: 来源系统
        exclude_fields: 排除的字段列表（如 datetime 字段）
    
    Returns:
        插入/更新记录数
    """
    from tortoise import Tortoise
    
    if exclude_fields is None:
        exclude_fields = EXCLUDE_FIELDS
    
    conn = Tortoise.get_connection(THIS_DB_NAME)
    
    # 获取字段映射：Python字段名(小写) -> 数据库字段名(大驼峰)
    field_map = {}
    field_types = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        field_map[field.model_field_name] = db_col_name
        field_types[field.model_field_name] = type(field).__name__
    
    # 获取主键字段（确保配置已初始化）- 用于日志记录
    base_table_name = table_name.replace('_staging', '')
    ensure_config_initialized()
    pk_fields = STAGING_TABLE_CONFIG.get(base_table_name, {}).get("business_keys", [])
    
    count = 0
    skipped_fields = set()
    
    for item in data_list:
        columns = ["_source_system", "_status"]
        values = [source_system, "pending"]
        
        for key, value in item.items():
            if value is not None and key not in exclude_fields:
                if key not in field_map:
                    skipped_fields.add(key)
                    continue
                db_column = field_map.get(key, key)
                columns.append(db_column)
                
                # 类型转换
                field_type = field_types.get(key, '')
                if field_type == 'IntField':
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                elif field_type == 'FloatField':
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        pass
                elif field_type == 'DecimalField':
                    try:
                        from decimal import Decimal
                        value = Decimal(str(value))
                    except:
                        pass
                values.append(value)
        
        placeholders = ", ".join(["$" + str(i+1) for i in range(len(values))])
        column_list = ", ".join([f'"{col}"' for col in columns])
        
        # 缓冲表无唯一约束，去重已在 apply_dedup_strategy 中完成，此处只需简单 INSERT
        query = f'INSERT INTO "{table_name}" ({column_list}) VALUES ({placeholders})'
        all_values = values
        
        await conn.execute_query(query, tuple(all_values))
        count += 1
    
    if skipped_fields:
        logger.warning(f"跳过未知字段: {skipped_fields}")
    
    return count


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
        
        # 添加兼容字段，确保前端可以正确处理
        stats_compat = {
            **stats,
            "validated": stats.get("relation_pass", 0),
            "rejected": (stats.get("relation_error", 0) + stats.get("compliance_error", 0))
        }
        
        return standard_response(
            success=1,
            message=f"校验完成",
            data=stats_compat
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
            # 添加兼容字段
            all_stats[table_name] = {
                **stats,
                "validated": stats.get("relation_pass", 0),
                "rejected": (stats.get("relation_error", 0) + stats.get("compliance_error", 0))
            }
        
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
    mode: str = Query("incremental", description="同步模式: incremental-增量, refresh-刷新"),
    target_dbs: str = Query(None, description="目标账套列表(逗号分隔)"),
    reset_retry: bool = Query(False, description="是否重置重试次数"),
    skip_truncate: bool = Query(False, description="是否跳过清空表(刷新模式分批调用时使用)"),
    db_name: str = Query(THIS_DB_NAME, description="账套")
):
    """将缓冲表数据同步到正式表
    
    Args:
        mode: 
            - incremental: 仅同步校验通过的记录
            - refresh: 清空正式表后同步全部记录
        target_dbs: 目标账套列表，多个用逗号分隔，为空则同步到所有账套
        reset_retry: 是否重置重试次数（将retry_count设为0）
        skip_truncate: 刷新模式分批调用时，后续批次跳过 TRUNCATE
    """
    try:
        from core.settings import MYAPS_DBSET_LIST, MYAPS_MAIN_DB
        from tortoise import Tortoise
        
        # 确定目标账套列表
        if target_dbs:
            target_db_list = [db.strip() for db in target_dbs.split(",") if db.strip()]
        else:
            target_db_list = MYAPS_DBSET_LIST
        
        if not target_db_list:
            raise ValueError("未配置目标账套")
        
        # 重置重试次数
        if reset_retry:
            staging_model = STAGING_MODEL_MAPPING.get(table_name)
            if staging_model:
                conn = Tortoise.get_connection(THIS_DB_NAME)
                staging_table_name = staging_model._meta.db_table
                reset_query = f'UPDATE "{staging_table_name}" SET "_retry_count" = 0 WHERE "_status" = $1'
                await conn.execute_query(reset_query, ("relation_pass",))
                logger.info(f"已重置重试次数: {staging_table_name}")
        
        processor = StagingProcessor(db_name)
        
        # 多账套同步：先同步所有账套，最后统一更新状态
        if len(target_db_list) > 1:
            all_stats = {}
            
            # 第一步：同步到所有账套（不更新状态）
            for target_db in target_db_list:
                stats = await processor.sync_to_production(
                    table_name=table_name,
                    batch_size=batch_size,
                    max_retries=max_retries,
                    mode=mode,
                    target_db=target_db,
                    update_status=False,  # 不更新状态
                    skip_truncate=skip_truncate
                )
                all_stats[target_db] = stats
            
            # 第二步：统一更新缓冲表状态
            all_synced_ids = []
            all_dedup_ids = []
            
            for target_db, db_stats in all_stats.items():
                all_synced_ids.extend(db_stats.get("synced_staging_ids", []))
                all_dedup_ids.extend(db_stats.get("dedup_staging_ids", []))
            
            total_synced = len(all_synced_ids)
            total_failed = sum(s.get("failed", 0) for s in all_stats.values())
            
            if all_synced_ids or all_dedup_ids:
                from tortoise import Tortoise
                
                staging_model = STAGING_MODEL_MAPPING.get(table_name)
                if staging_model:
                    conn = Tortoise.get_connection(THIS_DB_NAME)
                    staging_table_name = staging_model._meta.db_table
                    synced_time = datetime.now()
                    
                    # 更新成功同步的记录
                    if all_synced_ids:
                        update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_synced_time" = $2 WHERE "_staging_id" = ANY($3)'
                        await conn.execute_query(update_query, ("synced", synced_time, all_synced_ids))
                        logger.info(f"已更新成功记录状态: {len(all_synced_ids)}条")
                    
                    # 更新去重失败的记录
                    if all_dedup_ids:
                        for staging_id in all_dedup_ids:
                            error_json = json.dumps([{
                                "staging_id": staging_id,
                                "error_type": "duplicate_key",
                                "error_field": None,
                                "error_value": None,
                                "error_message": f"数据重复：存在相同主键的记录，被去重丢弃"
                            }], ensure_ascii=False)
                            update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                            await conn.execute_query(update_query, ("relation_error", error_json, staging_id))
                        logger.info(f"已更新去重失败记录状态: {len(all_dedup_ids)}条")
                    
                    logger.info(f"同步完成: {staging_table_name}, 成功{len(all_synced_ids)}条, 去重失败{len(all_dedup_ids)}条, 其他失败{total_failed}条")
        else:
            # 单账套：同步后立即更新状态
            all_stats = {}
            for target_db in target_db_list:
                stats = await processor.sync_to_production(
                    table_name=table_name,
                    batch_size=batch_size,
                    max_retries=max_retries,
                    mode=mode,
                    target_db=target_db,
                    update_status=True,  # 立即更新状态
                    skip_truncate=skip_truncate
                )
                all_stats[target_db] = stats
        
        # 汇总统计
        total_synced = sum(len(s.get("synced_staging_ids", [])) for s in all_stats.values())
        total_failed = sum(s.get("failed") or 0 for s in all_stats.values())
        total_skipped = sum(s.get("skipped") or 0 for s in all_stats.values())
        total_dedup = sum(len(s.get("dedup_staging_ids", [])) for s in all_stats.values())
        
        # 将details转为数组格式
        details_list = [
            {
                "target_db": db_name,
                "synced": len(stats.get("synced_staging_ids", [])),
                "failed": stats.get("failed") or 0,
                "skipped": stats.get("skipped") or 0,
                "dedup": len(stats.get("dedup_staging_ids", []))
            }
            for db_name, stats in all_stats.items()
        ]
        
        return standard_response(
            success=1,
            message=f"同步完成: {len(target_db_list)}个账套, 成功{total_synced}条, 去重失败{total_dedup}条, 其他失败{total_failed}条",
            data={
                "target_dbs": target_db_list,
                "total_synced": total_synced,
                "total_failed": total_failed,
                "total_skipped": total_skipped,
                "total_dedup": total_dedup,
                "details": details_list
            }
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


@rt.get("/rules/{table_key}", summary="获取表的校验规则文档")
async def get_validation_rules(
    request: Request,
    table_key: str
):
    """获取指定表的完整校验规则文档"""
    try:
        config = STAGING_TABLE_CONFIG.get(table_key)
        if not config:
            raise ValueError(f"未知的表: {table_key}")
        
        rules_doc = generate_validation_rules_doc(table_key, config)
        
        return standard_response(
            success=1,
            message="查询成功",
            data=rules_doc
        )
    except Exception as e:
        logger.error(f"查询校验规则失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/rules/list", summary="获取所有表的校验规则列表")
async def get_all_validation_rules():
    """获取所有表的校验规则列表（仅包含表名和表键）"""
    try:
        tables_list = []
        for table_key, config in STAGING_TABLE_CONFIG.items():
            tables_list.append({
                "table_key": table_key,
                "table_name": config.get("display_name", table_key)
            })
        
        return standard_response(
            success=1,
            message="查询成功",
            data=tables_list
        )
    except Exception as e:
        logger.error(f"获取表列表失败: {str(e)}")
        return standard_response(success=0, message=str(e))


@rt.get("/dblist", summary="获取账套列表")
async def get_db_list():
    """获取可用的账套列表"""
    return standard_response(
        success=1,
        message="查询成功",
        data=MYAPS_DBSET_LIST
    )


@rt.get("/status-meta", summary="获取状态元数据")
async def get_status_meta():
    """
    获取所有状态的元数据，包括值、标签、颜色

    Returns:
        List[Dict]: [
            {"value": "pending", "label": "待处理", "color": "warning"},
            ...
        ]
    """
    return standard_response(
        success=1,
        message="查询成功",
        data=[
            {
                "value": status.value,
                "label": status.label,
                "color": status.color
            }
            for status in StagingStatus
        ]
    )


@rt.get("/fk-options/{table_key}/{field_name}", summary="获取外键选项")
async def get_fk_options(
    request: Request,
    table_key: str,
    field_name: str,
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, description="返回数量限制", le=500)
):
    """
    获取指定表指定字段的外键选项（阶段三新增）

    Args:
        table_key: 表键名（如 t_material）
        field_name: 字段名（如 materialno）
        search: 搜索关键词（可选，模糊匹配 label_field）
        limit: 返回数量限制（默认100，最大500）

    Returns:
        [{ "value": "...", "label": "..." }, ...]
    """
    ensure_config_initialized()
    
    config = STAGING_TABLE_CONFIG.get(table_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"表 {table_key} 不存在")

    foreign_keys = config.get("foreign_keys", [])
    fk_config = None
    for fk in foreign_keys:
        if fk.get("field") == field_name:
            fk_config = fk
            break
    
    if not fk_config:
        return standard_response(
            success=1,
            message="无外键配置",
            data=[]
        )
    
    value_field = fk_config.get("value_field")
    label_field = fk_config.get("label_field")
    
    if not value_field or not label_field:
        return standard_response(
            success=1,
            message="外键未配置选项字段",
            data=[]
        )

    model = fk_config["model"]

    query = model.all()
    if search:
        try:
            filter_kwargs = {f"{label_field}__contains": search}
            query = query.filter(**filter_kwargs)
        except Exception as e:
            logger.warning(f"外键选项搜索失败: {e}")

    items = await query.limit(limit)

    return standard_response(
        success=1,
        message=f"查询成功，共{len(items)}条",
        data=[
            {
                "value": getattr(item, value_field),
                "label": getattr(item, label_field) or getattr(item, value_field)
            }
            for item in items
        ]
    )


@rt.get("/status/{table_name}", summary="获取缓冲表状态统计")
async def get_staging_status(
    request: Request,
    table_name: str
):
    """获取指定缓冲表的状态统计"""
    try:
        import sys
        from tortoise import Tortoise
        from core.settings import THIS_DB_NAME
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        # 使用原生SQL查询，确保与同步查询条件一致
        conn = Tortoise.get_connection(THIS_DB_NAME)
        table_name_staging = staging_model._meta.db_table
        
        stats = {}
        for status in StagingStatus:
            count = await staging_model.filter(_status=status).count()
            stats[status.value] = count
        
        stats["total"] = sum(stats.values())
        
        # 额外统计：retry_count >= 3 的记录数
        retry_exceeded_result = await conn.execute_query(
            f'SELECT COUNT(*) as cnt FROM "{table_name_staging}" WHERE "_retry_count" >= $1',
            (3,)
        )
        retry_exceeded = retry_exceeded_result[1][0]["cnt"] if retry_exceeded_result[1] else 0
        stats["retry_exceeded"] = retry_exceeded
        
        return standard_response(
            success=1,
            message="查询成功",
            data=stats
        )
    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        logger.error(f"查询状态统计失败: {error_detail}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=error_detail)


@rt.patch("/approve/{table_name}/{staging_id}", summary="审批缓冲表数据")
async def approve_staging(
    request: Request,
    table_name: str,
    staging_id: int,
    # db_name: str = Query(MYAPS_MAIN_DB, description="账套")  # 未使用，已注释
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
):
    """手动拒绝缓冲表记录"""
    try:
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")
        
        record = await staging_model.get(_staging_id=staging_id)
        record._status = StagingStatus.REJECTED
        error_json = json.dumps([{
            "staging_id": staging_id,
            "error_type": "manual_reject",
            "error_field": None,
            "error_value": None,
            "error_message": reason
        }], ensure_ascii=False)
        record._error_msg = error_json
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
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.PENDING.value}') as {StagingStatus.PENDING.value},
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.COMPLIANCE_PASS.value}') as {StagingStatus.COMPLIANCE_PASS.value},
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.COMPLIANCE_ERROR.value}') as {StagingStatus.COMPLIANCE_ERROR.value},
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.RELATION_PASS.value}') as {StagingStatus.RELATION_PASS.value},
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.RELATION_ERROR.value}') as {StagingStatus.RELATION_ERROR.value},
                    COUNT(*) FILTER (WHERE "_status" = '{StagingStatus.SYNCED.value}') as {StagingStatus.SYNCED.value},
                    MAX("_createtime") as last_created,
                    MAX("_synced_time") as last_synced
                FROM "{table}"
            '''
            result = await conn.execute_query(query)
            row = result[1][0] if result[1] else {}
            
            summary.append({
                "table": table,
                "total": row.get("total", 0),
                StagingStatus.PENDING.value: row.get(StagingStatus.PENDING.value, 0),
                StagingStatus.COMPLIANCE_PASS.value: row.get(StagingStatus.COMPLIANCE_PASS.value, 0),
                StagingStatus.COMPLIANCE_ERROR.value: row.get(StagingStatus.COMPLIANCE_ERROR.value, 0),
                StagingStatus.RELATION_PASS.value: row.get(StagingStatus.RELATION_PASS.value, 0),
                StagingStatus.RELATION_ERROR.value: row.get(StagingStatus.RELATION_ERROR.value, 0),
                StagingStatus.SYNCED.value: row.get(StagingStatus.SYNCED.value, 0),
                MONITOR_TIME_FIELDS[0]: row.get(MONITOR_TIME_FIELDS[0]).isoformat() if row.get(MONITOR_TIME_FIELDS[0]) else None,
                MONITOR_TIME_FIELDS[1]: row.get(MONITOR_TIME_FIELDS[1]).isoformat() if row.get(MONITOR_TIME_FIELDS[1]) else None,
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
    # db_name: str = Query(MYAPS_MAIN_DB, description="账套")  # 未使用，已注释
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
    dedup_strategy: str = Query("overwrite", description="去重策略: overwrite/skip/reject"),
    # db_name: str = Query(MYAPS_MAIN_DB, description="账套")  # 未使用，已注释
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
        data_list, parse_errors = parser.parse(file_bytes, filename=file.filename)
        
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
            # OVERWRITE策略：先删除已存在的记录
            if strategy == DedupStrategy.OVERWRITE:
                overwrite_records = [h for h in handled_data if h.get("action") == "overwrite"]
                if overwrite_records:
                    await delete_existing_records(staging_model, table_name_staging, overwrite_records)
            
            inserted_count = await insert_to_staging_table(
                staging_model, table_name_staging, processed_data, source_system
            )
        
        # 统计覆盖数量
        overwrite_count = len([h for h in handled_data if h.get("action") == "overwrite"])
        skip_count = len(handled_data) - overwrite_count
        
        return standard_response(
            success=1,
            message=f"导入完成: 新增{inserted_count - overwrite_count}条, 覆盖{overwrite_count}条, 跳过{skip_count}条",
            data={
                "total": len(data_list),
                "inserted": inserted_count,
                "overwritten": overwrite_count,
                "skipped": skip_count,
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
        field_types = {}
        for field in staging_model._meta.fields_map.values():
            db_col_name = field.source_field if field.source_field else field.model_field_name
            field_mapping[field.model_field_name] = db_col_name
            field_types[field.model_field_name] = type(field).__name__
        
        set_clauses = []
        params = []
        param_idx = 1
        
        for python_field, value in updates.items():
            db_field = field_mapping.get(python_field, python_field)
            if value is None:
                set_clauses.append(f'"{db_field}" = NULL')
            else:
                field_type = field_types.get(python_field, '')
                if field_type == 'IntField':
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                elif field_type == 'FloatField':
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        pass
                elif field_type == 'DecimalField':
                    try:
                        from decimal import Decimal
                        value = Decimal(str(value))
                    except:
                        pass
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
    # db_name: str = Query(MYAPS_MAIN_DB, description="账套")  # 未使用，已注释
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
        field_types = {}
        for field in staging_model._meta.fields_map.values():
            db_col_name = field.source_field if field.source_field else field.model_field_name
            field_map[field.model_field_name] = db_col_name
            field_types[field.model_field_name] = type(field).__name__
        
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
                    field_type = field_types.get(key, '')
                    if field_type == 'IntField':
                        try:
                            value = int(value)
                        except (ValueError, TypeError):
                            pass
                    elif field_type == 'FloatField':
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            pass
                    elif field_type == 'DecimalField':
                        try:
                            from decimal import Decimal
                            value = Decimal(str(value))
                        except:
                            pass
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
