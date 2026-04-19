import json
import pandas as pd
import requests
import time
import threading
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Literal, Callable, Union, Any, Type
from collections import defaultdict
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel


from core.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET
from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.schemas import (
    model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm
)
from apps.io_api.models import TSupply, TDemand
from apps.io_api.utils.db_operation import db_query
from apps.io_api.utils.common import standard_response
from globalobjects import globalconst, logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv
from globalobjects.json_manager import JSONManager



logger = log_config.get_logger(__name__)


SESSION = get_session()


class BaseConnection(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    
    def __init__(self):
        self._session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        pass


    # @abstractmethod
    def pull_from_source(self, *args, **kwargs):
        """
        从目标系统获取数据
        """
        pass


    # @abstractmethod
    def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass




# 缓存配置
CACHE_REFRESH_INTERVAL = 300.0  # 5分钟（秒）
# CACHE_MAX_PAGESIZE = 10000  # 单页最大数据量


class _ProductionDataCache:
    """生产数据缓存管理器"""
    
    def __init__(self):
        # 状态标志
        self._initialized = False
        self._is_loading = False
        self._load_lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        
        # 缓存数据
        self._cache: Dict[str, Dict[Any, Any]] = {
            'supply_mo': {},
            'orderwc': {},
            'demand': {},
            'peg': {},
            'material': {}
        }
        
        # 计时器（秒）
        self._last_refresh_time = 0.0
        
        # 统计信息
        self._stats = {
            'total_hits': 0,
            'total_misses': 0,
            'total_refreshes': 0,
            'last_refresh_time': None,
            'cache_size': 0
        }

    
    async def _full_refresh(self, db_name: str):
        """全量刷新缓存"""
        logger.info("生产数据缓存", "", "开始全量刷新...")
        
        try:
            # 使用 API 方式构建缓存
            self._build_supply_mo_cache(db_name)
            self._build_orderwc_cache(db_name)
            self._build_demand_cache(db_name)
            self._build_peg_cache(db_name)
            self._build_material_cache(db_name)
            
            self._last_refresh_time = time.time()
            self._stats['total_refreshes'] += 1
            self._stats['last_refresh_time'] = self._last_refresh_time
            self._stats['cache_size'] = sum(
                len(v) for v in self._cache.values() if isinstance(v, dict)
            )
            
            logger.success("生产数据缓存", "", f"全量刷新完成，共 {self._stats['cache_size']} 条数据")
            
        except Exception as e:
            logger.fail("生产数据缓存", "", f"全量刷新失败: {e}")
            raise
    

    def ensure_initialized(self, db_name: str):
        """同步方式确保缓存已初始化（使用线程事件阻塞）"""
        if self._initialized:
            return
        
        with self._load_lock:
            if self._initialized:
                return
            
            logger.info("生产数据缓存", "", "首次加载中，事件队列将等待...")
            self._is_loading = True
            
            try:
                # 直接运行同步版本的初始化，避免事件循环问题
                # 这样可以确保在任何线程中都能正常工作
                self._initialize(db_name)
                
                self._initialized = True
                logger.success("生产数据缓存", "", "首次加载完成")
                
            except Exception as e:
                logger.fail("生产数据缓存", "", f"首次加载失败: {e}")
                raise
            finally:
                self._is_loading = False
    

    def _initialize(self, db_name: str):
        """同步版本的初始化方法，使用 API 方式获取数据"""
        try:
            logger.info("生产数据缓存", "", "开始构建 supply_mo 缓存...")
            self._build_supply_mo_cache(db_name)
            logger.success("生产数据缓存", "", f"supply_mo 缓存加载: {len(self._cache['supply_mo'])} 条")
            
            logger.info("生产数据缓存", "", "开始构建 orderwc 缓存...")
            self._build_orderwc_cache(db_name)
            logger.success("生产数据缓存", "", f"orderwc 缓存加载: {len(self._cache['orderwc'])} 条")
            
            logger.info("生产数据缓存", "", "开始构建 demand 缓存...")
            self._build_demand_cache(db_name)
            logger.success("生产数据缓存", "", f"demand 缓存加载: {len(self._cache['demand'])} 条")
            
            logger.info("生产数据缓存", "", "开始构建 peg 缓存...")
            self._build_peg_cache(db_name)
            logger.success("生产数据缓存", "", f"peg 缓存加载: {len(self._cache['peg']['demand_to_supply'])} 条 DemandNo")
            
            logger.info("生产数据缓存", "", "开始构建 material 缓存...")
            self._build_material_cache(db_name)
            logger.success("生产数据缓存", "", f"material 缓存加载: {len(self._cache['material'])} 条")
            
            # 更新最后刷新时间
            self._last_refresh_time = time.time()
            self._stats['total_refreshes'] += 1
            self._stats['last_refresh_time'] = self._last_refresh_time
            self._stats['cache_size'] = sum(
                len(v) for v in self._cache.values() if isinstance(v, dict)
            )
            logger.success("生产数据缓存", "", f"全量加载完成，共 {self._stats['cache_size']} 条数据")
                
        except Exception as e:
            logger.fail("生产数据缓存", "", f"同步初始化失败: {e}")
            raise
    

    def _fetch_paginated_data(self, url: str, page_size: int = 1000):
        """通用的分页获取数据方法"""
        all_data = []
        page_index = 1
        max_retries = 3
        retry_delay = 2  # 秒
        
        while True:
            paginated_url = f"{url}&page_index={page_index}&page_size={page_size}"
            
            for attempt in range(max_retries):
                try:
                    response = SESSION.get(paginated_url, timeout=(30, 60))
                    response.raise_for_status()
                    result = response.json()
                    
                    data_list = result.get('data', [])
                    all_data.extend(data_list)
                    
                    # 检查是否还有下一页
                    total = result.get('meta', {}).get('total', 0)
                    if len(all_data) >= total:
                        return all_data
                    
                    page_index += 1
                    break
                except Exception as e:
                    logger.warning("生产数据缓存", "", f"分页获取数据失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    else:
                        # 达到最大重试次数，返回已获取的数据
                        return all_data
    

    def _build_cache(self, db_name: str, api_endpoint: str, cache_name: str, cache_factory, process_item):
        """通用的缓存构建方法"""
        cache = cache_factory()
        url = f"{THIS_BASE_URL}{api_endpoint}?db_name={db_name}"
        
        # 使用分页机制获取数据
        data_list = self._fetch_paginated_data(url)
        for item in data_list:
            process_item(item, cache)
        
        self._cache[cache_name] = cache
    

    def _build_supply_mo_cache(self, db_name: str):
        """使用 API 方式构建 supply_mo 缓存"""
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no] = item
        
        self._build_cache(
            db_name=db_name,
            api_endpoint="/api/v_supply_mo/page",
            cache_name="supply_mo",
            cache_factory=dict,
            process_item=process_item
        )
    

    def _build_orderwc_cache(self, db_name: str):
        """使用 API 方式构建 orderwc 缓存（以 supplyno 为索引）"""
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no].append(item)
        
        self._build_cache(
            db_name=db_name,
            api_endpoint="/api/v_orderwc/page",
            cache_name="orderwc",
            cache_factory=lambda: defaultdict(list),
            process_item=process_item
        )
    

    def _build_demand_cache(self, db_name: str):
        """使用 API 方式构建 demand 缓存"""
        def process_item(item, cache):
            demand_no = item.get('demandno', '')
            if demand_no:
                cache[demand_no].append(item)
        
        self._build_cache(
            db_name=db_name,
            api_endpoint="/api/v_demand/page",
            cache_name="demand",
            cache_factory=lambda: defaultdict(list),
            process_item=process_item
        )


    def _build_peg_cache(self, db_name: str):
        """使用 API 方式构建 peg 缓存（双向索引）"""
        def process_item(item, cache):
            demand_no = item.get('demandno', '')
            s_supply_no = item.get('s_supplyno', '')
            
            if demand_no and s_supply_no:
                if s_supply_no not in cache['demand_to_supply'][demand_no]:
                    cache['demand_to_supply'][demand_no].append(s_supply_no)
                if demand_no not in cache['supply_to_demand'][s_supply_no]:
                    cache['supply_to_demand'][s_supply_no].append(demand_no)
        
        def peg_cache_factory():
            return {
                'demand_to_supply': defaultdict(list),
                'supply_to_demand': defaultdict(list)
            }
        
        self._build_cache(
            db_name=db_name,
            api_endpoint="/api/v_peg/mini",
            cache_name="peg",
            cache_factory=peg_cache_factory,
            process_item=process_item
        )
    

    def _build_material_cache(self, db_name: str):
        """使用 API 方式构建 material 缓存"""
        def process_item(item, cache):
            material_no = item.get('materialno', '')
            if material_no:
                cache[material_no] = item
        
        self._build_cache(
            db_name=db_name,
            api_endpoint="/api/t_material/page",
            cache_name="material",
            cache_factory=dict,
            process_item=process_item
        )
    

    def establish_production_cache(self, db_name: str):
        """PL 状态变更事件处理"""
        # 检查是否正在加载缓存，如果是则直接返回
        if self._is_loading:
            logger.debug("生产数据缓存", "", "缓存正在加载中，跳过 PL 状态变更事件")
            return
        
        # 确保缓存已初始化
        self.ensure_initialized(db_name)
        
        # 检查是否需要刷新
        with self._refresh_lock:
            # 再次检查是否正在加载，避免并发问题
            if self._is_loading:
                logger.debug("生产数据缓存", "", "缓存正在加载中，跳过 PL 状态变更事件")
                return
                
            now = time.time()
            elapsed = now - self._last_refresh_time
            
            # 只有当 _last_refresh_time 大于 0（即已经初始化过）时才检查是否需要刷新
            if self._last_refresh_time > 0 and elapsed >= CACHE_REFRESH_INTERVAL:
                logger.info("生产数据缓存", "", f"计时器超时({elapsed:.1f}秒)，开始刷新...")
                # 使用同步方式刷新，避免事件循环问题
                self._initialize(db_name)
            else:
                logger.debug("生产数据缓存", "", f"计时器重置({elapsed:.1f}秒 < 5分钟)")
                # 计时器重置，但不实际重置变量，下次事件会重新计算


    def get_supply_mo(self, supply_no: str) -> Dict:
        """获取工单数据（按供应号查找）"""
        data = self._cache['supply_mo'].get(supply_no)
        if data:
            self._stats['total_hits'] += 1
            return data
        
        self._stats['total_misses'] += 1
        return {}
    

    def batch_get_supply_mo(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工单数据"""
        results = []
        for supply_no in supplynos:
            data = self._cache['supply_mo'].get(supply_no)
            if data:
                results.append(data)
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_orderwc(self, supply_no: str) -> List[Dict]:
        """获取工序数据（按供应号查找）"""
        data = self._cache['orderwc'].get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_orderwc(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工序数据（按供应号查找）"""
        results = []
        for supply_no in supplynos:
            data_list = self._cache['orderwc'].get(supply_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_demand(self, demand_no: str) -> List[Dict]:
        """获取需求数据"""
        data = self._cache['demand'].get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_demand(self, demandnos: List[str]) -> List[Dict]:
        """批量获取需求数据"""
        results = []
        for demand_no in demandnos:
            data_list = self._cache['demand'].get(demand_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_peg_by_demand(self, demand_no: str) -> List[str]:
        """根据 DemandNo 获取对应的 S_SupplyNo 列表"""
        cache = self._cache['peg']['demand_to_supply']
        data = cache.get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def get_peg_by_supply(self, supply_no: str) -> List[str]:
        """根据 S_SupplyNo 获取对应的 DemandNo 列表"""
        cache = self._cache['peg']['supply_to_demand']
        data = cache.get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_peg_by_demand(self, demandnos: List[str]) -> Dict[str, List[str]]:
        """批量根据 DemandNo 获取 S_SupplyNo 列表"""
        cache = self._cache['peg']['demand_to_supply']
        results = {}
        for demand_no in demandnos:
            data = cache.get(demand_no, [])
            results[demand_no] = data
            if data:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def batch_get_peg_by_supply(self, supplynos: List[str]) -> Dict[str, List[str]]:
        """批量根据 S_SupplyNo 获取 DemandNo 列表"""
        cache = self._cache['peg']['supply_to_demand']
        results = {}
        for supply_no in supplynos:
            data = cache.get(supply_no, [])
            results[supply_no] = data
            if data:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_material(self, material_no: str) -> List[Dict]:
        """获取物料数据"""
        data = self._cache['material'].get(material_no)
        if data:
            self._stats['total_hits'] += 1
            return [data]
        
        self._stats['total_misses'] += 1
        return []
    

    def batch_get_material(self, materialnos: List[str]) -> List[Dict]:
        """批量获取物料数据"""
        results = []
        for material_no in materialnos:
            data = self._cache['material'].get(material_no)
            if data:
                results.append(data)
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            **self._stats,
            'cache_sizes': {
                'supply_mo': len(self._cache['supply_mo']),
                'orderwc': len(self._cache['orderwc']),
                'demand': len(self._cache['demand']),
                'peg': len(self._cache['peg']),
                'material': len(self._cache['material'])
            }
        }


# 全局缓存实例
_production_cache = _ProductionDataCache()


def get_production_cache() -> _ProductionDataCache:
    """获取生产数据缓存管理器实例"""
    return _production_cache


class ApsHelpers:

    @staticmethod
    def _call_api(method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        通用 API 调用方法，包含错误处理、超时设置和重试机制
        
        Args:
            method: HTTP 方法，如 'GET', 'POST', 'PATCH', 'PUT'
            url: API 地址
            **kwargs: 其他参数，如 json, timeout 等
        
        Returns:
            API 返回的 JSON 数据
        
        Raises:
            Exception: API 调用失败
        """
        max_retries = 3
        retry_count = 0
        timeout = kwargs.pop('timeout', (30, 60))
        
        while retry_count < max_retries:
            try:
                if method.upper() == 'GET':
                    response = SESSION.get(url, timeout=timeout, **kwargs)
                elif method.upper() == 'POST':
                    response = SESSION.post(url, timeout=timeout, **kwargs)
                elif method.upper() == 'PATCH':
                    response = SESSION.patch(url, timeout=timeout, **kwargs)
                elif method.upper() == 'PUT':
                    response = SESSION.put(url, timeout=timeout, **kwargs)
                elif method.upper() == 'DELETE':
                    response = SESSION.delete(url, timeout=timeout, **kwargs)
                else:
                    raise ValueError(f"不支持的 HTTP 方法: {method}")
                
                response.raise_for_status()  # 检查 HTTP 状态码
                return response.json()
                
            except (requests.RequestException, ValueError, KeyError) as e:
                retry_count += 1
                logger.warning(f"API 调用失败，第{retry_count}次重试: {str(e)}")
                if retry_count >= max_retries:
                    logger.fail("API 调用", url, str(e))
                    raise
                time.sleep(1 * retry_count)  # 指数退避策略
        
        # 理论上不会走到这里
        raise Exception("API 调用失败：达到最大重试次数")


    @staticmethod
    def mto_workreport_to_virtual_stock(db:str=MYAPS_MAIN_DB):
        """
        将报工数据 转化为 虚拟库存 数据，只处理MTO报工
        🅰 db: 账套名称，默认MYAPS_MAIN_DB
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        url = f"{THIS_BASE_URL}/api/v_supply_complete?db_name={db}"
        response_json = ApsHelpers._call_api('GET', url)
        mo_complete_data = response_json.get('data')
        df_mto_vir_st = None
        if mo_complete_data:
            df_mo_complete = pd.DataFrame(mo_complete_data)
            df_mto_vir_st = (df_mo_complete[df_mo_complete['category'] == 'MTO']
                    [['materialno', 'vendorno', 'finalopqty', 'category', 'avail_date']]
                    .groupby('vendorno', as_index=False)
                    .agg({
                        'finalopqty': 'sum',
                        'materialno': 'first',
                        'category': 'first',
                        'avail_date': 'first',
                    }))
            df_mto_vir_st['supplyno'] = df_mto_vir_st['materialno'] + '-' + df_mto_vir_st['vendorno']
            df_mto_vir_st['type'] = 'ST'
            df_mto_vir_st['priority'] = 0
            df_mto_vir_st['status'] = 'NEW'
            df_mto_vir_st['dt_req'] = df_mto_vir_st['avail_date']
            df_mto_vir_st['create_date'] = now
            df_mto_vir_st['itemno'] = pdv.ITEMNO
            df_mto_vir_st.rename(columns={'finalopqty': 'avail_qty'}, inplace=True)
        return df_mto_vir_st


    @staticmethod
    def refresh_supply(supply_data:Union[List[Dict[str, Any]], pd.DataFrame], type_:Literal['ST', 'SO']='ST', dbs:str=MYAPS_DB_SET):
        from apps.io_api.schemas import AcceptSupply

        if isinstance(supply_data, pd.DataFrame):
            supply_data = supply_data.to_dict('records')
        supply_data = [AcceptSupply(**item).model_dump(exclude_none=True) for item in supply_data]
        url = f"{THIS_BASE_URL}/api/t_supply/type/{type_}?db_name={dbs}"
        refresh_result_json = ApsHelpers._call_api('PUT', url, json=supply_data)
        if refresh_result_json.get('success'):
            logger.success("刷新供应数据", f"type_{type_}", f"账套{dbs}")
        else:
            logger.fail("刷新供应数据", f"type_{type_}", refresh_result_json.get('message'))


    @staticmethod
    def confirm_workreport(db_name:str=MYAPS_MAIN_DB):
        """
        确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        """
        logger.start("确认报工记录任务")
        url = f"{THIS_BASE_URL}/api/t_confirm?db_name={db_name}"
        response_json = ApsHelpers._call_api('PATCH', url)
        logger.success("确认报工记录任务")
        return response_json



    @staticmethod
    def _modify_supply(supplyno: str, to_status: Literal['NEW', 'CRE', 'E2A', 'REL']=None, memo: str=None, _sn: str=None, _id: str=None, _entryid: str=None):
        url = f'{THIS_BASE_URL}/api/t_supply/{supplyno}/...?db_name={MYAPS_MAIN_DB}'
        response_json = ApsHelpers._call_api('PATCH', url, json={
            'status': to_status,
            'memo': memo[:255],
            'apiex_sn': _sn,
            'apiex_id': _id,
            'apiex_entryid': _entryid,
        })
        return response_json


    @staticmethod
    def pl_release_success(native_plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _id: str=None, _entryid: str=None):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段，作为私有方法在 def click_release_button() 中被直接调用
        🅰 native_plno: 原生PL计划单编号
        🅰 mono: MO号，可选，若传值则更改PL的原生SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        🅰 _id: 外部系统返回的 MO ID
        🅰 _entryid: 外部系统返回的 MO 详情 ID（对于某些有表头的ERP，具体的 MO 是存在于子表中的，有单独的行记录id
        """
        mono = mono or native_plno
        try:
            # logger.query("PL信息", native_plno, "")
            # mo_data = ApsHelpers.get_supplymo_detaildata(supplyno=native_plno)
            # logger.info(f"查询PL信息响应：成功")

            # if mo_data.get("type") != "PL":
            #     logger.fail("PL查询", native_plno, "非PL类型", to_file=True)
            #     return standard_response(status_code=400, success=0, message=f"Supply {native_plno} is not a PL.")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.success("推送 MO", f"原供应号{native_plno}", f"MO单号{mono}", to_file=True)

            memo = f"{now} ✅ {msg_from}: '{msg}, {mono}, {_id}, {_entryid}' @ {native_plno}"
            
            logger.update("PL状态", native_plno, f"目标状态{to_status}，MO单号{mono}")
            patch_url = f'{THIS_BASE_URL}/api/t_supply/{native_plno}?db_name={MYAPS_MAIN_DB}'
            patch_data = {
                'status': to_status,
                'apiex_sn': str(mono),
                'apiex_id': str(_id or ""),
                'apiex_entryid': str(_entryid or ""),
                'supplyno': str(mono),
                'memo': memo,
            }
            response_json = ApsHelpers._call_api('PATCH', patch_url, json=patch_data)
            logger.info(f"更新PL状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PL状态为MO时发生网络错误：{str(e)}"
            logger.fail("PL状态更新", native_plno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def pl_release_failed(native_plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, push_data: dict=None, msg_from: str=None):
        logger.warning_msg(f"推送 MO {msg}", json.dumps(push_data, ensure_ascii=False), to_file=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass

        memo = f"{now} 🚫 {msg_from}: '{msg}'"
        try:
            response_json = ApsHelpers._modify_supply(supplyno=native_plno, to_status=to_status, memo=memo)
            logger.info(f"更新PL状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PL状态时发生网络错误：{str(e)}"
            logger.fail("PL状态更新", native_plno, error_msg)
            return None


    @staticmethod
    def rs_push_success(rsno: str, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} ✅ {msg_from}: '{_code}, {_id}, {_entryid}' @ {rsno}"
            
            logger.update("RS状态", rsno, f"目标状态{to_status}")
            url = f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'status': to_status,
                'memo': memo,
            })
            logger.info(f"更新RS状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新RS状态时发生网络错误：{str(e)}"
            logger.fail("RS状态更新", rsno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def rs_push_failed(rsno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
        logger.fail("推送 RS", json.dumps(push_data, ensure_ascii=False), msg)
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} 🚫 {msg_from}: '{msg}'"

            url = f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'memo': memo,
            })
            return response_json
        except Exception as e:
            error_msg = f"更新RS失败状态时发生网络错误：{str(e)}"
            logger.fail("RS状态更新", rsno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def get_new_pr_data():
        import asyncio
        from apps.io_api.utils.db_operation import db_query

        # 使用 asyncio.run 来运行异步代码
        result = asyncio.run(db_query(MYAPS_MAIN_DB, "v_supply", "`Type`='PR' AND `Status`='NEW'"))
        return result.get('data', [])


    @staticmethod
    def aggregate_pr_data(pr_data_list: list[dict]=None, group_by: list=['materialno', 'avail_date', 'vendorno']) -> list[dict]:
        """
        聚合 PR avail_qty 字段
        Args:
            pr_data_list: PR 数据列表，若为None则查询主账套中状态为 NEW 的 PR 数据
            group_by: 分组字段，默认['materialno', 'avail_date', 'vendorno']
        Returns:
            聚合后的 PR 数据列表
        """
        import pandas as pd

        if not pr_data_list:
            pr_data_list = ApsHelpers.get_new_pr_data()
            if not pr_data_list:
                return []

        pr_datetime_fields = ('avail_date', 'create_date', 'avail_end_date', 'sys_date', 'sys_stamp')

        df = pd.DataFrame(pr_data_list)
        
        keep_cols = ['materialno', 'category', 'avail_qty', 'create_date', 'avail_date', 'vendorno']
        df = df[[col for col in keep_cols if col in df.columns]]
        
        for field in group_by:
            if field in pr_datetime_fields and field in df.columns:
                df[field] = pd.to_datetime(df[field], errors='coerce').dt.date
        
        agg_dict = {'avail_qty': 'sum'}
        other_cols = [col for col in df.columns if col not in group_by and col != 'avail_qty']
        for col in other_cols:
            agg_dict[col] = 'last'
        
        result_df = df.groupby(group_by, dropna=False).agg(agg_dict).reset_index()
        
        result_df = result_df.replace({pd.NA: None, pd.NaT: None, float('nan'): None})
        
        return result_df.to_dict('records')


    @staticmethod
    def pr_push_success(prno: str, msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} ✅ {msg_from}: '{_code}, {_id}, {_entryid}' @ {prno}"
            logger.update("PR状态", prno, "")
            response_json = ApsHelpers._modify_supply(supplyno=prno, to_status='CRE', memo=memo, _sn=_code, _id=_id, _entryid=_entryid)
            logger.info(f"更新PR状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PR状态时发生网络错误：{str(e)}"
            logger.fail("PR状态更新", prno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def pr_push_failed(prno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass
        logger.fail("推送 PR", json.dumps(push_data, ensure_ascii=False), msg)
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} 🚫 {msg_from}: '{msg}'"
            response_json = ApsHelpers._modify_supply(supplyno=prno, to_status='NEW', memo=memo)
            return response_json
        except Exception as e:
            error_msg = f"更新PR失败状态时发生网络错误：{str(e)}"
            logger.fail("PR状态更新", prno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)



    @staticmethod
    def query_material(materialnos: str | list[str]) -> list:
        """
        查询物料信息（优先从缓存获取，缓存未命中则访问API并加入缓存）
        Args:
            materialnos: 物料编号（多个用半角逗号分隔）或物料编号列表
        Returns:
            物料信息列表
        """
        if isinstance(materialnos, list):
            material_list = [m.strip() for m in materialnos if m.strip()]
        else:
            material_list = [m.strip() for m in materialnos.split(',') if m.strip()]
        
        if not material_list:
            return []
        
        cache = get_production_cache()
        
        # 批量从缓存获取
        cached_data = cache.batch_get_material(material_list)
        
        # 检查缓存命中情况
        cached_keys = {item['materialno'] for item in cached_data}
        missing_materials = [m for m in material_list if m not in cached_keys]
        
        if missing_materials:
            materialnos_str = ','.join(missing_materials)
            url = f"{THIS_BASE_URL}/api/t_material/{materialnos_str}?db_name={MYAPS_MAIN_DB}"
            try:
                response_json = ApsHelpers._call_api('GET', url)
                api_data = response_json.get('data', [])
                
                # 补充缓存
                for item in api_data:
                    material_no = item.get('materialno', '')
                    if material_no:
                        cache._cache['material'][material_no] = item
                
                # 合并结果
                cached_data.extend(api_data)
            except Exception as e:
                error_msg = f"查询物料信息时发生网络错误：{str(e)}"
                logger.fail("查询物料信息", materialnos_str, error_msg)
        
        return cached_data


    @staticmethod
    def get_supplymo_detaildata(supplyno: str, get_prev_mo:bool=False, get_next_mo:bool=False, get_origin_so:bool=False):
        """
        获取工单的工序详情、及MTO销售订单信息
        Args:
            supplyno: 工单号
            get_prev_mo: 是否查询前 前置 工单
            get_next_mo: 是否查询后 后置 工单
        Returns:
            工单计划单详情
        """
        cache = get_production_cache()
        mo_data = cache.get_supply_mo(supplyno)

        if mo_data:

            mo_data['orderwc'] = cache.get_orderwc(supplyno)
            
            if get_origin_so:
                vendorno = mo_data.get('vendorno', '')
                if vendorno:
                    mo_data['so'] = ApsHelpers.get_demand_datalist(vendorno)

            if get_prev_mo:
                related_demand = cache.get_demand(demand_no=supplyno)
                demands_data = [_ for _ in related_demand if _.get('type') != 'SO']
                if demands_data:
                    demands_no = [_['demandno'] for _ in demands_data]
                    peg_query_result = cache.batch_get_peg_by_demand(demands_no)
                    mo_data['prev_mo'] = cache.batch_get_supply_mo(peg_query_result)
                
            if get_next_mo:
                demands_no = cache.get_peg_by_supply(supplyno)
                mo_data['next_mo'] = cache.batch_get_supply_mo(demands_no)
            return mo_data
        else:
            url = f"{THIS_BASE_URL}/api/v_supply_mo/{supplyno}?db_name={MYAPS_MAIN_DB}&prev_mo={get_prev_mo}&next_mo={get_next_mo}&origin_so={get_origin_so}"
            supply_response_json = ApsHelpers._call_api('GET', url)
            try:
                if supply_response_json.get('success') != 0 and supply_response_json.get('data'):
                    mo_data = supply_response_json['data'][0]
                    cache._cache['supply_mo'][supplyno] = mo_data
                    return mo_data
                else:
                    # raise Exception(f"API返回错误: {supply_response_json.get('message', '未知错误')}")
                    logger.fail("获取工单计划单详情", supplyno, f"API返回错误: {supply_response_json.get('message', '未知错误')}")
            except Exception as e:
                logger.fail("获取工单计划单详情", supplyno, f"{str(e)}")


    @staticmethod
    def get_demand_datalist(demandno: str) -> List[Dict]:
        """
        获取需求信息（优先从缓存获取，缓存未命中则访问API并加入缓存）
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        cache = get_production_cache()
        result_data = cache.get_demand(demandno)
        
        if result_data:
            return result_data
        
        url = f"{THIS_BASE_URL}/api/v_demand/{demandno}?db_name={MYAPS_MAIN_DB}"
        demand_response_json = ApsHelpers._call_api('GET', url)
        api_data = demand_response_json.get('data', [])
        
        if api_data:
            cache._cache['demand'][demandno] = api_data
        
        return api_data


    @staticmethod
    def get_dategrouped_pr(db_name: str=None, period: int|str=30, groupdates: Optional[str]=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        db_name = db_name or MYAPS_MAIN_DB
        url = f"{THIS_BASE_URL}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}"
        response_json = ApsHelpers._call_api('GET', url)
        data = response_json.get('data', [])
        field_map = field_map or {
            'materialno': '料号',
            'datestr': '交期',
            'groupdate': '日期',
            'qty': '数量',
        }
        if not field_map:
            return data
        # 转换数据，确保所有日期对象都被转换为字符串
        result = []
        for item in data:
            mapped_item = {}
            for k, v in item.items():
                # 转换日期对象为字符串
                if isinstance(v, (date, datetime)):
                    v = str(v)
                mapped_item[field_map.get(k, k)] = v
            result.append(mapped_item)
        return result
