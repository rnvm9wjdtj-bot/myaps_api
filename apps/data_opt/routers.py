# from datetime import datetime
import os, importlib#, uuid
# from typing import List, Optional

from fastapi import APIRouter#, Query, Body, UploadFile, File, BackgroundTasks

from .connectors._manage import active_connector
from .schemas import SupplyOperationBody, SupplyAction
from apps.io_api.models import TSupply



# 创建路由器实例
rt = APIRouter()


@rt.post("/supply",
    tags=["数据操作 - 供应"],
    summary="供应数据操作",
    description="""
    执行供应数据操作，支持刷新库存。
    - **db_name**: 账套名称，默认为空，对所有账套生效
    - **action**: 操作类型，目前支持：
        - 刷新库存(st.refresh())
        - 关闭MO(mo.close())
    """
)
async def opt_supply(
    body: SupplyOperationBody,
    db_name: str | None = None,
):
    if body.action == SupplyAction.REFRESH_STOCK:
        return await active_connector.refresh_stock(db_name or None)
    elif body.action == SupplyAction.CLOSE_MO and body.type in ["MO", "PL"]:
        return await TSupply.filter(
            materialno=body.materialno,
            supplyno=body.supplyno,
        ).delete(using_db=db_name or None)

