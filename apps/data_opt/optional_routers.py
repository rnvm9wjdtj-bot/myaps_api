"""
可选路由注册模块

用于管理需要按条件加载的路由，保持 main.py 的整洁性。
"""


from fastapi import FastAPI

import os

enable_optional_routers = os.environ.get("OPTIONAL_ROUTERS")

def register_optional_routers(app: FastAPI):
    """根据条件注册可选路由"""
    if "cjt" in enable_optional_routers:
        from apps.data_opt.components.yonyou_tplus import rt as cjt_rt
        app.include_router(cjt_rt, tags=[])
