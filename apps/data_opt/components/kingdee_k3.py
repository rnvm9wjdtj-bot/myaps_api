# import pandas as pd

import os
from dataclasses import dataclass
import http.cookies
import asyncio
import inspect

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Literal, Optional, NamedTuple, Type, Callable

from globalobjects import logger as log_config

from . import ApsPayloadSponsor, EventResultPoster
from ._base import (
    PydanticModel, JSONManager, 
    logger,
    DataProcessor, globalconst, PROJECT_JSON_FILE, pdv,
    convert_timeunit, clean_value,
    model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm,
    db_query, TSupply, TDemand, ExternalBaseConnection, BaseSource, BaseVoucher, MoVoucher, RsVoucher, ExternalData, ExternalDataSet,
    async_rate_limit, async_service_operation, batch_service_operation
)



class K3Material(AcceptMaterial):

    class Config:
        extra = 'allow'
    
    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['materialno'] = clean_value(values['编码'])
        cleaned_values['description'] = clean_value(values['名称'])
        cleaned_values['size'] = clean_value(values['规格型号'])
        # cleaned_values['plant'] = values['生产车间']
        cleaned_values['planner'] = clean_value(values['计划员'])
        # cleaned_values['fifo'] = values['']
        cleaned_values['leadday'] = convert_timeunit(values.get('固定提前期', 0), values['固定提前期单位'], 'day')
        cleaned_values['expday'] = convert_timeunit(values.get('保质期', 0), values['保质期单位'], 'day')
        cleaned_values['grday'] = convert_timeunit(values.get('检验提前期', 0), values['检验提前期单位'], 'day')
        cleaned_values['abc'] = 'A' if values['物料属性'].replace(' ','') == '自制' else 'B'
        cleaned_values['unit'] = clean_value(values['生产单位'])
        cleaned_values['price'] = values['参考成本']
        # cleaned_values['groupno'] = values['']
        cleaned_values['type'] = 'E' if values['物料属性'].replace(' ','') == '自制' else 'F'
        cleaned_values['phantom'] = 'Y' if values['物料属性'].replace(' ','') == '虚拟' else 'N'
        # cleaned_values['phantommin'] = values['']
        # cleaned_values['firmday'] = values['']
        cleaned_values['daygap'] = values['批量拆分间隔天数']
        cleaned_values['candelay'] = 'Y' if values.get('允许延后天数', 0) > 0 else 'N'
        # cleaned_values['lotsize'] = values['']
        cleaned_values['lotfix'] = values['固定/经济批量']
        cleaned_values['lotmin'] = values['最小批量']
        cleaned_values['lotmax'] = values['最大批量']
        # cleaned_values['lotround'] = values['']
        cleaned_values['lotss'] = values['安全库存']
        cleaned_values['lotpoint'] = values['再订货点']
        cleaned_values['lottop'] = values['最大库存']
        # cleaned_values['planitem'] = values['']
        # cleaned_values['preday'] = values['']
        # cleaned_values['subday'] = values['']
        # cleaned_values['memo'] = values['']
        # cleaned_values['free1'] = values['']
        # cleaned_values['free2'] = values['']
        # cleaned_values['free3'] = values['']
        return cleaned_values
# reset_default_values(K3Material, required_fields=('materialno', 'description'))


class K3Config:
    """K3基础配置"""
    CACHE_JSON_FILE = PROJECT_JSON_FILE
    BASE_URL = "http://129.211.172.205:12980"
    ACCTID = "65a48b111c0197"
    LCID = "2052"
    USERNAME = "demo2"
    PASSWORD = "88888888"

    AUTH_ENDPOINT = "/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
    QUERY_ENDPOINT = "/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    
    # 默认分页大小，注意最大不得超过1000
    PAGE_SIZE = 1000

    # 最大返回行数，注意最大不得超过100000
    TOP_ROW_COUNT = 100000

    # 表单ID及字段映射
    PULL_SOURCE = {
        'material': {
            'form_id': 'BD_MATERIAL',
            'field_map': {
                "fMaterialId": "id", "fNumber": "编码", "fName": "名称",
                "fWorkShopId.fName": "生产车间", "fPlanerId.fName": "计划员",
                "fSpecification": "规格型号", "fCategoryId.fName": "存货类别",
                "fErpClsId.fCaption": "物料属性", "fProduceUnitId.fName": "生产单位",
                "fFixLeadTime": "固定提前期", "fFixLeadTimeType.fCaption": "固定提前期单位",
                "fExpPeriod": "保质期", "fExpUnit.fCaption": "保质期单位",
                "fCheckLeadTime": "检验提前期", "fCheckLeadTimeType.fCaption": "检验提前期单位",
                "fPlanIntervalsDays": "批量拆分间隔天数", "fCanDelayDays": "允许延后天数",
                "fMaxStock": "最大库存", "fPlanSafeStockQty": "安全库存", "fReOrderGood": "再订货点",
                "fEOQ": "固定/经济批量", "fRefCost": "参考成本", "fMaxQty": "最大批量", "fMinQty": "最小批量",
            },
            'base_filter': '',#'fUserOrgId=1',
            'pydantic_model': K3Material,
        },

        'bom': {
            'form_id': 'ENG_BOM',
            'field_map': {
                "fID": "父项id", "fNumber": "BOM版本", "fMaterialId.fNumber": "父项物料编码", "fMaterialId.fName": "父项物料名称",
                "fUnitId.fName": "父项物料单位", "fQty": "批量", "fBaseUnitId.fName": "父项基本单位",
                "fTreeEntity_fEntryId": "子项明细id",
                "fMaterialIdChild.fNumber": "子项物料编码", "fChildBaseUnitID.fName": "子项基本单位",
                "fChildUnitId.fName": "子项单位", "fNumerator": "用量:分子", "fDenominator": "用量:分母",
                "fBaseFixscrapQty": "基本单位固定损耗", "fBaseFixscrapQtyLot": "基本单位固定损耗数量"
            },
            'pydantic_model': None,
        },

        'workcenter': {
            'form_id': 'ENG_WORKCENTER',
            'field_map': {
                "fID": "id", "fNumber": "编码", "fName": "名称", "fDeptId.fName": "所属部门"
            },
            'pydantic_model': None,
        },

        'route': {
            'form_id': 'ENG_ROUTE',
            'field_map': {
                "fID": "父项id", "fNumber": "编码", "fName": "名称", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fProduceType.fCaption": "生产类型", "fApproveDate": "审核日期", "fForbidDate": "禁用日期",
                "fUnitId.fName": "单位", "fRouteGroupId.fName": "工艺路线分组",
                "fSubEntity_fDetailId": "子项明细id",
                "fWorkCenterId.fNumber": "工作中心", "fWorkCenterId.fName": "工作中心名称",
                "fOperNumber": "工序号", "fProcessId.fNumber": "工序编码", "fProcessId.fName": "工序名称"
            },
            'pydantic_model': None,
        },

        "so": {
            'form_id': 'SAL_SALEORDER',
            'field_map': {
                "fSaleOrderEntry_fEntryId": "子项明细id", "fSaleOrderEntry_fSeq": "序号", "fBillNo": "单据编号", "fModifyDate": "最后修改日期",
                "fCloseStatus.fCaption": "关闭状态", "fMrpCloseStatus.fCaption": "业务关闭", "fDocumentStatus.fCaption": "单据状态",
                "fDate": "日期", "fDeliveryDate": "要货日期", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fQty": "销售数量", "fUnitID.fName": "销售单位", "fBaseUnitId.fName": "基本单位",
            },
            'pydantic_model': None,
        },

        "mo": {
            'form_id': 'PRD_MO',
            'field_map': {
                "fId": "id", "fBillNo": "单据编号", "fDocumentStatus.fCaption": "单据状态", "fDate": "日期",
                "fTreeEntity_fEntryId": "子项明细id",
                "fTreeEntity_fSeq": "序号", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fQty": "数量", "fUnitId.fName": "单位", "fWorkshopId.fName": "生产车间",
                "fPlanStartDate": "计划开工时间", "fPlanFinishDate": "计划完工时间",
                "fScheduleStartTime": "排程开工时间", "fScheduleFinishTime": "排程完工时间",
                "fCancelDate": "作废日期",
                "fStatus.fCaption": "业务状态", "fPickMtrlStatus.fCaption": "领料状态",
                "fReqSrc.fCaption": "需求来源", "fSaleOrderId": "销售订单ID",
                "fSaleOrderEntryId": "销售订单子项ID", "fSaleOrderNo": "销售订单编号", "fSaleOrderEntrySeq": "需求单据行号",
                "fSrcBillNo": "源单编号", "fSrcSplitBillNo": "源拆分订单编号",
                "fMemoItem": "备注", "fBillType.fName": "单据类型",
            },
            'pydantic_model': None,
        },

        "stock": {
            'form_id': 'STK_Inventory',
            'field_map': {
                "fID": "id", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fStockLocId": "仓位", "fLot": "批号", "fStockOrgId": "库存组织", "fBomId.fNumber": "BOM版本",
                "fBaseUnitId.fName": "基本单位", "fStockUnitId.fName": "库存主单位", "fSecUnitId.fName": "库存辅单位",
                "fBaseQty": "库存量(基本单位)", "fQty": "库存量(主单位)", "fSecQty": "库存量(库存辅单位)",
                "fAvbQty": "可用量(主单位)", "fBaseAvbQty": "可用量(基本单位)", "fSecAVBQty": "可用量(库存辅单位)",
                "fUpdateTime": "最后更新时间",
            },
            'pydantic_model': None,
        },
    }


    PUSH_TARGET = {


    }


class KingdeeK3Connection(ExternalBaseConnection):

    def __init__(self, config: K3Config=K3Config):
        self.base_url = config.BASE_URL
        self.acctid = config.ACCTID
        self.username = config.USERNAME
        self.password = config.PASSWORD
        self.lcid = config.LCID
        self.config = config
        self._cookie = None
        self._cookie_expire = None
        self._auth_lock = asyncio.Lock()
        super().__init__()


    @classmethod
    def _parse_cookies(cls, set_cookie_header: str) -> tuple[str, datetime]:
        try:
            cookie_jar = http.cookies.SimpleCookie()
            cookie_jar.load(set_cookie_header)
            # 提取主要Cookie值
            cookie_parts = set_cookie_header.split(';')
            if len(cookie_parts) < 4:
                raise ValueError("Cookie格式不正确")
            cookie_value = cookie_parts[0] + ';' + cookie_parts[3].split(',')[1].strip()
            # 解析过期时间
            expire_str = cookie_parts[1].split('=')[1]
            # 解析为GMT时间
            gmt_time = datetime.strptime(expire_str, "%a, %d-%b-%Y %H:%M:%S %Z")
            # 添加GMT时区信息
            gmt_timezone = timezone(timedelta(hours=0), name='GMT')
            gmt_time = gmt_time.replace(tzinfo=gmt_timezone)
            # 转换为系统默认时区时间
            expire_time = gmt_time.astimezone()
            logger.debug(f"Cookie解析成功，GMT过期时间{gmt_time}，系统时区过期时间{expire_time}")
            return cookie_value, expire_time
        except (IndexError, ValueError, http.cookies.CookieError) as e:
            raise ConnectionError(f"Cookie解析失败: {e}")


    async def _post(self, endpoint: str, data: dict):
        """
        异步发送POST请求到金蝶K3 API
        
        使用父类的会话复用、自适应超时和增强重试机制。
        
        Args:
            endpoint: API端点路径
            data: 请求体数据
            
        Returns:
            响应JSON数据
            
        Raises:
            Exception: 请求失败时抛出异常
        """
        await self.auth()
        async_session = await self._get_async_session()
        
        async def make_request():
            headers = {
                "Cookie": self._cookie,
                "Content-Type": "application/json",
            }
            response = await async_session.post(
                f"{self.base_url}{endpoint}", 
                headers=headers, 
                json=data,
                timeout=self._read_timeout
            )
            return response
        
        response = await self.execute_with_timeout_protection(
            make_request,  # 传递函数引用而不是协程对象，支持重试
            f"POST {endpoint}"
        )
        
        response_json = response.json()
        # TODO 解析K3返回结果
        if hasattr(response, 'status_code'):
            status_code = response.status_code
            if status_code >= 500 and status_code < 600:
                if isinstance(response_json, dict):
                    err_msg = response_json.get("message") or status_code
                else:
                    err_msg = status_code
                raise Exception(f"HTTP 服务器错误: {err_msg}")

        return response_json
        

    async def auth(self, force: bool = False, max_retries: int = 5):
        """
        异步认证连接，支持重试机制
        
        Args:
            force: 是否强制刷新认证
            max_retries: 最大重试次数
            
        Returns:
            str: Cookie值
        """
        current_time = datetime.now().astimezone()
        
        if not force and self._cookie and self._cookie_expire:
            if (current_time + timedelta(minutes=15)) < self._cookie_expire:
                logger.debug(f"金蝶K3 Cookie有效，有效期至：{self._cookie_expire.strftime('%Y-%m-%d %H:%M:%S')}")
                return self._cookie
        
        async with self._auth_lock:
            # current_time = datetime.now().astimezone()
            if not force and self._cookie and self._cookie_expire:
                if (current_time + timedelta(minutes=15)) < self._cookie_expire:
                    logger.debug(f"金蝶K3 Cookie有效（锁后复检），有效期至：{self._cookie_expire.strftime('%Y-%m-%d %H:%M:%S')}")
                    return self._cookie
            
            retry_count = 0
            last_error = None
            async_session = None
            
            while retry_count < max_retries:
                try:
                    async_session = await self._get_async_session()
                    
                    try:
                        response = await async_session.post(
                            f"{self.base_url}{self.config.AUTH_ENDPOINT}",
                            data={
                                "acctid": self.acctid,
                                "username": self.username,
                                "password": self.password,
                                "lcid": self.lcid,
                            },
                            timeout=30.0
                        )
                    except Exception as request_error:
                        logger.fail(f"金蝶K3认证请求失败: {type(request_error).__name__}: {str(request_error)}")
                        raise
                    
                    if hasattr(response, 'raise_for_status'):
                        if inspect.iscoroutinefunction(response.raise_for_status):
                            await response.raise_for_status()
                        else:
                            response.raise_for_status()
                    
                    set_cookie = response.headers.get('Set-Cookie')
                    if not set_cookie:
                        raise ConnectionError("响应中缺少Set-Cookie头")
                    
                    cookie_value, expire_time = self._parse_cookies(set_cookie)
                    self._cookie = cookie_value
                    self._cookie_expire = expire_time
                    
                    if async_session and hasattr(async_session, 'headers'):
                        async_session.headers.update({
                            "Cookie": self._cookie,
                        })
                    
                    logger.success("金蝶K3认证", f"Cookie有效期至：{expire_time.strftime('%Y-%m-%d %H:%M:%S')}")

                    # 注意：不关闭会话 — _get_async_session() 返回的是基类缓存的共享会话，
                    # 会话生命周期由连接池管理（见 _base.py _get_async_session），
                    # 手动关闭会中断其他协程正在进行的请求。
                    return self._cookie
                    
                except Exception as e:
                    last_error = e
                    retry_count += 1
                    logger.warning(f"金蝶K3认证失败（第{retry_count}/{max_retries}次）: {str(e)}")

                    if retry_count >= max_retries:
                        break
                    
                    await asyncio.sleep(2 ** retry_count)
            
            logger.fail("金蝶K3认证", str(last_error))
            raise last_error


    # @sync_rate_limit()
    # async def pull_from_source(self, source_name: str, filter_string: str=None, only_today: bool=False, pydantic_model: PydanticModel=None):
    #     await self.auth()
    #     base_filterstring = self.config.PULL_SOURCE[source_name].get('base_filter') or "1=1"
    #     pydantic_model = pydantic_model or self.config.PULL_SOURCE[source_name].get('pydantic_model')
    #     if filter_string:
    #         filter_string = f"{filter_string} AND {base_filterstring}"
    #     else:
    #         filter_string = base_filterstring

    #     if only_today:
    #         today = datetime.now().strftime('%Y-%m-%d')
    #         filter_string = f"{filter_string} AND (( `fCreateDate` >= '{today} 00:00:00' AND `fCreateDate` <= '{today} 23:59:59' ) OR ( `fModifyDate` >= '{today} 00:00:00' AND `fModifyDate` <= '{today} 23:59:59' ))"
    #     k3_fields = set(self.config.PULL_SOURCE[source_name]['field_map'].keys())
    #     to_fields = [self.config.PULL_SOURCE[source_name]['field_map'][k] for k in k3_fields]

    #     start_row = 0
    #     page_size = self.config.PAGE_SIZE
    #     data_list = []
    #     async_session = None
        
    #     try:
    #         async_session = await self._get_async_session()
            
    #         while True:
    #             response = await async_session.post(
    #                 f"{self.base_url}{self.config.QUERY_ENDPOINT}",
    #                 json={
    #                     "data": {
    #                         "FormId": self.config.PULL_SOURCE[source_name]['form_id'],
    #                         "FieldKeys": ",".join(k3_fields),
    #                         "FilterString": filter_string,
    #                         "StartRow": start_row,
    #                         "Limit": page_size,
    #                         "TopRowCount": self.config.TOP_ROW_COUNT,
    #                         "SubSystemId": ""
    #                     }
    #                 },
    #                 timeout=self._read_timeout
    #             )
                
    #             if hasattr(response, 'text'):
    #                 if inspect.iscoroutinefunction(response.text):
    #                     response_text = await response.text()
    #                 else:
    #                     response_text = response.text
    #             else:
    #                 response_text = str(response)
                
    #             if 'ErrorCode' in response_text:
    #                 logger.fail("K3查询", "", response_text)
    #                 break
                
    #             if hasattr(response, 'json'):
    #                 if inspect.iscoroutinefunction(response.json):
    #                     raw_data = await response.json()
    #                 else:
    #                     raw_data = response.json()
    #             else:
    #                 raw_data = response
                
    #             data = []
    #             row_count = len(raw_data)
    #             for row in raw_data:
    #                 data.append({
    #                     to_fields[i]: row[i]
    #                     for i in range(len(k3_fields))
    #                 })
    #             data_list.extend(data)
    #             if row_count < page_size:
    #                 break
    #             start_row += page_size
    #     finally:
    #         if async_session:
    #             if hasattr(async_session, 'aclose'):
    #                 await async_session.aclose()
    #             elif hasattr(async_session, 'close'):
    #                 async_session.close()

    #     if pydantic_model:
    #         data_list = [pydantic_model(**item).model_dump() for item in data_list]
    #     return data_list


    # async def push_into_target(self, target_name: str, push_data: dict, pydantic_model: PydanticModel=None):
    #     pass


    def __repr__(self) -> str:
            """字符串表示"""
            return (f"K3Connection(url='{self.base_url}', "
                    f"user='{self.username}', acctid='{self.acctid}')")



class K3Mo(MoVoucher):

    _QUERY_ENDPOINT = ""
    _CREATE_ENDPOINT = ""
    _APPROVE_ENDPOINT = ""
    _EDIT_ENDPOINT = ""
    _PUSH_PYDANTIC_MODEL = None
    _DOCUMENTATION_URL = None


    @classmethod
    async def create(
        cls,
        event_data: dict,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None,
        remain_native_supplyno: bool = True,
        **kwargs
    ):
        # 尚未实现：基类 create_batch 以 return_exceptions=True 收集结果，
        # 空实现会静默返回 None 并被当作"推送失败"回执 ERP，无法区分未实现与成功，
        # 因此显式抛出，避免调用方误判。
        raise NotImplementedError("K3Mo.create 尚未实现")