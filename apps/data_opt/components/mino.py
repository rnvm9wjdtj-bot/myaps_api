"""
明珞 - 智造家 MES 连接
"""
from typing import Dict, Any, Optional
from urllib.parse import urlencode

import json, time, inspect, asyncio, hashlib
from typing import Dict, Any, Literal, Optional, NamedTuple, Type, Callable
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
    db_query, TSupply, TDemand, ExternalBaseConnection, BaseSource, BaseVoucher, MoVoucher, RsVoucher, ExternalData, ExternalDataSet,
    async_rate_limit, async_service_operation, batch_service_operation
)



CACHE_MINO = PROJECT_JSON_FILE.get("mino", {})


class MinoConfig:
    """
    明珞 MES 配置类
    
    配置示例（project_files/{PROJECT_DIR}/{PROJECT_JSON}.json）：
    {
        "mino": {
            "base_url": "https://betacore.imefuture.com",
            "access_key_secret": "your_secret_key",
            "max_qps": 50
        }
    }
    """
    def __init__(self, cache_file=PROJECT_JSON_FILE):
        if hasattr(cache_file, 'get'):
            self.cache_file = cache_file
        else:
            from globalobjects.json_manager import JSONManager
            self.cache_file = JSONManager(cache_file)
        
        cache_mino = self.cache_file.get("mino", {})
        self.base_url = cache_mino.get("base_url", "https://beta-tmgc2-gateway.imefuture.com")  # 默认测试地址，生产地址https://tmgc2-gateway.imefuture.com
        self.access_key_secret = cache_mino.get("access_key_secret", "")
        self.max_qps = cache_mino.get("max_qps", 50)
        
        if not self.access_key_secret:
            logger.warning("明珞 access_key_secret 未配置，请检查配置文件")


class MinoConnection(ExternalBaseConnection):
    """
    明珞 MES 连接类 - 继承自 ExternalBaseConnection
    
    实现智造家 的 MD5 签名鉴权机制：
    - sign = MD5(param + erptimestamp + accessKeySecret).toLowerCase()
    - GET 请求：param 为 URL 参数按字典排序
    - POST 请求：param 为完整 JSON body
    
    配置建议：
        - async_qps: 根据明珞服务器性能调整，建议不超过50
        - pool_maxsize: 建议与 async_qps 相等或更大
    """
    
    def __init__(self, config: MinoConfig = None):
        """
        初始化明珞 连接
        
        Args:
            config: MinoConfig 实例
            
        使用示例：
            config = MinoConfig()
            conn = MinoConnection(config)
        """
        if config is None:
            config = MinoConfig()
        
        super().__init__(
            async_qps=getattr(config, 'max_qps', None),
            pool_maxsize=getattr(config, 'max_qps', None)
        )
        
        self.config = config
        self.base_url = self.config.base_url
        self.access_key_secret = self.config.access_key_secret
    
    async def auth(self, method: str = "GET", params: Dict[str, Any] = None, body: Any = None) -> Dict[str, str]:
        """
        生成鉴权请求头
        
        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE）
            params: URL 参数（GET 请求使用）
            body: 请求体（POST/PUT/DELETE 请求使用）
            
        Returns:
            包含 sign 和 erptimestamp 的请求头字典
            
        使用示例：
            # GET 请求
            headers = conn.auth("GET", params={"order_id": "123", "enterprise_no": "A00003061"})
            
            # POST 请求
            headers = conn.auth("POST", body={"order_id": "123", "confirm_result": "1"})
        """
        def _generate_sign(param: str, erptimestamp: str) -> str:
            """生成 MD5 签名（小写）"""
            sign_str = f"{param}{erptimestamp}{self.access_key_secret}"
            return hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()
        
        def _sort_params(params_dict: Dict[str, Any]) -> str:
            """将参数按 ASCII 字典序排序并拼接"""
            if not params_dict:
                return ""
            sorted_items = sorted(params_dict.items(), key=lambda x: x[0])
            return "&".join([f"{k}={v}" for k, v in sorted_items])
        
        erptimestamp = str(int(time.time() * 1000))
        
        if method.upper() == "GET":
            param = _sort_params(params or {})
        else:
            param = json.dumps(body, ensure_ascii=False) if body else ""
        
        sign = _generate_sign(param, erptimestamp)
        
        return {
            "sign": sign,
            "erptimestamp": erptimestamp,
            "Content-Type": "application/json"
        }
    
    async def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        异步发送 GET 请求到明珞 MES
        
        Args:
            endpoint: API 端点路径（如 "/erp/V1/getReceiveOrder"）
            params: URL 参数
            
        Returns:
            响应 JSON 数据
        """
        headers = self.auth("GET", params=params)
        async_session = await self._get_async_session()
        
        url = f"{self.base_url}{endpoint}"
        response = await async_session.get(
            url,
            headers=headers,
            params=params,
            timeout=self._read_timeout
        )
        
        return response.json()
    
    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步发送 POST 请求到明珞 MES
        
        Args:
            endpoint: API 端点路径
            data: 请求体数据
            
        Returns:
            响应 JSON 数据
        """
        headers = self.auth("POST", body=data)
        async_session = await self._get_async_session()
        
        url = f"{self.base_url}{endpoint}"
        response = await async_session.post(
            url,
            headers=headers,
            json=data,
            timeout=self._read_timeout
        )
        
        return response.json()
    
    async def _put(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步发送 PUT 请求到明珞 MES
        
        Args:
            endpoint: API 端点路径
            data: 请求体数据
            
        Returns:
            响应 JSON 数据
        """
        headers = self.auth("PUT", body=data)
        async_session = await self._get_async_session()
        
        url = f"{self.base_url}{endpoint}"
        response = await async_session.put(
            url,
            headers=headers,
            json=data,
            timeout=self._read_timeout
        )
        
        return response.json()
    
    async def _delete(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        异步发送 DELETE 请求到明珞 MES
        
        Args:
            endpoint: API 端点路径
            data: 请求体数据（可选）
            
        Returns:
            响应 JSON 数据
        """
        headers = self.auth("DELETE", body=data)
        async_session = await self._get_async_session()
        
        url = f"{self.base_url}{endpoint}"
        response = await async_session.delete(
            url,
            headers=headers,
            json=data,
            timeout=self._read_timeout
        )
        
        return response.json()



class MoPushModel(PydanticModel):   # 对应 productionOrderVo
    plannedStartDateTime: str = Field()         # 计划开始时间
    plannedEndDateTime: str = Field()           # 计划结束时间
    departmentCode: str = Field()               # 部门编码
    sourceNo: str = Field()                     # 外部订单编号
    materialCode: str = Field()                 # 物料编码
    plannedQuantity: float = Field()            # 计划数量
    createUser: str = Field()                   # 创建人 员工工号
    createDateTime: str = Field()               # 创建时间
    priority: str = Field(enmu=["0", "1"])      # 优先 1：是 0：否
    operationTaskOrderVoList: list[dict] = Field()  # 工序任务单信息

    
    class Config:
        extra = 'allow'


    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        # now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        cleaned_values['plannedStartDateTime'] = values['dt_ordstart']
        cleaned_values['plannedEndDateTime'] = values['dt_ordend']
        cleaned_values['departmentCode'] = CACHE_MINO.get("$departmentCode", "")
        cleaned_values['sourceNo'] = values['vendorno']
        cleaned_values['materialCode'] = values['materialno']
        cleaned_values['plannedQuantity'] = values['avail_qty']
        cleaned_values['createUser'] = CACHE_MINO.get("$createUser", "")
        cleaned_values['createDateTime'] = values['create_date']
        cleaned_values['priority'] = '1'

        orderwc_list = values.get('orderwc')
        otovl = []
        cleaned_values['operationTaskOrderVoList'] = otovl
        if orderwc_list:
            for orderwc in orderwc_list:
                bom_list = values['_production_cache'].get_bom(
                    productno=orderwc['materialno'],
                    matver=orderwc['matver'],
                    itemno=orderwc['itemno']
                )
                if bom_list:
                    obl = [{'materialCode': bom['materialno'], 'quantity': bom['qty']} for bom in bom_list]
                else:
                    obl = []
                otovl.append({
                    'equipmentFlag': '1',                           # 是否设备报工标志（0否 1是）
                    'sourceNo': orderwc['orderno'],                 # 外部工序任务单编号
                    'operationCode': orderwc['itemno'],             # 工序编码
                    'workCenterCode': orderwc['workcenter'],        # 工作中心编码
                    'rowNumText': orderwc['sortno'],                # 工序顺序号
                    'plannedStartDateTime': orderwc['dt_start'],    # 计划开始时间
                    'plannedEndDateTime': orderwc['dt_end'],        # 计划结束时间
                    'plannedQuantity': orderwc['orderqty'],         # 计划数量
                    'createUser': CACHE_MINO.get("$createUser", ""),
                    'createDateTime': orderwc['sys_stamp'],
                    'operationBomList': obl
                })

        return cleaned_values



class MinoMo(MoVoucher):
    """
    工序任务单
    """

    # _QUERY_ENDPOINT = ""
    _CREATE_ENDPOINT = "/tmgc2-api/api-proxy/erp/operationTaskOrder/api/create"
    # _APPROVE_ENDPOINT = ""
    _PUSH_PYDANTIC_MODEL = MoPushModel
    _DOCUMENTATION_URL = "https://www.yuque.com/vqp0d0/liv2wo/tl7dsa336bgn50bu"
    
    @classmethod
    @async_rate_limit()
    # @async_service_operation(module="mino接口", operation="创建工序任务单")
    async def create(
        cls,
        event_data: dict,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None,
        remain_native_supplyno: bool = True,
        **kwargs
    ):

        try:
            endpoint = cls._CREATE_ENDPOINT
            supplyno = event_data.get('supplyno')
            task2 = _aps.get_supplymo_detaildata(supplyno=supplyno, get_next_mo=False, get_origin_so=False)
            supplymo_detaildata = await asyncio.gather(task2, return_exceptions=True)
            supplymo_detaildata = supplymo_detaildata[0]
            if isinstance(supplymo_detaildata, Exception):
                raise supplymo_detaildata
            supplymo_detaildata['_production_cache'] = _aps._production_cache

            pydantic_model = pydantic_model or cls._PUSH_PYDANTIC_MODEL

            dto = pydantic_model(**supplymo_detaildata).model_dump(exclude_none=True)

            payload = [{
                "siteCode": CACHE_MINO.get("$siteCode", ""),
                "productionOrderVo": dto
            }]
        
            mo_create_response_json = await cls._CONNECTION._post(endpoint=endpoint, data=payload)

            if mo_create_response_json.get("success"):
                await _erp.mo_release_success(
                    native_plno=supplyno,
                )
            else:
                err_msg = mo_create_response_json.get("errorMessage")
                await _erp.mo_release_failed(
                    native_plno=supplyno,
                    msg=err_msg,
                    msg_from='MES',
                )
        except Exception as e:
            logger.warning("创建工序任务单失败", str(e))
            await _erp.mo_release_failed(native_plno=supplyno, msg=str(e))