from datetime import datetime
import os, importlib#, uuid
from typing import List, Optional

from fastapi import APIRouter#, Query, Body, UploadFile, File, BackgroundTasks

from .schemas import SupplyOperationBody, SupplyAction

active_connector = importlib.import_module(os.getenv("ACTIVE_CONNECTOR"))


# 创建路由器实例
rt = APIRouter()


@rt.post("/supply",
    tags=["数据操作 - 供应"],
    summary="供应数据操作",
    description="""
    执行供应数据操作，支持刷新库存。
    - **db_name**: 账套名称，默认为空，刷新所有账套
    - **action**: 操作类型，目前仅支持刷新库存(st.refresh())
    """
)
async def opt_supply(
    body: SupplyOperationBody,
    db_name: str | None = None,
):
    if body.action == SupplyAction.REFRESH_STOCK:
        return await active_connector.refresh_stock(db_name or None)
    elif body.action == '':
        pass



