"""

"""
import json
import os
from typing import Dict, Any, Literal, Optional, NamedTuple
from datetime import datetime, timedelta, date
import pandas as pd

# from pydantic import InstanceOf

from config.settings import MYAPS_MAIN_DB


from ._base import (
    PydanticModel, JSONManager,
    logger,
    DataProcessor, globalconst, PROJECT_JSON_FILE, pdv,
    BaseConnection, ApsHelpers, convert_timeunit, clean_value,
    model_validator, Field,
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

MERGE_ENTRIY_KEY = '_entries_'
CACHE_ERP = PROJECT_JSON_FILE.get("erp", {})

class MaterialPullModel(AcceptMaterial):

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


class WorkcenterPullModel(AcceptWorkcenter):

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


class RoutePullModel(AcceptMatWc):

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


class BomPullModel(AcceptMatWcBom):

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


class StockPullModel(AcceptSupply):

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
        cleaned_values['category'] = 'MTS'
        cleaned_values['type'] = 'ST'
        cleaned_values['priority'] = 0
        cleaned_values['status'] = 'CRE'
        return cleaned_values


class MoPushModel(PydanticModel):
    """
    整理推送T+MO数据
    """
    ExternalCode: str = Field(None)
    BusiType: dict = Field(None)
    Department: dict = Field(None)
    Customer: dict = Field(None)
    StartDate: str = Field()
    FinishDate: str = Field()
    VoucherDate: str = Field()
    Memo: str = Field(None)
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
                    'IsMaterialRequest': True,    # 启用领料申请（明细行）
                })

        cleaned_values['ExternalCode'] = values['supplyno']
        cleaned_values['StartDate'] = values['dt_ordstart']
        cleaned_values['FinishDate'] = values['dt_ordend']
        cleaned_values['BusiType'] = {'Code': CACHE_ERP.get("$MoBusiType", "")}
        # cleaned_values['Department'] = {'Code': CACHE_ERP.get("$MoDepartment", "")}
        cleaned_values['VoucherDate'] = values['dt_ordstart']
        cleaned_values['IsMaterialRequest'] = True  # 启用领料申请（MO单据头）
        cleaned_values['Memo'] = values['vendorno']
        mod = {
            'Inventory': {'Code': values['materialno']},
            'Unit': {'Name': values.get('unit', "")},
            'Quantity': values['avail_qty'],
            'PreStartDate': values['dt_ordstart'],
            'PreFinishDate': values['dt_ordend'],
            'ManufactureOrderMaterialDetails': momd,
        }

        so = values.get('so')
        if so:
            partnerno = so.get('partnerno')
            # if partnerno:
            #     cleaned_values['Customer'] = {'Code': partnerno}
            cleaned_values['Customer'] = {'Code': partnerno}
            so_entryid = so.get('apiex_entryid')
            if so_entryid:
                # mod['SaleOrderCode'] = so.get('demandno', "")
                mod['idsourceVoucherType'] = "43"   # 销售订单
                mod['SourceVoucherDetailId'] = so_entryid

        cleaned_values['ManufactureOrderDetails'] = [mod]

        return cleaned_values


class RsPushModel(PydanticModel):
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
        cleaned_values['VoucherDate'] = values[MERGE_ENTRIY_KEY][0]['req_date']
        cleaned_values['BusiType'] = {"Code": "MR01"}
        cleaned_values['Department'] = {"Code": values.get('tplus_mo_data', {}).get('Department', {}).get('Code', "")}
        aps_demand_qty = {_['materialno']: _ for _ in values[MERGE_ENTRIY_KEY]}
        tplus_material_details = values["mo_material_details"]
        mr_details = []

        for md in tplus_material_details:
            mr = {}
            materialno = md['Inventory']['Code']
            mr['IdSourceVoucherType'] = "69"
            mr['SourceVoucherId'] = values['tplus_mo_id']
            # mr['SourceVoucherDetailId'] = values['tplus_mo_entryid']
            mr['SourceVoucherDetailId'] = md['ID']
            mr['Inventory'] = {'Code': materialno}
            mr['BaseQuantity'] = abs(aps_demand_qty.get(materialno, {}).get('req_qty', 0))
            mr_details.append(mr)
        cleaned_values['MaterialRequestDetails'] = mr_details
        return cleaned_values


class PrPushModel(PydanticModel):
    """
    整理推送T+请购单数据
    """
    ExternalCode: str = Field(None)
    Code: str = Field(None)
    VoucherDate: str = Field(None)
    RequisitionPerson: dict = Field(...)
    PurchaseRequisitionDetails: list[dict] = Field(...)

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        now_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        vo_date = datetime.now().strftime("%Y-%m-%d")
        cleaned_values = {
            'VoucherDate': None,    # 单据日期需要校验，不能晚于最早的物料需求日期
            'ExternalCode': now_stamp,
            'Code': now_stamp,
            'RequisitionPerson': {"Code": CACHE_ERP.get("$RequisitionPerson", "")}
        }
        # 处理直接传递列表的情况
        if isinstance(values, list):
            data_list = values

        else:
            # 处理通过 data 关键字参数传递的情况
            if 'data' in values:
                data_list = values['data']
            else:
                data_list = values
        
        prd = []
        earliest_req_date = vo_date
        for _ in data_list:
            # 确保日期字段是字符串格式
            # 校验并更新最早的物料需求日期            
            avail_date = _['avail_date']

            if isinstance(avail_date, (date, datetime)):
                avail_date = avail_date.strftime('%Y-%m-%d')
            
            if avail_date < earliest_req_date:
                earliest_req_date = avail_date
            prd.append({
                'Inventory': {'Code': _['materialno']},
                'Unit': {},
                'Quantity': _['avail_qty'],
                'RequireDate': avail_date,
            })

        cleaned_values['PurchaseRequisitionDetails'] = prd
        cleaned_values['VoucherDate'] = earliest_req_date
        return cleaned_values


class PullInterface(NamedTuple):
    endpoint: str
    field_map: Optional[dict[str, str]] = {}
    base_filter: Optional[dict[str, Any]] = {}
    remark: Optional[str] = ''


MaterialPullInterface = PullInterface(
    endpoint="/tplus/api/v2/inventory/Query",
    field_map={
        "ID": "ID", "Disabled": "是否停用", "Code": "编码", "Name": "名称", "Specification": "规格型号",
        "InventoryClassCode": "存货分类Code", "InventoryClassName": "存货分类Name",
        "UnitName": "单位Name", "BaseUnitName": "主计量单位Name", "UnitByManufactureName": "生产常用单位Name",
        "IsMaterial": "是否物料", "IsPurchase": "是否采购", "IsMadeSelf": "是否自制", "IsMadeRequest": "是否委外",
        "IsSuite": "是否套件", "IsPhantom": "是否虚拟件", "AvagCost": "平均成本", "Expired": "保质期", "ExpiredUnitName": "保质期单位",
        "IsNeedQualityInspection": "是否需要检验", "Ts": "时间戳",
    },
    base_filter={"Disabled": False, "IsMaterial": True, "Ts": None}
)

WorkcenterPullInterface = PullInterface(
    endpoint="/tplus/api/v2/WorkCenter/QueryPage",
    field_map={"ID": "ID", "Code": "编码", "Name": "名称", "Disabled": "是否停用"},
)

RoutingPullInterface = PullInterface(
    endpoint="/tplus/api/v2/bom/Query",  # 不用 "/tplus/api/v2/routing/Query", 因为 T+ 的工艺路线是抽象的，具体到物料的工艺路线是在 BOM 中定义的
    field_map={
        "ID": "ID", "Inventory / Code": "父件编码", "Inventory / Name": "父件名称", "BOMProcessDTOs / SequenceNumber": "加工顺序",
        "BOMProcessDTOs / Process / Code": "工序编码", "BOMProcessDTOs / Process / Name": "工序名称", "BOMProcessDTOs / Process / KeyProcess": "是否关键工序",
        "BOMProcessDTOs / Process / Workshop": "生产车间", "BOMProcessDTOs / Process / WorkCenter": "工作中心",
        "BOMProcessDTOs / Process / Equipment": "生产设备", "BOMProcessDTOs / Process / StandardWorkingHours": "标准工时",
    },
)

BomPullInterface = PullInterface(
    endpoint="/tplus/api/v2/bom/QueryPage",
    field_map={
        "ID": "ID", "Disabled": "是否停用", "Code": "父件编码", "Name": "父件名称", "Version": "版本号", "IsPhantom": "是否虚拟",
        "Unit / Name": "计量单位", "ProduceQuantity": "生产数量", "BOMChilds / Code": "子件编码", "BOMChilds / Name": "子件名称",
        "BOMChilds / Unit / Name": "子件计量单位", "BOMChilds / RequiredQuantity": "需用数量", "BOMChilds / WasteRate": "损耗率",
    },
)

StockPullInterface = PullInterface(
    endpoint="/tplus/api/v2/currentStock/Query",
    field_map={"InventoryCode": "存货编码", "ExistingQuantity": "现存量", "TS": "时间戳"},
    base_filter={"IsIncludeZero": True},
    remark="现存量查询 https://open.chanjet.com/docs/file/apiFile/tcloud/tjqt/xcl?id=30875，以 现存量字段 为库存数导入",
)

SingleMoQueryInterface = PullInterface(
    endpoint="/tplus/api/v2/ManufactureOrderOpenApi/GetVoucherDTO",
    field_map={"ID": "ID", "Code": "编码", "ExternalCode": "外部编码"},
)


# NewPoPullInterface = TplusPullInterface(
#     endpoint="/tplus/api/v2/PurchaseOrderOpenApi/FindVoucherList",
#     field_map={"ID": "ID", "Code": "编码", "ExternalCode": "外部编码"},
#     base_filter={"Status": "NEW"},
# )


class PushInterface(NamedTuple):
    endpoint: str
    remark: Optional[str] = ''


MoApproveInterface = PushInterface(
    endpoint="/tplus/api/v2/ManufactureOrderOpenApi/Audit",
)


MoCreateInterface = PushInterface(
    endpoint="/tplus/api/v2/ManufactureOrderOpenApi/Create",
)


RsCreateInterface = PushInterface(
    endpoint="/tplus/api/v2/MaterialRequestOpenApi/Create",
)

PrApproveInterface = PushInterface(
    endpoint="/tplus/api/v2/PurchaseRequisitionOpenApi/Audit",
)


PrCreateInterface = PushInterface(
    endpoint="/tplus/api/v2/PurchaseRequisitionOpenApi/Create",
)

PrDeleteInterface = PushInterface(
    endpoint="/tplus/api/v2/PurchaseRequisitionOpenApi/Delete",
)


class TplusConfig:
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
    }
    """
    def __init__(self, cache_file: str | JSONManager = PROJECT_JSON_FILE):
        if isinstance(cache_file, str):
            self.cache_file = JSONManager(cache_file)
        else:
            self.cache_file = cache_file
        cache_erp = self.cache_file.get("erp", {})
        self.base_url = cache_erp.get("base_url", "https://openapi.chanjet.com")
        self.token_expire_seconds = cache_erp.get("token_expire_seconds", 12 * 3600)     # 设token有效期为12hr
        # 默认分页大小，上限1000
        self.max_page_size = min(cache_erp.get("max_page_size", 1000), 1000)    


class TplusConnection(BaseConnection):
    
    def __init__(self, config: TplusConfig=TplusConfig()):
        """
        初始化畅捷通连接
        """
        super().__init__()
        self.config = config
        self.base_url = self.config.base_url
        self.cache_file = self.config.cache_file
        # 从缓存文件中读取认证信息，并将其设置为类实例属性
        self.credential_keys = ("app_key", "app_secret", "access_token", "refresh_token", "org_id", "_auth_at_")
        cache_erp = self.cache_file.get("erp", {})
        for key in self.credential_keys:
            setattr(self, key, cache_erp.get(key, ""))
        self._BOM_CODES = None  # 缓存已处理的BOM编码，用于取工艺路线（因为 T+ 的工艺路线是抽象的，具体到物料的工艺路线是在 BOM 中定义的，而只有通过具体BOM编号查询BOM时，才会展示工艺路线详情 


    def auth(self):
        assert self.access_token and self.refresh_token, "畅捷通token缺失"
        if self._auth_at_:
            expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=self.config.token_expire_seconds)
            if datetime.now() < expire_time:
                logger.debug(f"畅捷通token有效，有效期至：{expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                return self.access_token

        auth_response = self._session.get(
            url=f"{self.base_url}/auth/v2/refreshToken",
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
            logger.debug(f"畅捷通token刷新为：{self.access_token}")
            return self.access_token
        else:
            logger.fail("获取畅捷通token", auth_response, )
            raise Exception(auth_response.get("message", ""))


    def _get(self, endpoint: str, params: dict=None):
        # self.auth()
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
        self.auth()
        headers = {
            "appKey": self.app_key,
            "appSecret": self.app_secret,
            "openToken": self.access_token,
            "Content-Type": "application/json",
        }
        response = self._session.post(f"{self.base_url}{endpoint}", headers=headers, json=data)
        response.raise_for_status()
        return response


    def _pull_simple_data(self, pull_interface: PullInterface, filter: dict=None, pydantic_model: PydanticModel=None):
        self.auth()
        endpoint = pull_interface.endpoint
        field_map = pull_interface.field_map
        base_filter = pull_interface.base_filter
        params = {
            "PageIndex": 1,
            "PageSize": self.config.max_page_size,
            "SelectFields": ",".join(field_map.keys()),
            **base_filter,
        }
        if filter:
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
            
        if pydantic_model:
            # data_list = [pydantic_model(**item).model_dump(exclude_unset=True) for item in data_list]
            data_list = [pydantic_model(**item).model_dump(exclude_none=True) for item in data_list]
        return data_list


    def pull_material(self, filter: dict=None, pull_interface: PullInterface=MaterialPullInterface, pydantic_model: PydanticModel=MaterialPullModel):
        return self._pull_simple_data(pull_interface=pull_interface, filter=filter, pydantic_model=pydantic_model)
    
    
    def pull_workcenter(self, filter: dict=None, pull_interface: PullInterface=WorkcenterPullInterface, pydantic_model: PydanticModel=WorkcenterPullModel):
        return self._pull_simple_data(pull_interface=pull_interface, filter=filter, pydantic_model=pydantic_model)


    def pull_stock(self, filter: dict=None, pull_interface: PullInterface=StockPullInterface, pydantic_model: PydanticModel=StockPullModel):
        stock_data = self._pull_simple_data(pull_interface=pull_interface, filter=filter, pydantic_model=pydantic_model)
        if stock_data:
            timestamp = datetime.now().strftime('%m%d-%H%M')
            df = pd.DataFrame(stock_data)
            # 按materialno分组，avail_qty求和，其他字段取first
            sum_cols = ['avail_qty']
            first_cols = [col for col in df.columns if col not in ['materialno'] + sum_cols]
            agg_dict = {col: 'first' for col in first_cols}
            agg_dict.update({col: 'sum' for col in sum_cols})

            aggregated_stock = df.groupby('materialno').agg(agg_dict).reset_index()
            # 替换缺失值为None
            aggregated_stock = aggregated_stock.replace({pd.NA: None, pd.NaT: None, float('nan'): None})
            # 生成supplyno字段为materialno@timestamp
            aggregated_stock['supplyno'] = aggregated_stock['materialno'] + '@' + timestamp
            return aggregated_stock.to_dict(orient='records')
        else:
            return None


    def pull_routing(self, only_today: bool = False, pull_interface: PullInterface=RoutingPullInterface, pydantic_model: PydanticModel=RoutePullModel):
        bom_codes = self._BOM_CODES
        assert bom_codes, "请先拉取BOM数据，获取BOM CODES"
        self.auth()
        endpoint = pull_interface.endpoint
        field_map = pull_interface.field_map
        base_filter = pull_interface.base_filter
        params = {
            "PageIndex": 1,
            "PageSize": self.config.max_page_size,
            "SelectFields": ",".join(field_map.keys()),
            **base_filter,
        }       
        if only_today:
            today = datetime.now().strftime("%Y-%m-%d")
            params.update({"UpdateDateBegin": f"{today} 00:00:00", "UpdateDateEnd": f"{today} 23:59:59"})
        
        data_list = []
        # 使用线程池并行处理POST请求
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def process_route_data(data: dict, field_map: dict):
                """
                处理工艺路线数据，提取产品编码、产品名称、详情
                """
                flat_item = DataProcessor.expand_parent_child_data(data, 'BOMProcessDTOs')
                processed_data = []
                for row in flat_item:
                    processed_data.append({v: row.get(k) for k, v in field_map.items()})
                return processed_data

        def get_route_by_bomcode(bom_code):
            payload = {
                "dto": {"code": bom_code}
            }
            response = self._post(endpoint=endpoint, data=payload)
            bom_data = response.json()[0]     # 变量名没错，确实是 bom
            return process_route_data(bom_data, field_map=field_map)
        
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
                    logger.fail("BOM处理", bom_code, str(exc))
        
        self._BOM_CODES = None
        data_list = [pydantic_model(**item).model_dump() for item in data_list]
        return data_list


    def pull_bom(self, only_today: bool = False, pull_interface: PullInterface=BomPullInterface, pydantic_model: PydanticModel=BomPullModel):
        def process_bomdata(bomdata_list: list, field_map: dict):
            """
            处理BOM数据，提取产品编码、产品名称、组件编码、组件名称、组件数量
            """
            self._BOM_CODES = set[str]()
            processed_data = []
            for item in bomdata_list:
                self._BOM_CODES.add(item['Code'])
                flat_item = DataProcessor.expand_parent_child_data(item, 'BOMChilds')
                for row in flat_item:
                    processed_data.append({v: row.get(k) for k, v in field_map.items()})
            return processed_data
        
        self.auth()
        endpoint = pull_interface.endpoint
        field_map = pull_interface.field_map
        base_filter = pull_interface.base_filter
        params = {
            "PageIndex": 1,
            "PageSize": 100,    # 数据量太大，单次不宜太多。官方默认值为20，最大支持500
            **base_filter,
        }       
        if only_today:
            today = datetime.now().strftime("%Y-%m-%d")
            params.update({"UpdateDateBegin": f"{today} 00:00:00", "UpdateDateEnd": f"{today} 23:59:59"})

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
            data_list.extend(process_bomdata(raw_data, field_map=field_map))

        data_list = [pydantic_model(**item).model_dump() for item in data_list]
        return data_list


    def query_mo(self, index_value: str | int, filter_field: Literal['voucherID', 'voucherCode', 'externalCode']='voucherID') -> dict:
        """
        查询单个工单详情
        """
        self.auth()
        endpoint = SingleMoQueryInterface.endpoint
        payload = {"param": {filter_field: index_value}}
        response = self._post(endpoint=endpoint, data=payload)
        resp_json = response.json()
        try:
            return resp_json['data']
        except:
            return None
        
    
    def create_mo(self, supplyno: str, auto_push_rs: bool = True, remain_native_supplyno: bool = True, pydantic_model: PydanticModel=MoPushModel):
        """
        创建MO
        :param supplyno: APS 中的 PL号
        :param auto_push_rs: 是否自动推送领料申请
        :param remain_native_supplyno: 是否保留原生供应号，若为 false 则使用 T+ 生成的工单号作为 MO 供应号
        :return:
        """
        def approve_mo(tplus_moid):
            endpoint = MoApproveInterface.endpoint
            payload = {"param": {'voucherID': tplus_moid}}
            response = self._post(endpoint=endpoint, data=payload)
            return response.json()
        
        self.auth()
        endpoint = MoCreateInterface.endpoint
        # 材料需求
        demand_list = ApsHelpers.get_demand_datalist(demandno=supplyno)
        # PL及工序详情
        supplymo_detaildata = ApsHelpers.get_supplymo_detaildata(supplyno=supplyno, get_next_mo=True, get_origin_so=True)
        supplymo_detaildata['demand_list'] = demand_list
        # dto = pydantic_model(**supplymo_detaildata).model_dump(exclude_unset=True)
        dto = pydantic_model(**supplymo_detaildata).model_dump(exclude_none=True)
        if remain_native_supplyno:
            dto['Code'] = supplyno
        payload = {"dto": dto}
        logger.debug(f"向 T+ 推送生产加工单，发送数据：{json.dumps(payload, ensure_ascii=False)}")
        mo_create_response = self._post(endpoint=endpoint, data=payload)
        mo_create_response_json = mo_create_response.json()
        if str(mo_create_response_json['code']) == '0': # 响应错误码为0，MO 创建成功
            # 从响应中提取 data
            response_data = mo_create_response_json['data']
            tplus_mo_id = response_data['ID']
            tplus_mo_code = supplyno if remain_native_supplyno else response_data['Code']
            # 审批 MO ，要在领料申请前批准
            _x_a = approve_mo(tplus_moid=tplus_mo_id)
            # 查询推送成功的 MO 在 T+ 中的详情
            tplus_mo_data = self.query_mo(index_value=tplus_mo_id)
            # 从 T+ 中提取 MO 详情中的第一个详情记录的 ID 作为 _entryid
            tplus_mo_entryid = tplus_mo_data['ManufactureOrderDetails'][0]['ID']

            # 调用存储过程更改工单信息，❗一定放在最后一步，否则工单号变更太早，前面若有用原生供应号查询都会失败
            _x_c = ApsHelpers.pl_release_success(native_plno=supplyno, msg=mo_create_response_json['message'], msg_from='T+', mono=tplus_mo_code, _id=tplus_mo_id, _entryid=tplus_mo_entryid)
        else:
            _x_d = ApsHelpers.pl_release_failed(native_plno=supplyno, msg=mo_create_response_json['message'], push_data=payload, msg_from='T+')


    def push_rs(self, mdlist_or_supplyno: str | list[dict], tplus_mo_data_or_id: dict | str | int, pydantic_model:PydanticModel=RsPushModel):
        """
        创建领料申请
        🅰 mdlist_or_supplyno: 材料需求列表或工单号
        🅰 tplus_mo_data_or_id: T+ MO 数据 或 记录ID
        """
        endpoint = RsCreateInterface.endpoint
        if isinstance(mdlist_or_supplyno, str):
            rs_data = ApsHelpers.get_demand_datalist(demandno=mdlist_or_supplyno)     # 查询 指定工单号所需物料
            demandno = mdlist_or_supplyno
        else:
            rs_data = mdlist_or_supplyno
            demandno = rs_data[0]['demandno']

        if isinstance(tplus_mo_data_or_id, dict):
            mo_data = tplus_mo_data_or_id
        else:
            mo_data = self.query_mo(index_value=tplus_mo_data_or_id)

        processed_rsdata = DataProcessor.merge_common_fields(data=rs_data, merge_with=["demandno", "type", "status", "create_date"], entries_key=MERGE_ENTRIY_KEY)

        mo_id = mo_data['ID']
        mo_code = mo_data['Code']
        # mo_depart_code = mo_data.get('Department', {}).get('Code', '')
        tplus_mo_entryid = mo_data['ManufactureOrderDetails'][0]['ID']
        mo_material_details = mo_data['ManufactureOrderDetails'][0]['ManufactureOrderMaterialDetails']
        # mo_material_details_id = mo_material_details[0]['ID']

        processed_rsdata['tplus_mo_id'] = mo_id
        processed_rsdata['tplus_mo_entryid'] = tplus_mo_entryid
        processed_rsdata['tplus_mo_data'] = mo_data

        # processed_rsdata['mo_material_details_id'] = mo_material_details_id
        processed_rsdata['mo_material_details'] = mo_material_details

        dto = pydantic_model(**processed_rsdata).model_dump()
        payload = {"dto": dto}
        logger.debug(f"向 T+ 推送领料申请，发送数据：{json.dumps(payload, ensure_ascii=False)}")
        response = self._post(endpoint=endpoint, data=payload)
        rs_push_response_json = response.json()
        if str(rs_push_response_json['code']) == '0': # 创建成功
            ApsHelpers.rs_push_success(rsno=demandno, msg=rs_push_response_json['message'], msg_from='T+', _code=rs_push_response_json['data'].get('Code'), _id=rs_push_response_json['data'].get('ID'))
        else:
            ApsHelpers.rs_push_failed(rsno=demandno, msg=rs_push_response_json['message'], push_data=processed_rsdata, msg_from='T+')


    def push_pr(self, data_list: list[dict]=None, pydantic_model:PydanticModel=PrPushModel):
        """
        推送采购申请
        :param data_list: APS 中的 PR 数据
        """
        def approve_pr(tplus_pr_code):
            endpoint = PrApproveInterface.endpoint
            # payload = {"param": {'voucherID': tplus_pr_id}}
            payload = {"param": {'voucherCode': tplus_pr_code}}
            response = self._post(endpoint=endpoint, data=payload)
            response_json = response.json()
            if str(response_json['code']) == '0':
                logger.success("审批请购单", tplus_pr_code)
            else:
                logger.fail("审批请购单", tplus_pr_code, response_json['message'])
            return response_json
        
        if not data_list:
            data_list = ApsHelpers.get_new_pr_data()
            if not data_list:
                logger.debug("没有新的请购单数据")
                return

        agg_data_list = ApsHelpers.aggregate_pr_data(data_list)
        tplus_pr_data = pydantic_model(data=agg_data_list).model_dump(exclude_none=True)
        payload = {"dto": tplus_pr_data}
        logger.debug(f"向 T+ 推送请购单，发送数据：{json.dumps(payload, ensure_ascii=False)}")
        endpoint = PrCreateInterface.endpoint
        response = self._post(endpoint=endpoint, data=payload)
        pr_push_response_json = response.json()
        if str(pr_push_response_json['code']) == '0':
            tplus_pr_id = pr_push_response_json['data'].get('ID')
            tplus_pr_code = pr_push_response_json['data'].get('Code')
            for _ in data_list:
                ApsHelpers._pr_push_success(prno=_['supplyno'], msg=pr_push_response_json['message'], msg_from='T+', _code=tplus_pr_code, _id=tplus_pr_id)
            
            # 审批请购单
            approve_pr(tplus_pr_code=tplus_pr_code)
        
        else:
            for _ in data_list:
                ApsHelpers._pr_push_failed(prno=_['supplyno'], msg=pr_push_response_json['message'], msg_from='T+', push_data=payload)


    def delete_pr(self, tplus_pr_code: str):
        """
        删除采购申请（仅能删除未审核的）
        :param tplus_pr_code: T+ 采购申请编号
        """
        endpoint = PrDeleteInterface.endpoint
        payload = {"param": {'voucherCode': tplus_pr_code}}
        response = self._post(endpoint=endpoint, data=payload)
        response_json = response.json()
        if str(response_json['code']) == '0':
            logger.success("删除请购单", tplus_pr_code)
        else:
            logger.fail("删除请购单", tplus_pr_code, response_json['message'])
       
