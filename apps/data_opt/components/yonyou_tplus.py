"""

"""
import json
import os
from typing import Dict, Any
from datetime import datetime, timedelta


from ._base import (
    console_log,
    DataProcessor, globalconst,
    BaseConnection, convert_timeunit, clean_value, reset_default_values,
    BaseModel as PydanticModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold
)
from globalobjects._defaults import ProjectDefaultValues as pdv
from ..utils.json_manager import JSONManager



"""
以下模型适用于 清洗转换 从T+获取的数据
用于向HAP发送
在 @model_validator 中需要将：
无法通过处理原生数据获取的联合索引字段设为  "🈳❗"  占位，以保证能构成完整的联合索引
非必填（数据库可空）字段（类变量）的默认值统一设为None，由客户在HAP中填写。
"""
class TplusMaterial(AcceptMaterial):
    
    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        # values = super().model_valid(values)
        cleaned_values = {}
        cleaned_values['materialno'] = clean_value(values['编码'])
        cleaned_values['description'] = clean_value(values['名称'])
        cleaned_values['size'] = clean_value(values['规格型号'])
        cleaned_values['plant'] = pdv.MAT_PLANT
        cleaned_values['planner'] = pdv.MAT_PLANNER
        cleaned_values['fifo'] = pdv.MAT_FIFO
        cleaned_values['leadday'] = pdv.MAT_LEADDAY_E if values['是否需要检验'] else pdv.MAT_LEADDAY_F
        cleaned_values['expday'] = convert_timeunit(values.get('保质期', 0), values['保质期单位'], 'day')
        cleaned_values['grday'] = 1 if values['是否需要检验'] else 0
        cleaned_values['abc'] = globalconst.AbcEnum.A if values['是否自制'] == 'True' else globalconst.AbcEnum.B
        cleaned_values['unit'] = clean_value(values['主计量单位Name'])
        cleaned_values['price'] = values['平均成本']
        cleaned_values['groupno'] = str(values['存货分类Name'])
        cleaned_values['type'] = globalconst.EfEnum.E if values['是否自制'] == 'True' else globalconst.EfEnum.F
        cleaned_values['phantom'] = globalconst.YesNoEnum.YES if values['是否虚拟件'] else globalconst.YesNoEnum.NO
        # cleaned_values['phantommin'] = values['']
        # cleaned_values['firmday'] = values['']
        # cleaned_values['daygap'] = values['']
        # cleaned_values['candelay'] = values['']
        # cleaned_values['lotsize'] = values['']
        # cleaned_values['lotfix'] = values['']
        # cleaned_values['lotmin'] = values['']
        # cleaned_values['lotmax'] = values['']
        # cleaned_values['lotround'] = values['']
        # cleaned_values['lotss'] = values['']
        # cleaned_values['lotpoint'] = values['']
        # cleaned_values['lottop'] = values['']
        # cleaned_values['planitem'] = values['']
        # cleaned_values['preday'] = values['']
        # cleaned_values['subday'] = values['']
        # cleaned_values['memo'] = values['']
        # cleaned_values['free1'] = values['']
        # cleaned_values['free2'] = values['']
        # cleaned_values['free3'] = values['']
        return cleaned_values
# reset_default_values(TplusMaterial, required_fields=('materialno', 'description'))



class TplusWorkcenter(AcceptWorkcenter):

    class Config:
        extra = 'allow'


    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['workcenter'] = values['编码']
        cleaned_values['workcentername'] = values['名称']
        # cleaned_values['pri_wc'] = values['']
        # cleaned_values['bottleneck'] = values['']
        # cleaned_values['sortno'] = values['']
        # cleaned_values['plant'] = values['']
        # cleaned_values['location'] = values['']
        # cleaned_values['finite'] = values['']
        # cleaned_values['type'] = values['']
        # cleaned_values['capnum'] = values['']
        # cleaned_values['capmax'] = values['']
        # cleaned_values['worker'] = values['']
        # cleaned_values['setupno'] = values['']
        # cleaned_values['grpno'] = values['']
        return cleaned_values
# reset_default_values(TplusWorkcenter, required_fields=('workcenter', 'workcentername'))



class TplusMatWc(AcceptMatWc):

    class Config:
        extra = 'allow'

    matver: str = Field(None)
    itemno: str = Field(None)
    basesec: str = Field(None)
    workcenter: str = Field(None)

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['materialno'] = values['料号']
        cleaned_values['matver'] = "🈳❗"
        cleaned_values['workcenter'] = "🈳❗"
        cleaned_values['itemno'] = values['工序编码']
        cleaned_values['sortno'] = clean_value(values['加工顺序'])
        # cleaned_values['basesec'] = clean_value(values[''])
        # cleaned_values['fixqty'] = values['']
        # cleaned_values['fixsec'] = values['']
        # cleaned_values['sf'] = values['']
        # cleaned_values['offsetsec'] = values['']
        # cleaned_values['rate'] = values['']
        return cleaned_values



class TplusMatWcBom(AcceptMatWcBom):

    matver: str = Field(None)
    itemno: str = Field(None)

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['productno'] = values['父件编码']
        cleaned_values['matver'] = "🈳❗"
        cleaned_values['itemno'] = "🈳❗"
        cleaned_values['materialno'] = values['子件编码']
        cleaned_values['qty'] = values['需用数量']
        # cleaned_values['offsethour'] = values['']
        # cleaned_values['mto'] = values['']
        cleaned_values['scrap'] = values['损耗率']
        # cleaned_values['alt'] = values['']
        cleaned_values['denominator'] = values['生产数量']
        cleaned_values['pu'] = values['计量单位'] or ''
        cleaned_values['cu'] = values['子件计量单位'] or ''
        # cleaned_values[''] = values['']
        return cleaned_values



class TplusConfig:
    BASE_URL = "https://openapi.chanjet.com"
    CREDENTIAL_FILE = f"cache/{os.getenv("CACHE_FILE")}"
    """
    ⬆️credential JSON，用于存储畅捷通认证信息，存放在项目根目录下的cache文件夹中，文件名在环境变量CACHE_FILE中指定。文件包含如下结构用于T+的认证：
    {
        "erp_auth": {
            "app_key": "...",
            "app_secret": "...",
            "access_token": "...",
            "refresh_token": "...",
            "org_id": "",
            "_auth_at_": "2023-12-01 00:00:00"
        }
    """
    TOKEN_EXPIRE_SECONDS = 24 * 3600     # 设token有效期为1天，其实最长可达6天
    AUTH_ENDPOINT = "/auth/v2/refreshToken"
    # 默认分页大小，注意最大不得超过1000
    PAGE_SIZE = 1000


    PULL_SOURCE = {
        "material": {
            "endpoint": "/tplus/api/v2/inventory/Query",
            "field_map": {
                "ID":"ID", "Disabled":"是否停用", "Code":"编码", "Name":"名称",
                "Specification":"规格型号", "InventoryClassCode":"存货分类Code", "InventoryClassName":"存货分类Name",
                "UnitName":"单位Name", "BaseUnitName":"主计量单位Name",
                "UnitByManufactureName": "生产常用单位Name",
                "IsMaterial":"是否物料", "IsPurchase":"是否采购",
                "IsMadeSelf":"是否自制", "IsMadeRequest":"是否委外",
                "IsSuite":"是否套件", "IsPhantom":"是否虚拟件",
                "AvagCost":"平均成本", "Expired":"保质期", "ExpiredUnitName":"保质期单位",
                "IsNeedQualityInspection":"是否需要检验",
                "Ts": "时间戳",
            },
            "base_filter": {
                "Disabled": False,
                "IsMaterial": True,
                "Ts": None
            },
            "pydantic_model": TplusMaterial,
        },

        "workcenter": {
            "endpoint": "/tplus/api/v2/WorkCenter/Query",
            "field_map": {
                "ID": "ID", "Code": "编码", "Name": "名称", "Disabled": "是否停用"
            },
            "base_filter": {},
            "pydantic_model": TplusWorkcenter,
        },

        "route": {
            "endpoint": "/tplus/api/v2/routing/Query",
            "field_map": {
                "ID": "ID", "Disabled": "是否停用", "Code": "料号", "Name": "名称",
                "RoutingDetails / JobSequence": "加工顺序",
                "RoutingDetails / Process / Code": "工序编码", "RoutingDetails / Process / Name": "工序名称",
            },
            "base_filter": {},
            "pydantic_model": TplusMatWc,
        },

        "bom": {
            "endpoint": "/tplus/api/v2/bom/QueryPage",
            "field_map": {
                "ID": "ID", "Disabled": "是否停用", "Code": "父件编码", "Name": "父件名称", "Version": "版本号",
                "IsPhantom": "是否虚拟", "Unit / Name": "计量单位", "ProduceQuantity": "生产数量",
                "BOMChilds / Code": "子件编码", "BOMChilds / Name": "子件名称",
                "BOMChilds / Unit / Name": "子件计量单位", "BOMChilds / RequiredQuantity": "需用数量", 
                "BOMChilds / WasteRate": "损耗率",
            },
            "base_filter": {},
            "pydantic_model": TplusMatWcBom,
        },

        "stock": {  # 现存量查询 https://open.chanjet.com/docs/file/apiFile/tcloud/tjqt/xcl?id=30875，以 现存量字段 为库存数导入
            "endpoint": "/tplus/api/v2/currentStock/Query",
            "field_map": {
                
            },
            "base_filter": {},
            "pydantic_model": None,
        },

        "workreport": { # 工序汇报单列表查询 https://open.chanjet.com/docs/file/apiFile/tcloud/t+dj/t+gxhbd?id=32107
            "endpoint": "/tplus/api/v2/workReport/Query",
            "field_map": {

            },
            "base_filter": {},
            "pydantic_model": None,
        },
    }


    PUSH_TARGET = {
        "mo": { # 生产加工单创建 https://open.chanjet.com/docs/file/apiFile/tcloud/t+dj/t+scjgd?id=31949
            "endpoint": "/tplus/api/v2/ManufactureOrderOpenApi/Create",
            "field_map": {
                "supplyno": "",
            },
        }
    }



class TplusConnection(BaseConnection):
    
    def __init__(self, config: TplusConfig=TplusConfig):
        """
        初始化畅捷通连接
        """
        self.config = config
        self.base_url = config.BASE_URL
        self.credential = JSONManager(config.CREDENTIAL_FILE)
        # 从缓存文件中读取认证信息，并将其设置为类实例属性
        self.credential_keys = ("app_key", "app_secret", "access_token", "refresh_token", "org_id", "_auth_at_")
        for key in self.credential_keys:
            setattr(self, key, self.credential.get("erp_auth", {}).get(key, ""))
        super().__init__(config)


    def auth(self):
        assert self.access_token and self.refresh_token, "畅捷通token缺失"
        if self._auth_at_:
            expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=self.config.TOKEN_EXPIRE_SECONDS)
            if datetime.now() < expire_time:
                console_log.info(f"✅ 畅捷通 token 仍在有效期内，有效期至: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                return self.access_token

        auth_response = self._session.get(
            url=f"{self.base_url}{self.config.AUTH_ENDPOINT}",
            params={
                "grantType": "refresh_token",
                "refreshToken": self.refresh_token,
            },
            headers={
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
            self.credential.update("erp_auth", {
                "_auth_at_": self._auth_at_,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token})
            self.credential.save()
            console_log.info(f"畅捷通token刷新成功")
            return self.access_token
        else:
            raise Exception(f"获取畅捷通token失败: {auth_response}")


    def _get(self, endpoint: str, params: dict=None):
        self.auth()
        response = self._session.get(f"{self.base_url}{endpoint}", headers={
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "Content-Type": "application/json",
        }, params=params)
        response.raise_for_status()
        return response


    def _post(self, endpoint: str, data: dict):
        """
        发送POST请求到畅捷通API
        Args:
            endpoint: API端点路径
            data: 请求体数据
        Returns:
            响应JSON数据
        """
        headers = {
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "openToken": self.access_token,
            "Content-Type": "application/json",
        }
        response = self._session.post(f"{self.base_url}{endpoint}", headers=headers, json=data)
        response.raise_for_status()
        return response


    def pull_from_source(self, source_name: str, filter: dict=None, only_today: bool=False, pydantic_model: PydanticModel=None):
        """
        获取畅捷通数据列表
        Args:
            source_name: 表单名称
            filter: 查询过滤条件，默认None，仅在material、workcenter表单有效
            only_today: 是否仅获取今天更新的数据，默认False，对 route（工艺路线） 表单无效
        Returns:
            数据列表
        """
        self.auth()
        endpoint = self.config.PULL_SOURCE[source_name]['endpoint']
        field_map = self.config.PULL_SOURCE[source_name]['field_map']
        pydantic_model = pydantic_model or self.config.PULL_SOURCE[source_name].get('pydantic_model')
        base_filter = self.config.PULL_SOURCE[source_name].get('base_filter', {})

        if filter:
            filter.update(base_filter)
        else:
            filter = base_filter or {}

        if only_today:
            today = datetime.now().strftime("%Y-%m-%d")
            filter["UpdateDateBegin"] = f"{today} 00:00:00"
            filter["UpdateDateEnd"] = f"{today} 23:59:59"

        if source_name in ('material', 'workcenter'):
            params = {
                "PageIndex": 1,
                "PageSize": self.config.PAGE_SIZE,
                "SelectFields": ",".join(field_map.keys()),
            }
            params.update(filter)

            data_list = []
            while True:
                response = self._post(endpoint=endpoint, data={"param": params})
                resp_json = response.json()
                try:
                    raw_data = resp_json['Data']
                except:
                    raw_data = resp_json
                if not raw_data:
                    break
                params["PageIndex"] += 1
                params["Ts"] = raw_data[-1]["Ts"]
                data_list.extend([{v: row.get(k) for k, v in field_map.items()} for row in raw_data])

        elif source_name == 'route':
            response = self._post(endpoint=endpoint, data={"param": {}})
            data_list = self._process_route_data(response.json(), field_map=field_map)

        elif source_name == 'bom':
            params = {
                "PageIndex": 1,
                "PageSize": 100,    # 数据量太大，单次不宜太多。官方默认值为20
            }
            params.update(filter)

            data_list = []

            while True:
                response = self._post(endpoint=endpoint, data={"param": params})
                resp_json = response.json()
                try:
                    raw_data = resp_json['Data']
                except:
                    raw_data = resp_json
                if not raw_data:
                    break
                params["PageIndex"] += 1

                data_list.extend(self._process_bomdata(raw_data, field_map=field_map))

        if pydantic_model:
            data_list = [pydantic_model(**item).model_dump() for item in data_list]
        return data_list


    def _process_route_data(self, routedata_list: list, field_map: dict):
        """
        处理工艺路线数据，提取产品编码、产品名称、详情
        Args:
            route_data: 原始路由数据列表
        Returns:
            处理后的路由数据列表
        """
        processed_data = []
        for item in routedata_list:
            flat_item = DataProcessor.expand_parent_child_data(item, 'RoutingDetails')
            for row in flat_item:
                processed_data.append({v: row.get(k) for k, v in field_map.items()})
        return processed_data


    def _process_bomdata(self, bomdata_list: list, field_map: dict):
        """
        处理BOM数据，提取产品编码、产品名称、组件编码、组件名称、组件数量
        Args:
            bom_data: 原始BOM数据列表
        Returns:
            处理后的BOM数据列表
        """
        processed_data = []
        for item in bomdata_list:
            flat_item = DataProcessor.expand_parent_child_data(item, 'BOMChilds')
            for row in flat_item:
                processed_data.append({v: row.get(k) for k, v in field_map.items()})
        return processed_data


    def push_into_target(self, target_name: str, data_list: list, pydantic_model: PydanticModel=None):
        pass