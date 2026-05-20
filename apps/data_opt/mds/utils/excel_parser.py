"""
Excel解析工具
支持字段映射、数据校验、去重等功能
"""
import pandas as pd
import json
from io import BytesIO
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


def get_table_field_mappers() -> Dict[str, Dict[str, str]]:
    """
    动态生成所有表的字段映射
    
    Returns:
        {表名: {字段名: 中文名}}
    """
    from apps.data_opt.mds.config_generator import _PAGE_COLUMNS_CONFIG
    
    mappers = {}
    for table_key, columns in _PAGE_COLUMNS_CONFIG.items():
        field_mapper = {}
        for col in columns:
            field = col.get("field")
            title = col.get("title")
            if field and title and not field.startswith("_"):
                field_mapper[field] = title
        if field_mapper:
            mappers[table_key] = field_mapper
    
    return mappers


def get_table_required_fields() -> Dict[str, List[str]]:
    """
    动态生成所有表的必填字段（使用 business_keys）
    
    Returns:
        {表名: [必填字段列表]}
    """
    from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG, ensure_config_initialized
    
    ensure_config_initialized()
    
    required_fields = {}
    for table_key, config in STAGING_TABLE_CONFIG.items():
        business_keys = config.get("business_keys", [])
        if business_keys:
            required_fields[table_key] = business_keys
    
    return required_fields


TABLE_FIELD_MAPPERS = None
TABLE_REQUIRED_FIELDS = None


def get_field_mapper(table_name: str) -> Dict[str, str]:
    """获取指定表的字段映射"""
    global TABLE_FIELD_MAPPERS
    if TABLE_FIELD_MAPPERS is None:
        TABLE_FIELD_MAPPERS = get_table_field_mappers()
    return TABLE_FIELD_MAPPERS.get(table_name, {})


def get_required_fields(table_name: str) -> List[str]:
    """获取指定表的必填字段"""
    global TABLE_REQUIRED_FIELDS
    if TABLE_REQUIRED_FIELDS is None:
        TABLE_REQUIRED_FIELDS = get_table_required_fields()
    return TABLE_REQUIRED_FIELDS.get(table_name, [])


class ExcelParser:
    """Excel解析器"""
    
    def __init__(
        self,
        field_mapper: Dict[str, str] = None,
        required_fields: List[str] = None,
        sheet_name: str = 0,
        skip_empty_rows: bool = True
    ):
        """
        初始化Excel解析器
        
        Args:
            field_mapper: 字段映射 {内部字段名: Excel列名}
            required_fields: 必填字段列表
            sheet_name: 工作表名或索引，默认第一个
            skip_empty_rows: 是否跳过空行
        """
        self.field_mapper = field_mapper or {}
        self.required_fields = required_fields or []
        self.sheet_name = sheet_name
        self.skip_empty_rows = skip_empty_rows
        self.parsing_errors = []
    
    def parse(self, file_bytes: bytes, filename: str = None) -> Tuple[List[Dict], List[Dict]]:
        """
        解析Excel或CSV文件
        
        Args:
            file_bytes: 文件字节流
            filename: 文件名（用于判断文件类型）
        
        Returns:
            (成功解析的数据列表, 错误记录列表)
        """
        self.parsing_errors = []
        
        try:
            if filename and filename.lower().endswith('.csv'):
                df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8-sig')
            else:
                df = pd.read_excel(BytesIO(file_bytes), sheet_name=self.sheet_name)
        except Exception as e:
            file_type = "CSV" if filename and filename.lower().endswith('.csv') else "Excel"
            logger.error(f"读取{file_type}文件失败: {str(e)}")
            return [], [{"error": f"读取{file_type}文件失败: {str(e)}"}]
        
        if df.empty:
            return [], []
        
        column_validation = self._validate_columns(df)
        if not column_validation[0]:
            return [], [{"error": f"缺少必要列: {column_validation[1]}"}]
        
        df = self._apply_field_mapping(df)
        
        if self.skip_empty_rows:
            df = self._remove_empty_rows(df)
        
        data_list = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                record = self._row_to_dict(row, idx)
                validation = self._validate_record(record, idx)
                if validation[0]:
                    data_list.append(record)
                else:
                    errors.append({
                        "row": idx + 2,
                        "data": record,
                        "errors": validation[1]
                    })
            except Exception as e:
                errors.append({
                    "row": idx + 2,
                    "error": str(e)
                })
        
        self.parsing_errors = errors
        logger.info(f"Excel解析完成: 成功{len(data_list)}条, 失败{len(errors)}条")
        
        return data_list, errors
    
    def _validate_columns(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """校验必填列是否存在"""
        if not self.required_fields:
            return True, []
        
        excel_columns = set(df.columns.str.strip())
        required_excel_cols = set()
        
        for internal_field in self.required_fields:
            excel_col = self.field_mapper.get(internal_field, internal_field)
            required_excel_cols.add(excel_col)
        
        missing_cols = required_excel_cols - excel_columns
        return len(missing_cols) == 0, list(missing_cols)
    
    def _apply_field_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用字段映射"""
        if not self.field_mapper:
            return df
        
        reverse_mapper = {v: k for k, v in self.field_mapper.items() if v}
        df = df.rename(columns=reverse_mapper)
        
        return df
    
    def _remove_empty_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除空行"""
        return df.dropna(how='all')
    
    def _row_to_dict(self, row: pd.Series, idx: int) -> Dict[str, Any]:
        """将行转换为字典"""
        record = {}
        for col in row.index:
            value = row[col]
            if pd.isna(value):
                record[col] = None
            elif isinstance(value, datetime):
                record[col] = value.isoformat()
            elif isinstance(value, pd.Timestamp):
                record[col] = value.isoformat()
            else:
                record[col] = value
        return record
    
    def _validate_record(self, record: Dict, idx: int) -> Tuple[bool, List[str]]:
        """校验单条记录"""
        errors = []
        
        for field in self.required_fields:
            value = record.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ''):
                errors.append(f"必填字段 {field} 不能为空")
        
        return len(errors) == 0, errors
    
    def get_parsing_summary(self) -> Dict:
        """获取解析摘要"""
        return {
            "total_errors": len(self.parsing_errors),
            "errors": self.parsing_errors[:10]
        }


class ExcelExporter:
    """Excel导出器"""
    
    @staticmethod
    def export_to_bytes(
        data: List[Dict],
        columns: List[str] = None,
        sheet_name: str = "Sheet1"
    ) -> bytes:
        """
        导出数据为Excel字节流
        
        Args:
            data: 数据列表
            columns: 列顺序，默认使用数据的所有列
            sheet_name: 工作表名
        
        Returns:
            Excel文件字节流
        """
        if not data:
            df = pd.DataFrame()
        else:
            df = pd.DataFrame(data)
            if columns:
                df = df[[col for col in columns if col in df.columns]]
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    def export_with_errors(
        data: List[Dict],
        errors: List[Dict],
        columns: List[str] = None
    ) -> bytes:
        """
        导出数据和错误信息到Excel
        
        Args:
            data: 成功数据列表
            errors: 错误列表
            columns: 列顺序
        
        Returns:
            Excel文件字节流
        """
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if data:
                df_data = pd.DataFrame(data)
                if columns:
                    df_data = df_data[[col for col in columns if col in df_data.columns]]
                df_data.to_excel(writer, sheet_name="成功数据", index=False)
            
            if errors:
                df_errors = pd.DataFrame(errors)
                df_errors.to_excel(writer, sheet_name="错误数据", index=False)
        
        output.seek(0)
        return output.getvalue()


def get_parser_for_table(table_name: str) -> ExcelParser:
    """获取指定表的Excel解析器"""
    field_mapper = get_field_mapper(table_name)
    required_fields = get_required_fields(table_name)
    
    return ExcelParser(
        field_mapper=field_mapper,
        required_fields=required_fields
    )
