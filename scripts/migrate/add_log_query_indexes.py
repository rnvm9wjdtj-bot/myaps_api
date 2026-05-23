"""
数据库索引迁移脚本 - 日志查询功能强化
任务ID: T1.1

为支持日志查询功能强化（高级过滤、分页排序），添加以下索引：
1. api_requests: client_ip, method, (timestamp, status_code)
2. outbound_api_requests: method, (timestamp, status_code)
3. system_logs: (timestamp, level)

用法:
    # 执行迁移（创建索引）
    python scripts/migrate/add_log_query_indexes.py --action migrate
    
    # 回滚迁移（删除索引）
    python scripts/migrate/add_log_query_indexes.py --action rollback
    
    # 检查状态
    python scripts/migrate/add_log_query_indexes.py --action status
"""

import asyncio
import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tortoise import Tortoise
from tortoise.backends.sqlite.client import SqliteClient
from globalobjects import logger

INDEX_DEFINITIONS = {
    "api_requests": {
        "idx_api_requests_client_ip": ["client_ip"],
        "idx_api_requests_method": ["method"],
        "idx_api_requests_timestamp_status": ["timestamp", "status_code"],
    },
    "outbound_api_requests": {
        "idx_outbound_method": ["method"],
        "idx_outbound_timestamp_status": ["timestamp", "status_code"],
    },
    "system_logs": {
        "idx_logs_timestamp_level": ["timestamp", "level"],
    },
}


async def get_db_client() -> SqliteClient:
    """获取数据库客户端"""
    from core.settings import SQLITE_FILE
    
    if not Tortoise._inited:
        await Tortoise.init(
            db_url=f"sqlite://{SQLITE_FILE}",
            modules={"models": ["apps.common.monitor.models"]},
        )
    
    return Tortoise.get_connection("default")


async def check_table_exists(client: SqliteClient, table: str) -> bool:
    """检查表是否存在"""
    query = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
    result = await client.execute_query(query)
    return len(result[1]) > 0


async def check_index_exists(client: SqliteClient, table: str, index_name: str) -> bool:
    """检查索引是否存在（SQLite）"""
    if not await check_table_exists(client, table):
        return False
    query = f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}' AND name='{index_name}'"
    result = await client.execute_query(query)
    return len(result[1]) > 0


async def create_index(client: SqliteClient, table: str, index_name: str, columns: list) -> bool:
    """创建索引"""
    try:
        if not await check_table_exists(client, table):
            logger.info(f"表不存在，跳过: {table}")
            return False
        
        if await check_index_exists(client, table, index_name):
            logger.info(f"索引已存在，跳过: {table}.{index_name}")
            return False
        
        cols = ", ".join(columns)
        sql = f"CREATE INDEX {index_name} ON {table} ({cols})"
        await client.execute_query(sql)
        logger.success(f"创建索引成功", f"{table}.{index_name}", f"({cols})")
        return True
    except Exception as e:
        logger.error(f"创建索引失败: {table}.{index_name}", exc_info=True)
        return False


async def drop_index(client: SqliteClient, table: str, index_name: str) -> bool:
    """删除索引"""
    try:
        if not await check_index_exists(client, table, index_name):
            logger.info(f"索引不存在，跳过: {table}.{index_name}")
            return False
        
        sql = f"DROP INDEX {index_name}"
        await client.execute_query(sql)
        logger.success(f"删除索引成功", f"{table}.{index_name}")
        return True
    except Exception as e:
        logger.error(f"删除索引失败: {table}.{index_name}", exc_info=True)
        return False


async def migrate():
    """执行迁移：创建所有索引"""
    logger.start("执行索引迁移", "创建")
    
    client = await get_db_client()
    
    created_count = 0
    skipped_count = 0
    failed_count = 0
    
    for table, indexes in INDEX_DEFINITIONS.items():
        logger.info(f"处理表: {table}")
        for index_name, columns in indexes.items():
            result = await create_index(client, table, index_name, columns)
            if result:
                created_count += 1
            elif await check_index_exists(client, table, index_name):
                skipped_count += 1
            else:
                failed_count += 1
    
    logger.stop("索引迁移完成", f"创建:{created_count} 跳过:{skipped_count} 失败:{failed_count}")
    
    if failed_count > 0:
        logger.error("部分索引创建失败，请检查日志")
        return False
    return True


async def rollback():
    """回滚迁移：删除所有索引"""
    logger.start("执行索引迁移", "回滚")
    
    client = await get_db_client()
    
    dropped_count = 0
    skipped_count = 0
    failed_count = 0
    
    for table, indexes in INDEX_DEFINITIONS.items():
        logger.info(f"处理表: {table}")
        for index_name in indexes.keys():
            result = await drop_index(client, table, index_name)
            if result:
                dropped_count += 1
            elif not await check_index_exists(client, table, index_name):
                skipped_count += 1
            else:
                failed_count += 1
    
    logger.stop("索引回滚完成", f"删除:{dropped_count} 跳过:{skipped_count} 失败:{failed_count}")
    
    if failed_count > 0:
        logger.error("部分索引删除失败，请检查日志")
        return False
    return True


async def status():
    """检查索引状态"""
    logger.info("检查索引状态...")
    
    client = await get_db_client()
    
    print("\n" + "=" * 60)
    print("索引状态报告")
    print("=" * 60)
    
    total_count = 0
    existing_count = 0
    table_not_exists_count = 0
    
    for table, indexes in INDEX_DEFINITIONS.items():
        table_exists = await check_table_exists(client, table)
        print(f"\n表: {table}", "- 存在" if table_exists else "- 不存在")
        print("-" * 40)
        
        if not table_exists:
            table_not_exists_count += len(indexes)
            for index_name, columns in indexes.items():
                print(f"  {index_name:40} ⊘ 表不存在")
            continue
        
        for index_name, columns in indexes.items():
            exists = await check_index_exists(client, table, index_name)
            status_str = "✓ 已创建" if exists else "✗ 未创建"
            print(f"  {index_name:40} {status_str}")
            total_count += 1
            if exists:
                existing_count += 1
    
    print("\n" + "=" * 60)
    print(f"总计: {existing_count}/{total_count} 个索引已创建, {table_not_exists_count} 个索引待表创建")
    print("=" * 60 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="日志查询功能强化 - 索引迁移脚本")
    parser.add_argument(
        "--action",
        choices=["migrate", "rollback", "status"],
        default="status",
        help="操作类型: migrate(创建), rollback(回滚), status(检查)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.action == "migrate":
            success = await migrate()
            sys.exit(0 if success else 1)
        elif args.action == "rollback":
            success = await rollback()
            sys.exit(0 if success else 1)
        elif args.action == "status":
            await status()
            sys.exit(0)
    except Exception as e:
        logger.exception(f"执行失败: {e}")
        sys.exit(1)
    finally:
        if Tortoise._inited:
            await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
