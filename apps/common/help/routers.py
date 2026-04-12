"""
帮助模块路由

提供帮助文档相关的 API 端点
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Dict, Any
import json
from .service import help_service
from .schemas import DocItem, DocCategory

router = APIRouter(prefix="/help", tags=["help"])


@router.get("", response_class=HTMLResponse)
async def help_index():
    """
    帮助中心主页

    返回帮助文档的主页面
    """
    return help_service.get_index_page()


@router.get("/api/docs", response_model=List[DocItem])
async def get_docs():
    """
    获取文档列表

    返回所有可用的帮助文档列表
    """
    return help_service.get_docs_list()


@router.get("/api/docs/{doc_id}", response_model=Dict[str, Any])
async def get_doc_content(doc_id: str):
    """
    获取文档内容

    Args:
        doc_id: 文档ID

    Returns:
        文档内容
    """
    doc = help_service.get_doc_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.get("/api/categories", response_model=List[DocCategory])
async def get_categories():
    """
    获取文档分类

    返回所有文档分类
    """
    return help_service.get_categories()


@router.get("/api/categories/{category_id}/docs", response_model=List[DocItem])
async def get_docs_by_category(category_id: str):
    """
    获取指定分类的文档

    Args:
        category_id: 分类ID

    Returns:
        该分类下的文档列表
    """
    return help_service.get_docs_by_category(category_id)


@router.get("/api/structure", response_model=List[Dict[str, Any]])
async def get_structure():
    """
    获取帮助中心结构配置

    Returns:
        帮助中心的结构配置
    """
    try:
        with open("apps/common/help/structure.json", "r", encoding="utf-8") as f:
            structure = json.load(f)
        return structure
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法加载结构配置: {str(e)}")
