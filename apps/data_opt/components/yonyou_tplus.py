"""
用友T+接口组件
文档：https://open.chanjet.com/docs/file/learning
{"AppKey":"IomCbFyX","AppSecret":"375CA9BC57CBFE3095FDFD3AE4A1C516"}
企业ID1241741476857608
获取token-v2版本 /financial/v2/auth/getUserToken
刷新开放平台token-新版 /auth/v2/refreshToken
物料清单查询/tplus/api/v2/bom/Query

"""
from fastapi import APIRouter

rt = APIRouter()

@rt.get("/CHANJET_CHECK.txt")
async def check_chanjet():
    """畅捷通白名单认证回调接口"""
    return "N2QwMGE4NjZmMjkzNGNhYWE4YWUyY2FkY2ZjZmQyY2I="


@rt.post("/CHANJET_CHECK.json")
async def response_chanjet():
    """绑定畅捷通消息接收地址"""
    return {"result": "success"}
