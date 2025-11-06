from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import APIRouter#, Query, Body, UploadFile, File, BackgroundTasks
# from tortoise import Tortoise

# from .models import TDataImport, TDataExport, TDataBackup, TDataLog
# from .schemas import (
#     AcceptDataImport, DataImportResponse, 
#     AcceptDataExport, DataExportResponse,
#     AcceptDataBackup, DataBackupResponse,
#     AcceptDataRestore, PaginatedResponse, BatchOperationResponse
# )
# from .common import common_params, standard_response, common_get_by_orm
from .connectors.haidaxiangsu import get_stock



# 创建路由器实例
rt = APIRouter()

@rt.get("/stock")
async def get_st():
    get_stock()
    return {"message": "数据接收成功"}


