#!/usr/bin/env python3
"""
智能自动迁移脚本

功能：
1. 自动备份数据库（安全第一）
2. 自动检测数据库表结构
3. 自动创建缺失的表
4. 自动添加缺失的字段
5. 保留现有数据
6. 无需用户干预，一键完成迁移

使用方法：
    python scripts/migrate/auto_migrate.py
"""

import os
import sys
import asyncio
import shutil
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tortoise import Tortoise


def backup_database(db_path):
    """备份数据库文件"""
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{timestamp}.sqlite3"
    
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ 数据库备份成功: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ 数据库备份失败: {e}")
        return None


async def get_existing_tables(db):
    """获取数据库中已存在的表"""
    result = await db.execute_query("SELECT name FROM sqlite_master WHERE type='table';")
    return {row[0] for row in result}


async def get_existing_columns(db, table_name):
    """获取指定表中已存在的字段"""
    result = await db.execute_query(f"PRAGMA table_info({table_name});")
    return {row[1] for row in result}


async def get_model_fields(model):
    """获取模型定义的字段"""
    return {field_name: field for field_name, field in model._meta.fields_map.items()}


def get_sqlite_type(field):
    """获取字段对应的 SQLite 类型"""
    field_type = type(field).__name__
    
    type_mapping = {
        'IntField': 'INTEGER',
        'BigIntField': 'BIGINT',
        'SmallIntField': 'INTEGER',
        'CharField': 'TEXT',
        'TextField': 'TEXT',
        'LongTextField': 'TEXT',
        'FloatField': 'REAL',
        'DecimalField': 'REAL',
        'DatetimeField': 'TIMESTAMP',
        'DateField': 'DATE',
        'TimeField': 'TIME',
        'BooleanField': 'INTEGER',
        'JSONField': 'TEXT',
        'UUIDField': 'TEXT',
        'BinaryField': 'BLOB',
    }
    
    return type_mapping.get(field_type)


def format_sql_value(value):
    """格式化 SQL 值"""
    if value is None:
        return 'NULL'
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)


async def add_missing_columns(db, table_name, model):
    """为指定表添加缺失的字段"""
    existing_columns = await get_existing_columns(db, table_name)
    model_fields = await get_model_fields(model)
    
    added_columns = []
    for field_name, field in model_fields.items():
        if field_name not in existing_columns:
            # 跳过主键字段（应该已经存在）
            if isinstance(field, type) and hasattr(field, 'pk') and field.pk:
                continue
            
            # 生成 ALTER TABLE 语句
            sqlite_type = get_sqlite_type(field)
            if not sqlite_type:
                print(f"  ⚠️  无法识别字段类型: {field_name} ({type(field).__name__})")
                continue
            
            sql = f"ALTER TABLE {table_name} ADD COLUMN {field_name} {sqlite_type}"
            
            # 添加默认值（如果有）
            if hasattr(field, 'default') and field.default is not None and field.default != type(field).NO_DEFAULT:
                if callable(field.default):
                    try:
                        default_val = field.default()
                        if default_val is not None:
                            sql += f" DEFAULT {format_sql_value(default_val)}"
                    except Exception:
                        pass
                else:
                    sql += f" DEFAULT {format_sql_value(field.default)}"
            
            # 如果字段允许为空，添加 NULL
            if hasattr(field, 'null') and field.null:
                sql += " NULL"
            else:
                sql += " NOT NULL"
            
            print(f"  添加字段: {field_name}")
            await db.execute_query(sql)
            added_columns.append(field_name)
    
    return added_columns


async def create_table_if_not_exists(db, model):
    """如果表不存在，创建表"""
    table_name = model._meta.table
    existing_tables = await get_existing_tables(db)
    
    if table_name not in existing_tables:
        print(f"  创建表: {table_name}")
        # 使用 Tortoise 的 schema generator 生成创建表的 SQL
        from tortoise.backends.sqlite.schema_generator import SqliteSchemaGenerator
        generator = SqliteSchemaGenerator(Tortoise.get_connection('default'))
        await generator._create_table(model)
        return True
    return False


async def main():
    print("========================================")
    print("  🚀 智能自动迁移脚本")
    print("========================================")
    print("  正在自动执行数据库迁移...")
    print()
    
    # 获取数据库路径
    from core.settings import SQLITE_FILE
    db_path = Path("storage") / f"{SQLITE_FILE}.sqlite3"
    
    # Step 1: 备份数据库
    print("[Step 1] 备份数据库...")
    backup_path = backup_database(db_path)
    if not backup_path:
        print("  ⚠️  备份失败，继续执行迁移...")
    
    # Step 2: 初始化 Tortoise
    print("\n[Step 2] 连接数据库...")
    from scripts.migrate.migrate_with_tortoise import monitor_orm_config
    
    try:
        await Tortoise.init(config=monitor_orm_config)
        print("  ✅ 数据库连接成功")
    except Exception as e:
        print(f"  ❌ 数据库连接失败: {e}")
        sys.exit(1)
    
    try:
        db = Tortoise.get_connection('default')
        
        # Step 3: 获取所有注册的模型
        from apps.common.monitor.models import APIRequest, OutboundAPIRequest, SystemLog
        models = [APIRequest, OutboundAPIRequest, SystemLog]
        
        print("\n[Step 3] 处理表结构...")
        
        total_tables_created = 0
        total_columns_added = 0
        
        for model in models:
            table_name = model._meta.table
            print(f"\n  处理表: {table_name}")
            
            # 创建表（如果不存在）
            created = await create_table_if_not_exists(db, model)
            if created:
                total_tables_created += 1
                print(f"    ✅ 表已创建")
            else:
                # 添加缺失字段
                added_columns = await add_missing_columns(db, table_name, model)
                if added_columns:
                    total_columns_added += len(added_columns)
                    print(f"    ✅ 添加了 {len(added_columns)} 个字段: {', '.join(added_columns)}")
                else:
                    print(f"    ✅ 字段已完整，无需更新")
        
        # Step 4: 完成
        print("\n========================================")
        print("  ✅ 迁移完成!")
        print("========================================")
        print(f"  结果统计:")
        print(f"    - 创建表: {total_tables_created} 个")
        print(f"    - 添加字段: {total_columns_added} 个")
        if backup_path:
            print(f"    - 备份文件: {backup_path}")
        print("\n  🎉 数据库结构已同步到最新模型定义")
        
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())