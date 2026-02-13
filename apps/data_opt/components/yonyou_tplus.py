"""

"""
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from config.settings import MYAPS_MAIN_DB


from ._base import (
    PydanticModel,
    console_log, filelog_normal, filelog_error,
    DataProcessor, globalconst, CACHE_JSON, pdv,
    BaseConnection, convert_timeunit, clean_value,
    BaseModel as PydanticModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm,
    db_query, TSupply, TDemand
)



"""
以下模型适用于 清洗转换 从T+获取的数据用于向HAP发送
需要客户在HAP中填写的字段统一设为 Optional[str/int/...] = Field(None)。
在 @model_validator 中需要将：
无法通过处理原生数据获取的联合索引字段设为  "🈳❗"  占位，以保证能构成完整的联合索引
"""
class TplusPullMaterial(AcceptMaterial):

    size: Optional[str] = Field(None)   # 需要客户在HAP中填写的字段统一设为 None。
    candelay: Optional[str] = Field(None)   # 需要客户在HAP中填写的字段统一设为 None。
    lotsize: Optional[str] = Field(None)
    
    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        # values = super().model_valid(values)
        cleaned_values = {}
        cleaned_values['materialno'] = clean_value(values['编码'])
        cleaned_values['description'] = clean_value(values['名称'])
        cleaned_values['size'] = values['规格型号']
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
        # cleaned_values['candelay'] = globalconst.YesNoEnum.YES
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
        values = cleaned_values
        return values
# reset_default_values(TplusMaterial, required_fields=('materialno', 'description'))



class TplusPullWorkcenter(AcceptWorkcenter):

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



class TplusPullMatWc(AcceptMatWc):

    matver: Optional[str] = Field(None)
    itemno: Optional[str] = Field(None)
    basesec: Optional[int] = Field(None)
    workcenter: Optional[str] = Field(None)

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['materialno'] = values['父件编码']
        cleaned_values['matver'] = "🈳❗"
        cleaned_values['workcenter'] = values['工作中心']
        cleaned_values['itemno'] = values['工序编码']
        cleaned_values['sortno'] = clean_value(values['加工顺序'])
        # cleaned_values['basesec'] = clean_value(values[''])
        # cleaned_values['fixqty'] = values['']
        # cleaned_values['fixsec'] = values['']
        # cleaned_values['sf'] = values['']
        # cleaned_values['offsetsec'] = values['']
        # cleaned_values['rate'] = values['']
        return cleaned_values



class TplusPullMatWcBom(AcceptMatWcBom):

    matver: Optional[str] = Field(None)
    itemno: Optional[str] = Field(None)

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



class TplusPullStock(AcceptSupply):

    type: str = Field('ST')
    priority: int = Field(0)
    status: str = Field('CRE')

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cleaned_values = {}
        cleaned_values['materialno'] = values['存货编码']
        cleaned_values['supplyno'] = values['存货编码']
        cleaned_values['itemno'] = "stock"
        cleaned_values['avail_qty'] = values['现存量']
        cleaned_values['create_date'] = now
        cleaned_values['avail_date'] = now
        cleaned_values['dt_req'] = now
        return cleaned_values


class TplusPushMo(PydanticModel):
    """
    整理推送T+MO数据
    """
    ExternalCode: str = Field()
    StartDate: str = Field()
    FinishDate: str = Field()
    BusiType: dict = Field()
    Department: dict = Field()
    VoucherDate: str = Field()
    Memo: str = Field()
    IsMaterialRequest: bool = Field(True)
    ManufactureOrderDetails: list[dict] = Field()
    
    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}

        demand_list = values.get('demand_list')
        momd = []
        if demand_list:
            for demand in demand_list:
                momd.append({
                    'Inventory': {'Code': demand['materialno']},
                    'Unit': {'Name': demand.get('unit', "")},
                    'SonNeededQuantity': demand['req_qty'] * -1,
                    'SonScaleQuantity': demand['req_qty'] * -1,
                    'Quantity': demand['req_qty'] * -1,
                    'IsMaterialRequest': True,
                })


        cleaned_values['ExternalCode'] = values['supplyno']
        cleaned_values['StartDate'] = values['dt_ordstart']
        cleaned_values['FinishDate'] = values['dt_ordend']
        erp_config = CACHE_JSON.get("erp", {})
        cleaned_values['BusiType'] = {'Code': erp_config.get("$MoBusiType", "")}
        cleaned_values['Department'] = {'Code': erp_config.get("$MoDepartment", "")}
        cleaned_values['VoucherDate'] = values['dt_ordstart']
        cleaned_values['IsMaterialRequest'] = True
        cleaned_values['Memo'] = values['vendorno']
        cleaned_values['ManufactureOrderDetails'] = [
            {
                'Inventory': {'Code': values['materialno']},
                'Unit': {'Name': values.get('unit', "")},
                'Quantity': values['avail_qty'],
                'PreStartDate': values['dt_ordstart'],
                'PreFinishDate': values['dt_ordend'],
                'ManufactureOrderMaterialDetails': momd,
            }
        ]
        return cleaned_values


class TplusPushRs(PydanticModel):
    """
    整理推送T+领料申请数据
    """
    ExternalCode: str = Field()
    VoucherType: dict = Field()
    VoucherDate: str = Field()
    BusiType: dict = Field()
    Department: dict = Field()
    MaterialRequestDetails: list[dict] = Field()

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['ExternalCode'] = values['demandno']
        cleaned_values['VoucherType'] = {"Code": "ST1039"}
        cleaned_values['VoucherDate'] = values["_entries_"][0]['req_date']
        cleaned_values['BusiType'] = {"Code": "MR01"}
        erp_config = CACHE_JSON.get("erp", {})
        cleaned_values['Department'] = {"Code": erp_config.get("$MoDepartment", "")}

        mr_details = []
        for entry in values["_entries_"]:
            mr = {}
            mr['IdSourceVoucherType'] = "69"
            mr['SourceVoucherId'] = values['tplus_mo_id']
            mr['SourceVoucherDetailId'] = values['tplus_mo_entryid']
            mr['Inventory'] = {'Code': entry['materialno']}
            mr['BaseQuantity'] = entry['req_qty'] * -1
            mr_details.append(mr)
        cleaned_values['MaterialRequestDetails'] = mr_details
        return cleaned_values


class TplusPushPr(PydanticModel):
    """
    整理推送T+请购单数据
    """
    ExternalCode: str = Field()
    RequisitionPerson: dict = Field()
    PurchaseRequisitionDetails: list[dict] = Field()

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['ExternalCode'] = values['aupplyno']
        erp_config = CACHE_JSON.get("erp", {})
        cleaned_values['RequisitionPerson'] = {"Code": erp_config.get("$RequisitionPerson", "")}
        cleaned_values['PurchaseRequisitionDetails'] = []
        pass



class TplusConfig:
    CACHE_FILE = CACHE_JSON
    """
    ⬆️缓存文件用于存储畅捷通认证信息。文件包含如下结构用于T+的认证：
    {
        "erp": {
            "app_key": "...",
            "app_secret": "...",
            "access_token": "...",
            "refresh_token": "...",
            "org_id": "",
            "_auth_at_": "2023-12-01 00:00:00"
        }
    """
    BASE_URL = "https://openapi.chanjet.com"
    TOKEN_EXPIRE_SECONDS = 12 * 3600     # 设token有效期为12hr
    AUTH_ENDPOINT = "/auth/v2/refreshToken"
    # 默认分页大小，注意最大不得超过1000
    PAGE_SIZE = 1000

    _BOM_CODES = None  # 缓存已处理的BOM编码，用于取工艺路线（因为 T+ 的工艺路线是抽象的，具体到物料的工艺路线是在 BOM 中定义的，而只有通过具体BOM编号查询BOM时，才会展示工艺路线详情

    PULL_SOURCE = {
        "material": {
            "endpoint": "/tplus/api/v2/inventory/Query",
            "field_map": {
                "ID": "ID", "Disabled": "是否停用", "Code": "编码", "Name": "名称",
                "Specification": "规格型号", "InventoryClassCode": "存货分类Code", "InventoryClassName": "存货分类Name",
                "UnitName": "单位Name", "BaseUnitName": "主计量单位Name",
                "UnitByManufactureName": "生产常用单位Name",
                "IsMaterial": "是否物料", "IsPurchase": "是否采购",
                "IsMadeSelf": "是否自制", "IsMadeRequest": "是否委外",
                "IsSuite": "是否套件", "IsPhantom": "是否虚拟件",
                "AvagCost": "平均成本", "Expired": "保质期", "ExpiredUnitName": "保质期单位",
                "IsNeedQualityInspection": "是否需要检验",
                "Ts": "时间戳",
            },
            "base_filter": {
                "Disabled": False,
                "IsMaterial": True,
                "Ts": None
            },
            "pydantic_model": TplusPullMaterial,
        },

        "workcenter": {
            "endpoint": "/tplus/api/v2/WorkCenter/QueryPage",
            "field_map": {
                "ID": "ID", "Code": "编码", "Name": "名称", "Disabled": "是否停用"
            },
            "base_filter": {},
            "pydantic_model": TplusPullWorkcenter,
        },

        "route": {
            "endpoint": "/tplus/api/v2/bom/Query",  # 不用 "/tplus/api/v2/routing/Query", 因为 T+ 的工艺路线是抽象的，具体到物料的工艺路线是在 BOM 中定义的
            "field_map": {
                "ID": "ID", "Inventory / Code": "父件编码", "Inventory / Name": "名父件称",
                "BOMProcessDTOs / SequenceNumber": "加工顺序",
                "BOMProcessDTOs / Process / Code": "工序编码", "BOMProcessDTOs / Process / Name": "工序名称",
                "BOMProcessDTOs / Process / KeyProcess": "是否关键工序",
                "BOMProcessDTOs / Process / Workshop": "生产车间", "BOMProcessDTOs / Process / WorkCenter": "工作中心",
                "BOMProcessDTOs / Process / Equipment": "生产设备", "BOMProcessDTOs / Process / StandardWorkingHours": "标准工时",
            },
            "base_filter": {},
            "pydantic_model": TplusPullMatWc,
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
            "pydantic_model": TplusPullMatWcBom,
        },

        "stock": {
            "endpoint": "/tplus/api/v2/currentStock/Query",
            # 现存量查询 https://open.chanjet.com/docs/file/apiFile/tcloud/tjqt/xcl?id=30875，以 现存量字段 为库存数导入
            "field_map": {
                "InventoryCode": "存货编码",
                # "AvailableQuantity": "可用量",
                "ExistingQuantity": "现存量",
                "TS": "时间戳",
            },
            "base_filter": {
                "IsIncludeZero": True
            },
            "pydantic_model": TplusPullStock,
        },

        "workreport": {
            "endpoint": "/tplus/api/v2/reportQuery/GetReportData",
            # 工序汇报单列表查询 https://open.chanjet.com/docs/file/apiFile/tcloud/t+dj/t+gxhbd?id=32107
            "field_map": {},
            "base_filter": {},
            "pydantic_model": None,
        },

        "mo_single": {
            "endpoint": "/tplus/api/v2/ManufactureOrderOpenApi/GetVoucherDTO",
            "field_map": {
                "ID": "ID", "Code": "编码", "ExternalCode": "外部编码",
            },
            "base_filter": {},
            "pydantic_model": None,
        },
    }


    PUSH_TARGET = {
        "mo_single": {
            "endpoint": "/tplus/api/v2/ManufactureOrderOpenApi/Create",
            "pydantic_model": TplusPushMo,
        },

        "mo_approve": {
            "endpoint": "/tplus/api/v2/ManufactureOrderOpenApi/Audit",
            "pydantic_model": None,
        },

        "rs": { # 领料申请，supply RS
            "endpoint": "/tplus/api/v2/MaterialRequestOpenApi/Create",
            "pydantic_model": TplusPushRs,
        },

        "pr": { # 采购申请 supply PR
            "endpoint": "/tplus/api/v2/PurchaseRequisitionOpenApi/Create",
            "field_map": {
                # "[]": "PurchaseRequisitionDetails",

                "ExternalCode": "supplyno",
                # "Code": "supplyno",   # 注释掉，Code 字段不传，让 T+ 自行生成编码
                "RequisitionPerson / Code": "$RequisitionPerson",
                "PurchaseRequisitionDetails / Inventory / Code": "materialno",
                "PurchaseRequisitionDetails / Unit / Name": "unit",
                "PurchaseRequisitionDetails / Quantity": "avail_qty",
                "PurchaseRequisitionDetails / RequireDate": "avail_date",
                # "PurchaseRequisitionDetails / IdSourceVoucherType": "$IdSourceVoucherType",
                # "PurchaseRequisitionDetails / SourceVoucherCode": "dt_ordend",
                # "PurchaseRequisitionDetails / SourceVoucherDetailId": "dt_ordend",
            },
            "static_values": {
                "RequisitionPerson": CACHE_JSON.get("erp", {}).get("$PrRequisitionPerson", ""),
                "IdSourceVoucherType": "43",    # 来源单据的单据类型ID  43：销售订单  预测单：68
            },
        },
    }



class TplusConnection(BaseConnection):
    
    def __init__(self, config: TplusConfig=TplusConfig):
        """
        初始化畅捷通连接
        """
        self.config = config
        self.base_url = config.BASE_URL
        self.cache_file = config.CACHE_FILE
        # 从缓存文件中读取认证信息，并将其设置为类实例属性
        self.credential_keys = ("app_key", "app_secret", "access_token", "refresh_token", "org_id", "_auth_at_")
        for key in self.credential_keys:
            setattr(self, key, self.cache_file.get("erp", {}).get(key, ""))
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
            self.cache_file.update("erp", {
                "_auth_at_": self._auth_at_,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token})
            self.cache_file.save()
            console_log.info(f"✅ 畅捷通token刷新成功")
            return self.access_token
        else:
            filelog_error.error(f"🚫 获取畅捷通token失败: {auth_response}")
            raise Exception(f"🚫 获取畅捷通token失败: {auth_response}")



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


    def pull_from_source(self, source_name: str, filter: dict=None, only_today: bool=False, pydantic_model: PydanticModel=None, **kwargs):
        """
        获取畅捷通数据列表
        Args:
            source_name: 表单名称
            filter: 查询过滤条件，默认None，仅在material、workcenter、bom表单有效
            only_today: 是否仅获取今天更新的数据，默认False，对 route（工艺路线） 表单无效
        Returns:
            数据列表
        """
        self.auth()
        source_name = source_name.lower()
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

        if source_name in ('material', 'workcenter', 'stock'):
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
                ts_value = raw_data[-1].get("Ts") or raw_data[-1].get("TS")
                params["Ts"] = ts_value
                data_list.extend([{v: row.get(k) for k, v in field_map.items()} for row in raw_data])

        elif source_name == 'bom':
            params = {
                "PageIndex": 1,
                "PageSize": 100,    # 数据量太大，单次不宜太多。官方默认值为20，最大支持500
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

        elif source_name == 'route':
            bom_codes = self.config._BOM_CODES
            assert bom_codes, "请先拉取BOM数据，获取BOM CODES"
            data_list = []
            # 使用线程池并行处理POST请求
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def get_route_by_bomcode(bom_code):
                payload = {
                    "dto": {"code": bom_code}
                }
                response = self._post(endpoint=endpoint, data=payload)
                bom_data = response.json()[0]     # 变量名没错，确实是 bom
                return self._process_route_data(bom_data, field_map=field_map)
            
            # 创建线程池，最大线程数为10
            with ThreadPoolExecutor(max_workers=10) as executor:
                # 提交所有任务
                future_to_bom = {executor.submit(get_route_by_bomcode, bom_code): bom_code for bom_code in bom_codes}
                # 收集结果
                for future in as_completed(future_to_bom):
                    bom_code = future_to_bom[future]
                    try:
                        result = future.result()
                        data_list.extend(result)
                    except Exception as exc:
                        console_log.error(f"处理BOM编码 {bom_code} 时出错: {exc}")
            
            self.config._BOM_CODES = None
            
        elif source_name == 'workreport':
            params = {
                "pageIndex": 0,     # 这个接口的第一页是0，不是1。。。
                "pageSize": 1000,   # 这里必须用小驼峰，大驼峰会报错
                "selectFields": ",".join(field_map.keys()),
            }

        elif source_name == 'mo_single':
            # 这是查询单个mo的接口
            response = self._post(endpoint=endpoint, data={"param": filter})
            # filter 的值可以是：
            # filter = { "voucherID": 1 }
            # filter = { "voucherCode": "MO-2026-01-0008" }
            # filter = { "externalCode": "1464077493719531520" }
            resp_json = response.json()
            mo_data = resp_json['data']
            data_list = [mo_data]

        if pydantic_model:
            data_list = [pydantic_model(**item).model_dump() for item in data_list]
        return data_list


    def _process_route_data(self, data: dict, field_map: dict):
        """
        处理工艺路线数据，提取产品编码、产品名称、详情
        Args:
            route_data: 原始路由数据列表
        Returns:
            处理后的路由数据列表
        """
        flat_item = DataProcessor.expand_parent_child_data(data, 'BOMProcessDTOs')
        processed_data = []
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
        self.config._BOM_CODES = set[str]()
        processed_data = []
        for item in bomdata_list:
            self.config._BOM_CODES.add(item['Code'])
            flat_item = DataProcessor.expand_parent_child_data(item, 'BOMChilds')
            for row in flat_item:
                processed_data.append({v: row.get(k) for k, v in field_map.items()})
        return processed_data


    def push_into_target(self, target_name: str, push_data: dict | list[dict], use_nativeno: bool = False, **kwargs):
        """
        推送数据到T+
        Args:
            target_name: 目标名称
            push_data: APS数据库查询结果， MO为字典格式， RS、PR为列表格式先合并清洗
            use_nativeno: 是否使用 APS 原生编号，默认False
        Returns:

        """
        self.auth()
        target_name = target_name.lower()
        endpoint = self.config.PUSH_TARGET[target_name]['endpoint']
        pydantic_model = self.config.PUSH_TARGET[target_name].get('pydantic_model')
        
        # 先合并、清洗数据
        if target_name == 'rs':
            # 先合并一下表头，以适配 T+ 数据结构
            push_data = DataProcessor.merge_common_fields(data=push_data, merge_with=["demandno", "type", "status", "create_date"], entries_key="_entries_")  

            tplus_mo_id = kwargs['tplus_mo_id'] # 这个一定会有
            # 尝试从 kwargs 中提取 tplus_mo_entryid
            tplus_mo_entryid = kwargs.get('tplus_mo_entryid')
            # 如果提取不到，就尝试调用 T+ 接口查询 MO 记录
            if not (tplus_mo_id and tplus_mo_entryid):
                try:
                    mo_in_tplus = self.pull_from_source(source_name='mo_single', filter={"voucherID": tplus_mo_id})[0]
                    tplus_mo_id = mo_in_tplus['ID']
                    tplus_mo_entryid = mo_in_tplus['ManufactureOrderDetails'][0]['ID']
                except:
                    pass
            if not (tplus_mo_id and tplus_mo_entryid):
                # 如果调用接口查询也没有结果，就报错
                filelog_error.error(f"❌ 未在 T+ 中找到对应 MO 记录，demandno: {push_data['demandno']}，领料申请推送失败，对应工单：{push_data['demandno']}")
                return
            # 结果计入推送数据，以便后续通过字段映射的配置直接取值
            push_data['tplus_mo_id'] = tplus_mo_id
            push_data['tplus_mo_entryid'] = tplus_mo_entryid
        elif target_name == 'pr':
            pass


        if target_name in ('mo_single', 'rs', 'pr'):
            dto = pydantic_model(**push_data).model_dump()
            if use_nativeno:
                nativeno = push_data.get('supplyno') or push_data.get('demandno')
                dto['Code'] = nativeno
            payload = {"dto": dto}
            response = self._post(endpoint=endpoint, data=payload)
            return response
        elif target_name == 'mo_approve':
            payload = {"param": push_data}
            response = self._post(endpoint=endpoint, data=payload)
            return response
        else:
            raise ValueError(f"❌ 未知的目标名称: {target_name}")