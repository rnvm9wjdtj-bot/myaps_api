# from datetime import datetime
import os, importlib#, uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, Body, HTTPException

from .connectors import  active_connector
from .connectors.project import MyapsDbActionsAbc
from .schemas import SupplyOperationBody, SupplyAction
from apps.io_api.models import TSupply
from .utils.barcode_qrcode_generator import generate_qrcode_file, generate_barcode_file
from apps.io_api.common import standard_response, common_params


# 创建路由器实例
rt = APIRouter()


supply_action = {
    "refresh_stock": "st.refresh",
    "close_mo": "mo.close",
    "pl_to_mo": "pl.to_mo",
}


@rt.post("/supply",
    tags=["数据操作 - 供应"],
    summary="供应数据操作",
    description="""
    执行供应数据操作，支持刷新库存。
    - **db_name**: 账套名称，默认为空，对所有账套生效
    - **action**: 操作类型，目前支持：
        - 刷新库存(st.refresh)
    """
)
async def opt_supply(
    body: SupplyOperationBody,
    db_name: str | None = None,
    x_api_key: str = common_params["x_api_key"]
):
    if body.action == SupplyAction.REFRESH_STOCK:
        return await active_connector.refresh_stock(db_name or None)
    # elif body.action == SupplyAction.CLOSE_MO and body.type in ["MO", "PL"]:
    #     return await TSupply.filter(
    #         materialno=body.materialno,
    #         supplyno=body.supplyno,
    #     ).delete(using_db=db_name or None)
    # elif body.action == SupplyAction.PL_TO_MO and body.type == "PL":
    #     return await active_connector.MyapsDbActions.pl_to_mo(body.supplyno, body.mono, db_name or None)


@rt.post("/generate/qrcode",
    tags=["数据操作 - 二维码生成"],
    summary="生成二维码",
    description="生成二维码并返回BASE64格式数据"
)
async def generate_qrcode_api(
    content: str = Body(..., description="二维码内容"),
    version: Optional[int] = Body(1, ge=1, le=40, description="二维码版本，1-40"),
    box_size: Optional[int] = Body(10, ge=1, description="二维码每个小方格的像素大小"),
    border: Optional[int] = Body(4, ge=1, description="二维码边框的小方格数"),
    error_correction: Optional[str] = Body("H", regex="^(L|M|Q|H)$", description="纠错级别：L(7%), M(15%), Q(25%), H(30%)"),
    back_color: Optional[str] = Body("#FFFFFF", regex="^#[0-9A-Fa-f]{6}$", description="背景颜色，十六进制颜色码"),
    fill_color: Optional[str] = Body("#000000", regex="^#[0-9A-Fa-f]{6}$", description="填充颜色，十六进制颜色码"),
    image_format: Optional[str] = Body("SVG", regex="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(12, ge=8, description="内容文字大小"),
    x_api_key: str = common_params["x_api_key"]
):
    try:
        result = generate_qrcode_file(
            content=content,
            version=version,
            box_size=box_size,
            border=border,
            error_correction=error_correction,
            back_color=back_color,
            fill_color=fill_color,
            image_format=image_format,
            show_content=show_content,
            content_font_size=content_font_size,
            output_type="BASE64"
        )
        return standard_response(
            data={
                "base64": result["base64"],
                "content": content,
                "image_format": image_format
            }
        )
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"二维码生成失败: {str(e)}"
        )


@rt.post("/generate/barcode",
    tags=["数据操作 - 条形码生成"],
    summary="生成条形码",
    description="生成条形码并返回BASE64格式数据"
)
async def generate_barcode_api(
    content: str = Body(..., description="条形码内容"),
    barcode_type: Optional[str] = Body("code128", description="条形码类型"),
    width: Optional[int] = Body(300, ge=50, description="条形码宽度(像素)", example=200),
    height: Optional[int] = Body(100, ge=30, description="条形码高度(像素)", example=100),
    margin: Optional[int] = Body(12, ge=0, description="条形码边距(像素)", example=10),
    font_size: Optional[int] = Body(10, ge=6, description="条形码文字大小", example=10),
    add_text: Optional[bool] = Body(True, description="是否在条形码下方添加文字"),
    fill_color: Optional[str] = Body("#000000", regex="^#[0-9A-Fa-f]{6}$", description="条形码颜色"),
    back_color: Optional[str] = Body("#FFFFFF", regex="^#[0-9A-Fa-f]{6}$", description="条形码背景颜色"),
    image_format: Optional[str] = Body("SVG", regex="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(12, ge=8, description="内容文字大小"),
    x_api_key: str = common_params["x_api_key"]
):
    try:
        result = generate_barcode_file(
            content=content,
            barcode_type=barcode_type,
            width=width,
            height=height,
            margin=margin,
            font_size=font_size,
            add_text=add_text,
            fill_color=fill_color,
            back_color=back_color,
            image_format=image_format,
            show_content=show_content,
            content_font_size=content_font_size,
            output_type="BASE64"
        )
        return standard_response(
            data={
                "base64": result["base64"],
                "content": content,
                "barcode_type": barcode_type,
                "image_format": image_format
            }
        )

    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"条形码生成失败: {str(e)}"
        )

