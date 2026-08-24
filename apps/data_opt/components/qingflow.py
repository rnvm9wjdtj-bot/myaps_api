"""
轻流(QingFlow) OpenAPI 接口组件

基于轻流OpenAPI文档实现，支持：
- 获取accessToken认证
- 获取应用数据（分页、筛选、排序）
- 通过租户配置的字段映射规则，将轻流工作表数据转换为APS标准格式

设计要点：
    轻流是低代码平台，所有工作表查询逻辑相同（POST /openApi/app/{appKey}/apply/filter），
    区别仅在于字段映射规则。因此：
    1. QingflowConnection 只负责连接、认证、原始数据获取
    2. QingflowSource 抽象通用查询逻辑，由各租户通过 field_map + pydantic_model 配置具体规则
    3. 映射规则和Pydantic模型由租户客户端 client.py 注入，适配不同租户
"""
import asyncio
import inspect
from typing import Dict, Any, Optional, List, Type
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

    仅负责连接、认证和原始数据获取，不包含任何业务字段映射逻辑。
    字段映射由 QingflowSource + 租户配置的 field_map 完成。

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
        assert self.base_url, "轻流base_url未配置，请在租户配置文件中添加qingflow.base_url"
        assert self.ws_id and self.ws_secret, "轻流工作区ID或密钥缺失，请在租户配置文件中添加qingflow.ws_id/ws_secret"

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
        获取轻流应用单页数据

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
            所有页的数据列表（result数组，每项含answers和applyBaseInfo）
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
    def parse_answer_values(answers: list) -> Dict[str, Any]:
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
    def parse_apply_data(apply_data: dict) -> Dict[str, Any]:
        """
        解析单条轻流应用数据，提取字段值和基础信息

        Args:
            apply_data: 轻流返回的单条数据（含answers和applyBaseInfo）

        Returns:
            扁平化的数据字典，包含字段值（以queTitle为键）和基础信息
        """
        parsed = QingflowConnection.parse_answer_values(apply_data.get("answers", []))

        base_info = apply_data.get("applyBaseInfo", {})
        parsed["applyId"] = apply_data.get("applyId", "")
        parsed["applyNum"] = base_info.get("applyNum", "")
        parsed["applyTime"] = base_info.get("applyTime", "")
        parsed["applyUser"] = base_info.get("applyUser", {}).get("userName", "")
        parsed["lastUpdateTime"] = base_info.get("lastUpdateTime", "")
        parsed["formTitle"] = base_info.get("formTitle", "")

        return parsed


#################################################################################
# 轻流通用数据源（抽象查询逻辑，复用于所有工作表）
#################################################################################

class QingflowSource(BaseSource):
    """
    轻流通用数据源 - 抽象所有工作表的查询逻辑

    轻流是低代码平台，所有工作表查询逻辑相同（POST /openApi/app/{appKey}/apply/filter），
    区别仅在于字段映射规则。本类通过 pydantic_model 参数化配置，
    使同一套查询逻辑可复用于物料、BOM、工艺路线、库存等任何工作表。

    字段映射+清洗统一由 pydantic_model 的 @model_validator(mode="before") 完成，
    直接接收轻流原始字段（queTitle为键），在 validator 中映射为 APS 标准字段并清洗。

    使用方式：
        1. 在租户client.py中定义 pydantic_model（含 model_validator 做映射+清洗）
        2. 通过 QingflowSource.configure(...) 创建专属数据源类
        3. 注册到 QingflowConnection 后即可调用 query_batch()

    配置参数：
        pydantic_model: 数据清洗模型，继承自 AcceptMaterial/AcceptSupply 等，
                        其 @model_validator(mode="before") 直接接收轻流原始字段
        app_key: 可选，覆盖默认应用ID（不同工作表可能在不同应用下）
        queries: 可选，默认筛选条件
        sorts: 可选，默认排序条件
        user_id: 可选，默认userId
        scope: 可选，数据范围， 1 - 全部数据（默认）， 2 - 已填写的数据， 3 - 未填写的数据
    """

    _APP_KEY: Optional[str] = None
    _DEFAULT_QUERIES: Optional[list] = None
    _DEFAULT_SORTS: Optional[list] = None
    _DEFAULT_USER_ID: Optional[str] = None
    _DEFAULT_SCOPE: int = 1

    @classmethod
    def configure(
        cls,
        pydantic_model: Type[PydanticModel],
        app_key: str = None,
        queries: list = None,
        sorts: list = None,
        user_id: str = None,
        scope: int = 1,
        class_name: str = None,
    ) -> Type['QingflowSource']:
        """
        工厂方法：创建一个配置好的专属数据源子类

        Args:
            pydantic_model: 数据清洗Pydantic模型，其 model_validator 直接接收轻流原始字段
            app_key: 可选，应用ID
            queries: 可选，默认筛选条件
            sorts: 可选，默认排序条件
            user_id: 可选，默认userId
            scope: 可选，数据范围
            class_name: 可选，生成的类名

        Returns:
            配置好的 QingflowSource 子类

        使用示例：
            QingflowMaterial = QingflowSource.configure(
                pydantic_model=MaterialPullModel,
                class_name="QingflowMaterial",
            )
            conn.register_source(QingflowMaterial)
            data = await QingflowMaterial.query_batch()
        """
        new_cls = type(
            class_name or f"QingflowSource_{pydantic_model.__name__}",
            (cls,),
            {
                "_PULL_PYDANTIC_MODEL": pydantic_model,
                "_APP_KEY": app_key,
                "_DEFAULT_QUERIES": queries,
                "_DEFAULT_SORTS": sorts,
                "_DEFAULT_USER_ID": user_id,
                "_DEFAULT_SCOPE": scope,
            }
        )
        return new_cls

    @classmethod
    async def query_batch(
        cls,
        queries: list = None,
        sorts: list = None,
        user_id: str = None,
        scope: int = None,
        app_key: str = None,
    ):
        """
        查询批量数据（通用查询逻辑，复用于所有工作表）

        流程：
            1. 通过 QingflowConnection.fetch_all_app_data 获取原始数据
            2. 解析每条数据的 answers 数组为 {queTitle: value} 字典
            3. 返回 ExternalDataSet 包装的数据（由 pydantic_model 的 model_validator 完成映射+清洗）

        Args:
            queries: 筛选条件，默认使用类配置的 _DEFAULT_QUERIES
            sorts: 排序条件，默认使用类配置的 _DEFAULT_SORTS
            user_id: 可选userId
            scope: 数据范围
            app_key: 应用ID，默认使用类配置或连接配置

        Returns:
            ExternalDataSet 包装的数据
        """
        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        assert cls._PULL_PYDANTIC_MODEL, "未配置 pydantic_model 数据模型"
        await cls._CONNECTION.auth()

        queries = queries if queries is not None else cls._DEFAULT_QUERIES
        sorts = sorts if sorts is not None else cls._DEFAULT_SORTS
        user_id = user_id if user_id is not None else cls._DEFAULT_USER_ID
        scope = scope if scope is not None else cls._DEFAULT_SCOPE
        app_key = app_key or cls._APP_KEY

        raw_results = await cls._CONNECTION.fetch_all_app_data(
            app_key=app_key,
            queries=queries,
            sorts=sorts,
            user_id=user_id,
            scope=scope,
        )

        data_list = [
            QingflowConnection.parse_apply_data(item)
            for item in raw_results
        ]

        return ExternalDataSet(raw_data=data_list, pydantic_model=cls._PULL_PYDANTIC_MODEL)


