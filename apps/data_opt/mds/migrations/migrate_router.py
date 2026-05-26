"""
数据库迁移 API 路由
提供差异检测、执行迁移、权限校验等接口
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Query, Body, Request

from pydantic import BaseModel

from .model_diff import ModelDiffer
from apps.data_opt.mds.staging_cleaner import STAGING_MODEL_MAPPING, ensure_config_initialized
from apps.io_api.utils.common import standard_response
from core.database import get_db_connection_safely
from core.settings import THIS_DB_NAME
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

migrate_router = APIRouter(prefix="/migrate", tags=["数据库迁移"])


class ExecuteMigrateRequest(BaseModel):
    """执行迁移请求"""
    tables: List[str] = []
    force: bool = False


async def execute_migration_sql(sql_statement: str, db_name: str) -> bool:
    """
    执行单条 ALTER TABLE 语句
    
    Args:
        sql_statement: SQL 语句
        db_name: 数据库名
        
    Returns:
        是否成功
    """
    try:
        conn = await get_db_connection_safely(db_name)
        await conn.execute_query(sql_statement)
        return True
    except Exception as e:
        logger.error(f"执行迁移失败: {sql_statement}, 错误: {str(e)}")
        return False


@migrate_router.get("/check-permission", summary="校验数据库迁移权限")
async def check_migration_permission(
    request: Request,
    db_name: str = Query(None, description="数据库名称，默认当前账套")
):
    """
    校验当前用户是否有数据库迁移权限
    
    通过尝试执行一个无害的查询来验证数据库连接和权限
    
    Returns:
        {"success": 1, "data": {"has_permission": true/false, "message": "..."}}
    """
    try:
        target_db = db_name or THIS_DB_NAME
        conn = await get_db_connection_safely(target_db)
        
        result = await conn.execute_query("SELECT current_user, current_database()")
        
        if result and result[1]:
            row = result[1][0]
            current_user = row.get('current_user', 'unknown')
            current_db = row.get('current_database', 'unknown')
            
            test_query = """
                SELECT has_schema_privilege(current_user, 'public', 'CREATE') as can_create,
                       has_schema_privilege(current_user, 'public', 'USAGE') as can_usage
            """
            priv_result = await conn.execute_query(test_query)
            
            if priv_result and priv_result[1]:
                priv_row = priv_result[1][0]
                can_create = priv_row.get('can_create', False)
                can_usage = priv_row.get('can_usage', False)
                
                if can_create and can_usage:
                    return standard_response(
                        success=1,
                        message="权限校验通过",
                        data={
                            "has_permission": True,
                            "user": current_user,
                            "database": current_db,
                            "can_create": can_create,
                            "can_usage": can_usage
                        }
                    )
                else:
                    return standard_response(
                        success=1,
                        message="权限不足：需要 CREATE 和 USAGE 权限",
                        data={
                            "has_permission": False,
                            "user": current_user,
                            "database": current_db,
                            "can_create": can_create,
                            "can_usage": can_usage
                        }
                    )
        
        return standard_response(
            success=1,
            message="无法获取权限信息",
            data={"has_permission": False}
        )
        
    except Exception as e:
        import traceback
        logger.error(f"权限校验失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(
            success=1,
            message=f"权限校验异常: {str(e)}",
            data={"has_permission": False, "error": str(e)}
        )


@migrate_router.get("/diff", summary="获取模型与数据库差异")
async def get_migration_diff(
    request: Request,
    db_name: str = Query(None, description="数据库名称，默认当前账套")
):
    """
    检测 ORM 模型与数据库表结构的差异
    
    Returns:
        差异列表、统计信息
    """
    try:
        ensure_config_initialized()
        
        target_db = db_name or THIS_DB_NAME
        differ = ModelDiffer(target_db)
        
        result = await differ.diff_all(STAGING_MODEL_MAPPING)
        
        return standard_response(
            success=1,
            message=f"检测完成，发现 {result['total_fields']} 个待迁移字段",
            data=result
        )
    except Exception as e:
        import traceback
        logger.error(f"差异检测失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@migrate_router.post("/execute", summary="执行数据库迁移")
async def execute_migration(
    request: Request,
    data: ExecuteMigrateRequest = Body(...),
    db_name: str = Query(None, description="数据库名称，默认当前账套")
):
    """
    执行数据库迁移
    
    Args:
        tables: 要迁移的表列表，空数组表示全部
        force: 是否强制执行（跳过幂等检查）
        
    Returns:
        迁移结果
    """
    try:
        ensure_config_initialized()
        
        target_db = db_name or THIS_DB_NAME
        differ = ModelDiffer(target_db)
        
        diff_result = await differ.diff_all(STAGING_MODEL_MAPPING)
        all_differences = diff_result.get("differences", [])
        
        if data.tables:
            all_differences = [
                d for d in all_differences 
                if d.get("table_key") in data.tables
            ]
        
        if not all_differences:
            return standard_response(
                success=1,
                message="无需迁移，模型与数据库一致",
                data={
                    "version": None,
                    "applied_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "changes": []
                }
            )
        
        version = datetime.now().strftime("V%Y%m%d%H%M%S")
        
        applied_count = 0
        failed_count = 0
        changes = []
        
        for diff in all_differences:
            sql = diff.get("sql")
            table = diff.get("table")
            field = diff.get("field")
            db_field = diff.get("db_field")
            
            success = await execute_migration_sql(sql, target_db)
            
            change_record = {
                "table": table,
                "field": field,
                "db_field": db_field,
                "sql": sql,
                "success": success,
                "timestamp": datetime.now().isoformat()
            }
            changes.append(change_record)
            
            if success:
                applied_count += 1
                logger.info(f"迁移成功: {table}.{db_field}")
            else:
                failed_count += 1
                logger.error(f"迁移失败: {table}.{db_field}")
        
        return standard_response(
            success=1 if failed_count == 0 else 0,
            message=f"迁移完成，版本 {version}，成功 {applied_count} 个，失败 {failed_count} 个",
            data={
                "version": version,
                "applied_count": applied_count,
                "failed_count": failed_count,
                "skipped_count": 0,
                "changes": changes
            }
        )
    except Exception as e:
        import traceback
        logger.error(f"执行迁移失败: {str(e)}")
        logger.error(traceback.format_exc())
        return standard_response(success=0, message=str(e))


@migrate_router.get("/versions", summary="获取迁移历史")
async def get_migration_versions(
    request: Request,
    limit: int = Query(20, description="返回数量限制")
):
    """
    获取迁移历史记录（简化版本，返回最近执行的迁移信息）
    
    Note: 完整版本需要 version_manager.py 配合数据库存储
    """
    try:
        return standard_response(
            success=1,
            message="查询成功",
            data={
                "versions": [],
                "note": "完整版本记录需要启用 version_manager"
            }
        )
    except Exception as e:
        logger.error(f"查询迁移历史失败: {str(e)}")
        return standard_response(success=0, message=str(e))
