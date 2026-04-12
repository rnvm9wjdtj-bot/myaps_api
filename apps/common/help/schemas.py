"""
帮助模块数据模型

定义帮助文档相关的数据结构
"""

from pydantic import BaseModel
from typing import List, Optional


class DocItem(BaseModel):
    """文档项模型"""
    id: str
    title: str
    category_id: str
    category_name: str
    summary: Optional[str] = None
    content: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocCategory(BaseModel):
    """文档分类模型"""
    id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    order: int = 0
