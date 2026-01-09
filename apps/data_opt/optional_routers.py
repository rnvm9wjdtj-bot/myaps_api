"""
可选路由注册模块

用于管理需要按条件加载的路由，保持 main.py 的整洁性。
"""


from fastapi import FastAPI

import os

use_connections = os.environ.get("USE_CONNECTIONS", "")

def register_optional_routers(app: FastAPI):
    """根据条件注册可选路由"""
    if "yonyou_tplus.py" in use_connections:
        from apps.data_opt.components.yonyou_tplus import rt as yonyou_tplus_rt
        app.include_router(yonyou_tplus_rt, tags=[])
