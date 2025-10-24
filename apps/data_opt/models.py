# from tortoise.models import Model as TortoiseBaseModel
# from tortoise import fields


# class TDataImport(TortoiseBaseModel):
#     """数据导入记录表"""
#     id = fields.CharField(primary_key=True, max_length=64)
#     import_type = fields.CharField(source_field='ImportType', max_length=50, description='导入类型')  # 例如：material, bom, workcenter等
#     file_name = fields.CharField(source_field='FileName', max_length=255, description='文件名')
#     file_size = fields.IntField(source_field='FileSize', description='文件大小(字节)')
#     import_status = fields.CharField(source_field='ImportStatus', max_length=20, default='processing', description='导入状态：processing, success, failed')
#     success_count = fields.IntField(source_field='SuccessCount', default=0, description='成功记录数')
#     failed_count = fields.IntField(source_field='FailedCount', default=0, description='失败记录数')
#     import_by = fields.CharField(source_field='ImportBy', max_length=50, description='导入人')
#     import_time = fields.DatetimeField(source_field='ImportTime', auto_now_add=True, description='导入时间')
#     error_message = fields.TextField(source_field='ErrorMessage', null=True, description='错误信息')
#     db_name = fields.CharField(source_field='DBName', max_length=50, description='操作的账套')

#     class Meta:
#         managed = True
#         table = 't_data_import'


# class TDataExport(TortoiseBaseModel):
#     """数据导出记录表"""
#     id = fields.CharField(primary_key=True, max_length=64)
#     export_type = fields.CharField(source_field='ExportType', max_length=50, description='导出类型')  # 例如：material, bom, order等
#     file_name = fields.CharField(source_field='FileName', max_length=255, description='生成的文件名')
#     file_path = fields.CharField(source_field='FilePath', max_length=500, description='文件保存路径')
#     export_status = fields.CharField(source_field='ExportStatus', max_length=20, default='processing', description='导出状态：processing, success, failed')
#     record_count = fields.IntField(source_field='RecordCount', default=0, description='导出记录数')
#     export_by = fields.CharField(source_field='ExportBy', max_length=50, description='导出人')
#     export_time = fields.DatetimeField(source_field='ExportTime', auto_now_add=True, description='导出时间')
#     download_count = fields.IntField(source_field='DownloadCount', default=0, description='下载次数')
#     error_message = fields.TextField(source_field='ErrorMessage', null=True, description='错误信息')
#     db_name = fields.CharField(source_field='DBName', max_length=50, description='操作的账套')

#     class Meta:
#         managed = True
#         table = 't_data_export'


# class TDataBackup(TortoiseBaseModel):
#     """数据备份记录表"""
#     id = fields.CharField(primary_key=True, max_length=64)
#     backup_name = fields.CharField(source_field='BackupName', max_length=255, description='备份名称')
#     backup_path = fields.CharField(source_field='BackupPath', max_length=500, description='备份文件路径')
#     backup_size = fields.IntField(source_field='BackupSize', description='备份文件大小(字节)')
#     backup_status = fields.CharField(source_field='BackupStatus', max_length=20, default='processing', description='备份状态：processing, success, failed')
#     backup_type = fields.CharField(source_field='BackupType', max_length=20, description='备份类型：full, incremental, differential')
#     backup_by = fields.CharField(source_field='BackupBy', max_length=50, description='备份操作人')
#     backup_time = fields.DatetimeField(source_field='BackupTime', auto_now_add=True, description='备份时间')
#     restore_count = fields.IntField(source_field='RestoreCount', default=0, description='恢复次数')
#     error_message = fields.TextField(source_field='ErrorMessage', null=True, description='错误信息')
#     db_name = fields.CharField(source_field='DBName', max_length=50, description='备份的账套')

#     class Meta:
#         managed = True
#         table = 't_data_backup'


# class TDataLog(TortoiseBaseModel):
#     """数据操作日志表"""
#     id = fields.CharField(primary_key=True, max_length=64)
#     operation_type = fields.CharField(source_field='OperationType', max_length=50, description='操作类型：create, update, delete, import, export, backup, restore')
#     table_name = fields.CharField(source_field='TableName', max_length=100, description='操作的表名')
#     record_id = fields.CharField(source_field='RecordId', max_length=64, null=True, description='操作的记录ID')
#     operation_by = fields.CharField(source_field='OperationBy', max_length=50, description='操作人')
#     operation_time = fields.DatetimeField(source_field='OperationTime', auto_now_add=True, description='操作时间')
#     operation_ip = fields.CharField(source_field='OperationIP', max_length=50, description='操作IP地址')
#     old_data = fields.TextField(source_field='OldData', null=True, description='操作前数据(JSON格式)')
#     new_data = fields.TextField(source_field='NewData', null=True, description='操作后数据(JSON格式)')
#     result = fields.BooleanField(source_field='Result', default=True, description='操作结果：True-成功，False-失败')
#     error_message = fields.TextField(source_field='ErrorMessage', null=True, description='错误信息')
#     db_name = fields.CharField(source_field='DBName', max_length=50, description='操作的账套')

#     class Meta:
#         managed = True
#         table = 't_data_log'