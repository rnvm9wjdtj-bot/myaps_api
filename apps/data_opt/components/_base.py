import json
import pandas as pd
import time
import threading
import asyncio
import inspect
from pathlib import Path

from enum import Enum
from typing import List, Dict, Optional, Literal, Callable, Union, Any, Type
from collections import defaultdict
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel


from core.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET
from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.utils.db_operation import db_exec_sql
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


class BaseConnection(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    
    def __init__(self):
        self._session = get_session()
        self._async_session = None

    async def _get_async_session(self):
        """
        获取异步会话
        """
        # 每次都获取新的异步会话，避免使用已关闭的会话
        from apps.data_opt.utils.common import get_async_session
        return await get_async_session()

    async def _close_async_session(self):
        """
        关闭异步会话
        """
        if self._async_session:
            if hasattr(self._async_session, 'aclose'):
                await self._async_session.aclose()
            elif hasattr(self._async_session, 'close'):
                self._async_session.close()
            self._async_session = None


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
    async def pull_from_source_async(self, *args, **kwargs):
        """
        异步从目标系统获取数据
        """
        pass

    # @abstractmethod
    def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass

    # @abstractmethod
    async def push_into_target_async(self, *args, **kwargs):
        """
        异步推送数据到目标系统
        """
        pass


class CacheItem(Enum):
    SUPPLY_MO = 'supply_mo'
    ORDER_WC = 'orderwc'
    DEMAND = 'demand'
    PEG = 'peg'
    MATERIAL = 'material'


class _ProductionDataCache:
    """生产数据缓存管理器"""
    
    def __init__(self):
        # 状态标志
        self._initialized = False
        self._is_loading = False
        self._load_lock = asyncio.Lock()
        # [已移除] self._refresh_lock = threading.Lock()
        
        # 等待队列（用于批次间等待机制）
        self._wait_queue: List[asyncio.Future] = []
        self._wait_lock = asyncio.Lock()
        
        # 待合并的 supplynos（用于增量加载）
        self._pending_supplynos: set = set()
        self._pending_lock = asyncio.Lock()
        
        # 配置
        self.WAIT_TIMEOUT = 30.0  # 等待超时（秒）
        self.LOAD_TIMEOUT = 60.0  # 加载超时（秒）
        
        # 加载完成信号（用于跨协程通知）
        self._loading_complete = asyncio.Event()
        self._loading_complete.set()
        
        # 缓存项配置（由子类/项目配置覆盖）
        self.CACHE_ITEMS = [CacheItem.SUPPLY_MO.value, CacheItem.ORDER_WC.value, CacheItem.DEMAND.value, CacheItem.PEG.value, CacheItem.MATERIAL.value]
        
        # 缓存项依赖关系（声明式配置）
        # 格式：{ CacheItem: [依赖项列表] }
        # 如果声明加载某项，但其依赖基础未在 CACHE_ITEMS 中，则自动补充
        self.CACHE_ITEM_DEPS = {
            CacheItem.DEMAND: [CacheItem.PEG],
            CacheItem.ORDER_WC: [CacheItem.SUPPLY_MO],
            CacheItem.PEG: [CacheItem.SUPPLY_MO],
            CacheItem.MATERIAL: [CacheItem.SUPPLY_MO, CacheItem.DEMAND],
        }
        
        # 强制加载的缓存项（即使未在 CACHE_ITEMS 中也会加载）
        self.CACHE_ITEMS_FORCE = [CacheItem.SUPPLY_MO.value]
        
        # 解析后的有效缓存项（运行时计算）
        self._effective_cache_items: List[str] = []
        
        # 缓存数据
        self._cache: Dict[str, Dict[Any, Any]] = {
            CacheItem.SUPPLY_MO.value: {},
            CacheItem.ORDER_WC.value: {},
            CacheItem.DEMAND.value: {},
            CacheItem.PEG.value: {},
            CacheItem.MATERIAL.value: {}
        }
    
        # 统计信息
        self._stats = {
            'total_hits': 0,
            'total_misses': 0,
            'total_refreshes': 0,
            'cache_size': 0
        }


    def set_cache_items(self, cache_items: List[Union[str, 'CacheItem']]):
        """设置缓存项配置
        
        允许使用字符串或 CacheItem 枚举对象来指定缓存项。
        会自动处理依赖关系并更新有效缓存项列表。
        
        Args:
            cache_items: 缓存项列表，可以是字符串或 CacheItem 枚举对象
        """
        # 处理输入，确保所有项都是字符串
        processed_items = []
        for item in cache_items:
            if isinstance(item, CacheItem):
                processed_items.append(item.value)
            elif isinstance(item, str):
                # 验证字符串是否是有效的缓存项
                valid_values = [e.value for e in CacheItem]
                if item in valid_values:
                    processed_items.append(item)
                else:
                    logger.warning("生产数据缓存", "", f"忽略无效的缓存项: {item}")
        
        # 更新缓存项配置
        self.CACHE_ITEMS = processed_items
        
        # 重新解析依赖关系，更新有效缓存项
        self._resolve_cache_items()
        logger.info("生产数据缓存", "", f"已设置缓存项: {self.CACHE_ITEMS}")


    async def ensure_initialized(self):
        """异步方式确保缓存已初始化
        
        [注意] 全量加载已禁用，请使用 load_on_demand 方法按需加载数据
        
        Args:
            db_name: 数据库名称（此参数在当前实现中不再使用）
        """
        if self._initialized:
            return
        
        # [已修改] 全量加载已禁用，提示用户使用按需加载
        logger.warning(
            "生产数据缓存", 
            "", 
            "全量加载已禁用。请使用 cache.load_on_demand(db_name, supplynos=[...]) 按需加载指定工单数据"
        )
        # 不执行任何加载操作，等待用户显式调用 load_on_demand
        return
    
    def _resolve_cache_items(self) -> List[str]:
        """解析缓存项配置，处理依赖补充和强制加载项
        
        依赖补充规则：
        - 如果声明加载某项，但其依赖基础未在 CACHE_ITEMS 中，则自动补充
        - 强制加载项（supply_mo, orderwc, peg）始终加载
        - 支持多层依赖传递（如 demand -> peg -> supply_mo）
        
        Returns:
            解析后的有效缓存项列表
        """
        def resolve_deps(item: CacheItem, resolved: set):
            """递归解析依赖项"""
            for dep in self.CACHE_ITEM_DEPS.get(item, []):
                if dep not in resolved:
                    resolved.add(dep.value)
                    resolve_deps(dep, resolved)
        
        effective = set()
        
        for item in self.CACHE_ITEMS:
            effective.add(item if isinstance(item, str) else item.value)
        
        for item in self.CACHE_ITEMS_FORCE:
            effective.add(item if isinstance(item, str) else item.value)
        
        for item in list(effective):
            item_enum = CacheItem(item) if item in [e.value for e in CacheItem] else None
            if item_enum:
                resolve_deps(item_enum, effective)
        
        self._effective_cache_items = list(effective)
        return self._effective_cache_items
    
    async def _initialize_on_needed(self, db_name: str, supplynos: list):
        """按需加载缓存，只加载指定 supplyno 相关的数据
        
        加载顺序：
        1. supply_mo - 只加载指定的 supplyno 数据
        2. orderwc - 只加载与指定 supplyno 相关的工序数据
        3. peg - 只加载与指定 supplyno 相关的匹配关系，并收集 demandno
        4. demand - 只加载 peg 中收集到的 demandno 数据
        5. material - 全量加载（或根据需要优化）
        
        Args:
            db_name: 数据库名称
            supplynos: supplyno 列表，指定需要加载的数据
        """
        if not supplynos:
            logger.warning("生产数据缓存", "", "传入的 supplyno 列表为空，跳过按需加载")
            return
        
        try:
            effective_items = self._resolve_cache_items()
            logger.info("生产数据缓存", "", f"开始按需加载，共 {len(supplynos)} 个 supplyno，缓存项: {effective_items}")
            
            # 1. 加载 supply_mo 缓存（核心数据）- 必须加载
            logger.info("生产数据缓存", "", "开始构建 supply_mo 缓存（按需）...")
            await self._build_supply_mo_cache(db_name, supplynos=supplynos)
            logger.success("生产数据缓存", "", f"{CacheItem.SUPPLY_MO.value} 缓存加载: {len(self._cache[CacheItem.SUPPLY_MO.value])} 条")
            
            # 2. 加载 orderwc 缓存（子表，通过 supplyno 关联）- 必须加载
            logger.info("生产数据缓存", "", "开始构建 orderwc 缓存（按需）...")
            await self._build_orderwc_cache(db_name, supplynos=supplynos)
            logger.success("生产数据缓存", "", f"{CacheItem.ORDER_WC.value} 缓存加载: {len(self._cache[CacheItem.ORDER_WC.value])} 条")
            
            # 3. 加载 peg 缓存（多对多关系），并收集 demandno - 必须加载
            logger.info("生产数据缓存", "", "开始构建 peg 缓存（按需）...")
            demand_nos = await self._build_peg_cache(db_name, supplynos=supplynos)
            logger.success("生产数据缓存", "", f"{CacheItem.PEG.value} 缓存加载: {len(self._cache[CacheItem.PEG.value]['demand_to_supply'])} 条 DemandNo")
            
            # 4. 加载 demand 缓存（根据 peg 中收集的 demandno）
            if CacheItem.DEMAND.value in effective_items:
                logger.info("生产数据缓存", "", "开始构建 demand 缓存（按需）...")
                await self._build_demand_cache(db_name, demandnos=demand_nos)
                logger.success("生产数据缓存", "", f"{CacheItem.DEMAND.value} 缓存加载: {len(self._cache[CacheItem.DEMAND.value])} 条")
            else:
                logger.info("生产数据缓存", "", "跳过 demand 缓存（未启用）")
            
            # 5. 加载 material 缓存（收集 supply_mo 和 demand 中的 materialno 并集）
            if CacheItem.MATERIAL.value in effective_items:
                material_nos_from_supply = {item.get('materialno') for item in self._cache[CacheItem.SUPPLY_MO.value].values() if item.get('materialno')}
                material_nos_from_demand = {item.get('materialno') for item in self._cache[CacheItem.DEMAND.value].values() if item.get('materialno')}
                material_nos = list(material_nos_from_supply | material_nos_from_demand)
                logger.info("生产数据缓存", "", f"开始构建 material 缓存（按需），共 {len(material_nos)} 个物料号）...")
                await self._build_material_cache(db_name, material_nos=material_nos)
                logger.success("生产数据缓存", "", f"{CacheItem.MATERIAL.value} 缓存加载: {len(self._cache[CacheItem.MATERIAL.value])} 条")
            else:
                logger.info("生产数据缓存", "", "跳过 material 缓存（未启用）")
            
            self._stats['total_refreshes'] += 1
            self._stats['cache_size'] = sum(
                len(v) for v in self._cache.values() if isinstance(v, dict)
            )
            logger.success("生产数据缓存", "", f"按需加载完成，共 {self._stats['cache_size']} 条数据")
                
        except Exception as e:
            logger.fail("生产数据缓存", "", f"按需加载失败: {e}")
            raise
    

    async def _build_cache(self, db_name: str, table_name: str, cache_name: str, cache_factory, process_item, filter_string: str = ''):
        """通用的缓存构建方法"""
        cache = cache_factory()
        
        # 直接从数据库获取数据，不分页，因为 db_query 已经处理了分页
        result = await db_query(db_name=db_name, model_or_tablename=table_name, filter_string=filter_string, page_size=1000, page_index=0)
        data_list = result.get('data', [])
        
        for item in data_list:
            process_item(item, cache)
        
        self._cache[cache_name] = cache
        return data_list
    

    async def _build_supply_mo_cache(self, db_name: str, supplynos: list = None):
        """使用数据库查询方式构建 supply_mo 缓存
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 的数据
        """
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no] = item
        
        # 构建过滤条件
        filter_string = ''
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            filter_string = f"`SupplyNo` IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_supply_mo",
            cache_name=CacheItem.SUPPLY_MO.value,
            cache_factory=dict,
            process_item=process_item,
            filter_string=filter_string
        )
    

    async def _build_orderwc_cache(self, db_name: str, supplynos: list = None):
        """使用数据库查询方式构建 orderwc 缓存（以 supplyno 为索引）
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 的数据
        """
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no].append(item)
        
        # 构建过滤条件
        filter_string = ''
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            filter_string = f"`SupplyNo` IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_orderwc",
            cache_name=CacheItem.ORDER_WC.value,
            cache_factory=lambda: defaultdict(list),
            process_item=process_item,
            filter_string=filter_string
        )
    

    async def _build_demand_cache(self, db_name: str, demandnos: list = None):
        """使用数据库查询方式构建 demand 缓存
        
        Args:
            db_name: 数据库名称
            demandnos: 可选，demandno 列表，如果提供则只加载这些 demandno 的数据
        """
        def process_item(item, cache):
            demand_no = item.get('demandno', '')
            if demand_no:
                cache[demand_no].append(item)
        
        # 构建过滤条件
        filter_string = ''
        if demandnos:
            formatted_nos = ','.join([f"'{d}'" for d in demandnos])
            filter_string = f"`DemandNo` IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_demand",
            cache_name=CacheItem.DEMAND.value,
            cache_factory=lambda: defaultdict(list),
            process_item=process_item,
            filter_string=filter_string
        )


    async def _build_peg_cache(self, db_name: str, supplynos: list = None):
        """使用直接 SQL 方式构建 peg 缓存（双向索引），加快构建速度
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 相关的 peg 数据
            
        Returns:
            list: 收集到的所有 demandno 列表
        """
        from apps.io_api.routers import MINI_PEG_SQL

        demand_nos = set()
        
        # 构建 peg 缓存结构
        peg_cache = {
            'demand_to_supply': defaultdict(list),
            'supply_to_demand': defaultdict(list)
        }
        
        # 构建 WHERE 子句
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            where_string = f"s.SupplyNo IN ({formatted_nos})"
        else:
            where_string = "1=1"  # 全量获取
        
        # 填充 SQL 语句
        sql = MINI_PEG_SQL.format(where_string=where_string)
        
        # 执行 SQL 查询
        try:
            logger.info("生产数据缓存", "", f"开始执行 PEG SQL 查询，{'全量' if not supplynos else f'按需({len(supplynos)}个)'}模式")
            result = await db_exec_sql(db_name, sql, description="构建 PEG 缓存")
            
            # 处理查询结果（db_exec_sql 返回 standard_response 格式）
            data_list = result.get('data', []) if isinstance(result, dict) else result
            
            # 处理查询结果
            for item in data_list:
                demand_no = item.get('DemandNo', '')
                s_supply_no = item.get('S_SupplyNo', '')
                
                if demand_no and s_supply_no:
                    # 收集 demandno
                    demand_nos.add(demand_no)
                    
                    # 构建双向索引
                    if s_supply_no not in peg_cache['demand_to_supply'][demand_no]:
                        peg_cache['demand_to_supply'][demand_no].append(s_supply_no)
                    if demand_no not in peg_cache['supply_to_demand'][s_supply_no]:
                        peg_cache['supply_to_demand'][s_supply_no].append(demand_no)
            
            # 更新缓存
            self._cache[CacheItem.PEG.value] = peg_cache
            logger.success("生产数据缓存", "", f"PEG 缓存构建完成，共 {len(peg_cache['demand_to_supply'])} 条 DemandNo")
            
        except Exception as e:
            logger.fail("生产数据缓存", "", f"PEG 缓存构建失败: {e}")
            raise
        
        return list(demand_nos)
    

    async def _build_material_cache(self, db_name: str, material_nos: list = None):
        """使用数据库查询方式构建 material 缓存
        
        Args:
            db_name: 数据库名称
            material_nos: 可选，materialno 列表，如果提供则只加载这些物料号的数据
        """
        def process_item(item, cache):
            material_no = item.get('materialno', '')
            if material_no:
                cache[material_no] = item
        
        filter_string = ''
        if material_nos:
            formatted_nos = ','.join([f"'{m}'" for m in material_nos])
            filter_string = f"materialno IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="t_material",
            cache_name=CacheItem.MATERIAL.value,
            cache_factory=dict,
            process_item=process_item,
            filter_string=filter_string
        )


    async def _wait_for_loading(self, timeout: float = None) -> bool:
        """等待缓存加载完成
        
        Args:
            timeout: 等待超时时间（秒），默认使用 self.WAIT_TIMEOUT
            
        Returns:
            bool: True 表示等待成功（加载完成），False 表示超时
        """
        if timeout is None:
            timeout = self.WAIT_TIMEOUT
        
        try:
            await asyncio.wait_for(self._loading_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning("生产数据缓存", "", f"等待缓存加载超时（{timeout}秒）")
            return False


    async def _merge_pending_supplynos(self, new_supplynos: list) -> list:
        """合并待加载的 supplynos
        
        Args:
            new_supplynos: 新的 supplyno 列表
            
        Returns:
            list: 合并后的完整 supplyno 列表
        """
        async with self._pending_lock:
            self._pending_supplynos.update(new_supplynos)
            return list(self._pending_supplynos.copy())


    def _clear_pending_supplynos(self):
        """清除待加载的 supplynos"""
        self._pending_supplynos.clear()


    async def establish_production_cache(self, db_name: str, supplynos: list):
        """PL 状态变更事件处理
        
        重新构建缓存：丢弃旧缓存，按需加载全新缓存。
        支持多批次并发时的等待机制和增量合并。
        
        Args:
            db_name: 数据库名称
            supplynos: supplyno 列表，指定需要加载的数据
        """
        if not supplynos:
            logger.warning("生产数据缓存", "", "传入的 supplyno 列表为空，跳过按需加载")
            return
        
        async with self._load_lock:
            if self._is_loading:
                logger.info("生产数据缓存", "", f"缓存正在加载中（{len(supplynos)}个supplyno等待中）...")
                wait_success = await self._wait_for_loading()
                
                if not wait_success:
                    logger.warning("生产数据缓存", "", "等待缓存加载超时")
                else:
                    logger.info("生产数据缓存", "", "等待的缓存加载已完成")
                
                if self._initialized:
                    logger.info("生产数据缓存", "", "缓存已就绪，无需重新加载")
                    return
            
            merged_supplynos = await self._merge_pending_supplynos(supplynos)
            all_supplynos = list(set(merged_supplynos) | set(supplynos))
            
            logger.info("生产数据缓存", "", f"开始按需加载 {len(all_supplynos)} 个 supplyno 的数据...")
            self._is_loading = True
            self._loading_complete.clear()
            
            try:
                await asyncio.wait_for(
                    self._initialize_on_needed(db_name, all_supplynos),
                    timeout=self.LOAD_TIMEOUT
                )
                self._initialized = True
                self._clear_pending_supplynos()
                logger.success("生产数据缓存", "", f"按需加载完成，共 {len(all_supplynos)} 个 supplyno")
                
            except asyncio.TimeoutError:
                logger.fail("生产数据缓存", "", f"按需加载超时（{self.LOAD_TIMEOUT}秒）")
                self._is_loading = False
                self._loading_complete.set()
                self._initialized = False
                raise
            except Exception as e:
                logger.fail("生产数据缓存", "", f"按需加载失败: {e}")
                self._loading_complete.set()
                raise
            finally:
                if self._is_loading:
                    self._is_loading = False
                    self._loading_complete.set()


    def get_supply_mo(self, supply_no: str) -> Dict:
        """获取工单数据（按供应号查找）"""
        data = self._cache[CacheItem.SUPPLY_MO.value].get(supply_no)
        if data:
            self._stats['total_hits'] += 1
            return data
        
        self._stats['total_misses'] += 1
        return {}
    

    def batch_get_supply_mo(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工单数据"""
        results = []
        for supply_no in supplynos:
            data = self._cache[CacheItem.SUPPLY_MO.value].get(supply_no)
            if data:
                results.append(data)
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_orderwc(self, supply_no: str) -> List[Dict]:
        """获取工序数据（按供应号查找）"""
        data = self._cache[CacheItem.ORDER_WC.value].get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_orderwc(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工序数据（按供应号查找）"""
        results = []
        for supply_no in supplynos:
            data_list = self._cache[CacheItem.ORDER_WC.value].get(supply_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_demand(self, demand_no: str) -> List[Dict]:
        """获取需求数据"""
        data = self._cache[CacheItem.DEMAND.value].get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_demand(self, demandnos: List[str]) -> List[Dict]:
        """批量获取需求数据"""
        results = []
        for demand_no in demandnos:
            data_list = self._cache[CacheItem.DEMAND.value].get(demand_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_peg_by_demand(self, demand_no: str) -> List[str]:
        """根据 DemandNo 获取对应的 S_SupplyNo 列表"""
        cache = self._cache[CacheItem.PEG.value]['demand_to_supply']
        data = cache.get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def get_peg_by_supply(self, supply_no: str) -> List[str]:
        """根据 S_SupplyNo 获取对应的 DemandNo 列表"""
        cache = self._cache[CacheItem.PEG.value]['supply_to_demand']
        data = cache.get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_peg_by_demand(self, demandnos: List[str]) -> Dict[str, List[str]]:
        """批量根据 DemandNo 获取 S_SupplyNo 列表"""
        cache = self._cache[CacheItem.PEG.value]['demand_to_supply']
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
        cache = self._cache[CacheItem.PEG.value]['supply_to_demand']
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
        data = self._cache[CacheItem.MATERIAL.value].get(material_no)
        if data:
            self._stats['total_hits'] += 1
            return [data]
        
        self._stats['total_misses'] += 1
        return []
    

    def batch_get_material(self, materialnos: List[str]) -> List[Dict]:
        """批量获取物料数据"""
        results = []
        for material_no in materialnos:
            data = self._cache[CacheItem.MATERIAL.value].get(material_no)
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
                CacheItem.SUPPLY_MO.value: len(self._cache[CacheItem.SUPPLY_MO.value]),
                CacheItem.ORDER_WC.value: len(self._cache[CacheItem.ORDER_WC.value]),
                CacheItem.DEMAND.value: len(self._cache[CacheItem.DEMAND.value]),
                CacheItem.PEG.value: len(self._cache[CacheItem.PEG.value]),
                CacheItem.MATERIAL.value: len(self._cache[CacheItem.MATERIAL.value])
            }
        }


# 全局缓存实例
_production_cache = _ProductionDataCache()


def get_production_cache() -> _ProductionDataCache:
    """获取生产数据缓存管理器实例"""
    return _production_cache


class ApsHelpers:
    
    # 物料信息缓存，最大缓存1000条
    _material_cache = {}
    _material_cache_max_size = 1000

    @staticmethod
    def _call_api_sync(method: str, url: str, **kwargs) -> Dict[str, Any]:
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
    async def _call_api_async(method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        异步通用 API 调用方法，包含错误处理、超时设置和重试机制
        
        Args:
            method: HTTP 方法，如 'GET', 'POST', 'PATCH', 'PUT'
            url: API 地址
            **kwargs: 其他参数，如 json, timeout 等
        
        Returns:
            API 返回的 JSON 数据
        
        Raises:
            Exception: API 调用失败
        """
        from apps.data_opt.utils.common import get_async_session
        
        max_retries = 3
        retry_count = 0
        timeout = kwargs.pop('timeout', (30, 60))
        
        while retry_count < max_retries:
            # 每次重试都获取新的异步会话
            async_session = await get_async_session()
            
            try:
                # 直接使用原始的 httpx.AsyncClient 方法
                if hasattr(async_session, 'client') and hasattr(async_session.client, 'request'):
                    # 使用包装的客户端
                    response = await async_session.client.request(method, url, timeout=timeout, **kwargs)
                elif hasattr(async_session, 'request'):
                    # 使用直接的客户端
                    response = await async_session.request(method, url, timeout=timeout, **kwargs)
                else:
                    # 尝试使用 get_async 等方法
                    # 获取对应的异步方法
                    if method.upper() == 'GET':
                        method_func = getattr(async_session, 'get_async', None)
                    elif method.upper() == 'POST':
                        method_func = getattr(async_session, 'post_async', None)
                    elif method.upper() == 'PATCH':
                        method_func = getattr(async_session, 'patch_async', None)
                    elif method.upper() == 'PUT':
                        method_func = getattr(async_session, 'put_async', None)
                    elif method.upper() == 'DELETE':
                        method_func = getattr(async_session, 'delete_async', None)
                    else:
                        raise ValueError(f"不支持的 HTTP 方法: {method}")
                    
                    # 检查方法是否存在且可调用
                    if not method_func:
                        raise Exception(f"异步会话没有 {method.upper()}_async 方法")
                    if not callable(method_func):
                        raise Exception(f"{method.upper()}_async 不是可调用对象，类型: {type(method_func)}")
                    
                    # 调用方法获取响应
                    response = await method_func(url, timeout=timeout, **kwargs)
                
                # 检查 HTTP 状态码
                if hasattr(response, 'raise_for_status'):
                    response.raise_for_status()
                elif hasattr(response, 'status_code') and response.status_code >= 400:
                    raise Exception(f"HTTP 错误: {response.status_code}")
                
                # 获取响应数据
                # 检查 response 是否是字符串
                if isinstance(response, str):
                    # 如果是字符串，尝试解析为 JSON
                    try:
                        return json.loads(response)
                    except json.JSONDecodeError:
                        raise Exception(f"响应是字符串但不是有效的 JSON: {response}")
                
                # 检查 response 是否是 None
                if response is None:
                    raise Exception("响应对象为 None")
                
                # 检查 response 是否有 json 方法
                if hasattr(response, 'json'):
                    if callable(response.json):
                        if inspect.iscoroutinefunction(response.json):
                            return await response.json()
                        else:
                            return response.json()
                    else:
                        # 如果 json 不是可调用对象，尝试直接返回它
                        return response.json
                # 检查 response 是否有 text 方法
                elif hasattr(response, 'text'):
                    if callable(response.text):
                        text = await response.text() if inspect.iscoroutinefunction(response.text) else response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            raise Exception(f"响应文本不是有效的 JSON: {text}")
                    else:
                        # 如果 text 不是可调用对象，尝试直接返回它
                        try:
                            return json.loads(response.text)
                        except json.JSONDecodeError:
                            raise Exception(f"响应文本不是有效的 JSON: {response.text}")
                # 检查 response 是否是字典
                elif isinstance(response, dict):
                    return response
                # 检查 response 是否是列表
                elif isinstance(response, list):
                    return response
                else:
                    raise Exception(f"无法获取响应数据，响应类型: {type(response)}")
                    
            except (Exception) as e:
                retry_count += 1
                logger.warning(f"API 调用失败，第{retry_count}次重试: {str(e)}")
                if retry_count >= max_retries:
                    logger.fail("API 调用", url, str(e))
                    raise
                await asyncio.sleep(1 * retry_count)  # 指数退避策略
            finally:
                # 关闭异步会话
                if hasattr(async_session, 'aclose'):
                    await async_session.aclose()
                elif hasattr(async_session, 'close'):
                    async_session.close()
        
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
    async def mto_workreport_to_virtual_stock_async(db:str=MYAPS_MAIN_DB):
        """
        异步将报工数据 转化为 虚拟库存 数据，只处理MTO报工
        🅰 db: 账套名称，默认MYAPS_MAIN_DB
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        url = f"{THIS_BASE_URL}/api/v_supply_complete?db_name={db}"
        response_json = await ApsHelpers._call_api_async('GET', url)
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
    async def refresh_supply_async(supply_data:Union[List[Dict[str, Any]], pd.DataFrame], type_:Literal['ST', 'SO']='ST', dbs:str=MYAPS_DB_SET):
        from apps.io_api.schemas import AcceptSupply

        if isinstance(supply_data, pd.DataFrame):
            supply_data = supply_data.to_dict('records')
        supply_data = [AcceptSupply(**item).model_dump(exclude_none=True) for item in supply_data]
        url = f"{THIS_BASE_URL}/api/t_supply/type/{type_}?db_name={dbs}"
        refresh_result_json = await ApsHelpers._call_api_async('PUT', url, json=supply_data)
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
    async def confirm_workreport_async(db_name:str=MYAPS_MAIN_DB):
        """
        异步确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        """
        logger.start("确认报工记录任务")
        url = f"{THIS_BASE_URL}/api/t_confirm?db_name={db_name}"
        response_json = await ApsHelpers._call_api_async('PATCH', url)
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
    async def _modify_supply_async(supplyno: str, to_status: Literal['NEW', 'CRE', 'E2A', 'REL']=None, memo: str=None, _sn: str=None, _id: str=None, _entryid: str=None):
        url = f'{THIS_BASE_URL}/api/t_supply/{supplyno}/...?db_name={MYAPS_MAIN_DB}'
        response_json = await ApsHelpers._call_api_async('PATCH', url, json={
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
    async def pl_release_success_async(native_plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _id: str=None, _entryid: str=None):
        """
        异步通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段
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
            logger.query("PL信息", native_plno, "")
            query_url = f"{THIS_BASE_URL}/api/v_supply_mo/{native_plno}?db_name={MYAPS_MAIN_DB}"
            query_result_json = await ApsHelpers._call_api_async('GET', query_url)
            logger.info(f"查询PL信息响应：成功")

            if query_result_json.get('success') == 0:
                logger.fail("PL查询", native_plno, query_result_json.get('message'))
                return standard_response(status_code=query_result_json.get('status_code', 500), success=0, message=query_result_json.get('message'))

            query_data = query_result_json.get('data', [])
            if not query_data or len(query_data) > 1:
                logger.fail("PL查询", native_plno, "未找到或多条匹配", to_file=True)
                return standard_response(success=0, message=f"PL {native_plno} not found or multiple records matched.")

            if query_data[0].get("type") != "PL":
                logger.fail("PL查询", native_plno, "非PL类型", to_file=True)
                return standard_response(status_code=400, success=0, message=f"Supply {native_plno} is not a PL.")

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
            response_json = await ApsHelpers._call_api_async('PATCH', patch_url, json=patch_data)
            logger.info(f"更新PL状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PL状态为MO时发生网络错误：{str(e)}"
            logger.fail("PL状态更新", native_plno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def pl_release_failed(native_plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, push_data: dict=None, msg_from: str=None, **kwargs):
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
    async def pl_release_failed_async(native_plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, push_data: dict=None, msg_from: str=None):
        logger.warning_msg(f"推送 MO {msg}", json.dumps(push_data, ensure_ascii=False), to_file=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass

        memo = f"{now} 🚫 {msg_from}: '{msg}'"
        try:
            response_json = await ApsHelpers._modify_supply_async(supplyno=native_plno, to_status=to_status, memo=memo)
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
    async def rs_push_success_async(rsno: str, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} ✅ {msg_from}: '{_code}, {_id}, {_entryid}' @ {rsno}"
            
            logger.update("RS状态", rsno, f"目标状态{to_status}")
            url = f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}'
            response_json = await ApsHelpers._call_api_async('PATCH', url, json={
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
    async def rs_push_failed_async(rsno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
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
            response_json = await ApsHelpers._call_api_async('PATCH', url, json={
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
    async def pr_push_success_async(prno: str, msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} ✅ {msg_from}: '{_code}, {_id}, {_entryid}' @ {prno}"
            logger.update("PR状态", prno, "")
            response_json = await ApsHelpers._modify_supply_async(supplyno=prno, to_status='CRE', memo=memo, _sn=_code, _id=_id, _entryid=_entryid)
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
    async def pr_push_failed_async(prno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass
        logger.fail("推送 PR", json.dumps(push_data, ensure_ascii=False), msg)
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = f"{now} 🚫 {msg_from}: '{msg}'"
            response_json = await ApsHelpers._modify_supply_async(supplyno=prno, to_status='NEW', memo=memo)
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
                        cache._cache[CacheItem.MATERIAL.value][material_no] = item
                
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
                    cache._cache[CacheItem.SUPPLY_MO.value][supplyno] = mo_data
                    return mo_data
                else:
                    # raise Exception(f"API返回错误: {supply_response_json.get('message', '未知错误')}")
                    logger.fail("获取工单计划单详情", supplyno, f"API返回错误: {supply_response_json.get('message', '未知错误')}")
            except Exception as e:
                logger.fail("获取工单计划单详情", supplyno, f"{str(e)}")

    @staticmethod
    async def get_supplymo_detaildata_async(supplyno: str, get_prev_mo:bool=False, get_next_mo:bool=False, get_origin_so:bool=False):
        """
        异步获取工单的工序详情、及MTO销售订单信息
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
                    mo_data['so'] = await ApsHelpers.get_demand_datalist_async(vendorno)

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
            supply_response_json = await ApsHelpers._call_api_async('GET', url)
            try:
                if supply_response_json.get('success') != 0 and supply_response_json.get('data'):
                    mo_data = supply_response_json['data'][0]
                    cache._cache[CacheItem.SUPPLY_MO.value][supplyno] = mo_data
                    return mo_data
                else:
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
            cache._cache[CacheItem.DEMAND.value][demandno] = api_data
        
        return api_data

    @staticmethod
    async def get_demand_datalist_async(demandno: str) -> List[Dict]:
        """
        异步获取需求信息（优先从缓存获取，缓存未命中则访问API并加入缓存）
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
        demand_response_json = await ApsHelpers._call_api_async('GET', url)
        api_data = demand_response_json.get('data', [])
        
        if api_data:
            cache._cache[CacheItem.DEMAND.value][demandno] = api_data
        
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
