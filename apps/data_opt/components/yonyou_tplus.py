"""
用友T+接口组件
文档：
所需接口和消息https://open.chanjet.com/docs/file/guide/commonContent/jcwd-yykt/yykt-sxjkhxx
https://open.chanjet.com/docs/file/learning
https://open.chanjet.com/docs/file/apiFile/tcloud/tjrzy/tplusguide
自建应用{"AppKey":"IomCbFyX","AppSecret":"375CA9BC57CBFE3095FDFD3AE4A1C516"}

{"SandBoxAppKey":"U6RWGjRY","SandBoxAppSecret":"875DDD26FD9733D2E62214B265503687","AppKey":"OCMvYMks","AppSecret":"11E80FE5812FFB4B2F663D3588734571"}

企业ID1241741476857608
2023年行业账套企业ID1233773658254206
获取token-v2版本 /financial/v2/auth/getUserToken
刷新开放平台token-新版 /auth/v2/refreshToken
物料清单查询/tplus/api/v2/bom/Query

"""
import json
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ._base import BaseConnection, aes_decrypt



_TPLUS_CACHE_FILE = Path(__file__).parent / "tplus_cache.json"


class TplusConfig():
    CHECK_TXT = "N2QwMGE4NjZmMjkzNGNhYWE4YWUyY2FkY2ZjZmQyY2I="
    AES_KEY = "0000000000000000"
    APP_ID = None
    APP_KEY = None
    APP_TICKET = None

    @classmethod
    def load(cls):
        if _TPLUS_CACHE_FILE.exists():
            try:
                with open(_TPLUS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                cls.APP_ID = data.get("app_id")
                cls.APP_KEY = data.get("app_key")
                cls.APP_TICKET = data.get("app_ticket")
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 从文件加载配置成功")
            except Exception as e:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 从文件加载配置失败: {e}")

    @classmethod
    def save(cls):
        try:
            data = {
                "app_id": cls.APP_ID,
                "app_key": cls.APP_KEY,
                "app_ticket": cls.APP_TICKET,
                "updated_at": datetime.now().isoformat()
            }
            with open(_TPLUS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 配置已保存到文件")
        except Exception as e:
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 保存配置到文件失败: {e}")

    @classmethod
    def update(cls, app_id: str, app_key: str, app_ticket: str):
        cls.APP_ID = app_id
        cls.APP_KEY = app_key
        cls.APP_TICKET = app_ticket
        cls.save()


rt = None
_router_initialized = False

def get_router():
    global rt, _router_initialized
    if rt is None:
        rt = APIRouter()
        _router_initialized = True

        @rt.get("/CHANJET_CHECK.txt")
        async def check_chanjet():
            """畅捷通白名单认证回调接口"""
            return PlainTextResponse(TplusConfig.CHECK_TXT)

        @rt.post("/cjt/msg")
        async def response_chanjet(request: Request):
            data = await request.json()
            try:
                encrypt_msg = data["encryptMsg"]
                msg_dict = aes_decrypt(encrypt_msg, TplusConfig.AES_KEY)
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 收到畅捷通消息: {msg_dict}")
                TplusConfig.APP_ID = msg_dict.get("appId")
                TplusConfig.APP_KEY = msg_dict.get("appKey")
                TplusConfig.APP_TICKET = msg_dict["bizContent"].get("appTicket")
                TplusConfig.save()
                
            except Exception as e:
                print(f"解密畅捷通消息失败: {e}")
            return {"result": "success"}
    return rt


class TplusConnection(BaseConnection):
    _instance_count = 0

    def __init__(self, app_id: str = None, app_key: str = None, app_ticket: str = None):
        TplusConnection._instance_count += 1
        if TplusConnection._instance_count == 1:
            get_router()

        if app_id is None or app_key is None or app_ticket is None:
            config_data = self._load_from_file()
            self.app_id = app_id or config_data.get("app_id")
            self.app_key = app_key or config_data.get("app_key")
            self.app_ticket = app_ticket or config_data.get("app_ticket")
        else:
            self.app_id = app_id
            self.app_key = app_key
            self.app_ticket = app_ticket
        super().__init__()

    def _load_from_file(self):
        if _TPLUS_CACHE_FILE.exists():
            try:
                with open(_TPLUS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 从文件加载配置失败: {e}")
        return {}