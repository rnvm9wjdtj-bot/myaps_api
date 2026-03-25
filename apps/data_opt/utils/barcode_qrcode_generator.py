#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二维码和条形码生成工具

该模块提供了生成二维码和条形码的功能，可以将字符串内容转换为对应的图形并保存为图片文件。
支持自定义参数，如尺寸、颜色、格式等。
"""

import os
import base64
from io import BytesIO
from typing import Dict, Optional, Union, Tuple, Any

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
# from qrcode.image.styles.colormasks import SquareGradiantColorMask
from qrcode.image.svg import SvgImage#, SvgFragmentImage
import barcode
from barcode.writer import ImageWriter, SVGWriter
from PIL import Image, ImageDraw, ImageFont
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)

def create_qrcode(
    content: str,
    size: int = 200,
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
    version: Optional[int] = None,
    error_correction: Union[int, str] = qrcode.constants.ERROR_CORRECT_M,
    image_format: str = "PNG",
    add_logo: Optional[str] = None,
    logo_size: Tuple[int, int] = (40, 40),
    show_content: bool = False,
    content_font_size: int = 12
) -> Union[Image.Image, BytesIO, bytes]:
    """
    生成二维码
    
    Args:
        content: 要编码的字符串内容
        size: 生成图片的大小（像素，仅对像素图有效）
        box_size: 二维码中每个小格子的大小
        border: 二维码边框的格子数
        fill_color: 二维码的颜色
        back_color: 二维码的背景色
        version: 二维码的版本（1-40），None表示自动选择
        error_correction: 纠错级别（L, M, Q, H）
        image_format: 输出图片的格式（PNG, JPEG, GIF, SVG等）
        add_logo: 可选，添加到二维码中心的logo图片路径（仅对像素图有效）
        logo_size: logo的大小（像素，仅对像素图有效）
        show_content: 是否在二维码底部显示原始字符串内容
        content_font_size: 显示内容的字体大小（仅对像素图有效）
        
    Returns:
        Union[PIL.Image.Image, bytes]: 生成的二维码图片对象（像素图）或SVG字符串（矢量图）
    """
    try:
        logger.query("二维码", f"内容长度{len(content)}")
        
        # 处理纠错级别参数（支持字符串或常量）
        if isinstance(error_correction, str):
            error_correction_map = {
                'L': qrcode.constants.ERROR_CORRECT_L,
                'M': qrcode.constants.ERROR_CORRECT_M,
                'Q': qrcode.constants.ERROR_CORRECT_Q,
                'H': qrcode.constants.ERROR_CORRECT_H
            }
            error_correction = error_correction_map.get(error_correction.upper(), qrcode.constants.ERROR_CORRECT_M)

        # 创建QRCode对象
        qr = qrcode.QRCode(
            version=version,
            error_correction=error_correction,
            box_size=box_size,
            border=border,
        )
        
        # 添加内容
        qr.add_data(content)
        qr.make(fit=True)
        
        # 生成SVG矢量图
        if image_format.upper() == "SVG":
            img = qr.make_image(
                fill_color=fill_color,
                back_color=back_color,
                image_factory=SvgImage,
            )
            
            # 转换为bytes
            buffer = BytesIO()
            img.save(buffer)
            svg_data = buffer.getvalue()
            
            logger.success("生成SVG二维码")
            return svg_data
        
        # 生成像素图
        else:
            # 创建基础二维码
            img = qr.make_image(
                fill_color=fill_color,
                back_color=back_color,
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
            )
            
            # 调整图片大小
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            
            # 添加logo
            if add_logo and os.path.exists(add_logo):
                logger.info(f"添加logo：{add_logo}")
                logo = Image.open(add_logo)
                logo = logo.resize(logo_size, Image.Resampling.LANCZOS)
                
                # 确保logo是RGBA格式
                if logo.mode != 'RGBA':
                    logo = logo.convert('RGBA')
                
                # 计算logo位置（居中）
                logo_pos = ((size - logo_size[0]) // 2, (size - logo_size[1]) // 2)
                
                # 创建透明背景的logo
                logo_with_background = Image.new('RGBA', logo.size, back_color)
                logo_with_background.paste(logo, (0, 0), logo)
                
                # 将logo粘贴到二维码上
                img.paste(logo_with_background, logo_pos, logo_with_background)
            
            # 在底部显示原始字符串
            if show_content:
                # 创建一个新的图片，高度增加，用于容纳二维码和文字
                total_height = size + 40  # 40px用于显示文字
                new_img = Image.new('RGBA', (size, total_height), back_color)
                
                # 粘贴二维码
                new_img.paste(img, (0, 0))
                
                # 添加文字
                draw = ImageDraw.Draw(new_img)
                try:
                    # 尝试使用默认字体
                    font = ImageFont.truetype("arial.ttf", content_font_size)
                except IOError:
                    # 如果没有安装arial字体，使用默认字体
                    font = ImageFont.load_default()
                
                # 计算文字位置（居中）
                text_bbox = draw.textbbox((0, 0), content, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = (size - text_width) // 2
                text_y = size + (40 - text_height) // 2
                
                # 绘制文字
                draw.text((text_x, text_y), content, font=font, fill=fill_color)
                
                img = new_img
            
            logger.success("生成二维码")
            return img
        
    except Exception as e:
        logger.fail("生成二维码", "", str(e))
        raise

def create_barcode(
    content: str,
    barcode_type: str = "code128",
    width: int = 200,
    height: int = 100,
    margin: int = 10,
    font_size: int = 10,
    add_text: bool = True,
    show_content: bool = False,
    content_font_size: int = 12,
    fill_color: str = "black",
    back_color: str = "white",
    image_format: str = "PNG"
) -> Union[Image.Image, BytesIO, bytes]:
    """
    生成条形码
    
    Args:
        content: 要编码的字符串内容
        barcode_type: 条形码类型（code128, ean13, ean8, upc, code39等）
        width: 生成图片的宽度（像素，仅对像素图有效）
        height: 生成图片的高度（像素，仅对像素图有效）
        margin: 条形码的边距
        font_size: 条形码下方文字的字体大小
        add_text: 是否在条形码下方添加文字
        show_content: 是否在图片底部显示原始字符串内容
        content_font_size: 显示内容的字体大小
        fill_color: 条形码的颜色
        back_color: 条形码的背景色
        image_format: 输出图片的格式（PNG, JPEG, GIF, SVG等）
        
    Returns:
        Union[PIL.Image.Image, bytes]: 生成的条形码图片对象（像素图）或SVG字符串（矢量图）
    """
    try:
        logger.query("条形码", f"类型{barcode_type}，内容{content}")
        
        # 检查条形码类型是否支持
        if barcode_type not in barcode.PROVIDED_BARCODES:
            raise ValueError(f"不支持的条形码类型: {barcode_type}，支持的类型: {', '.join(barcode.PROVIDED_BARCODES)}")
        
        # 创建条形码
        if image_format.upper() == "SVG":
            # 使用SVGWriter生成矢量图
            barcode_class = barcode.get_barcode_class(barcode_type)
            barcode_obj = barcode_class(content, writer=SVGWriter())
            
            # 配置写入器
            options = {
                'module_width': 0.2,
                'module_height': 15.0 if add_text else 20.0,
                'quiet_zone': margin,
                'font_size': font_size,
                'text_distance': 5.0 if add_text else 0,
                'background': back_color,
                'foreground': fill_color,
                'write_text': add_text,
            }
            
            # 生成SVG
            buffer = BytesIO()
            barcode_obj.write(buffer, options=options)
            buffer.seek(0)
            svg_data = buffer.getvalue()
            
            logger.success("生成SVG条形码")
            return svg_data
        
        else:
            # 计算实际高度（考虑是否显示额外内容）
            actual_height = height + 40 if show_content else height
            
            # 使用ImageWriter生成像素图
            barcode_class = barcode.get_barcode_class(barcode_type)
            barcode_obj = barcode_class(content, writer=ImageWriter())
            
            # 配置写入器
            options = {
                'module_width': width / (len(content) * 10 + margin * 2),
                'module_height': actual_height * 0.7 if add_text else actual_height,
                'quiet_zone': margin,
                'font_size': font_size,
                'text_distance': 10 if add_text else 0,
                'background': back_color,
                'foreground': fill_color,
                'write_text': add_text,
            }
            
            # 生成图片
            buffer = BytesIO()
            barcode_obj.write(buffer, options=options)
            buffer.seek(0)
            
            # 打开图片并调整大小
            img = Image.open(buffer)
            img = img.resize((width, actual_height), Image.Resampling.LANCZOS)
            
            # 在底部显示原始字符串
            if show_content:
                # 创建新图片并设置背景
                new_img = Image.new('RGBA', (width, actual_height), back_color)
                
                # 粘贴条形码
                if actual_height > height:
                    new_img.paste(img.crop((0, 0, width, height)), (0, 0))
                else:
                    new_img = img
                
                # 添加文字
                draw = ImageDraw.Draw(new_img)
                try:
                    # 尝试使用默认字体
                    font = ImageFont.truetype("arial.ttf", content_font_size)
                except IOError:
                    # 如果没有安装arial字体，使用默认字体
                    font = ImageFont.load_default()
                
                # 计算文字位置（居中）
                text_bbox = draw.textbbox((0, 0), content, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = (width - text_width) // 2
                text_y = actual_height - 30 + (30 - text_height) // 2  # 底部预留30px
                
                # 绘制文字
                draw.text((text_x, text_y), content, font=font, fill=fill_color)
                
                img = new_img
            
            logger.success("生成条形码")
            return img
        
    except Exception as e:
        logger.fail("生成条形码", "", str(e))
        raise

def save_image(
    image: Union[Image.Image, bytes],
    file_path: str,
    image_format: str = "PNG",
    quality: int = 95
) -> str:
    """
    保存图片到文件
    
    Args:
        image: 要保存的图片对象（像素图）或SVG数据（矢量图）
        file_path: 保存路径
        image_format: 图片格式
        quality: 图片质量（1-100，仅对像素图有效）
        
    Returns:
        str: 保存成功的文件路径
    """
    try:
        logger.info(f"保存图片：{file_path}")
        
        # 确保目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        # 保存SVG矢量图
        if isinstance(image, bytes):
            with open(file_path, 'wb') as f:
                f.write(image)
        
        # 保存像素图
        else:
            if image_format.upper() == "JPEG":
                # JPEG不支持透明通道，需要转换
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])
                    image = background
                image.save(file_path, format=image_format, quality=quality)
            else:
                image.save(file_path, format=image_format, quality=quality)
        
        logger.success("保存图片", file_path)
        return file_path
        
    except Exception as e:
        logger.fail("保存图片", file_path, str(e))
        raise

def image_to_base64(
    image: Union[Image.Image, bytes],
    image_format: str = "PNG"
) -> str:
    """
    将图片转换为BASE64编码字符串
    
    Args:
        image: 图片对象或SVG字节数据
        image_format: 图片格式（PNG, JPEG, GIF等）
        
    Returns:
        str: BASE64编码的图片字符串
    """
    try:
        if isinstance(image, bytes):
            # 已经是SVG字节数据
            base64_str = base64.b64encode(image).decode('utf-8')
            return f"data:image/svg+xml;base64,{base64_str}"
        else:
            # 是PIL Image对象
            buffer = BytesIO()
            image.save(buffer, format=image_format)
            buffer.seek(0)
            base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/{image_format.lower()};base64,{base64_str}"
    except Exception as e:
        logger.fail("图片转BASE64", "", str(e))
        raise


def generate_qrcode(
    content: str,
    file_path: Optional[str] = None,
    output_type: str = ["base64", "file"][0],
    **kwargs
) -> Union[str, Dict[str, Any]]:
    """
    生成二维码
    
    Args:
        content: 要编码的字符串内容
        file_path: 保存路径（当output_type为"file"时）
        output_type: 输出类型（"file"或"base64"）
        **kwargs: 传递给create_qrcode的参数
        
    Returns:
        Union[str, Dict[str, Any]]: 如果是"file"类型，返回文件路径；如果是"base64"类型，返回包含BASE64字符串和图片信息的字典
    
    Raises:
        ValueError: 当output_type为"file"但未提供file_path时
    """
    img = create_qrcode(content, **kwargs)
    
    if output_type.lower() == "base64":
        image_format = kwargs.get("image_format", "PNG").upper()
        base64_str = image_to_base64(img, image_format)
        return {
            "base64": base64_str,
            "image_format": image_format,
            "content": content
        }
    else:
        if not file_path:
            raise ValueError("file_path must be provided when output_type is 'file'")
        return save_image(img, file_path)

def generate_barcode(
    content: str,
    file_path: Optional[str] = None,
    output_type: str = ["base64", "file"][0],
    **kwargs
) -> Union[str, Dict[str, Any]]:
    """
    生成条形码
    
    Args:
        content: 要编码的字符串内容
        file_path: 保存路径（当output_type为"file"时）
        output_type: 输出类型（"file"或"base64"）
        **kwargs: 传递给create_barcode的参数
        
    Returns:
        Union[str, Dict[str, Any]]: 如果是"file"类型，返回文件路径；如果是"base64"类型，返回包含BASE64字符串和图片信息的字典
    
    Raises:
        ValueError: 当output_type为"file"但未提供file_path时
    """
    img = create_barcode(content, **kwargs)
    
    if output_type.lower() == "base64":
        image_format = kwargs.get("image_format", "PNG").upper()
        base64_str = image_to_base64(img, image_format)
        return {
            "base64": base64_str,
            "image_format": image_format,
            "content": content,
            "barcode_type": kwargs.get("barcode_type", "code128")
        }
    else:
        if not file_path:
            raise ValueError("file_path must be provided when output_type is 'file'")
        return save_image(img, file_path)

def get_qrcode_buffer(
    content: str,
    image_format: str = "PNG",
    **kwargs
) -> BytesIO:
    """
    生成二维码并返回BytesIO对象
    
    Args:
        content: 要编码的字符串内容
        image_format: 图片格式
        **kwargs: 传递给create_qrcode的参数
        
    Returns:
        BytesIO: 包含图片数据的BytesIO对象
    """
    img = create_qrcode(content, **kwargs)
    buffer = BytesIO()
    img.save(buffer, format=image_format)
    buffer.seek(0)
    return buffer

def get_barcode_buffer(
    content: str,
    image_format: str = "PNG",
    **kwargs
) -> BytesIO:
    """
    生成条形码并返回BytesIO对象
    
    Args:
        content: 要编码的字符串内容
        image_format: 图片格式
        **kwargs: 传递给create_barcode的参数
        
    Returns:
        BytesIO: 包含图片数据的BytesIO对象
    """
    img = create_barcode(content, **kwargs)
    buffer = BytesIO()
    img.save(buffer, format=image_format)
    buffer.seek(0)
    return buffer

if __name__ == "__main__":
    # 示例用法
    logging.basicConfig(level=logging.INFO)
    
    # 生成像素二维码示例（文件输出）
    qrcode_content = "https://www.example.com"
    qrcode_file = "qrcode_example.png"
    generate_qrcode(
        content=qrcode_content,
        file_path=qrcode_file,
        size=300,
        fill_color="#000000",
        back_color="#ffffff",
        error_correction=qrcode.constants.ERROR_CORRECT_H
    )
    print(f"像素二维码生成成功: {qrcode_file}")
    
    # 生成显示内容的像素二维码示例（文件输出）
    qrcode_with_content_file = "qrcode_with_content_example.png"
    generate_qrcode(
        content=qrcode_content,
        file_path=qrcode_with_content_file,
        size=300,
        fill_color="#000000",
        back_color="#ffffff",
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        show_content=True,
        content_font_size=12
    )
    print(f"显示内容的像素二维码生成成功: {qrcode_with_content_file}")
    
    # 生成SVG二维码示例（文件输出）
    qrcode_svg_file = "qrcode_example.svg"
    generate_qrcode(
        content=qrcode_content,
        file_path=qrcode_svg_file,
        image_format="SVG",
        fill_color="#000000",
        back_color="#ffffff",
        error_correction=qrcode.constants.ERROR_CORRECT_H
    )
    print(f"SVG二维码生成成功: {qrcode_svg_file}")
    
    # 生成二维码BASE64示例
    qrcode_base64 = generate_qrcode(
        content=qrcode_content,
        file_path="",  # 文件路径在base64模式下可选
        size=300,
        fill_color="#000000",
        back_color="#ffffff",
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        output_type="base64"
    )
    print(f"二维码BASE64生成成功，长度: {len(qrcode_base64['base64'])}字符")
    print(f"BASE64前缀: {qrcode_base64['base64'][:50]}...")
    
    # 生成像素条形码示例（文件输出）
    barcode_content = "123456789012"
    barcode_file = "barcode_example.png"
    generate_barcode(
        content=barcode_content,
        file_path=barcode_file,
        barcode_type="ean13",
        width=300,
        height=100,
        add_text=True
    )
    print(f"像素条形码生成成功: {barcode_file}")
    
    # 生成显示内容的像素条形码示例（文件输出）
    barcode_with_content_file = "barcode_with_content_example.png"
    generate_barcode(
        content=barcode_content,
        file_path=barcode_with_content_file,
        barcode_type="ean13",
        width=300,
        height=100,
        add_text=True,
        show_content=True,
        content_font_size=12
    )
    print(f"显示内容的像素条形码生成成功: {barcode_with_content_file}")
    
    # 生成SVG条形码示例（文件输出）
    barcode_svg_file = "barcode_example.svg"
    generate_barcode(
        content=barcode_content,
        file_path=barcode_svg_file,
        barcode_type="ean13",
        image_format="SVG",
        add_text=True
    )
    print(f"SVG条形码生成成功: {barcode_svg_file}")
    
    # 生成条形码BASE64示例
    barcode_base64 = generate_barcode(
        content=barcode_content,
        file_path="",  # 文件路径在base64模式下可选
        barcode_type="ean13",
        width=300,
        height=100,
        add_text=True,
        output_type="base64"
    )
    print(f"条形码BASE64生成成功，长度: {len(barcode_base64['base64'])}字符")
    print(f"BASE64前缀: {barcode_base64['base64'][:50]}...")