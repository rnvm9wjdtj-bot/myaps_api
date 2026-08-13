"""
轻流(QingFlow) OpenAPI 接口组件

基于轻流OpenAPI文档实现，支持：
- 获取accessToken认证
- 获取应用数据（分页、筛选、排序）
"""
import asyncio
import inspect
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from . import ApsPayloadSponsor, EventResultPoster
from ._base import (
    PydanticModel, JSONManager,
    logger,
    DataProcessor, globalconst, PROJECT_JSON_FILE, pdv,
    convert_timeunit, clean_value,
    model_validator, Field,
    AcceptMaterial, AcceptSupply,
    db_query, ExternalBaseConnection, BaseSource, ExternalData, ExternalDataSet,
    async_rate_limit, async_service_operation, batch_service_operation
)


CACHE_QINGFLOW = PROJECT_JSON_FILE.get("qingflow", {})


#################################################################################
# 数据规范模型
#################################################################################

class MaterialPullModel(AcceptMaterial):

    size: Optional[str] = Field(None)
    candelay: Optional[str] = Field(None)
    lotsize: Optional[str] = Field(None)

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['materialno'] = clean_value(values.get('料号', ''))
        cleaned_values['description'] = clean_value(values.get('物料类型', ''))
        cleaned_values['size'] = values.get('规格型号')
        cleaned_values['plant'] = pdv.MAT_PLANT
        cleaned_values['planner'] = pdv.MAT_PLANNER
        cleaned_values['fifo'] = pdv.MAT_FIFO
        cleaned_values['leadday'] = pdv.MAT_LEADDAY_F
        cleaned_values['expday'] = 0
        cleaned_values['grday'] = 0
        cleaned_values['abc'] = globalconst.AbcEnum.B
        cleaned_values['unit'] = ''
        cleaned_values['price'] = 0
        cleaned_values['groupno'] = ''
        cleaned_values['type'] = globalconst.EfEnum.F
        cleaned_values['phantom'] = globalconst.YesNoEnum.NO
        values = cleaned_values
        return values




#################################################################################
# 轻流连接及配置
#################################################################################

class QingflowConfig:
    """
    轻流OpenAPI配置类

    缓存文件用于存储轻流认证信息，结构如下：
    {
        "qingflow": {
            "base_url": "...",
            "ws_id": "...",
            "ws_secret": "...",
            "app_key": "...",
            "access_token": "...",
            "_auth_at_": "2026-08-11 09:00:00"
        }
    }
    """

    def __init__(self, cache_file: str | JSONManager = PROJECT_JSON_FILE):
        if isinstance(cache_file, str):
            self.cache_file = JSONManager(cache_file)
        else:
            self.cache_file = cache_file
        cache_qf = self.cache_file.get("qingflow", {})
        self.base_url = cache_qf.get("base_url")
        self.ws_id = cache_qf.get("ws_id")
        self.ws_secret = cache_qf.get("ws_secret")
        self.app_key = cache_qf.get("app_key")
        self.token_expire_seconds = cache_qf.get("token_expire_seconds", 7200)
        self.max_page_size = min(cache_qf.get("max_page_size", 100), 100)


class QingflowConnection(ExternalBaseConnection):
    """
    轻流 OpenAPI 连接类 - 继承自 ExternalBaseConnection

    使用父类提供的限流、连接池和超时保护机制，
    实现轻流 OpenAPI 的认证和请求处理。

    认证流程：
        1. GET /openApi/accessToken?wsId=xxx&wsSecret=xxx 获取accessToken
        2. 后续请求通过Header传递accessToken进行鉴权
        3. accessToken有效期7200秒，过期自动刷新

    数据获取流程：
        1. POST /openApi/app/{appKey}/apply/filter 获取应用数据
        2. 支持分页（pageSize/pageNum）、排序（sorts）、筛选（queries）
    """

    _ping_endpoint = None

    def __init__(self, config: QingflowConfig = QingflowConfig()):
        super().__init__(
            async_qps=getattr(config, 'max_qps', None),
            async_burst=getattr(config, 'max_burst', None),
            pool_maxsize=getattr(config, 'max_qps', None)
        )
        self.config = config
        self.base_url = self.config.base_url
        self.cache_file = self.config.cache_file
        self.credential_keys = ("ws_id", "ws_secret", "app_key", "access_token", globalconst.StaticString.AUTH_AT.value)
        cache_qf = self.cache_file.get("qingflow", {})
        for key in self.credential_keys:
            setattr(self, key, cache_qf.get(key, ""))
        self._auth_lock = asyncio.Lock()


    async def auth(self, force: bool = False, max_retries: int = 5):
        """
        异步认证连接，获取accessToken

        轻流的accessToken通过GET请求获取，有效期7200秒。
        支持缓存复用，过期自动刷新，含重试机制。
        """
        assert self.ws_id and self.ws_secret, "轻流工作区ID或密钥缺失"

        if self._auth_at_:
            expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=self.config.token_expire_seconds)
            if datetime.now() < expire_time and not force:
                logger.debug(f"轻流accessToken有效，有效期至：{expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                return self.access_token

        async with self._auth_lock:
            if self._auth_at_:
                expire_time = datetime.strptime(self._auth_at_, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=self.config.token_expire_seconds)
                if datetime.now() < expire_time and not force:
                    logger.debug(f"轻流accessToken有效（锁后复检），有效期至：{expire_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    return self.access_token

            retry_count = 0
            last_error = None
            async_session = None
            while retry_count < max_retries:
                try:
                    async_session = await self._get_async_session()
                    try:
                        auth_response = await async_session.get(
                            url=f"{self.base_url}/openApi/accessToken",
                            params={
                                "wsId": self.ws_id,
                                "wsSecret": self.ws_secret,
                            },
                            headers={
                                "Content-Type": "application/json",
                            },
                            timeout=60.0
                        )
                    except Exception as request_error:
                        logger.fail(f"轻流认证请求失败: {type(request_error).__name__}: {str(request_error)}")
                        raise

                    if hasattr(auth_response, 'json'):
                        if inspect.iscoroutinefunction(auth_response.json):
                            auth_response = await auth_response.json()
                        else:
                            auth_response = auth_response.json()

                    err_code = auth_response.get("errCode", -1)
                    if err_code == 0:
                        result = auth_response.get("result", {})
                        self._auth_at_ = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.access_token = result.get("accessToken", "")
                        self.cache_file.update("qingflow", {
                            globalconst.StaticString.AUTH_AT.value: self._auth_at_,
                            "access_token": self.access_token,
                        })
                        self.cache_file.save()
                        logger.debug(f"轻流accessToken获取成功")
                        if async_session:
                            if hasattr(async_session, 'aclose'):
                                await async_session.aclose()
                            elif hasattr(async_session, 'close'):
                                async_session.close()
                        return self.access_token
                    else:
                        err_msg = auth_response.get("errMsg", "未知错误")
                        raise Exception(f"轻流认证失败 errCode={err_code}: {err_msg}")
                except Exception as e:
                    last_error = e
                    retry_count += 1
                    logger.warning(f"轻流认证失败（第{retry_count}/{max_retries}次）: {str(e)}")
                    if async_session:
                        if hasattr(async_session, 'aclose'):
                            await async_session.aclose()
                        elif hasattr(async_session, 'close'):
                            async_session.close()
                    if retry_count >= max_retries:
                        break
                    await asyncio.sleep(2 ** retry_count)
            logger.fail("轻流认证", str(last_error))
            raise last_error


    async def _get(self, endpoint: str, params: dict = None):
        """异步发送GET请求到轻流API"""
        await self.auth()
        async_session = await self._get_async_session()

        headers = {
            "accessToken": self.access_token,
            "Content-Type": "application/json",
        }
        response = await async_session.get(
            f"{self.base_url}{endpoint}",
            headers=headers,
            params=params,
            timeout=self._read_timeout
        )
        response_json = response.json()
        return response_json


    async def _post(self, endpoint: str, data: dict, user_id: str = None):
        """
        异步发送POST请求到轻流API

        Args:
            endpoint: API端点路径
            data: 请求体数据
            user_id: 可选，用户userId（type值非8时需传输）
        """
        await self.auth()
        async_session = await self._get_async_session()

        async def make_request():
            headers = {
                "accessToken": self.access_token,
                "Content-Type": "application/json",
            }
            if user_id:
                headers["userId"] = user_id
            response = await async_session.post(
                f"{self.base_url}{endpoint}",
                headers=headers,
                json=data,
                timeout=self._read_timeout
            )
            return response

        response = await self.execute_with_timeout_protection(
            make_request,
            f"POST {endpoint}"
        )

        response_json = response.json()

        if hasattr(response, 'status_code'):
            status_code = response.status_code
            if status_code >= 500 and status_code < 600:
                if isinstance(response_json, dict):
                    err_msg = response_json.get("errMsg") or status_code
                else:
                    err_msg = status_code
                raise Exception(f"HTTP 服务器错误: {err_msg}")

        err_code = response_json.get("errCode", 0) if isinstance(response_json, dict) else 0
        if err_code != 0:
            err_msg = response_json.get("errMsg", "未知错误") if isinstance(response_json, dict) else "未知错误"
            raise Exception(f"轻流API错误 errCode={err_code}: {err_msg}")

        return response_json


    async def fetch_app_data(
        self,
        app_key: str = None,
        page_size: int = None,
        page_num: int = 1,
        sorts: list = None,
        queries: list = None,
        queries_rel: str = "and",
        user_id: str = None,
        scope: int = 1,
    ) -> Dict[str, Any]:
        """
        获取轻流应用数据（自动分页）

        Args:
            app_key: 应用ID，默认使用配置中的app_key
            page_size: 每页数据条数，默认使用配置中的max_page_size
            page_num: 起始页码
            sorts: 排序条件列表 [{"queId": int, "isAscend": bool}]
            queries: 筛选条件列表 [{"queId": int, ...}]
            queries_rel: 条件间逻辑关系 "and" 或 "or"
            user_id: 可选userId
            scope: 数据范围 1全部 2已填写 3未填写

        Returns:
            完整的API响应数据
        """
        app_key = app_key or self.config.app_key
        page_size = page_size or self.config.max_page_size
        endpoint = f"/openApi/app/{app_key}/apply/filter"

        body = {
            "pageSize": page_size,
            "pageNum": page_num,
            "scope": scope,
        }
        if sorts:
            body["sorts"] = sorts
        if queries:
            body["queriesRel"] = queries_rel
            body["queries"] = queries

        response = await self._post(endpoint=endpoint, data=body, user_id=user_id)
        return response


    async def fetch_all_app_data(
        self,
        app_key: str = None,
        page_size: int = None,
        sorts: list = None,
        queries: list = None,
        queries_rel: str = "and",
        user_id: str = None,
        scope: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        获取轻流应用全部数据（自动翻页）

        Args:
            同fetch_app_data

        Returns:
            所有页的数据列表（result数组）
        """
        app_key = app_key or self.config.app_key
        page_size = page_size or self.config.max_page_size
        all_results = []
        current_page = 1

        while True:
            response = await self.fetch_app_data(
                app_key=app_key,
                page_size=page_size,
                page_num=current_page,
                sorts=sorts,
                queries=queries,
                queries_rel=queries_rel,
                user_id=user_id,
                scope=scope,
            )

            result = response.get("result", {})
            page_data = result.get("result", [])
            if not page_data:
                break

            all_results.extend(page_data)

            page_amount = result.get("pageAmount", 1)
            if current_page >= page_amount:
                break
            current_page += 1

        return all_results


    @staticmethod
    def _parse_answer_values(answers: list) -> Dict[str, Any]:
        """
        解析轻流数据中的answers数组，转换为 {queTitle: value} 的字典

        Args:
            answers: 轻流返回的answers数组

        Returns:
            以字段标题为键、字段值为值的字典
        """
        parsed = {}
        for answer in answers:
            que_title = answer.get("queTitle", "")
            que_type = answer.get("queType", 0)
            values = answer.get("values", [])

            if que_type == 18:
                table_values = answer.get("tableValues", [])
                parsed[que_title] = table_values
            elif values:
                value_items = []
                for v in values:
                    value_items.append(v.get("value", ""))
                if len(value_items) == 1:
                    parsed[que_title] = value_items[0]
                else:
                    parsed[que_title] = value_items
            else:
                parsed[que_title] = ""

        return parsed


    @staticmethod
    def _parse_apply_data(apply_data: dict) -> Dict[str, Any]:
        """
        解析单条轻流应用数据，提取字段值和基础信息

        Args:
            apply_data: 轻流返回的单条数据（含answers和applyBaseInfo）

        Returns:
            扁平化的数据字典，包含字段值和基础信息
        """
        parsed = QingflowConnection._parse_answer_values(apply_data.get("answers", []))

        base_info = apply_data.get("applyBaseInfo", {})
        parsed["applyId"] = apply_data.get("applyId", "")
        parsed["applyNum"] = base_info.get("applyNum", "")
        parsed["applyTime"] = base_info.get("applyTime", "")
        parsed["applyUser"] = base_info.get("applyUser", {}).get("userName", "")
        parsed["lastUpdateTime"] = base_info.get("lastUpdateTime", "")
        parsed["formTitle"] = base_info.get("formTitle", "")

        return parsed


#################################################################################
# 轻流数据对象管理器
#################################################################################

class QingflowMaterial(BaseSource):
    """
    轻流物料数据源

    从轻流"物料主数据"应用中拉取物料信息，
    通过queId映射字段并转换为APS标准格式。
    """

    _PULL_PYDANTIC_MODEL = MaterialPullModel


    @classmethod
    async def query_batch(cls, queries: list = None, user_id: str = None):
        """
        查询批量物料数据

        Args:
            queries: 可选筛选条件
            user_id: 可选userId

        Returns:
            ExternalDataSet 包装的物料数据
        """
        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        await cls._CONNECTION.auth()

        raw_results = await cls._CONNECTION.fetch_all_app_data(
            queries=queries,
            user_id=user_id,
        )

        data_list = []
        for item in raw_results:
            parsed = QingflowConnection._parse_apply_data(item)
            data_list.append(parsed)

        return ExternalDataSet(raw_data=data_list, pydantic_model=cls._PULL_PYDANTIC_MODEL)