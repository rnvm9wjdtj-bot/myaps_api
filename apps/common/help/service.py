"""
帮助模块服务

处理帮助文档相关的业务逻辑
"""

from typing import List, Dict, Any, Optional
from .schemas import DocItem, DocCategory


class HelpService:
    """帮助服务类"""
    
    def __init__(self):
        """初始化帮助服务"""
        # 模拟数据
        self._categories = [
            DocCategory(
                id="1",
                name="产品介绍",
                description="关于产品的基本介绍和功能说明",
                icon="info",
                order=1
            ),
            DocCategory(
                id="2",
                name="使用指南",
                description="产品的使用方法和操作步骤",
                icon="book",
                order=2
            ),
            DocCategory(
                id="3",
                name="API文档",
                description="API接口的详细说明和使用示例",
                icon="code",
                order=3
            ),
            DocCategory(
                id="4",
                name="常见问题",
                description="常见问题的解答和解决方案",
                icon="question",
                order=4
            )
        ]
        
        self._docs = [
            DocItem(
                id="1",
                title="产品概述",
                category_id="1",
                category_name="产品介绍",
                summary="了解产品的基本功能和特点",
                content="<h2>产品概述</h2><p>本产品是一个功能强大的系统，提供了多种实用功能...</p>",
                created_at="2026-01-01",
                updated_at="2026-01-01"
            ),
            DocItem(
                id="2",
                title="快速开始",
                category_id="2",
                category_name="使用指南",
                summary="快速上手产品的基本操作",
                content="<h2>快速开始</h2><p>1. 注册账号<br>2. 登录系统<br>3. 开始使用...</p>",
                created_at="2026-01-02",
                updated_at="2026-01-02"
            ),
            DocItem(
                id="3",
                title="API接口说明",
                category_id="3",
                category_name="API文档",
                summary="API接口的详细参数和使用方法",
                content="<h2>API接口说明</h2><p>本系统提供了丰富的API接口，支持多种操作...</p>",
                created_at="2026-01-03",
                updated_at="2026-01-03"
            ),
            DocItem(
                id="4",
                title="常见问题解答",
                category_id="4",
                category_name="常见问题",
                summary="常见问题的详细解答",
                content="<h2>常见问题解答</h2><p>Q: 如何重置密码？<br>A: 点击忘记密码，按照提示操作...</p>",
                created_at="2026-01-04",
                updated_at="2026-01-04"
            )
        ]
    
    def get_index_page(self) -> str:
        """
        获取帮助中心主页
        
        Returns:
            HTML页面内容
        """
        try:
            with open("static/help/index.html", "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"<h1>错误</h1><p>无法加载帮助页面: {str(e)}</p>"
    
    def get_docs_list(self) -> List[DocItem]:
        """
        获取文档列表
        
        Returns:
            文档列表
        """
        return self._docs
    
    def get_doc_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            文档详情
        """
        for doc in self._docs:
            if doc.id == doc_id:
                return doc.model_dump()
        return None
    
    def get_categories(self) -> List[DocCategory]:
        """
        获取分类列表
        
        Returns:
            分类列表
        """
        return self._categories
    
    def get_docs_by_category(self, category_id: str) -> List[DocItem]:
        """
        根据分类获取文档
        
        Args:
            category_id: 分类ID
            
        Returns:
            该分类下的文档列表
        """
        return [doc for doc in self._docs if doc.category_id == category_id]


# 实例化服务
try:
    help_service = HelpService()
except Exception as e:
    print(f"初始化帮助服务失败: {e}")
    help_service = None
