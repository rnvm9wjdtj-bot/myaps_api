# from datetime import datetime
import os#, importlib#, uuid
from pathlib import Path
from typing import Optional#, Dict, Any
# from datetime import datetime


import pandas as pd
from fastapi import APIRouter, Query, Body, Header, File, UploadFile#, HTTPException
from fastapi.responses import HTMLResponse#, StreamingResponse

from config.settings import BASE_DIR
from project_files import  project_client, hap_conn
# from .schemas import SupplyOperationBody, SupplyAction
# from apps.io_api.models import TSupply
from .utils.barcode_qrcode_generator import generate_qrcode, generate_barcode
from apps.io_api.utils.common import standard_response
from apps.data_opt.utils.bomchecker import BOMChecker
from apps.data_opt.utils.routechecker import RouteChecker



# 创建路由器实例
rt = APIRouter()


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
    x_api_key: str = Header(None, description="API密钥")
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
    x_api_key: str = Header(None, description="API密钥")
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


@rt.post("/check/bom",
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
    x_api_key: str = Header(None, description="API密钥")
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
        return checker.export_results_as_excel()
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )


@rt.get("/tools", tags=["数据操作 - 校验工具页面"])
async def bom_check_page():
    """
    校验工具页面
    提供用户友好的Web界面来上传Excel文件并进行BOM和工序数据校验
    """
    html_path = os.path.join(BASE_DIR, "static", "tools.html")
    if os.path.exists(html_path):
        html_content = open(html_path, 'r', encoding='utf-8').read()
        status_code = 200
    else:
        html_content = """
        <html>
            <body>
                <h1>BOM校验页面未找到</h1>
                <p>请确保static/tools.html文件存在</p>
                <a href="/">返回首页</a>
            </body>
        </html>
        """
        status_code = 404
    return HTMLResponse(content=html_content, status_code=status_code)


@rt.get("/check/bom",
    tags=["数据操作 - 校验BOM"],
    summary="获取校验BOM结果",
    description="校验三方系统的BOM，结果输出至 excel 文件 或 HAP"
)
async def get_bom_check_result_api(
    output_method: str = Query(..., example="EXCEL", enum=["EXCEL", "HAP"], description="输出方式"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        bom_json_data = await project_client.ScheduleTasks.get_bom()

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

        output_method = output_method.strip().upper()
        if output_method == "EXCEL":
            return checker.export_results_as_excel()
        elif output_method == "HAP":
            if hap_conn is None:
                return standard_response(
                    status_code=500,
                    success=0,
                    message="HAP 配置未完成，无法连接"
                )
            return standard_response(**checker.output_results_to_hap(hap_conn))
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"BOM校验失败: {str(e)}"
        )


@rt.post("/check/route",
    tags=["数据操作 - 校验工艺路线"],
    summary="校验工艺路线问题",
    description="校验传入的 工艺路线 excel，返回问题列表"
)
def check_route_excel(
    file: UploadFile = File(..., description="工艺路线 excel 文件，必须为 xlsx 格式"),
    product_col: str = Query(..., example="MaterialNo", description="产品料号"),
    productversion_col: str = Query(None, example="MatVer", description="产品版本号"),
    sortno_col: str = Query(..., example="SortNo", description="顺序号"),
    itemno_col: str = Query(..., example="ItemNo", description="工序项"),
    workcenter_col: str = Query(None, example="WorkCenter", description="工作中心"),
    x_api_key: str = Header(None, description="API密钥")
):
    try:
        # 验证文件格式是否为 xlsx
        if not file.filename.lower().endswith('.xlsx'):
            return standard_response(
                status_code=400,
                success=0,
                message="文件格式错误：请上传 xlsx 格式的 Excel 文件"
            )
        route_df = pd.read_excel(file.file)
        checker = RouteChecker(
            product_col=product_col,
            productversion_col=productversion_col,
            sortno_col=sortno_col,
            itemno_col=itemno_col,
            workcenter_col=workcenter_col,
        )
        checker.start_check(route_df)
        return checker.export_results_as_excel()
    except Exception as e:
        return standard_response(
            status_code=500,
            success=0,
            message=f"执行失败: {str(e)}"
        )