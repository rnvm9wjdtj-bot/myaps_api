"""
连接类（同步和异步）
"""

import os
import time
import threading
import requests
from typing import Dict, Any, Optional, List, Type, TypeVar, Generic, Callable, AsyncGenerator, Union, Literal
from concurrent.futures import ThreadPoolExecutor
import asyncio

from ..common import get_optimized_session
from ._base import CACHE_JSON, console_log, HapConfig, ModelType, _MAX_CONCURRENCY, _DEFAULT_BUFFER_SIZE, _DEFAULT_MAX_RETRIES, _DEFAULT_RETRY_DELAY
from .utils import(
    HapUtils, AdaptiveTimeout, EnhancedRetryStrategy, TokenBucket, DecimalEncoder, HapApiMonitor,
    StringInternPool, DataProcessingPipeline, LightweightRow, ObjectPool, ConnectionPoolWarmer, SmartBatchSizeCalculator,
    AdaptiveRateController, hap_async_timer
)
from .models import Model
from .data_objects import HapRowSet, HapQuerySet, AsyncHapQuerySet


class HapConnection:
    def __init__(self, config: HapConfig=HapConfig):
        self.config = config
        self.base_url = config.BASE_URL
        self.app_key = config.APP_KEY
        self.sign = config.SIGN
        self.description = config.DESCRIPTION
        self.max_workers = config.MAX_WORKERS
        self.refresh_interval_seconds = config.REFRESH_INTERVAL_SECONDS
        self.qps_limit = getattr(config, 'QPS_LIMIT', 50)  # 从配置中读取QPS限制，默认为50
        self.models: Dict[str, Type[Model]] = {}
        self.headers = {
            'HAP-Appkey': self.app_key,
            'HAP-Sign': self.sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        # 缓存结构，包含数据和索引
        self.cache_data: Dict[str, Dict[str, Dict[str, Any]]] = {}  # 以 rowid 为键存储实际数据
        self.cache_indexes: Dict[str, Dict[str, Dict[str, str]]] = {}  # 存储不同索引到 rowid 的映射
        
        # 初始化令牌桶，用于控制QPS
        self.token_bucket = TokenBucket(capacity=self.qps_limit, refill_rate=self.qps_limit)
        
        # 根据 max_workers 动态调整 session 参数，确保至少 20 个连接
        session_pool_size = max(self.max_workers, 20)
        # 初始化Session并配置性能参数（使用优化版本，支持HTTP/2和连接池预热）
        self.session = get_optimized_session(
            retries=3,
            allowed_methods=["GET", "POST", "PATCH", "DELETE"],
            pool_connections=session_pool_size,  # 根据并发度动态调整连接池数量
            pool_maxsize=session_pool_size,     # 根据并发度动态调整最大连接数  
            connect_timeout=5.0,  # 增加连接超时时间
            read_timeout=60.0,    # 增加读取超时时间
            enable_http2=getattr(config, 'ENABLE_HTTP2', True),   # 默认启用HTTP/2
            enable_warmup=True,   # 启用连接池预热
        )
        
        # 初始化连接池预热器并执行预热
        self._connection_warmer = ConnectionPoolWarmer(
            session=self.session,
            max_warm_connections=min(session_pool_size, 10)  # 预热连接数不超过池大小
        )
        # 异步执行预热，不阻塞主流程
        self._connection_warmer.warm_up(
            base_url=self.base_url,
            headers=self.headers,
            timeout=5.0
        )
        
        # 初始化自适应超时管理器
        self.timeout_manager = AdaptiveTimeout(
            base_connect=5.0,
            base_read=60.0
        )
        
        # 初始化增强重试策略
        self.retry_strategy = EnhancedRetryStrategy(
            max_retries=3,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=0.1
        )
        
        # 初始化线程池
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # 内存监控相关
        self._memory_threshold_mb = config.MEMORY_THRESHOLD_MB
        self._cache_max_size = config.CACHE_MAX_SIZE
        self._enable_memory_management = config.ENABLE_MEMORY_MANAGEMENT
        
        # 初始化智能批处理大小计算器
        self._batch_size_calculator = SmartBatchSizeCalculator(
            base_size=200,
            min_size=50,
            max_size=500
        )
        
        # 启动缓存定时刷新任务
        self._start_cache_refresh_task()
    
    def get_optimal_batch_size(
        self,
        data_size: int,
        field_count: int = 10,
        complexity_score: float = 1.0
    ) -> int:
        """获取最优批处理大小
        
        根据数据特征动态计算最优批次大小。
        
        Args:
            data_size: 数据总量
            field_count: 字段数量
            complexity_score: 复杂度评分
            
        Returns:
            int: 最优批次大小
        """
        # 估算网络延迟（可以根据实际情况调整）
        network_latency = 100.0  # 默认 100ms
        
        return self._batch_size_calculator.calculate(
            data_size=data_size,
            field_count=field_count,
            complexity_score=complexity_score,
            network_latency=network_latency
        )
    
    def get_batch_size_recommendation(self) -> dict:
        """获取批处理大小优化建议"""
        return self._batch_size_calculator.get_recommendation()
    
    def get_memory_usage(self) -> dict:
        """获取当前内存使用情况"""
        import sys
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            return {
                'rss_mb': memory_info.rss / 1024 / 1024,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'python_objects': len(gc.get_objects()) if 'gc' in globals() else 0
            }
        except ImportError:
            return {
                'rss_mb': 0,
                'vms_mb': 0,
                'python_objects': 0
            }
    
    def _check_memory_and_cleanup(self) -> bool:
        """检查内存使用情况，必要时进行清理，返回是否进行了清理"""
        if not self._enable_memory_management:
            return False
        
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            if memory_mb > self._memory_threshold_mb:
                console_log.warning(f"内存使用过高 ({memory_mb:.1f}MB)，开始清理缓存...")
                self._cleanup_cache()
                return True
        except ImportError:
            pass
        return False
    
    def _cleanup_cache(self):
        """清理缓存，释放内存"""
        for worksheet_id in list(self.cache_data.keys()):
            cache_dict = self.cache_data[worksheet_id]
            
            if len(cache_dict) > self._cache_max_size:
                sorted_items = sorted(
                    cache_dict.items(),
                    key=lambda x: x[1].get('_access_time', 0) if isinstance(x[1], dict) else 0
                )
                
                items_to_remove = len(cache_dict) - self._cache_max_size // 2
                for i in range(items_to_remove):
                    row_id, _ = sorted_items[i]
                    del cache_dict[row_id]
                    
                    if worksheet_id in self.cache_indexes:
                        for index_dict in self.cache_indexes[worksheet_id].values():
                            if row_id in index_dict:
                                del index_dict[row_id]
                
                console_log.info(f"已清理缓存 {worksheet_id}，释放 {items_to_remove} 条记录")


    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """统一的请求方法，支持自适应超时和增强重试"""
        attempt = 0
        last_exception = None
        
        while attempt <= self.retry_strategy.max_retries:
            try:
                start_time = time.time()
                
                # 获取当前自适应超时设置
                connect_timeout, read_timeout = self.timeout_manager.get_timeout()
                kwargs.setdefault('timeout', (connect_timeout, read_timeout))
                
                # 根据方法选择请求函数
                if method.upper() == 'POST':
                    response = self.session.post(url, **kwargs)
                elif method.upper() == 'GET':
                    response = self.session.get(url, **kwargs)
                elif method.upper() == 'PATCH':
                    response = self.session.patch(url, **kwargs)
                elif method.upper() == 'DELETE':
                    response = self.session.delete(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response_time = time.time() - start_time
                response.raise_for_status()
                
                # 记录成功请求
                self.timeout_manager.record_success(response_time)
                
                return response
                
            except Exception as e:
                last_exception = e
                attempt += 1
                
                # 记录失败请求
                self.timeout_manager.record_failure()
                
                # 检查是否应该重试
                status_code = getattr(e, 'response', None)
                status_code = status_code.status_code if status_code else None
                
                if self.retry_strategy.should_retry(attempt, status_code, e):
                    delay = self.retry_strategy.get_delay(attempt)
                    time.sleep(delay)
                    continue
                else:
                    break
        
        raise last_exception


    def _post(self, endpoint: str, payload: dict):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        
        response = self._make_request(
            'POST',
            url,
            headers=self.headers,
            json=payload
        )
        return response.json()


    def _get(self, endpoint: str, params: dict=None):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        
        response = self._make_request(
            'GET',
            url,
            headers=self.headers,
            params=params
        )
        return response.json()


    def _patch(self, endpoint: str, payload: dict):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        
        response = self._make_request(
            'PATCH',
            url,
            headers=self.headers,
            json=payload
        )
        return response.json()


    def _delete(self, endpoint: str, payload: dict=None):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        
        response = self._make_request(
            'DELETE',
            url,
            headers=self.headers,
            json=payload
        )
        return response.json()


    def register_model(self, model: Type[Model]):
        """注册模型"""
        # 同时通过 worksheet_id 和类名存储模型
        worksheet_id = model.get_worksheet_id()
        self.models[worksheet_id] = model
        self.models[model.__name__] = model  # 通过类名存储模型
        
        # 检查模型是否配置了缓存
        cache_fields = getattr(model.Meta, 'cache', None)
        if cache_fields:
            # 初始化该模型的缓存数据和索引
            self.cache_data[worksheet_id] = {}
            self.cache_indexes[worksheet_id] = {
                'pk': {},  # 主键到 rowid 的映射
                'rowid': {}  # rowid 到 rowid 的映射（自身映射）
            }
            
            # 获取冲突字段
            conflict_fields = model.get_conflict_fields()
            pk_field = model.get_pk_field()
            
            # 获取该表的所有行数据
            try:
                # 创建查询对象
                query = self.rows(model)
                # 流式获取所有数据，避免内存溢出
                for model_instance in query.stream():
                    # 获取 rowid
                    row_id = getattr(model_instance, 'row_id', str(id(model_instance)))
                    
                    # 生成缓存值
                    cache_value = {}
                    # 首先添加 row_id
                    cache_value['row_id'] = row_id
                    # 然后添加用户指定的字段（使用field_name作为键）
                    for field_name in cache_fields:
                        if hasattr(model_instance, field_name):
                            # 标准化字段名，使用field_name作为键
                            normalized_field = HapUtils.normalize_field_name(model, field_name)
                            cache_value[normalized_field] = getattr(model_instance, field_name)
                    
                    # 存储数据（以 rowid 为键）
                    self.cache_data[worksheet_id][row_id] = cache_value
                    
                    # 创建 rowid 索引
                    self.cache_indexes[worksheet_id]['rowid'][row_id] = row_id
                    
                    # 如果有主键，创建主键索引
                    if pk_field and hasattr(model_instance, pk_field):
                        pk_value = str(getattr(model_instance, pk_field))
                        self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                        # 同时添加按field_name的索引
                        normalized_pk_field = HapUtils.normalize_field_name(model, pk_field)
                        if not normalized_pk_field in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][normalized_pk_field] = {}
                        self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
                    
                    # 如果有冲突字段，创建冲突字段索引
                    elif conflict_fields:
                        # 使用冲突字段形成元组作为键
                        key_parts = []
                        for field_name in conflict_fields:
                            if hasattr(model_instance, field_name):
                                key_parts.append(str(getattr(model_instance, field_name)))
                        conflict_key = tuple(key_parts)
                        if not 'conflict' in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id]['conflict'] = {}
                        self.cache_indexes[worksheet_id]['conflict'][conflict_key] = row_id
                    
                    # 为所有缓存字段创建索引
                    for field_name in cache_fields:
                        if hasattr(model_instance, field_name):
                            field_value = str(getattr(model_instance, field_name))
                            # 标准化字段名，使用field_name作为索引键
                            normalized_field = HapUtils.normalize_field_name(model, field_name)
                            # 如果该字段还没有索引，创建一个
                            if not normalized_field in self.cache_indexes[worksheet_id]:
                                self.cache_indexes[worksheet_id][normalized_field] = {}
                            # 添加字段值到索引
                            self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
            except Exception as e:
                # 缓存失败时记录错误，但不影响模型注册
                console_log.error(f"缓存模型 {model.__name__} 失败: {str(e)}")


    def register_models(self, models: List[Type[Model]]):
        """批量注册模型"""
        for model in models:
            self.register_model(model)


    def get_model(self, model_name: str) -> Type[Model]:
        """获取模型"""
        return self.models[model_name]
    

    def get_cached_data(self, model: Type[Model], key: Union[str, tuple], index_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        从缓存中获取数据
        
        Args:
            model: 模型类
            key: 索引值
            index_type: 索引类型，可选值: 'pk' (主键), 'rowid' (行ID), 'conflict' (冲突字段)。
                      如果为 None，则自动检测索引类型。
            
        Returns:
            Optional[Dict[str, Any]]: 缓存的数据，如果不存在则返回 None
        """
        import re
        
        # 自动检测索引类型
        if index_type is None:
            if isinstance(key, tuple):
                # 元组类型使用冲突字段索引
                index_type = 'conflict'
            elif isinstance(key, str):
                # 检查是否为 UUID 格式
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                if re.match(uuid_pattern, key, re.IGNORECASE):
                    # UUID 格式使用 rowid 索引
                    index_type = 'rowid'
                else:
                    # 其他字符串使用主键索引
                    index_type = 'pk'
            else:
                # 不支持的类型
                return None
        
        worksheet_id = model.get_worksheet_id()
        
        # 检查缓存是否存在
        if worksheet_id not in self.cache_data or worksheet_id not in self.cache_indexes:
            return None
        
        # 检查索引类型是否存在
        if index_type not in self.cache_indexes[worksheet_id]:
            return None
        
        # 通过索引获取 rowid
        row_id = self.cache_indexes[worksheet_id][index_type].get(key)
        if not row_id:
            return None
        
        # 通过 rowid 获取缓存数据
        return self.cache_data[worksheet_id].get(row_id)
    

    def get_choice_sets(self):
        self.choice_sets = {}
        response = self._get("/v3/app/optionsets")
        return response



    def rows(self, model: Type[ModelType]) -> 'HapQuerySet[ModelType]':
        """获取模型的查询集"""
        return HapQuerySet(model=model, hap_conn=self)
    

    def _update_cache_for_instance(self, model_instance: Model) -> None:
        """
        更新缓存中的模型实例数据
        
        Args:
            model_instance: 模型实例
        """
        # 检查模型是否配置了缓存
        cache_fields = getattr(model_instance.__class__.Meta, 'cache', None)
        if not cache_fields:
            return
        
        worksheet_id = model_instance.__class__.get_worksheet_id()
        row_id = getattr(model_instance, 'row_id', None)
        
        if not row_id or worksheet_id not in self.cache_data:
            return
        
        # 更新缓存数据
        cache_value = {'row_id': row_id, '_access_time': time.time()}
        
        for field_name in cache_fields:
            if hasattr(model_instance, field_name):
                normalized_field = HapUtils.normalize_field_name(model_instance.__class__, field_name)
                cache_value[normalized_field] = getattr(model_instance, field_name)
        
        self.cache_data[worksheet_id][row_id] = cache_value
        
        # 定期检查内存使用情况
        if hasattr(self, '_check_memory_and_cleanup'):
            self._check_memory_and_cleanup()
        
        # 更新索引
        pk_field = model_instance.__class__.get_pk_field()
        if pk_field and hasattr(model_instance, pk_field):
            pk_value = str(getattr(model_instance, pk_field))
            self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
            # 同时更新按field_name的索引
            normalized_pk_field = HapUtils.normalize_field_name(model_instance.__class__, pk_field)
            if normalized_pk_field in self.cache_indexes[worksheet_id]:
                self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
        
        # 更新缓存字段的索引
        for field_name in cache_fields:
            if hasattr(model_instance, field_name):
                field_value = str(getattr(model_instance, field_name))
                # 标准化字段名，使用field_name作为索引键
                normalized_field = HapUtils.normalize_field_name(model_instance.__class__, field_name)
                if normalized_field in self.cache_indexes[worksheet_id]:
                    self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
    

    def _remove_from_cache(self, row_id: str) -> None:
        """
        从缓存中移除指定的行数据
        
        Args:
            row_id: 行ID
        """
        # 遍历所有模型的缓存
        for worksheet_id, cache_data in self.cache_data.items():
            if row_id in cache_data:
                # 从缓存数据中移除
                del cache_data[row_id]
                
                # 从索引中移除
                if worksheet_id in self.cache_indexes:
                    # 从 rowid 索引中移除
                    if 'rowid' in self.cache_indexes[worksheet_id] and row_id in self.cache_indexes[worksheet_id]['rowid']:
                        del self.cache_indexes[worksheet_id]['rowid'][row_id]
                    
                    # 从其他索引中移除
                    for index_name, index_data in self.cache_indexes[worksheet_id].items():
                        if index_name not in ['pk', 'rowid', 'conflict']:
                            # 查找并删除引用该 row_id 的条目
                            keys_to_delete = []
                            for key, value in index_data.items():
                                if value == row_id:
                                    keys_to_delete.append(key)
                            for key in keys_to_delete:
                                del index_data[key]
                break
    
    def _update_cache_for_instances(self, model_instances: List[Model]) -> None:
        """
        批量更新缓存中的模型实例数据
        
        Args:
            model_instances: 模型实例列表
        """
        if not model_instances:
            return
        
        # 按模型类型分组处理
        instances_by_model = {}
        for instance in model_instances:
            model_class = instance.__class__
            if model_class not in instances_by_model:
                instances_by_model[model_class] = []
            instances_by_model[model_class].append(instance)
        
        # 分组处理每个模型的实例
        for model_class, instances in instances_by_model.items():
            # 检查模型是否配置了缓存
            cache_fields = getattr(model_class.Meta, 'cache', None)
            if not cache_fields:
                continue
            
            worksheet_id = model_class.get_worksheet_id()
            if worksheet_id not in self.cache_data:
                continue
            
            # 批量更新缓存
            for instance in instances:
                row_id = getattr(instance, 'row_id', None)
                if not row_id:
                    continue
                
                # 更新缓存数据
                cache_value = {}
                cache_value['row_id'] = row_id
                
                for field_name in cache_fields:
                    if hasattr(instance, field_name):
                        # 标准化字段名，使用field_name作为键
                        normalized_field = HapUtils.normalize_field_name(model_class, field_name)
                        cache_value[normalized_field] = getattr(instance, field_name)
                
                self.cache_data[worksheet_id][row_id] = cache_value
                
                # 更新索引
                pk_field = model_class.get_pk_field()
                if pk_field and hasattr(instance, pk_field):
                    pk_value = str(getattr(instance, pk_field))
                    self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                    # 同时更新按field_name的索引
                    normalized_pk_field = HapUtils.normalize_field_name(model_class, pk_field)
                    if normalized_pk_field in self.cache_indexes[worksheet_id]:
                        self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
                
                # 更新缓存字段的索引
                for field_name in cache_fields:
                    if hasattr(instance, field_name):
                        field_value = str(getattr(instance, field_name))
                        # 标准化字段名，使用field_name作为索引键
                        normalized_field = HapUtils.normalize_field_name(model_class, field_name)
                        if normalized_field in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
    
    def _start_cache_refresh_task(self):
        """
        启动缓存定时刷新任务
        """
        import threading
        import time
        
        def refresh_cache():
            """
            定时刷新缓存的函数
            """
            while True:
                try:
                    # 每隔30分钟刷新一次
                    time.sleep(30 * 60)
                    
                    # 遍历所有已注册的模型
                    for model_name, model_class in self.models.items():
                        # 只处理类名对应的模型（避免重复处理）
                        if not isinstance(model_name, str) or model_name != model_class.__name__:
                            continue
                        
                        # 检查模型是否配置了缓存
                        cache_fields = getattr(model_class.Meta, 'cache', None)
                        if not cache_fields:
                            continue
                        
                        worksheet_id = model_class.get_worksheet_id()
                        if worksheet_id not in self.cache_data:
                            continue
                        
                        # 获取最新的1000条记录
                        try:
                            # 构建查询：过滤所有记录，按utime降序排序，获取最新的1000条
                            query = self.rows(model_class)
                            # 应用过滤和排序
                            query = query.filter()  # 空过滤，获取所有记录
                            query = query.order_by("-utime")  # 按utime降序排序
                            query.page_size = 1000  # 设置每页大小为1000
                            query.limit = 1000  # 限制最多获取1000条
                            
                            # 执行查询
                            latest_instances = query.all()
                            
                            # 刷新缓存
                            if latest_instances.count() > 0:
                                self._update_cache_for_instances(latest_instances.row_objects)
                                console_log.info(f"已刷新模型 {model_class.__name__} 的缓存，更新了 {latest_instances.count()} 条记录")
                        except Exception as e:
                            console_log.error(f"刷新模型 {model_class.__name__} 的缓存失败: {str(e)}")
                except Exception as e:
                    console_log.error(f"缓存刷新任务执行失败: {str(e)}")
        
        # 启动后台线程执行定时刷新
        refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
        refresh_thread.start()
        console_log.info("缓存定时刷新任务已启动")



class AsyncHapConnection:
    """HAP 连接的异步包装器
    
    通过线程池将同步 HAP 操作转换为异步操作，保持与同步版本相同的 API 接口。
    复用 HapConnection 的线程池，避免资源重复创建。
    
    Attributes:
        _sync_conn: 原始的同步 HAP 连接
        _executor: 线程池执行器（复用自 sync_conn）
        _max_workers: 最大工作线程数
    
    Example:
        >>> hap_conn = HapConnection(app_key="xxx", sign="yyy")
        >>> async_hap = AsyncHapConnection(hap_conn)
        >>> 
        >>> # 方式一：直接调用 upsert
        >>> result = await async_hap.upsert(MyModel, data_list)
        >>> 
        >>> # 方式二：使用查询集
        >>> query = async_hap.query(MyModel).filter(status="active")
        >>> results = await query.all()
    """
    
    def __init__(
        self, 
        sync_conn: HapConnection, 
        enable_monitor: bool = True
    ):
        """
        初始化异步 HAP 连接
        
        Args:
            sync_conn: 同步 HAP 连接实例
            enable_monitor: 是否启用 API 监控，默认 True
        """
        self._sync_conn = sync_conn
        self._executor = sync_conn.executor
        self._max_workers = sync_conn.max_workers
        self._func_cache = {}
        self._monitor = HapApiMonitor() if enable_monitor else None
        self._connection_warmer = getattr(sync_conn, '_connection_warmer', None)
    
    def _run_in_executor(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """在线程池中执行同步函数
        
        Args:
            func: 要执行的同步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            asyncio.Future: 异步 Future 对象
        """
        loop = asyncio.get_event_loop()
        if kwargs:
            # 对于有关键字参数的情况，使用闭包避免 functools.partial
            def wrapper():
                return func(*args, **kwargs)
            return loop.run_in_executor(self._executor, wrapper)
        else:
            # 对于只有位置参数的情况，直接传递
            return loop.run_in_executor(self._executor, func, *args)
    
    def _run_with_monitor(
        self, 
        func: Callable, 
        method: str,
        endpoint: str,
        *args, 
        **kwargs
    ) -> asyncio.Future:
        """在线程池中执行同步函数并监控
        
        Args:
            func: 要执行的同步函数
            method: HTTP 方法
            endpoint: API 端点
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            asyncio.Future: 异步 Future 对象
        """
        import time
        
        async def monitored_wrapper():
            start_time = time.time()
            success = True
            error = None
            status_code = None
            
            try:
                result = await self._run_in_executor(func, *args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                response_time = time.time() - start_time
                
                # 记录监控数据
                if self._monitor:
                    self._monitor.record_request(
                        method=method,
                        endpoint=endpoint,
                        params=kwargs,
                        response_time=response_time,
                        success=success,
                        error=error
                    )
        
        return monitored_wrapper()
    
    # ==================== 监控相关方法 ====================
    
    def get_monitor_stats(self, last_n: int = 100) -> dict:
        """获取 API 监控统计数据
        
        Args:
            last_n: 统计最近 N 条记录
            
        Returns:
            dict: 统计信息
        """
        if not self._monitor:
            return {"error": "监控未启用"}
        return self._monitor.get_stats(last_n)
    
    def get_recent_errors(self, limit: int = 10) -> list:
        """获取最近的错误记录
        
        Args:
            limit: 返回的记录数
            
        Returns:
            list: 错误记录列表
        """
        if not self._monitor:
            return []
        return self._monitor.get_recent_errors(limit)
    
    def clear_monitor(self):
        """清空监控数据"""
        if self._monitor:
            self._monitor.clear()
    
    def is_monitor_enabled(self) -> bool:
        """检查监控是否启用
        
        Returns:
            bool: 是否启用监控
        """
        return self._monitor is not None
    
    # ==================== 模型注册与管理 ====================
    
    async def register_model(self, model: Type[ModelType]) -> None:
        """异步注册模型
        
        Args:
            model: 模型类
        """
        await self._run_in_executor(self._sync_conn.register_model, model)
    
    async def register_models(self, models: List[Type[ModelType]]) -> None:
        """异步批量注册模型
        
        Args:
            models: 模型类列表
        """
        await self._run_in_executor(self._sync_conn.register_models, models)
    
    def get_model(self, model_name: str) -> Type[ModelType]:
        """获取模型（同步，不涉及 IO）
        
        Args:
            model_name: 模型名称或 worksheet_id
            
        Returns:
            Type[ModelType]: 模型类
        """
        return self._sync_conn.get_model(model_name)
    
    # ==================== 核心数据操作方法 ====================
    
    @hap_async_timer()
    async def upsert(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        exclude_none: bool = True,
        trigger_workflow: bool = True,
        when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
    ) -> HapRowSet[ModelType]:
        """异步 upsert 操作
        
        根据主键或冲突字段判断是更新还是创建记录。
        
        Args:
            model: 模型类
            data_list: 要 upsert 的数据列表
            exclude_none: 是否排除值为 None 的字段，默认 True
            trigger_workflow: 是否触发工作流，默认 True
            when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
                - 'jumpover': 跳过不更新
                - 'update': 强制更新
                
        Returns:
            HapRowSet[ModelType]: 包含 upsert 后模型实例的行集合
            
        Example:
            >>> result = await async_hap.upsert(
            ...     MyModel,
            ...     [{"id": "1", "name": "test"}, {"id": "2", "name": "test2"}],
            ...     trigger_workflow=False
            ... )
            >>> print(f"处理了 {result.count()} 条记录")
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.upsert,
            data_list=data_list,
            exclude_none=exclude_none,
            trigger_workflow=trigger_workflow,
            when_value_equal_then=when_value_equal_then
        )
    
    @hap_async_timer()
    async def bulk_create(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量创建
        
        Args:
            model: 模型类
            data_list: 要创建的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 创建的模型实例列表
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.bulk_create,
            data_list=data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def bulk_update(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量更新
        
        Args:
            model: 模型类
            data_list: 要更新的数据列表（必须包含 row_id 或主键）
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 更新的模型实例列表
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.bulk_update,
            data_list=data_list,
            trigger_workflow=trigger_workflow
        )
    
    # ==================== 批量处理优化（针对生成器）====================
    
    @hap_async_timer()
    async def upsert_from_generator(
        self,
        model: Type[ModelType],
        data_source,
        buffer_size: int = None,
        max_concurrency: int = None,
        max_retries: int = None,
        retry_delay: float = None,
        adaptive: bool = True,
        target_qps: float = None,
        **kwargs
    ) -> int:
        """从生成器函数批量 upsert 数据（高性能版本）[已废弃]
        
        .. deprecated::
            请使用新的调用方式：await async_hap.rows(Model).upsert_from_generator(data_generator_func)
        针对 `pull_incremental_data` 等场景优化，支持批量收集和并发处理。
        包含错误处理、重试机制和自适应速率控制。
        
        Args:
            model: 模型类
            data_source: 数据生成器函数，每次调用返回一个数据列表的生成器
            buffer_size: 缓冲区大小，None 时使用自适应调节
            max_concurrency: 最大并发数，None 时使用自适应调节
            max_retries: 最大重试次数，None 时使用配置默认值
            retry_delay: 重试延迟（秒），None 时使用配置默认值
            adaptive: 是否启用自适应速率控制，默认 True
            target_qps: 目标 QPS（每秒请求数），None 时自动从 HapConfig 获取
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
            
        Example:
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(data_gen_func)
        """
        from typing import Callable, Generator
        import logging
        import time
        
        if callable(data_source):
            data_generator = data_source()
        else:
            raise ValueError("data_source 必须是生成器函数，请传递函数名而非函数调用结果")
        
        # 使用配置的默认值
        if max_retries is None:
            max_retries = _DEFAULT_MAX_RETRIES
        if retry_delay is None:
            retry_delay = _DEFAULT_RETRY_DELAY
        
        # 自动从 HapConfig 获取 QPS 限制
        if target_qps is None:
            target_qps = getattr(self._sync_conn, 'qps_limit', 10.0)
            console_log.info(f"从 HapConfig 自动获取 QPS 限制: {target_qps}")
        
        # 使用智能批处理大小计算器（如果同步版本已配置）
        smart_batch_calculator = getattr(self._sync_conn, '_batch_size_calculator', None)
        
        # 初始化自适应控制器
        if adaptive:
            # 如果提供了 buffer_size，使用提供的值；否则使用智能计算
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值初始化，后续根据实际数据量调整
                initial_buffer = _DEFAULT_BUFFER_SIZE
            else:
                initial_buffer = buffer_size or _DEFAULT_BUFFER_SIZE
            
            controller = AdaptiveRateController(
                initial_buffer_size=initial_buffer,
                initial_concurrency=max_concurrency or _MAX_CONCURRENCY,
                target_qps=target_qps,
            )
            current_buffer_size = controller.buffer_size
            current_concurrency = controller.concurrency
        else:
            # 非自适应模式，使用智能批处理大小
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值，后续根据实际数据调整
                current_buffer_size = _DEFAULT_BUFFER_SIZE
            else:
                current_buffer_size = buffer_size or _DEFAULT_BUFFER_SIZE
            current_concurrency = max_concurrency or _MAX_CONCURRENCY
        
        buffer = []
        total_count = 0
        semaphore = asyncio.Semaphore(current_concurrency)
        tasks = []
        
        async def do_upsert_with_retry(data_batch, batch_index):
            """带重试和性能监控的 upsert"""
            nonlocal current_buffer_size, current_concurrency, semaphore
            
            async with semaphore:
                start_time = time.time()
                for attempt in range(max_retries):
                    try:
                        result = await self.upsert(model, data_batch, **kwargs)
                        response_time = time.time() - start_time
                        
                        # 记录成功请求到自适应控制器
                        if adaptive:
                            controller.record_request(True, response_time)
                        
                        # 记录到监控器
                        if self._monitor:
                            # 安全获取 worksheet_id
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=True
                            )
                        
                        return result.count()
                    except Exception as e:
                        response_time = time.time() - start_time
                        console_log.warning(f"批次 {batch_index} 第 {attempt + 1} 次尝试失败: {e}")
                        
                        # 记录失败请求到自适应控制器
                        if adaptive:
                            controller.record_request(False, response_time)
                        
                        # 记录到监控器
                        if self._monitor:
                            # 安全获取 worksheet_id
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=False,
                                error=str(e)
                            )
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                        else:
                            console_log.error(f"批次 {batch_index} 最终失败，跳过 {len(data_batch)} 条数据")
                            return 0
                return 0
        
        batch_index = 0
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= current_buffer_size:
                batch_index += 1
                
                # 自适应调整参数
                if adaptive and batch_index % 5 == 0:
                    new_buffer_size, new_concurrency = controller.adjust()
                    
                    if new_concurrency != current_concurrency:
                        # 更新信号量
                        current_concurrency = new_concurrency
                        semaphore = asyncio.Semaphore(current_concurrency)
                        console_log.info(f"自适应调整: 并发数 -> {current_concurrency}")
                    
                    if new_buffer_size != current_buffer_size:
                        current_buffer_size = new_buffer_size
                        console_log.info(f"自适应调整: 缓冲区 -> {current_buffer_size}")
                    
                    # 定期输出统计信息
                    if batch_index % 20 == 0:
                        stats = controller.get_stats()
                        console_log.info(
                            f"统计: 成功率={stats['success_rate']:.2%}, "
                            f"平均响应={stats['avg_response_time']:.2f}s, "
                            f"当前参数: buffer={current_buffer_size}, concurrency={current_concurrency}"
                        )
                
                # 提交当前缓冲区的数据
                tasks.append(asyncio.create_task(
                    do_upsert_with_retry(buffer[:], batch_index)
                ))
                buffer = []
                
                # 控制并发数量，避免内存溢出
                if len(tasks) >= current_concurrency * 2:
                    done, pending = await asyncio.wait(
                        tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        try:
                            total_count += await task
                        except Exception as e:
                            console_log.error(f"任务执行失败: {e}")
                    tasks = list(pending)
        
        # 处理剩余数据
        if buffer:
            batch_index += 1
            tasks.append(asyncio.create_task(
                do_upsert_with_retry(buffer, batch_index)
            ))
        
        # 等待所有任务完成
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, int):
                    total_count += result
                elif isinstance(result, Exception):
                    console_log.error(f"任务异常: {result}")
        
        # 输出最终统计
        if adaptive:
            stats = controller.get_stats()
            console_log.info(
                f"完成: 总请求={stats['request_count']}, "
                f"成功率={stats['success_rate']:.2%}, "
                f"最终参数: buffer={stats['buffer_size']}, concurrency={stats['concurrency']}"
            )
        
        return total_count
    
    async def upsert_buffered(
        self,
        model: Type[ModelType],
        data_generator,
        buffer_size: int = 500,
        **kwargs
    ) -> int:
        """缓冲批量 upsert（简单版本，无并发）
        
        适用于数据量较小或不需要高并发的场景。
        
        Args:
            model: 模型类
            data_generator: 数据生成器
            buffer_size: 缓冲区大小，默认 500
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
        """
        buffer = []
        total_count = 0
        
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= buffer_size:
                result = await self.upsert(model, buffer, **kwargs)
                total_count += result.count()
                buffer = []
        
        # 处理剩余数据
        if buffer:
            result = await self.upsert(model, buffer, **kwargs)
            total_count += result.count()
        
        return total_count
    
    # ==================== 查询操作 ====================
    
    def query(self, model: Type[ModelType]) -> 'AsyncHapQuerySet[ModelType]':
        """获取异步查询集
        
        Args:
            model: 模型类
            
        Returns:
            AsyncHapQuerySet[ModelType]: 异步查询集实例
            
        Example:
            >>> query = async_hap.query(MyModel)
            >>> results = await query.filter(status="active").order_by("-created").all()
        """
        return AsyncHapQuerySet(model, self._sync_conn, self._executor, async_hap=self)
    
    # 兼容 rows 方法名
    def rows(self, model: Type[ModelType]) -> 'AsyncHapQuerySet[ModelType]':
        """获取异步查询集（与 query 方法相同）
        
        Args:
            model: 模型类
            
        Returns:
            AsyncHapQuerySet[ModelType]: 异步查询集实例
        """
        return self.query(model)
    
    # ==================== 缓存操作 ====================
    
    async def get_cached_data(
        self,
        model: Type[ModelType],
        key: Union[str, tuple],
        index_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """异步获取缓存数据
        
        Args:
            model: 模型类
            key: 索引值（主键、rowid 或冲突字段元组）
            index_type: 索引类型，可选 'pk', 'rowid', 'conflict'，默认自动检测
            
        Returns:
            Optional[Dict[str, Any]]: 缓存的数据，不存在则返回 None
        """
        return await self._run_in_executor(
            self._sync_conn.get_cached_data,
            model,
            key,
            index_type
        )
    
    async def warmup_cache(self, model: Type[ModelType]) -> None:
        """异步预热缓存
        
        重新加载模型的缓存数据。
        
        Args:
            model: 模型类
        """
        await self._run_in_executor(self._sync_conn.register_model, model)
    
    # ==================== 选项集操作 ====================
    
    async def get_choice_sets(self) -> Dict[str, Any]:
        """异步获取选项集
        
        Returns:
            Dict[str, Any]: 选项集数据
        """
        return await self._run_in_executor(self._sync_conn.get_choice_sets)
    
    # ==================== 生命周期管理 ====================
    
    async def close(self) -> None:
        """关闭连接，释放资源
        
        关闭线程池，等待所有任务完成。
        """
        self._executor.shutdown(wait=True)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False




# ==================== 便捷函数 ====================

async def async_upsert(
    model: Type[ModelType],
    data_list: List[Dict[str, Any]],
    sync_conn: Optional[HapConnection] = None,
    **kwargs
) -> HapRowSet[ModelType]:
    """便捷函数：快速 upsert
    
    无需创建 AsyncHapConnection 实例，直接调用 upsert。
    
    Args:
        model: 模型类
        data_list: 要 upsert 的数据列表
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        **kwargs: 其他参数传递给 upsert 方法
        
    Returns:
        HapRowSet[ModelType]: upsert 结果
        
    Example:
        >>> result = await async_upsert(MyModel, [{"name": "test"}])
    """
    if sync_conn is None:
        # 尝试从 hap 模块获取全局连接
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    try:
        return await async_hap.upsert(model, data_list, **kwargs)
    finally:
        await async_hap.close()


async def async_bulk_create(
    model: Type[ModelType],
    data_list: List[Dict[str, Any]],
    sync_conn: Optional[HapConnection] = None,
    **kwargs
) -> List[ModelType]:
    """便捷函数：快速批量创建
    
    Args:
        model: 模型类
        data_list: 要创建的数据列表
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        **kwargs: 其他参数传递给 bulk_create 方法
        
    Returns:
        List[ModelType]: 创建的模型实例列表
    """
    if sync_conn is None:
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    try:
        return await async_hap.bulk_create(model, data_list, **kwargs)
    finally:
        await async_hap.close()


async def async_query(
    model: Type[ModelType],
    sync_conn: Optional[HapConnection] = None
) -> 'AsyncHapQuerySet[ModelType]':
    """便捷函数：快速获取查询集
    
    Args:
        model: 模型类
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        
    Returns:
        AsyncHapQuerySet[ModelType]: 异步查询集
    """
    if sync_conn is None:
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    return async_hap.query(model)