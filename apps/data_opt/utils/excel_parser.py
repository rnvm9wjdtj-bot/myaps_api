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
    
    def parse(self, file_bytes: bytes) -> Tuple[List[Dict], List[Dict]]:
        """
        解析Excel文件
        
        Args:
            file_bytes: Excel文件字节流
        
        Returns:
            (成功解析的数据列表, 错误记录列表)
        """
        self.parsing_errors = []
        
        try:
            df = pd.read_excel(BytesIO(file_bytes), sheet_name=self.sheet_name)
        except Exception as e:
            logger.error(f"读取Excel文件失败: {str(e)}")
            return [], [{"error": f"读取Excel文件失败: {str(e)}"}]
        
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


TABLE_FIELD_MAPPERS = {
    "t_material": {
        "materialno": "物料号",
        "description": "物料描述",
        "plant": "工厂",
        "type": "物料类型",
        "phantom": "虚拟件",
        "candelay": "可否延迟",
        "lotsize": "批量策略",
        "leadday": "提前期",
        "lotmin": "最小批量",
        "lotmax": "最大批量",
        "unit": "单位",
    },
    "t_workcenter": {
        "workcenter": "工作中心",
        "description": "描述",
        "bottleneck": "瓶颈",
        "finite": "有限产能",
        "capacity": "产能",
    },
    "t_mat_ver": {
        "materialno": "物料号",
        "matver": "版本号",
        "description": "描述",
        "active": "激活",
        "lotfrom": "批量下限",
        "lotto": "批量上限",
    },
    "t_mat_wc": {
        "materialno": "物料号",
        "matver": "版本号",
        "itemno": "工序号",
        "workcenter": "工作中心",
        "sf": "串并行",
        "basesec": "基础工时",
    },
    "t_mat_wc_bom": {
        "productno": "父件料号",
        "materialno": "子件料号",
        "matver": "版本号",
        "itemno": "工序号",
        "qty": "用量",
        "scrap": "损耗率",
        "mto": "MTO",
        "alt": "替代料",
    },
    "t_mold": {
        "moldno": "模具编号",
        "description": "描述",
        "type": "类型",
        "status": "状态",
        "moldnum": "穴数",
        "qty": "台数",
    },
    "t_mat_wc_mold": {
        "materialno": "物料号",
        "workcenter": "工作中心",
        "itemno": "工序号",
        "moldno": "模具编号",
        "basesec": "UPH",
    },
}

TABLE_REQUIRED_FIELDS = {
    "t_material": ["materialno", "description", "plant"],
    "t_workcenter": ["workcenter"],
    "t_mat_ver": ["materialno", "matver"],
    "t_mat_wc": ["materialno", "matver", "itemno", "workcenter"],
    "t_mat_wc_bom": ["productno", "materialno", "qty"],
    "t_mold": ["moldno"],
    "t_mat_wc_mold": ["materialno", "workcenter", "moldno"],
}


def get_parser_for_table(table_name: str) -> ExcelParser:
    """获取指定表的Excel解析器"""
    field_mapper = TABLE_FIELD_MAPPERS.get(table_name, {})
    required_fields = TABLE_REQUIRED_FIELDS.get(table_name, [])
    
    return ExcelParser(
        field_mapper=field_mapper,
        required_fields=required_fields
    )
