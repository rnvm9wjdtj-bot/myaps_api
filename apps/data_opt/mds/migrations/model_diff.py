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
    
    async def diff(self, model_class) -> List[AlterStmt]:
        """
        对比单个模型与数据库表的差异
        
        Args:
            model_class: Tortoise ORM 模型类
            
        Returns:
            差异列表（需要新增的字段）
        """
        table_name = model_class._meta.db_table
        
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
