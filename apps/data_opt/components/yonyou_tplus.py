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


from ._base import BaseConnection#, aes_decrypt
from ..utils.json_manager import JSONManager
from apps.io_api.schemas import (
    BaseModel as PydanticModel,
    model_validator, AcceptMaterial, Field
)


FORMS = {
    "material": {
        "endpoint": "tplus/api/v2/inventory/Query",
        "field_map": {
            "ID":"ID", "Disabled":"是否停用", "Code":"编码", "Name":"名称",
            "Specification":"规格型号", "InventoryClassCode":"存货分类Code", "InventoryClassName":"存货分类Name",
            "UnitName":"单位Name", "BaseUnitName":"主计量单位Name",
            "UnitByManufactureName":"生产常用单位Name",
            "IsMaterial":"是否物料", "IsPurchase":"是否采购",
            "IsMadeSelf":"是否自制", "IsMadeRequest":"是否委外",
            "IsSuite":"是否套件",   # 虚拟件？
            "AvagCost":"平均成本", "Expired":"保质期", "ExpiredUnitName":"保质期单位",
            "IsNeedQualityInspection":"是否需要检验",
        },
        "base_filter": {
            "Disabled": False,
        },
    },
}

class TplusConnection(BaseConnection):
    
    def __init__(self, base_url: str = 'https://openapi.chanjet.com'):
        """
        初始化畅捷通连接
        Args:
            base_url: 畅捷通API基础URL
        """

        """
        credential JSON，用于存储畅捷通认证信息。文件结构如下：
        {
            "auth": {
                "app_key": "...",
                "app_secret": "...",
                "access_token": "...",
                "refresh_token": "...",
                "org_id": "",
                "_auth_at_": "2023-12-01 00:00:00"
            }
        """
        self.credential = JSONManager("cache/T+.json")
        self.base_url = base_url
        # 从缓存文件中读取认证信息，并将其设置为类实例属性
        self.credential_keys = ("app_key", "app_secret", "access_token", "refresh_token", "org_id", "_auth_at_")
        for key in self.credential_keys:
            setattr(self, key, self.credential.get("auth", {}).get(key, ""))
        super().__init__()


    def auth(self):
        assert self.access_token and self.refresh_token, "畅捷通token缺失"
        if self._auth_at_:
            expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)  # 假设token有效期为1天，其实最长可达6天
            if datetime.now() < expire_time:
                logger.info(f"畅捷通token未过期，有效期至: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                return self.access_token

        auth_response = self._session.get(f"{self.base_url}/auth/v2/refreshToken?grantType=refresh_token&refreshToken={self.refresh_token}", headers={
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "Content-Type": "application/json",
        })
        # 解析响应JSON
        auth_response = auth_response.json()
        auth_result = auth_response.get("result")
        if int(auth_response.get("code", 0)) == 200 and auth_result:
            # 更新认证时间
            self._auth_at_ = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.access_token = auth_result["access_token"]
            self.refresh_token = auth_result["refresh_token"]
            # 保存更新后的认证信息到缓存文件
            self.credential.update("auth", {
                "_auth_at_": self._auth_at_,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token})
            self.credential.save()
            logger.info(f"畅捷通token刷新成功")
            return self.access_token
        else:
            raise Exception(f"获取畅捷通token失败: {auth_response}")

    
    def _post(self, endpoint: str, data: dict):
        """
        发送POST请求到畅捷通API
        Args:
            endpoint: API端点路径
            data: 请求体数据
        Returns:
            响应JSON数据
        """
        self.auth()
        headers = {
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "openToken": self.access_token,
            "Content-Type": "application/json",
        }
        response = self._session.post(f"{self.base_url}/{endpoint}", headers=headers, json=data)
        response.raise_for_status()
        return response.json()



    def _get_paged_data(self, endpoint: str, field_map: dict=None, filter: dict=None, only_today: bool=False):
        field_map = field_map or {
            "ID":"ID", "Disabled":"是否停用", "Code":"编码", "Name":"名称",
            "Specification":"规格型号", "InventoryClassCode":"存货分类Code", "InventoryClassName":"存货分类Name",
            "UnitName":"单位Name", "BaseUnitName":"主计量单位Name", "UnitByManufactureName":"生产常用单位Name",
            "IsMaterial":"是否物料", "IsPurchase":"是否采购", "IsMadeSelf":"是否自制", "IsMadeRequest":"是否委外",
            "IsSuite":"是否套件",   # 虚拟件？
            "AvagCost":"平均成本", "Expired":"保质期", "ExpiredUnitName":"保质期单位",
            "IsNeedQualityInspection":"是否需要检验",
        }

        filter = filter or {
            "Disabled": False,
        }
        params = {
            "PageSize": 1000,
            "SelectFields":",".join(field_map.keys()),
        }

        if only_today:
            filter["UpdateDateBegin"] = datetime.now().strftime("%Y-%m-%d 00:00:00")
            filter["UpdateDateEnd"] = datetime.now().strftime("%Y-%m-%d 23:59:59")

        params.update(filter)

        # 调用POST方法发送请求
        
        response_json = self._post(endpoint=endpoint, data={"param": params})


    def data_list(self, form_name: str, field_map: dict=None, filter: dict=None, only_today: bool=False, pydantic_model: PydanticModel=None):
        """
        获取畅捷通数据列表
        Args:
            form_name: 表单名称
            field_map: 字段映射字典
            filter: 查询过滤条件
            only_today: 是否仅获取今天更新的数据
        Returns:
            数据列表
        """
        response_json = self._get_paged_data(endpoint=endpoint, field_map=field_map, filter=filter, only_today=only_today)
        return response_json.get("result", {}).get("list", [])