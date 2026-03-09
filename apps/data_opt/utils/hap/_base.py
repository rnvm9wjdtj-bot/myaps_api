"""
基础配置和类型定义
"""

import os
from typing import TypeVar#, Generic, List, Dict, Any, Optional, Union, Literal, Generator, Type, NamedTuple

from globalobjects import CACHE_JSON, logger as log_config


console_log = log_config.get_logger(__name__)
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')


# 类型定义
ModelType = TypeVar('ModelType', bound='Model')


class HapConfig:
    """HAP 配置类"""
    _SAAS_ENV = "https://api.mingdao.com"
    MAX_WORKERS = os.cpu_count() * 5
    # 调用刷新函数时，距离上次刷新超过这个秒数，才会刷新行数据，否则直接返回缓存数据
    REFRESH_INTERVAL_SECONDS = 60
    BASE_URL = CACHE_JSON.get("hap", {}).get("base_url", _SAAS_ENV)
    # QPS 限制，SAAS环境默认 50，私有部署默认 1000
    QPS_LIMIT = 50 if BASE_URL == _SAAS_ENV else 1000
    APP_KEY = CACHE_JSON.get("hap", {}).get("app_key", "")
    SIGN = CACHE_JSON.get("hap", {}).get("sign", "")
    DESCRIPTION = CACHE_JSON.get("hap", {}).get("description", "")
    # 是否启用 HTTP/2 支持（默认 True）
    ENABLE_HTTP2 = CACHE_JSON.get("hap", {}).get("enable_http2", True)
    # 每个模型缓存的最大记录数
    CACHE_MAX_SIZE = CACHE_JSON.get("hap", {}).get("cache_max_size", 10000)
    # 内存阈值（MB），超过时触发清理
    MEMORY_THRESHOLD_MB = CACHE_JSON.get("hap", {}).get("memory_threshold_mb", 1024)
    # 是否启用内存管理（默认 True）
    ENABLE_MEMORY_MANAGEMENT = CACHE_JSON.get("hap", {}).get("enable_memory_management", True)


# 配置常量
_MAX_CONCURRENCY = CACHE_JSON.get("hap", {}).get("max_concurrency", os.cpu_count() * 3)
_DEFAULT_BUFFER_SIZE = CACHE_JSON.get("hap", {}).get("default_buffer_size", 200)
_ADAPTIVE_MIN_BUFFER_SIZE = CACHE_JSON.get("hap", {}).get("adaptive_min_buffer_size", 50)
_ADAPTIVE_SCALE_UP_FAST = CACHE_JSON.get("hap", {}).get("adaptive_scale_up_fast", 1.5)
_ADAPTIVE_SCALE_UP_SLOW = CACHE_JSON.get("hap", {}).get("adaptive_scale_up_slow", 1.3)
_ADAPTIVE_SCALE_DOWN = CACHE_JSON.get("hap", {}).get("adaptive_scale_down", 0.8)
_ADAPTIVE_SCALE_DOWN_FAST = CACHE_JSON.get("hap", {}).get("adaptive_scale_down_fast", 0.5)
_DEFAULT_MAX_RETRIES = CACHE_JSON.get("hap", {}).get("default_max_retries", 3)
_DEFAULT_RETRY_DELAY = CACHE_JSON.get("hap", {}).get("default_retry_delay", 1.0)
