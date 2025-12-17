# from datetime import datetime
# import os, importlib#, uuid
from typing import Optional#, Dict, Any
from datetime import datetime


import pandas as pd
from fastapi import APIRouter, Query, Body, File, UploadFile#, HTTPException
from fastapi.responses import StreamingResponse

from .projects import  active_connector
# from .connectors.project import MyapsDbActionsAbc
from .schemas import SupplyOperationBody, SupplyAction
# from apps.io_api.models import TSupply
from .utils.barcode_qrcode_generator import generate_qrcode, generate_barcode
from apps.io_api.common import standard_response, common_params
from apps.data_opt.projects import active_connector
from apps.data_opt.utils.bomchecker import BOMChecker, HAP_CTRLID
from apps.data_opt.components.hap_v3 import HapApiV3


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
    error_correction: Optional[str] = Body("H", pattern="^(L|M|Q|H)$", description="纠错级别：L(7%), M(15%), Q(25%), H(30%)"),
    back_color: Optional[str] = Body("#FFFFFF", pattern="^#[0-9A-Fa-f]{6}$", description="背景颜色，十六进制颜色码"),
    fill_color: Optional[str] = Body("#000000", pattern="^#[0-9A-Fa-f]{6}$", description="填充颜色，十六进制颜色码"),
    image_format: Optional[str] = Body("SVG", pattern="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(12, ge=8, description="内容文字大小"),
    x_api_key: str = common_params["x_api_key"]
):
    try:
        result = generate_qrcode(
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
    width: Optional[int] = Body(500, ge=50, description="条形码宽度(像素)", examples=[200]),
    height: Optional[int] = Body(150, ge=30, description="条形码高度(像素)", examples=[100]),
    margin: Optional[int] = Body(20, ge=0, description="条形码边距(像素)", examples=[10]),
    font_size: Optional[int] = Body(14, ge=6, description="条形码文字大小", examples=[10]),
    add_text: Optional[bool] = Body(True, description="是否在条形码下方添加文字"),
    fill_color: Optional[str] = Body("#000000", pattern="^#[0-9A-Fa-f]{6}$", description="条形码颜色"),
    back_color: Optional[str] = Body("#FFFFFF", pattern="^#[0-9A-Fa-f]{6}$", description="条形码背景颜色"),
    image_format: Optional[str] = Body("SVG", pattern="^(PNG|JPEG|GIF|SVG)$", description="图片格式"),
    show_content: Optional[bool] = Body(True, description="是否在图片底部显示原字符串内容"),
    content_font_size: Optional[int] = Body(20, ge=8, description="内容文字大小"),
    x_api_key: str = common_params["x_api_key"]
):
    try:
        result = generate_barcode(
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


@rt.post("/check/bomxlsx",
    tags=["数据操作 - 校验BOM"],
    summary="校验BOM",
    description="校验传入的 BOM excel，结果输出至 新的 excel 文件"
)
async def check_bom_excel(
    file: UploadFile = File(..., description="BOM excel 文件，必须为 xlsx 格式"),
    parentversion_col: str = Query(None, example="MatVer", description="版本号"),
    parent_col: str = Query(..., example="ProductNo", description="父料号"),
    child_col: str = Query(..., example="MaterialNo", description="子料号"),
    numerator_col: str = Query(..., example="Qty", description="数量"),
    denominator_col: str = Query(None, example=None, description="分母"),
    parentunit_col: str = Query(None, example=None, description="父单位"),
    childunit_col: str = Query(None, example=None, description="子单位"),
    x_api_key: str = common_params["x_api_key"]
):

    try:
        # 验证文件格式是否为 xlsx
        if not file.filename.lower().endswith('.xlsx'):
            return standard_response(
                status_code=400,
                success=0,
                message="文件格式错误：请上传 xlsx 格式的 Excel 文件"
            )
        bom_df = pd.read_excel(file.file)
        checker = BOMChecker(
            numerator_col=numerator_col,
            denominator_col=denominator_col,
            parent_col=parent_col,
            child_col=child_col,
            parentversion_col=parentversion_col,
            parentunit_col=parentunit_col,
            childunit_col=childunit_col,
            # dtofield_mapper=dtofield_mapper,
        )
        checker.start_check(bom_df)
        excel_data = checker.export_results_as_excel()
        return StreamingResponse(
            excel_data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=bom_check_results.xlsx"
            }
        )
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )


@rt.get("/check/bomdata",
    tags=["数据操作 - 校验BOM"],
    summary="获取校验BOM结果",
    description="校验三方系统的BOM，结果输出至 excel 文件 或 HAP"
)
async def get_bom_check_result_api(
    output_type: str = Query(..., example="EXCEL", enum=["EXCEL", "HAP"], description="输出格式"),
    x_api_key: str = common_params["x_api_key"]
):
    try:
        sap_url1 = 'http://192.168.201.2:8000/zrestful_test2?sap-client=800'
        sap_session1 = requests.Session()
        response = sap_session1.get(url=f"{sap_url1}", headers={'interface': 'bom', 'werks': "1600"})
        bom_json_data = response.json()['data']

        mainfield_mapper = {
            "id": None,
            "pn": "matnr",   # 产品料号
            "pu": "bmein",   # 产品单位
            "cn": "idnrk",   # 物料料号
            "cu": "meins",   # 物料单位
            "n": "menge",   # 数量
            "d": "bmeng",   # 分母
            "pv": "stlal"      # 产品版本号
        }

        dtofield_mapper = {
            "productno": "matnr",
            "materialno": "idnrk",
            "matver": "stlal",
        }

        checker = BOMChecker(
            mainfield_mapper=mainfield_mapper,
            dtofield_mapper=dtofield_mapper,
        )

        checker.start_check(bom_json_data)
        summary_markdown = checker.output_results_as_markdown()

        if output_type.strip().upper() == "EXCEL":
            excel_data = checker.export_results_as_excel()
            ts = summary_markdown.get("check_timestamp", datetime.now().strftime("%Y%m%d%H%M%S"))
            return StreamingResponse(
                excel_data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f"attachment; filename=BomCheckResults_{ts}.xlsx"
                }
            )
        elif output_type.strip().upper() == "HAP":
            hap_app_key = "d519a8ea60f9efa6"
            hap_sign = "NjAwYzI5OWJlMTNhNTcwODM5ZTEwOWE2YjE3ZDZiNWRmYzk4NTJjNTZmODQ4N2EzNGNjNWM2ZGMzNTBlYjY0Ng=="
            hap_base_url = "https://api.mingdao.com"

            marked_data = checker.bom_result['marked_data']
            material_units_map_list = checker.unit_result['material_units_map_list']
            markdown_result = checker.output_results_as_markdown()
            mingdao_api = HapApiV3(app_key=hap_app_key, sign=hap_sign, base_url=hap_base_url)
            mingdao_api.add_rows(worksheet_id='bom_check_summary', rows=[markdown_result])
            mingdao_api.add_rows(worksheet_id="transit_bom_structure", rows=marked_data)
            mingdao_api.add_rows(worksheet_id='material_units_map', rows=material_units_map_list)
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"BOM校验失败: {str(e)}"
        )
