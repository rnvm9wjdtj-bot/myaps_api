"""
用友T+接口组件
文档：
所需接口和消息https://open.chanjet.com/docs/file/guide/commonContent/jcwd-yykt/yykt-sxjkhxx
https://open.chanjet.com/docs/file/learning
https://open.chanjet.com/docs/file/apiFile/tcloud/tjrzy/tplusguide

获取token-v2版本 /financial/v2/auth/getUserToken
刷新开放平台token-新版 /auth/v2/refreshToken
物料清单查询/tplus/api/v2/bom/Query

"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ._base import BaseConnection, aes_decrypt
from ..utils.json_manager import JSONManager



# rt = APIRouter()


# @rt.get("/CHANJET_CHECK.txt")
# async def check_chanjet():
#     """畅捷通白名单认证回调接口"""
#     return PlainTextResponse("N2QwMGE4NjZmMjkzNGNhYWE4YWUyY2FkY2ZjZmQyY2I=")

# @rt.post("/webhook/cjt/msg")
# async def response_chanjet(request: Request):
#     data = await request.json()
#     try:
#         encrypt_msg = data["encryptMsg"]
#         msg_dict = aes_decrypt(encrypt_msg, TplusConfig.AES_KEY)
#         print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 收到畅捷通消息: {msg_dict}")
#         TplusConfig.update(msg_dict)

        
#     except Exception as e:
#         print(f"解密畅捷通消息失败: {e}")
#     return {"result": "success"}



class TplusConnection(BaseConnection):
    
    def __init__(self, base_url: str = 'https://openapi.chanjet.com', credential: str = "chanjet"):
        """
        初始化畅捷通连接
        Args:
            base_url: 畅捷通API基础URL
            credential: JSON 文件名（默认："chanjet"），用于存储畅捷通认证信息。
                文件必须包含以下键值对：
                {
                    "app_key": "...",
                    "app_secret": "...",
                    "access_token": "...",
                    "refresh_token": "...",
                    "org_id": "",
                    "auth_at": "2023-12-01 00:00:00"
                }
        """
        self.base_url = base_url
        self.credential = JSONManager(f"cache/{credential}.json")
        # 从缓存文件中读取认证信息，并将其设置为类实例属性
        self.credential_keys = ("app_key", "app_secret", "access_token", "refresh_token", "org_id", "auth_at")
        for key in self.credential_keys:
            setattr(self, key, self.credential.get(key, ""))
        super().__init__()


    def auth(self):
        assert self.access_token and self.refresh_token, "畅捷通token缺失"
        if self.auth_at:
            expire_time = datetime.strptime(self.auth_at, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)  # 假设token有效期为1天，其实最长可达6天
            if datetime.now() < expire_time:
                return

        self._session.get(f"{self.base_url}/auth/v2/refreshToken?grantType=refresh_token&refreshToken={self.refresh_token}", headers={
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "Content-Type": "application/json",
        })
        # 解析响应
        auth_response = self._session.response.json()
        auth_result = auth_response.get("result")
        if int(auth_response["code"]) == 200 and auth_result:
            # 更新认证时间
            self.auth_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.access_token = auth_result["access_token"]
            self.refresh_token = auth_result["refresh_token"]
            # 保存更新后的认证信息到缓存文件
            self.credential.update("auth_at", self.auth_at)
            self.credential.update("access_token", self.access_token)
            self.credential.update("refresh_token", self.refresh_token)
        else:
            raise Exception(f"获取畅捷通token失败: {auth_response}")

    def _get_paged_data(self):
        pass