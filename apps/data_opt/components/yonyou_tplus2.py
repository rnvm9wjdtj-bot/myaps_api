"""
用友T+ 接口组件（新版本）

支持链式调用，如：tplus.mo(**{}).create()
"""
import json, time, inspect, asyncio
from typing import Dict, Any, Literal, Optional, NamedTuple, Type
from datetime import datetime, timedelta, date
import pandas as pd
from pydantic.v1.errors import cls_kwargs

from core.settings import MYAPS_MAIN_DB

from . import ApsPayloadSponsor, EventResultPoster
from ._base import (
    PydanticModel, JSONManager, 
    logger,
    DataProcessor, globalconst, PROJECT_JSON_FILE, pdv,
    convert_timeunit, clean_value,
    model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm,
    db_query, TSupply, TDemand, ExternalBaseConnection, BaseSource, BaseVoucher, InternalData, ExternalData,
)



MERGE_ENTRIY_KEY = '_entries_'
CACHE_ERP = PROJECT_JSON_FILE.get("erp", {})


#################################################################################
# 数据规范模型
#################################################################################
"""
以下模型适用于 清洗转换 从T+获取的数据用于向HAP发送
需要客户在HAP中填写的字段统一设为 Optional[str/int/...] = Field(None)。
在 @model_validator 中需要将：
无法通过处理原生数据获取的联合索引字段设为  "🈳❗"  占位，以保证能构成完整的联合索引
"""

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
    Memo: Optional[str] = Field(None)
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
        now_stamp = str(int(time.time() * 10000000))
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


#################################################################################
# 用友T+连接及配置
#################################################################################
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


class YonyouTplusConnection2(ExternalBaseConnection):
    """
    用友T+连接类（新版本）
    
    支持链式调用，如：tplus.mo(**{}).create()
    """


    def __init__(self, config: TplusConfig=TplusConfig()):
        """
        初始化畅捷通连接
        
        Args:
            config: TplusConfig实例
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


    async def auth(self):
        """
        异步认证连接
        """
        assert self.access_token and self.refresh_token, "畅捷通token缺失"
        if self._auth_at_:
            expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=self.config.token_expire_seconds)
            if datetime.now() < expire_time:
                logger.debug(f"畅捷通token有效，有效期至：{expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                return self.access_token

        # 获取新的异步会话
        async_session = None
        try:
            logger.debug("开始获取异步会话...")  # 临时日志，日后可删除
            async_session = await self._get_async_session()
            logger.debug(f"成功获取异步会话: {type(async_session).__name__}")  # 临时日志，日后可删除
            
            logger.debug(f"开始发送认证请求到: {self.base_url}/auth/v2/refreshToken")  # 临时日志，日后可删除
            try:
                auth_response = await async_session.get(
                    url=f"{self.base_url}/auth/v2/refreshToken",
                    params={
                        "grantType": "refresh_token",
                        "refreshToken": self.refresh_token,
                    },
                    headers={
                        "appKey": self.app_key,
                        "appSecret": self.app_secret,
                        "Content-Type": "application/json",
                    },
                    timeout=60.0  # 明确指定60秒超时
                )
                logger.debug(f"请求发送成功，状态码: {getattr(auth_response, 'status_code', '未知')}")  # 临时日志，日后可删除
            except Exception as request_error:
                logger.fail(f"认证请求失败: {type(request_error).__name__}: {str(request_error)}")
                import traceback
                logger.debug(f"请求失败详细错误：{traceback.format_exc()}")
                raise
            
            # 解析响应JSON
            if hasattr(auth_response, 'json'):
                if inspect.iscoroutinefunction(auth_response.json):
                    auth_response = await auth_response.json()
                else:
                    auth_response = auth_response.json()
            logger.debug(f"响应解析完成: {type(auth_response).__name__}")  # 临时日志，日后可删除
            
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
        except Exception as e:
            logger.fail("畅捷通认证失败", str(e))  # 临时日志，日后可删除
            import traceback
            logger.debug(f"认证失败详细错误：{traceback.format_exc()}")  # 临时日志，日后可删除
            raise
        finally:
            # 关闭异步会话
            if async_session:
                try:
                    if hasattr(async_session, 'aclose'):
                        await async_session.aclose()
                    elif hasattr(async_session, 'close'):
                        async_session.close()
                    logger.debug("异步会话已关闭")  # 临时日志，日后可删除
                except Exception as close_error:
                    logger.warning(f"关闭异步会话时出错: {close_error}")  # 临时日志，日后可删除


    async def _get(self, endpoint: str, params: dict=None):
        await self.auth()
        async_session = await self._get_async_session()
        
        try:
            headers = {
                "appKey": self.app_key,
                "appSecret": self.app_secret,
                "openToken": self.access_token,
                "Content-Type": "application/json",
            }
            response = await async_session.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
            if hasattr(response, 'json'):
                if inspect.iscoroutinefunction(response.json):
                    response = await response.json()
                else:
                    response = response.json()
            return response
        finally:
            if async_session:
                if hasattr(async_session, 'aclose'):
                    await async_session.aclose()
                elif hasattr(async_session, 'close'):
                    async_session.close()


    async def _post(self, endpoint: str, data: dict, max_retries: int = 5):
        """
        异步发送POST请求到畅捷通API，支持重试机制
        Args:
            endpoint: API端点路径
            data: 请求体数据
            max_retries: 最大重试次数，默认5次
        Returns:
            响应JSON数据
        """
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                await self.auth()
                async_session = await self._get_async_session()
                
                try:
                    headers = {
                        "appKey": self.app_key,
                        "appSecret": self.app_secret,
                        "openToken": self.access_token,
                        "Content-Type": "application/json",
                    }
                    response = await async_session.post(f"{self.base_url}{endpoint}", headers=headers, json=data)
                    if hasattr(response, 'status_code') and response.status_code >= 400 and response.status_code <= 500:
                        raise Exception(f"HTTP 错误: {response.status_code}")
                    if hasattr(response, 'json'):
                        if inspect.iscoroutinefunction(response.json):
                            response = await response.json()
                        else:
                            response = response.json()
                    return response
                finally:
                    if async_session:
                        if hasattr(async_session, 'aclose'):
                            await async_session.aclose()
                        elif hasattr(async_session, 'close'):
                            async_session.close()
            except Exception as e:
                retry_count += 1
                last_error = e
                if retry_count < max_retries:
                    wait_time = 2 * retry_count  # 递增等待时间
                    logger.warning_msg(f"API请求失败，{wait_time}秒后重试", endpoint, f"第{retry_count}/{max_retries}次重试: {str(e)}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.fail(f"API请求失败，已达最大重试次数", endpoint, str(e))
        
        # 所有重试都失败，抛出最后一个错误
        if last_error is None:
            raise Exception(f"API请求失败，已达最大重试次数，但未捕获到具体错误")
        raise last_error


    async def _pull_simple_data(self, endpoint: str, field_hints: dict[str, str], filter: dict=None):
        await self.auth()
        params = {
            "PageIndex": 1,
            "PageSize": self.config.max_page_size,
            "SelectFields": ",".join(field_hints.keys()),
            **filter,
        }
        if filter:
            params.update(filter)

        data_list = []
        while True:
            resp_json = await self._post(endpoint=endpoint, data={"param": params})
            try:
                raw_data = resp_json['Data']
            except:
                raw_data = resp_json
            if not raw_data:
                break
            params["PageIndex"] += 1
            ts_value = raw_data[-1].get("Ts") or raw_data[-1].get("TS")
            params["Ts"] = ts_value
            data_list.extend([{v: row.get(k) for k, v in field_hints.items()} for row in raw_data])
            
        return data_list


#################################################################################
# ERP对象管理器
#################################################################################

class TplusMaterial(BaseSource):

    _QUERY_BATCH_ENDPOINT = "/tplus/api/v2/inventory/Query"
    _PULL_PYDANTIC_MODEL = MaterialPullModel
    _FIELD_HINTS = {
        "ID": "ID", "Disabled": "是否停用", "Code": "编码", "Name": "名称", "Specification": "规格型号",
        "InventoryClassCode": "存货分类Code", "InventoryClassName": "存货分类Name",
        "UnitName": "单位Name", "BaseUnitName": "主计量单位Name", "UnitByManufactureName": "生产常用单位Name",
        "IsMaterial": "是否物料", "IsPurchase": "是否采购", "IsMadeSelf": "是否自制", "IsMadeRequest": "是否委外",
        "IsSuite": "是否套件", "IsPhantom": "是否虚拟件", "AvagCost": "平均成本", "Expired": "保质期", "ExpiredUnitName": "保质期单位",
        "IsNeedQualityInspection": "是否需要检验", "Ts": "时间戳",
    }

    @classmethod
    async def query_batch(cls, disabled: bool = False, is_material: bool = False, ts: str = None):
        """
        查询批量物料数据
        """
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()
        endpoint = cls._QUERY_BATCH_ENDPOINT
        filter = {
            "Disabled": disabled,
            "IsMaterial": is_material,
            "Ts": ts,
        }
        data = await cls._CONNECTION._pull_simple_data(
            endpoint=endpoint,
            field_hints=cls._FIELD_HINTS,
            filter=filter
        )

        return ExternalData(data=data, pydantic_model=cls._PULL_PYDANTIC_MODEL)



class TplusWorkcenter(BaseSource):

    _QUERY_BATCH_ENDPOINT = "/tplus/api/v2/WorkCenter/QueryPage"
    _PULL_PYDANTIC_MODEL = WorkcenterPullModel
    _FIELD_HINTS = {"ID": "ID", "Code": "编码", "Name": "名称", "Disabled": "是否停用"}

    @classmethod
    async def query_batch(cls):
        """
        查询批量工作中心数据
        """
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()
        endpoint = cls._QUERY_BATCH_ENDPOINT
        data = await cls._CONNECTION._pull_simple_data(
            endpoint=endpoint,
            field_hints=cls._FIELD_HINTS,
        )

        return ExternalData(data=data, pydantic_model=cls._PULL_PYDANTIC_MODEL)



class TplusStock(BaseSource):

    _QUERY_BATCH_ENDPOINT = "/tplus/api/v2/currentStock/Query"
    _PULL_PYDANTIC_MODEL = StockPullModel
    _FIELD_HINTS = {"InventoryCode": "存货编码", "ExistingQuantity": "现存量", "TS": "时间戳"}


    @classmethod
    async def query_batch(cls, is_include_zero: bool = False):
        """
        查询批量库存数据
        """
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()
        endpoint = cls._QUERY_BATCH_ENDPOINT
        data = await cls._CONNECTION._pull_simple_data(
            endpoint=endpoint,
            field_hints=cls._FIELD_HINTS,
            filter={"IsIncludeZero": is_include_zero}
        )

        return ExternalData(data=data, pydantic_model=cls._PULL_PYDANTIC_MODEL)

    
    async def pull(cls, is_include_zero: bool = False, pydantic_model: PydanticModel = None):
        """
        查询批量库存数据
        """
        stock_data: ExternalData = await cls.query_batch(is_include_zero)
        if stock_data.is_empty():
            return []
        else:
            pydantic_model = pydantic_model or cls._PULL_PYDANTIC_MODEL
            stock_data = stock_data.loads(pydantic_model=pydantic_model)
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
        
        
        
class TplusRouting(BaseSource):

    _QUERY_ENDPOINT = "/tplus/api/v2/bom/Query"
    _PULL_PYDANTIC_MODEL = RoutePullModel
    _FIELD_HINTS = {
        "ID": "ID", "Inventory / Code": "父件编码", "Inventory / Name": "父件名称", "BOMProcessDTOs / SequenceNumber": "加工顺序",
        "BOMProcessDTOs / Process / Code": "工序编码", "BOMProcessDTOs / Process / Name": "工序名称", "BOMProcessDTOs / Process / KeyProcess": "是否关键工序",
        "BOMProcessDTOs / Process / Workshop": "生产车间", "BOMProcessDTOs / Process / WorkCenter": "工作中心",
        "BOMProcessDTOs / Process / Equipment": "生产设备", "BOMProcessDTOs / Process / StandardWorkingHours": "标准工时",
    }

    @classmethod
    async def query_batch(cls, only_today: bool = False, filter: dict = None):
        """
        查询批量工艺路线数据
        """
        def process_route_data(data: dict, field_map: dict):
                """
                处理工艺路线数据，提取产品编码、产品名称、详情
                """
                flat_item = DataProcessor.expand_parent_child_data(data, 'BOMProcessDTOs')
                processed_data = []
                for row in flat_item:
                    processed_data.append({v: row.get(k) for k, v in field_map.items()})
                return processed_data

        async def get_route_by_bomcode_async(bom_code: str):
            try:
                payload = {
                    "dto": {"code": bom_code}
                }
                response = await self._CONNECTION._post(endpoint=endpoint, data=payload)
                # 修复：检查 response 是否为可等待对象
                if inspect.iscoroutine(response):
                    response = await response
                # 修复：直接使用 response 而不是调用 json()
                bom_data = response[0] if isinstance(response, list) and response else {}
                return process_route_data(bom_data, field_map=self._FIELD_HINTS)
            except Exception as e:
                logger.fail("BOM处理", bom_code, str(e))
                return []

        assert cls._CONNECTION, "未获得连接对象，请先注册"
        assert cls._CONNECTION._BOM_CODES, "请先拉取BOM数据，获取BOM CODES"
        await cls._CONNECTION.auth()

        endpoint = cls._QUERY_ENDPOINT
        params = {
            "PageIndex": 1,
            "PageSize": cls._CONNECTION.config.max_page_size,
            "SelectFields": ",".join(cls._FIELD_HINTS.keys()),
        } 
        if only_today:
            today = datetime.now().strftime("%Y-%m-%d")
            params.update({"UpdateDateBegin": f"{today} 00:00:00", "UpdateDateEnd": f"{today} 23:59:59"})
 
        data_list = []

        # 使用 asyncio.gather 并发处理
        tasks = [get_route_by_bomcode_async(bom_code) for bom_code in cls._CONNECTION._BOM_CODES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                data_list.extend(result)
            elif isinstance(result, Exception):
                logger.fail("BOM处理", "未知BOM", str(result))
        
        cls._CONNECTION._BOM_CODES = None

        return ExternalData(data=data_list, pydantic_model=cls._PULL_PYDANTIC_MODEL)

    @classmethod
    async def pull(cls, only_today: bool = False, pydantic_model: PydanticModel=None, filter: dict = None):
        """
        查询批量工艺路线数据
        """
        pydantic_model = pydantic_model or cls._PULL_PYDANTIC_MODEL
        routing_data: ExternalData = await cls.query_batch(only_today=only_today, filter=filter)
        if routing_data.is_empty():
            return []
        else:
            return routing_data.loads(pydantic_model=pydantic_model)
        

class TplusBom(BaseSource):
    
    _QUERY_BATCH_ENDPOINT = "/tplus/api/v2/bom/QueryPage"
    _FIELD_HINTS = {
        "ID": "ID", "Disabled": "是否停用", "Code": "父件编码", "Name": "父件名称", "Version": "版本号", "IsPhantom": "是否虚拟",
        "Unit / Name": "计量单位", "ProduceQuantity": "生产数量", "BOMChilds / Code": "子件编码", "BOMChilds / Name": "子件名称",
        "BOMChilds / Unit / Name": "子件计量单位", "BOMChilds / RequiredQuantity": "需用数量", "BOMChilds / WasteRate": "损耗率",
    }
    _PULL_PYDANTIC_MODEL = BomPullModel

    @classmethod
    async def query_batch(cls, only_today: bool = False, filter: dict = None):
        async def process_bomdata_async(bomdata_list: list, field_map: dict):   
            """
            处理BOM数据，提取产品编码、产品名称、组件编码、组件名称、组件数量
            """
            cls._CONNECTION._BOM_CODES = set[str]()
            processed_data = []
            for item in bomdata_list:
                cls._CONNECTION._BOM_CODES.add(item['Code'])
                flat_item = DataProcessor.expand_parent_child_data(item, 'BOMChilds')
                for row in flat_item:
                    processed_data.append({v: row.get(k) for k, v in field_map.items()})
            return processed_data

        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()

        params = {
            "PageIndex": 1,
            "PageSize": 100,    # 数据量太大，单次不宜太多。官方默认值为20，最大支持500
        }  
        if only_today:
            today = datetime.now().strftime("%Y-%m-%d")
            params.update({"UpdateDateBegin": f"{today} 00:00:00", "UpdateDateEnd": f"{today} 23:59:59"})
        
        if filter:
            params.update(filter)
        
        data_list = []

        while True:
            response = await cls._CONNECTION._post(endpoint=cls._QUERY_BATCH_ENDPOINT, data={"param": params})
            resp_json = await response.json()
            try:
                raw_data = resp_json['Data']
            except:
                raw_data = resp_json
            if not raw_data:
                break
            params["PageIndex"] += 1
            data_list.extend(await process_bomdata_async(raw_data, field_map=cls._FIELD_HINTS))

        return ExternalData(data=data_list, pydantic_model=cls._PULL_PYDANTIC_MODEL)



class TplusMo(BaseVoucher):
    """
    生产加工单
    """
    _QUERY_ENDPOINT = "/tplus/api/v2/ManufactureOrderOpenApi/GetVoucherDTO"
    _CREATE_ENDPOINT = "/tplus/api/v2/ManufactureOrderOpenApi/Create"
    _APPROVE_ENDPOINT = "/tplus/api/v2/ManufactureOrderOpenApi/Audit"
    # _PULL_PYDANTIC_MODEL = MoPullModel
    # _FIELD_HINTS = {"ID": "ID", "Code": "编码", "ExternalCode": "外部编码"}
    _PUSH_PYDANTIC_MODEL = MoPushModel
    _DOCUMENTATION_URL = None
    

    # def __init__(self, data=None):
    #     self.data = data or {}
        
    
    async def create(
        self,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None,
        remain_native_supplyno: bool = True
    ):
        assert self._CONNECTION, "未获得连接对象，请先注册"
        await self._CONNECTION.auth()

        endpoint = self._CREATE_ENDPOINT
        supplyno = self.raw_data.get('supplyno')
        demand_list = await _aps.get_demand_datalist(demandno=supplyno)
        supplymo_detaildata = await _aps.get_supplymo_detaildata(supplyno=supplyno, get_next_mo=True, get_origin_so=True)   
        supplymo_detaildata['demand_list'] = demand_list

        pydantic_model = pydantic_model or self._PUSH_PYDANTIC_MODEL
        # dto = InternalData(data=supplymo_detaildata).dump(pydantic_model=pydantic_model)
        dto = pydantic_model(**supplymo_detaildata).model_dump(exclude_none=True)

        if remain_native_supplyno:
            dto['Code'] = supplyno
        payload = {"dto": dto}
        
        mo_create_response_json = await self._CONNECTION._post(endpoint=endpoint, data=payload)
        if str(mo_create_response_json['code']) == '0': # 响应错误码为0，MO 创建成功
            response_data = mo_create_response_json['data']
            tplus_mo_id = response_data['ID']
            tplus_mo_code = supplyno if remain_native_supplyno else response_data['Code']
            # 审批 MO ，要在领料申请前批准
            _x_a = await self.approve(tplus_moid=tplus_mo_id)
            # 查询推送成功的 MO 在 T+ 中的详情
            tplus_mo_data = await self.query(index_value=tplus_mo_id).data_list[0]
            # 从 T+ 中提取 MO 详情中的第一个详情记录的 ID 作为 _entryid
            tplus_mo_entryid = tplus_mo_data['ManufactureOrderDetails'][0]['ID']
            # 调用存储过程更改工单信息，❗一定放在最后一步，否则工单号变更太早，前面若有用原生供应号查询都会失败
            _x_b = await _erp.mo_release_success(
                native_plno=supplyno,
                msg=mo_create_response_json['message'],
                msg_from='T+',
                mono=tplus_mo_code,
                _id=tplus_mo_id,
                _entryid=tplus_mo_entryid
            )
        else:
            _x_c = await _erp.mo_release_failed(
                native_plno=supplyno,
                msg=mo_create_response_json['message'],
                push_data=payload,
                msg_from='T+'
            )
        return self


    @classmethod
    async def approve(cls, tplus_moid: str):
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()

        endpoint = cls._APPROVE_ENDPOINT
        payload = {"param": {"VoucherID": tplus_moid}}
        resp_json = await cls._CONNECTION._post(endpoint=endpoint, data=payload)
        if str(resp_json['code']) == '0': # 响应错误码为0，MO 审批成功
            return True
        else:
            return False


    @classmethod
    async def query(
        cls,
        index_value: str | int,
        filter_field: Literal['voucherID', 'voucherCode', 'externalCode']='voucherID'
    ):
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()

        payload = {"param": {filter_field: index_value}}
        resp_json = await cls._CONNECTION._post(endpoint=cls._QUERY_ENDPOINT, data=payload)

        return ExternalData(data=resp_json['data'], pydantic_model=cls._PULL_PYDANTIC_MODEL)


# TODO: 
class TplusRs(BaseVoucher):
    """
    领料申请单
    """
    _CREATE_ENDPOINT = "/tplus/api/v2/MaterialRequestOpenApi/Create"
    _PUSH_PYDANTIC_MODEL = RsPushModel
    _DOCUMENTATION_URL = None

    def __init__(self, supplymo_data: dict):
        """
        初始化领料申请对象
        
        Args:
            supplymo_data: APS 供应数据
        """
        super().__init__(supplymo_data)


    async def create(self,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None
    ):
        assert self._CONNECTION, "未获得连接对象，请先注册"
        await self._CONNECTION.auth()
        endpoint = self._CREATE_ENDPOINT
        pydantic_model = pydantic_model or self._PUSH_PYDANTIC_MODEL

        rs_no = self.raw_data.get('supplyno')
        tplus_mo_id = self.raw_data.get('apiex_id')
        rs_data_list = await _aps.get_demand_datalist(demandno=rs_no)
        tplus_mo_data = await TplusMo.query(index_value=tplus_mo_id).first()

        processed_rsdata = DataProcessor.merge_common_fields(
            data=rs_data_list,
            merge_with=["demandno", "type", "status", "create_date"],
            entries_key=MERGE_ENTRIY_KEY
        )

        mo_id = tplus_mo_data['ID']
        # mo_code = tplus_mo_data['Code']
        # mo_depart_code = tplus_mo_data.get('Department', {}).get('Code', '')
        tplus_mo_entryid = tplus_mo_data['ManufactureOrderDetails'][0]['ID']
        mo_material_details = tplus_mo_data['ManufactureOrderDetails'][0]['ManufactureOrderMaterialDetails']
        # mo_material_details_id = mo_material_details[0]['ID']

        processed_rsdata['tplus_mo_id'] = mo_id
        processed_rsdata['tplus_mo_entryid'] = tplus_mo_entryid
        processed_rsdata['tplus_mo_data'] = mo_data
        
        # processed_rsdata['mo_material_details_id'] = mo_material_details_id
        processed_rsdata['mo_material_details'] = mo_material_details

        dto = pydantic_model(**processed_rsdata).model_dump()
        if dto["MaterialRequestDetails"]:   # 有领料申请详情
            payload = {"dto": dto}
            logger.debug(f"向 T+ 推送领料申请，发送数据：{json.dumps(payload, ensure_ascii=False)}")
            response = await self._post(endpoint=endpoint, data=payload)
            # 修复：检查 response 是否为可等待对象
            if inspect.iscoroutine(response):
                response = await response
            rs_push_response_json = response
            if str(rs_push_response_json['code']) == '0': # 创建成功
                await _erp.rs_release_success(rsno=rs_no, msg=rs_push_response_json['message'], msg_from='T+', _code=rs_push_response_json['data'].get('Code'), _id=rs_push_response_json['data'].get('ID'))
            else:
                await _erp.rs_release_failed(rsno=rs_no, msg=rs_push_response_json['message'], push_data=processed_rsdata, msg_from='T+')
        else:
            await _erp.rs_release_success(rsno=rs_no, msg="无领料申请详情", msg_from='APS')



class TplusPr(BaseVoucher):
    """
    请购单
    """
    _CREATE_ENDPOINT = "/tplus/api/v2/PurchaseRequisitionOpenApi/Create"
    _DELETE_ENDPOINT = "/tplus/api/v2/PurchaseRequisitionOpenApi/Delete"
    _APPROVE_ENDPOINT = "/tplus/api/v2/PurchaseRequisitionOpenApi/Audit"
    _PUSH_PYDANTIC_MODEL = PrPushModel
    _DOCUMENTATION_URL = None

    def __init__(self, event_data_list: list[dict]):
        """
        初始化请购单对象
        
        Args:
            event_data_list: T+ 请购单数据列表，由事件传入
        """
        self.raw_data = event_data_list


    async def create(self,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None
    ):
        assert self._CONNECTION, "未获得连接对象，请先注册"
        await self._CONNECTION.auth()
        endpoint = self._CREATE_ENDPOINT
        pydantic_model = pydantic_model or self._PUSH_PYDANTIC_MODEL
        return True








    @classmethod
    async def approve(cls, tplus_pr_code: str):
        assert cls._CONNECTION, "未获得连接对象，请先注册"
        await cls._CONNECTION.auth()

        endpoint = cls._APPROVE_ENDPOINT
        payload = {"param": {'voucherCode': tplus_pr_code}}
        response_json = await cls._CONNECTION._post(endpoint=endpoint, data=payload)
        if str(response_json['code']) == '0': # 审批成功
            logger.success("请购单审批", tplus_pr_code)
        else:
            logger.warning_msg(f"请购单{tplus_pr_code}审批失败" , response_json['message'])
