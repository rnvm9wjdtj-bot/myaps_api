from fastapi import FastAPI
from core.settings import PORT

def create_app(lifespan=None):
    app = FastAPI(
        title="MyAPS API",
        description="MyAPS API系统接口文档，提供物料、工作中心、工序、BOM等主数据管理，以及供应需求等生产数据管理功能。",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon-32x32.png",
        swagger_ui_parameters={
            "configUrl": None,
            "defaultModelsExpandDepth": 2,
            "defaultModelExpandDepth": 3,
            "displayRequestDuration": True,
            "docExpansion": "list",
            "tryItOutEnabled": True,
            "jsonEditor": True,
            "showCommonExtensions": True,
            "showExtensions": True,
            "showMutatedRequest": True
        },
        lifespan=lifespan
    )
    
    app.openapi_version = "3.0.2"
    
    return app
