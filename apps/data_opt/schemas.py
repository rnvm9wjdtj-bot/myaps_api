# from datetime import datetime
# from typing import Optional, List, Literal
# from pydantic import BaseModel, Field, field_validator


# class AcceptDataImport(BaseModel):
#     """数据导入请求模型"""
#     import_type: str = Field(..., description="导入类型：material, bom, workcenter等")
#     file_name: str = Field(..., max_length=255, description="文件名")
#     file_size: int = Field(..., ge=0, description="文件大小(字节)")
#     import_by: str = Field(..., max_length=50, description="导入人")
#     db_name: str = Field(..., max_length=50, description="操作的账套")

#     @field_validator('import_type')
#     def validate_import_type(cls, v):
#         valid_types = ['material', 'bom', 'workcenter', 'order', 'inventory', 'demand', 'supply']
#         if v not in valid_types:
#             raise ValueError(f"导入类型必须是以下之一: {', '.join(valid_types)}")
#         return v


# class DataImportResponse(BaseModel):
#     """数据导入响应模型"""
#     id: str
#     import_type: str
#     file_name: str
#     file_size: int
#     import_status: str
#     success_count: int
#     failed_count: int
#     import_by: str
#     import_time: datetime
#     error_message: Optional[str] = None
#     db_name: str

#     class Config:
#         from_attributes = True


# class AcceptDataExport(BaseModel):
#     """数据导出请求模型"""
#     export_type: str = Field(..., description="导出类型：material, bom, order等")
#     export_by: str = Field(..., max_length=50, description="导出人")
#     filters: Optional[dict] = Field(None, description="导出过滤条件")
#     db_name: str = Field(..., max_length=50, description="操作的账套")

#     @field_validator('export_type')
#     def validate_export_type(cls, v):
#         valid_types = ['material', 'bom', 'workcenter', 'order', 'inventory', 'demand', 'supply', 'capacity']
#         if v not in valid_types:
#             raise ValueError(f"导出类型必须是以下之一: {', '.join(valid_types)}")
#         return v


# class DataExportResponse(BaseModel):
#     """数据导出响应模型"""
#     id: str
#     export_type: str
#     file_name: Optional[str] = None
#     file_path: Optional[str] = None
#     export_status: str
#     record_count: int
#     export_by: str
#     export_time: datetime
#     download_count: int
#     error_message: Optional[str] = None
#     db_name: str

#     class Config:
#         from_attributes = True


# class AcceptDataBackup(BaseModel):
#     """数据备份请求模型"""
#     backup_name: str = Field(..., max_length=255, description="备份名称")
#     backup_type: Literal['full', 'incremental', 'differential'] = Field(..., description="备份类型")
#     backup_by: str = Field(..., max_length=50, description="备份操作人")
#     db_name: str = Field(..., max_length=50, description="备份的账套")


# class DataBackupResponse(BaseModel):
#     """数据备份响应模型"""
#     id: str
#     backup_name: str
#     backup_path: Optional[str] = None
#     backup_size: int
#     backup_status: str
#     backup_type: str
#     backup_by: str
#     backup_time: datetime
#     restore_count: int
#     error_message: Optional[str] = None
#     db_name: str

#     class Config:
#         from_attributes = True


# class AcceptDataRestore(BaseModel):
#     """数据恢复请求模型"""
#     backup_id: str = Field(..., description="备份ID")
#     restore_by: str = Field(..., max_length=50, description="恢复操作人")
#     db_name: str = Field(..., max_length=50, description="恢复到的账套")
#     overwrite: bool = Field(False, description="是否覆盖现有数据")


# class PaginatedResponse(BaseModel):
#     """分页响应通用模型"""
#     total: int
#     page_size: int
#     page_index: int
#     data: List[dict]


# class BatchOperationResponse(BaseModel):
#     """批量操作响应模型"""
#     success_count: int
#     failed_count: int
#     success_ids: List[str]
#     failed_details: List[dict]
#     message: str = "操作完成"