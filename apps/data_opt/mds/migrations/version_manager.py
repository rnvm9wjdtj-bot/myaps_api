"""
SchemaVersionManager - 迁移版本记录管理
负责记录每次迁移的版本和变更内容
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from tortoise import Tortoise

class SchemaVersionManager:
    """版本管理器"""
    
    VERSION_TABLE = "t_schema_version"
    
    async def ensure_table_exists(self, db_name: str):
        """确保版本表存在"""
        conn = Tortoise.get_connection(db_name)
        await conn.execute_query('''
            CREATE TABLE IF NOT EXISTS t_schema_version (
                id SERIAL PRIMARY KEY,
                version VARCHAR(16) UNIQUE NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                sql_scripts TEXT,
                status VARCHAR(16) DEFAULT 'applied'
            )
        ''')
    
    async def get_applied_versions(self, db_name: str) -> List[str]:
        """获取已应用的版本列表"""
        conn = Tortoise.get_connection(db_name)
        result = await conn.execute_query(
            "SELECT version FROM t_schema_version WHERE status='applied' ORDER BY version"
        )
        return [row[0] for row in result[1]] if result[1] else []
    
    async def get_latest_version(self, db_name: str) -> Optional[str]:
        """获取最新版本号"""
        conn = Tortoise.get_connection(db_name)
        result = await conn.execute_query(
            "SELECT version FROM t_schema_version WHERE status='applied' ORDER BY version DESC LIMIT 1"
        )
        return result[1][0][0] if result[1] else None
    
    async def generate_next_version(self, db_name: str) -> str:
        """生成下一个版本号"""
        latest = await self.get_latest_version(db_name)
        if latest:
            version_num = int(latest.replace('V', '')) + 1
        else:
            version_num = 1
        return f"V{version_num:03d}"
    
    async def record_version(self, db_name: str, version: str, description: str, sql_scripts: str):
        """记录新版本"""
        conn = Tortoise.get_connection(db_name)
        await conn.execute_query(
            """INSERT INTO t_schema_version (version, description, sql_scripts, status)
               VALUES ($1, $2, $3, 'applied')""",
            (version, description, sql_scripts)
        )
    
    async def version_exists(self, db_name: str, version: str) -> bool:
        """检查版本是否已存在"""
        conn = Tortoise.get_connection(db_name)
        result = await conn.execute_query(
            "SELECT COUNT(*) FROM t_schema_version WHERE version = $1",
            (version,)
        )
        return result[1][0][0] > 0
