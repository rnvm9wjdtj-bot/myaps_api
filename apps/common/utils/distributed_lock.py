"""
分布式锁实现模块（含配置管理）

功能特性：
1. 基于Redis的分布式锁机制
2. 使用SET NX EX原子操作获取锁
3. 使用Lua脚本安全释放锁
4. 支持上下文管理器（async with）
5. 自动过期和降级策略
6. 锁键名安全验证
7. 环境变量配置管理

配置参数：
- DISTRIBUTED_LOCK_TIMEOUT: 锁超时时间（秒），默认30，范围[5, 300]
- DISTRIBUTED_LOCK_RETRY_INTERVAL: 锁获取重试间隔（秒），默认0.1，范围[0.01, 1.0]
- DEFAULT_MAX_CONCURRENT: 默认最大并发数，默认1，范围[1, 10]
- DEFAULT_WAIT_TIMEOUT: 默认等待超时时间（秒），默认15.0，范围[5.0, 60.0]

使用示例：
    from apps.common.utils.distributed_lock import DistributedLock, get_distributed_lock_config
    
    # 获取配置
    config = get_distributed_lock_config()
    
    # 方式1：手动获取和释放
    lock = DistributedLock("my_resource", timeout=30)
    if await lock.acquire(max_wait=10.0):
        try:
            # 执行需要加锁的操作
            pass
        finally:
            await lock.release()
    
    # 方式2：使用上下文管理器（推荐）
    async with DistributedLock("my_resource").lock(max_wait=10.0) as acquired:
        if acquired:
            # 执行需要加锁的操作
            pass
        else:
            # 获取锁失败的处理
            pass
"""

import os
import asyncio
import time
import re
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from apps.common.utils.redis_pool_manager import get_redis_client
from globalobjects import logger as log_config

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


# ============================================================================
# 配置管理部分
# ============================================================================

def validate_int_param(
    value: str,
    param_name: str,
    default: int,
    min_value: int,
    max_value: int
) -> int:
    """
    验证整数参数合法性
    
    Args:
        value: 环境变量值（字符串）
        param_name: 参数名称（用于日志）
        default: 默认值
        min_value: 最小值
        max_value: 最大值
    
    Returns:
        验证后的整数值
    
    说明：
        如果参数非法（无法转换、超出范围），记录警告日志并返回默认值
    """
    if not value:
        return default
    
    try:
        int_value = int(value)
        
        if int_value < min_value or int_value > max_value:
            logger.warning(
                f"配置参数 {param_name}={int_value} 超出范围 [{min_value}, {max_value}]，"
                f"使用默认值 {default}"
            )
            return default
        
        return int_value
    
    except (ValueError, TypeError) as e:
        logger.warning(
            f"配置参数 {param_name}={value} 格式非法，"
            f"使用默认值 {default}。错误: {e}"
        )
        return default


def validate_float_param(
    value: str,
    param_name: str,
    default: float,
    min_value: float,
    max_value: float
) -> float:
    """
    验证浮点数参数合法性
    
    Args:
        value: 环境变量值（字符串）
        param_name: 参数名称（用于日志）
        default: 默认值
        min_value: 最小值
        max_value: 最大值
    
    Returns:
        验证后的浮点数值
    
    说明：
        如果参数非法（无法转换、超出范围），记录警告日志并返回默认值
    """
    if not value:
        return default
    
    try:
        float_value = float(value)
        
        if float_value < min_value or float_value > max_value:
            logger.warning(
                f"配置参数 {param_name}={float_value} 超出范围 [{min_value}, {max_value}]，"
                f"使用默认值 {default}"
            )
            return default
        
        return float_value
    
    except (ValueError, TypeError) as e:
        logger.warning(
            f"配置参数 {param_name}={value} 格式非法，"
            f"使用默认值 {default}。错误: {e}"
        )
        return default


def get_distributed_lock_config() -> Dict[str, Any]:
    """
    获取分布式锁配置参数
    
    从环境变量读取配置参数，进行合法性验证，返回配置字典。
    
    Returns:
        配置字典，包含以下键：
        - timeout: 锁超时时间（秒）
        - retry_interval: 锁获取重试间隔（秒）
        - max_concurrent: 默认最大并发数
        - wait_timeout: 默认等待超时时间（秒）
    
    环境变量：
        DISTRIBUTED_LOCK_TIMEOUT: 锁超时时间，默认30，范围[5, 300]
        DISTRIBUTED_LOCK_RETRY_INTERVAL: 重试间隔，默认0.1，范围[0.01, 1.0]
        DEFAULT_MAX_CONCURRENT: 最大并发数，默认1，范围[1, 10]
        DEFAULT_WAIT_TIMEOUT: 等待超时，默认15.0，范围[5.0, 60.0]
    
    使用示例：
        config = get_distributed_lock_config()
        lock = DistributedLock(
            lock_key="my_resource",
            timeout=config['timeout'],
            retry_interval=config['retry_interval']
        )
    """
    config = {
        'timeout': validate_int_param(
            value=os.getenv("DISTRIBUTED_LOCK_TIMEOUT"),
            param_name="DISTRIBUTED_LOCK_TIMEOUT",
            default=30,
            min_value=5,
            max_value=300
        ),
        'retry_interval': validate_float_param(
            value=os.getenv("DISTRIBUTED_LOCK_RETRY_INTERVAL"),
            param_name="DISTRIBUTED_LOCK_RETRY_INTERVAL",
            default=0.1,
            min_value=0.01,
            max_value=1.0
        ),
        'max_concurrent': validate_int_param(
            value=os.getenv("DEFAULT_MAX_CONCURRENT"),
            param_name="DEFAULT_MAX_CONCURRENT",
            default=1,
            min_value=1,
            max_value=10
        ),
        'wait_timeout': validate_float_param(
            value=os.getenv("DEFAULT_WAIT_TIMEOUT"),
            param_name="DEFAULT_WAIT_TIMEOUT",
            default=15.0,
            min_value=5.0,
            max_value=60.0
        )
    }
    
    logger.debug(f"分布式锁配置加载完成: {config}")
    
    return config


DEFAULT_CONFIG = get_distributed_lock_config()


# ============================================================================
# 分布式锁实现部分
# ============================================================================

class DistributedLock:
    """
    基于Redis的分布式锁
    
    使用Redis的SET NX EX命令实现分布式锁，确保原子性。
    使用Lua脚本确保锁释放的安全性，防止误删他人的锁。
    
    Attributes:
        lock_key: 锁的完整键名（包含前缀）
        timeout: 锁超时时间（秒）
        retry_interval: 获取锁的重试间隔（秒）
        _token: 锁持有者标识符
        _acquired: 是否已获取锁（用于降级模式）
    
    注意事项：
        1. 锁键名会自动添加前缀 "myaps:lock:"
        2. Redis不可用时会自动降级为无锁模式
        3. 锁超时后会被Redis自动删除
        4. 释放锁时会验证持有者，防止误删他人的锁
    """
    
    LOCK_PREFIX = "myaps:lock:"
    MAX_KEY_LENGTH = 200
    KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_:\-\.]+$')
    
    def __init__(
        self,
        lock_key: str,
        timeout: Optional[int] = None,
        retry_interval: Optional[float] = None
    ):
        """
        初始化分布式锁
        
        Args:
            lock_key: 业务键名（不含前缀）
            timeout: 锁超时时间（秒），默认从配置读取
            retry_interval: 获取锁的重试间隔（秒），默认从配置读取
        
        Raises:
            ValueError: 锁键名不合法
        
        使用示例：
            lock = DistributedLock("user:123", timeout=30)
        """
        self._validate_lock_key(lock_key)
        
        self.lock_key = f"{self.LOCK_PREFIX}{lock_key}"
        self.timeout = timeout if timeout is not None else DEFAULT_CONFIG['timeout']
        self.retry_interval = retry_interval if retry_interval is not None else DEFAULT_CONFIG['retry_interval']
        
        self._token: Optional[str] = None
        self._acquired: bool = False
    
    def _validate_lock_key(self, lock_key: str) -> None:
        """
        验证锁键名合法性
        
        Args:
            lock_key: 业务键名
        
        Raises:
            ValueError: 键名不合法
        
        验证规则：
            1. 长度：1-200字符
            2. 字符白名单：字母、数字、下划线、冒号、连字符、点
            3. 危险模式检测：禁止 ".."、禁止以 "/" 开头或结尾
        """
        if not lock_key:
            raise ValueError("锁键名不能为空")
        
        if len(lock_key) > self.MAX_KEY_LENGTH:
            raise ValueError(
                f"锁键名过长，最大长度为 {self.MAX_KEY_LENGTH} 字符，"
                f"当前长度为 {len(lock_key)} 字符"
            )
        
        if ".." in lock_key:
            raise ValueError("锁键名不能包含 '..'")
        
        if lock_key.startswith("/") or lock_key.endswith("/"):
            raise ValueError("锁键名不能以 '/' 开头或结尾")
        
        if not self.KEY_PATTERN.match(lock_key):
            raise ValueError(
                f"锁键名包含非法字符，只允许字母、数字、下划线、冒号、连字符和点"
            )
    
    def _generate_token(self) -> str:
        """
        生成唯一标识符
        
        Returns:
            格式为 "{timestamp}:{object_id}" 的唯一标识符
        
        说明：
            用于标识锁的持有者，确保只有持有者才能释放锁
        """
        return f"{time.time()}:{id(self)}"
    
    async def acquire(self, max_wait: float = 10.0) -> bool:
        """
        获取锁
        
        Args:
            max_wait: 最大等待时间（秒）
        
        Returns:
            True: 获取成功
            False: 获取失败（超时或异常）
        
        说明：
            1. 使用Redis SET NX EX命令原子性获取锁
            2. 如果获取失败，会重试直到超时
            3. Redis不可用时自动降级为无锁模式
            4. 获取成功后设置_token和_acquired
        
        使用示例：
            if await lock.acquire(max_wait=10.0):
                try:
                    # 执行业务逻辑
                    pass
                finally:
                    await lock.release()
        """
        redis_client = get_redis_client()
        
        if not redis_client:
            logger.warning(
                f"Redis不可用，降级为无锁模式: {self.lock_key}"
            )
            self._acquired = True
            return True
        
        start_time = time.time()
        self._token = self._generate_token()
        
        while True:
            try:
                acquired = redis_client.set(
                    self.lock_key,
                    self._token,
                    nx=True,
                    ex=self.timeout
                )
                
                if acquired:
                    elapsed = time.time() - start_time
                    logger.debug(
                        f"获取锁成功: {self.lock_key}，耗时: {elapsed:.3f}秒"
                    )
                    self._acquired = True
                    return True
                
                elapsed = time.time() - start_time
                if elapsed >= max_wait:
                    logger.warning(
                        f"获取锁超时: {self.lock_key}，等待时间: {elapsed:.2f}秒"
                    )
                    return False
                
                await asyncio.sleep(self.retry_interval)
                
            except Exception as e:
                logger.error(
                    f"获取锁异常: {self.lock_key}，错误: {e}",
                    exc_info=True
                )
                return False
    
    async def release(self) -> None:
        """
        释放锁
        
        说明：
            1. 使用Lua脚本确保原子性和安全性
            2. 只释放自己持有的锁，防止误删他人的锁
            3. 清理本地状态（_token和_acquired）
            4. Redis不可用时直接返回
        
        Lua脚本逻辑：
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        """
        if not self._token:
            return
        
        redis_client = get_redis_client()
        if not redis_client:
            self._token = None
            self._acquired = False
            return
        
        try:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            result = redis_client.eval(lua_script, 1, self.lock_key, self._token)
            
            if result == 1:
                logger.debug(f"释放锁成功: {self.lock_key}")
            else:
                logger.debug(
                    f"释放锁失败: {self.lock_key}，锁已过期或被他人获取"
                )
            
        except Exception as e:
            logger.error(
                f"释放锁异常: {self.lock_key}，错误: {e}",
                exc_info=True
            )
        finally:
            self._token = None
            self._acquired = False
    
    @asynccontextmanager
    async def lock(self, max_wait: float = 10.0):
        """
        上下文管理器方式使用锁
        
        Args:
            max_wait: 最大等待时间（秒）
        
        Yields:
            bool: 锁获取状态（True=成功，False=失败）
        
        说明：
            1. 进入时自动获取锁
            2. 退出时自动释放锁（无论是否发生异常）
            3. 确保异常安全
        
        使用示例：
            async with DistributedLock("my_resource").lock(max_wait=10.0) as acquired:
                if acquired:
                    # 执行需要加锁的操作
                    pass
                else:
                    # 获取锁失败的处理
                    raise Exception("无法获取锁")
        """
        acquired = await self.acquire(max_wait=max_wait)
        try:
            yield acquired
        finally:
            await self.release()
    
    @property
    def is_acquired(self) -> bool:
        """
        检查锁是否已获取
        
        Returns:
            bool: True=已获取，False=未获取
        """
        return self._acquired
