"""
ORM 模型与数据库表结构差异检测模块
对比 Tortoise ORM 模型定义与实际数据库表结构，生成 ALTER TABLE 语句
"""
from typing import List, Dict, Any, Optional, Tuple
from tortoise import Tortoise
from tortoise.fields import (
    CharField, IntField, FloatField, DecimalField, BooleanField,
    DatetimeField, DateField, TextField, JSONField
)

from core.database import get_db_connection_safely
from core.settings import THIS_DB_NAME
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


class AlterStmt:
    """ALTER TABLE 语句封装"""
    
    def __init__(
        self,
        table_name: str,
        field_name: str,
        db_field_name: str,
        sql_type: str,
        sql_statement: str,
        is_nullable: bool = True,
        default_value: Any = None
    ):
        self.table_name = table_name
        self.field_name = field_name
        self.db_field_name = db_field_name
        self.sql_type = sql_type
        self.sql_statement = sql_statement
        self.is_nullable = is_nullable
        self.default_value = default_value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table_name,
            "field": self.field_name,
            "db_field": self.db_field_name,
            "sql_type": self.sql_type,
            "sql": self.sql_statement,
            "nullable": self.is_nullable,
            "default": self.default_value
        }


class ModelDiffer:
    """
    ORM 模型与数据库表结构差异检测器
    
    检测 Tortoise ORM 模型定义中新增的字段，生成对应的 ALTER TABLE ADD COLUMN 语句
    """
    
    FIELD_TYPE_MAPPING = {
        'CharField': 'VARCHAR',
        'IntField': 'INTEGER',
        'FloatField': 'DOUBLE PRECISION',
        'DecimalField': 'DECIMAL',
        'BooleanField': 'BOOLEAN',
        'DatetimeField': 'TIMESTAMP',
        'DateField': 'DATE',
        'TextField': 'TEXT',
        'JSONField': 'JSONB',
    }
    
    def __init__(self, db_name: str = None):
        """
        初始化差异检测器
        
        Args:
            db_name: 数据库名称，默认使用 THIS_DB_NAME
        """
        self.db_name = db_name or THIS_DB_NAME
    
    async def get_db_columns(self, table_name: str) -> Dict[str, Dict[str, Any]]:
        """
        查询数据库表的字段信息
        
        Args:
            table_name: 表名
            
        Returns:
            字段信息字典 {字段名: {type, nullable, default}}
        """
        conn = await get_db_connection_safely(self.db_name)
        
        query = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_name = $1 AND table_schema = 'public'
            ORDER BY ordinal_position
        """
        
        result = await conn.execute_query(query, (table_name,))
        
        columns = {}
        for row in (result[1] or []):
            col_name = row['column_name']
            columns[col_name] = {
                'type': row['data_type'],
                'nullable': row['is_nullable'] == 'YES',
                'default': row['column_default'],
                'max_length': row['character_maximum_length'],
                'precision': row['numeric_precision'],
                'scale': row['numeric_scale']
            }
        
        return columns
    
    def get_model_fields(self, model_class) -> Dict[str, Any]:
        """
        获取 ORM 模型的字段定义
        
        Args:
            model_class: Tortoise ORM 模型类
            
        Returns:
            字段映射字典 {Python字段名: field对象}
        """
        return dict(model_class._meta.fields_map)
    
    def _map_field_type_to_sql(self, field) -> Tuple[str, str]:
        """
        将 Tortoise ORM 字段类型映射为 SQL 类型
        
        Args:
            field: Tortoise 字段对象
            
        Returns:
            (SQL类型字符串, 完整类型定义字符串)
        """
        field_type_name = type(field).__name__
        
        if field_type_name == 'CharField':
            max_length = getattr(field, 'max_length', 255)
            return 'VARCHAR', f'VARCHAR({max_length})'
        
        elif field_type_name == 'DecimalField':
            precision = getattr(field, 'max_digits', 10)
            scale = getattr(field, 'decimal_places', 2)
            return 'DECIMAL', f'DECIMAL({precision}, {scale})'
        
        elif field_type_name in self.FIELD_TYPE_MAPPING:
            return self.FIELD_TYPE_MAPPING[field_type_name], self.FIELD_TYPE_MAPPING[field_type_name]
        
        else:
            return 'VARCHAR', 'VARCHAR(255)'
    
    def _generate_alter_sql(
        self,
        table_name: str,
        field_name: str,
        field
    ) -> AlterStmt:
        """
        生成 ALTER TABLE ADD COLUMN 语句
        
        Args:
            table_name: 表名
            field_name: Python 字段名
            field: Tortoise 字段对象
            
        Returns:
            AlterStmt 对象
        """
        db_field_name = getattr(field, 'source_field', None) or field_name
        _, sql_type_def = self._map_field_type_to_sql(field)
        
        is_nullable = getattr(field, 'null', True)
        default_value = getattr(field, 'default', None)
        
        has_default = default_value is not None and str(default_value) != 'PydanticUndefined'
        
        parts = [f'ALTER TABLE "{table_name}" ADD COLUMN "{db_field_name}" {sql_type_def}']
        
        if not is_nullable:
            parts.append('NOT NULL')
        
        if has_default:
            if isinstance(default_value, str):
                parts.append(f"DEFAULT '{default_value}'")
            elif isinstance(default_value, bool):
                parts.append(f"DEFAULT {'TRUE' if default_value else 'FALSE'}")
            else:
                parts.append(f'DEFAULT {default_value}')
        
        sql_statement = ' '.join(parts)
        
        return AlterStmt(
            table_name=table_name,
            field_name=field_name,
            db_field_name=db_field_name,
            sql_type=sql_type_def,
            sql_statement=sql_statement,
            is_nullable=is_nullable,
            default_value=default_value if has_default else None
        )
    
    async def table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在于数据库中
        
        Args:
            table_name: 表名
            
        Returns:
            表是否存在
        """
        conn = await get_db_connection_safely(self.db_name)
        
        query = """
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_name = $1 AND table_schema = 'public'
            )
        """
        
        result = await conn.execute_query(query, (table_name,))
        
        if result and result[1]:
            return result[1][0].get('exists', False)
        return False

    def _generate_create_table_sql(self, model_class) -> str:
        """
        生成 CREATE TABLE 语句
        
        Args:
            model_class: Tortoise ORM 模型类
            
        Returns:
            CREATE TABLE SQL 语句
        """
        table_name = model_class._meta.db_table
        model_fields = self.get_model_fields(model_class)
        
        columns = []
        primary_key = None
        
        for field_name, field in model_fields.items():
            db_field_name = getattr(field, 'source_field', None) or field_name
            _, sql_type_def = self._map_field_type_to_sql(field)
            
            is_nullable = getattr(field, 'null', True)
            default_value = getattr(field, 'default', None)
            has_default = default_value is not None and str(default_value) != 'PydanticUndefined'
            
            # 检查主键
            if getattr(field, 'pk', False) or field_name == 'id':
                primary_key = db_field_name
                # 处理主键字段
                if isinstance(field, IntField) and getattr(field, 'generated', False):
                    columns.append(f'"{db_field_name}" SERIAL PRIMARY KEY')
                else:
                    columns.append(f'"{db_field_name}" {sql_type_def} PRIMARY KEY')
                continue
            
            parts = [f'"{db_field_name}" {sql_type_def}']
            
            if not is_nullable:
                parts.append('NOT NULL')
            
            if has_default:
                if isinstance(default_value, str):
                    parts.append(f"DEFAULT '{default_value}'")
                elif isinstance(default_value, bool):
                    parts.append(f"DEFAULT {'TRUE' if default_value else 'FALSE'}")
                else:
                    parts.append(f'DEFAULT {default_value}')
            
            columns.append(' '.join(parts))
        
        # 添加主键约束（如果没有自动主键）
        if primary_key is None and '_staging_id' in [getattr(f, 'source_field', None) or fn for fn, f in model_fields.items()]:
            columns.append(f'PRIMARY KEY ("_staging_id")')
        
        sql_statement = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n    ' + ',\n    '.join(columns) + '\n)'
        
        return sql_statement

    def _load_staging_sql_script(self, table_name: str) -> Optional[str]:
        """
        从 SQL 文件加载指定表的创建脚本
        
        Args:
            table_name: 表名
            
        Returns:
            SQL 脚本内容，如果找不到返回 None
        """
        import os
        from pathlib import Path
        
        # 定位 SQL 文件
        sql_file = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts" / "migrate" / "staging" / "staging_tables.sql"
        
        if not sql_file.exists():
            logger.warning(f"SQL迁移脚本不存在: {sql_file}")
            return None
            
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 SQL 文件，提取指定表的创建脚本
            # SQL 文件结构: 以 "-- =====================================================" 分隔不同表的定义
            sections = content.split('-- =====================================================')
            
            for section in sections:
                # 查找包含 CREATE TABLE 且表名匹配的部分
                if f'CREATE TABLE IF NOT EXISTS {table_name}' in section or f'CREATE TABLE IF NOT EXISTS "{table_name}"' in section:
                    # 提取从 CREATE TABLE 到下一个分隔符或文件结束的内容
                    lines = []
                    in_comment_block = False
                    
                    for line in section.split('\n'):
                        # 跳过空行和注释行，但保留 DO $$ ... END $$ 块内的注释
                        stripped = line.strip()
                        
                        # 处理 DO $$ 块
                        if stripped.startswith('DO $$'):
                            in_comment_block = True
                            lines.append(line)
                            continue
                        if stripped.startswith('END $$;') and in_comment_block:
                            lines.append(line)
                            in_comment_block = False
                            continue
                        if in_comment_block:
                            lines.append(line)
                            continue
                            
                        # 跳过普通注释行
                        if stripped.startswith('--'):
                            continue
                        if not stripped:
                            continue
                            
                        lines.append(line)
                    
                    return '\n'.join(lines)
            
            logger.warning(f"在SQL文件中未找到表 {table_name} 的定义")
            return None
            
        except Exception as e:
            logger.error(f"读取SQL文件失败: {str(e)}")
            return None

    async def diff(self, model_class) -> List[AlterStmt]:
        """
        对比单个模型与数据库表的差异
        
        优化策略：
        - 表不存在时：使用 SQL 文件创建（包含索引、注释、触发器等完整功能）
        - 表已存在时：进行字段差异检测，动态生成 ALTER TABLE 语句
        
        Args:
            model_class: Tortoise ORM 模型类
            
        Returns:
            差异列表（需要新增的字段或表）
        """
        table_name = model_class._meta.db_table
        
        # 检查表是否存在
        if not await self.table_exists(table_name):
            # 如果表不存在，优先使用 SQL 文件
            sql_script = self._load_staging_sql_script(table_name)
            
            if sql_script:
                logger.info(f"检测到表不存在，将使用SQL文件创建: {table_name}")
                create_stmt = AlterStmt(
                    table_name=table_name,
                    field_name='__table__',
                    db_field_name='__table__',
                    sql_type='TABLE',
                    sql_statement=sql_script,
                    is_nullable=False,
                    default_value=None
                )
                return [create_stmt]
            else:
                # SQL 文件不可用，降级到动态生成
                logger.warning(f"SQL文件不可用，将动态生成创建语句: {table_name}")
                create_sql = self._generate_create_table_sql(model_class)
                create_stmt = AlterStmt(
                    table_name=table_name,
                    field_name='__table__',
                    db_field_name='__table__',
                    sql_type='TABLE',
                    sql_statement=create_sql,
                    is_nullable=False,
                    default_value=None
                )
                return [create_stmt]
        
        # 表已存在，检测字段差异
        db_columns = await self.get_db_columns(table_name)
        model_fields = self.get_model_fields(model_class)
        
        differences = []
        
        for field_name, field in model_fields.items():
            if field_name.startswith('_') and field_name not in (
                '_staging_id', '_source_system', '_source_id', '_status',
                '_error_msg', '_transform_rules', '_retry_count',
                '_createtime', '_updatetime', '_synced_id', '_synced_time'
            ):
                continue
            
            db_field_name = getattr(field, 'source_field', None) or field_name
            
            if db_field_name not in db_columns:
                alter_stmt = self._generate_alter_sql(table_name, field_name, field)
                differences.append(alter_stmt)
                logger.debug(f"检测到新字段: {table_name}.{db_field_name}")
        
        return differences
    
    async def diff_all(self, model_mapping: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量检测所有表的差异
        
        Args:
            model_mapping: 模型映射字典 {表键: 模型类}
            
        Returns:
            汇总结果 {
                "differences": [...],
                "total_tables": int,
                "total_fields": int
            }
        """
        all_differences = []
        tables_with_diff = set()
        
        for table_key, model_class in model_mapping.items():
            try:
                diffs = await self.diff(model_class)
                if diffs:
                    tables_with_diff.add(table_key)
                    for diff in diffs:
                        all_differences.append({
                            "table_key": table_key,
                            **diff.to_dict()
                        })
            except Exception as e:
                logger.error(f"检测差异失败 [{table_key}]: {str(e)}")
        
        return {
            "differences": all_differences,
            "total_tables": len(tables_with_diff),
            "total_fields": len(all_differences)
        }
