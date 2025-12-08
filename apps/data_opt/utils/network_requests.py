"""
通用网络请求加固模块
提供高抽象层次的网络请求处理逻辑，支持超时处理、重试机制、事务性操作等
尽量使用Python标准库实现，减少第三方依赖
"""

import time
import random
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
import urllib.error
import urllib.request
import json

# 设置日志
logger = logging.getLogger(__name__)

# 类型变量\T = TypeVar('T')


class RequestConfig:
    """
    请求配置类，用于封装请求的各种参数
    """
    def __init__(
        self,
        timeout: Tuple[float, float] = (10.0, 30.0),  # (连接超时, 读取超时)
        max_retries: int = 3,
        retry_delay_base: float = 1.0,
        retry_delay_max: float = 30.0,
        retry_on_exceptions: Optional[List[Type[Exception]]] = None,
        retry_on_status_codes: Optional[List[int]] = None,
    ):
        """
        初始化请求配置
        
        Args:
            timeout: 超时时间元组 (连接超时, 读取超时)
            max_retries: 最大重试次数
            retry_delay_base: 重试基础延迟时间（指数退避算法）
            retry_delay_max: 最大重试延迟时间
            retry_on_exceptions: 需要重试的异常类型列表
            retry_on_status_codes: 需要重试的状态码列表
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.retry_delay_max = retry_delay_max
        
        # 默认重试的异常类型
        self.retry_on_exceptions = retry_on_exceptions or [
            urllib.error.URLError,
            urllib.error.HTTPError,
            ConnectionResetError,
            TimeoutError,
        ]
        
        # 默认重试的状态码（服务器错误）
        self.retry_on_status_codes = retry_on_status_codes or [500, 502, 503, 504]


class RequestResponse:
    """
    请求响应类，用于封装请求的结果
    """
    def __init__(
        self,
        success: bool,
        status_code: Optional[int] = None,
        content: Optional[bytes] = None,
        text: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        error: Optional[Exception] = None,
        retry_count: int = 0,
    ):
        """
        初始化请求响应
        
        Args:
            success: 请求是否成功
            status_code: HTTP状态码
            content: 响应内容（二进制）
            text: 响应内容（字符串）
            json_data: 响应内容（JSON）
            headers: 响应头
            error: 错误信息
            retry_count: 重试次数
        """
        self.success = success
        self.status_code = status_code
        self.content = content
        self.text = text
        self.json_data = json_data
        self.headers = headers
        self.error = error
        self.retry_count = retry_count


class NetworkRequestor:
    """
    网络请求器类，提供高抽象层次的网络请求处理
    """
    def __init__(self, config: Optional[RequestConfig] = None):
        """
        初始化网络请求器
        
        Args:
            config: 请求配置，如不提供则使用默认配置
        """
        self.config = config or RequestConfig()
        self.opener = urllib.request.build_opener()
        
    def _should_retry(self, exception: Exception, status_code: Optional[int] = None) -> bool:
        """
        判断是否应该重试请求
        
        Args:
            exception: 异常对象
            status_code: HTTP状态码
            
        Returns:
            是否应该重试
        """
        # 检查异常类型
        for exc_type in self.config.retry_on_exceptions:
            if isinstance(exception, exc_type):
                return True
        
        # 检查状态码
        if status_code is not None and status_code in self.config.retry_on_status_codes:
            return True
        
        return False
    
    def _exponential_backoff(self, attempt: int) -> float:
        """
        计算指数退避延迟时间
        
        Args:
            attempt: 当前重试次数
            
        Returns:
            延迟时间（秒）
        """
        delay = self.config.retry_delay_base * (2 ** attempt) + random.uniform(0, 1)
        return min(delay, self.config.retry_delay_max)
    
    def make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Union[bytes, str, Dict[str, Any]]] = None,
        parse_json: bool = True,
    ) -> RequestResponse:
        """
        发送网络请求，包含重试逻辑
        
        Args:
            url: 请求URL
            method: 请求方法 (GET, POST, PUT, DELETE等)
            headers: 请求头
            data: 请求数据
            parse_json: 是否解析JSON响应
            
        Returns:
            请求响应对象
        """
        retry_count = 0
        
        # 处理请求数据
        if data is not None:
            if isinstance(data, dict):
                data = json.dumps(data).encode("utf-8")
                if headers is None:
                    headers = {}
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
            elif isinstance(data, str):
                data = data.encode("utf-8")
        
        while retry_count <= self.config.max_retries:
            try:
                # 创建请求对象
                req = urllib.request.Request(url, method=method, headers=headers or {})
                
                # 设置超时
                response = self.opener.open(req, data=data, timeout=self.config.timeout)
                
                # 读取响应
                content = response.read()
                text = content.decode("utf-8", errors="ignore")
                
                # 解析JSON
                json_data = None
                if parse_json and text:
                    try:
                        json_data = json.loads(text)
                    except json.JSONDecodeError:
                        json_data = None
                
                # 获取响应头
                response_headers = {k.decode(): v.decode() for k, v in response.getheaders()}
                
                return RequestResponse(
                    success=True,
                    status_code=response.status,
                    content=content,
                    text=text,
                    json_data=json_data,
                    headers=response_headers,
                    retry_count=retry_count,
                )
                
            except urllib.error.HTTPError as e:
                # HTTP错误
                response = RequestResponse(
                    success=False,
                    status_code=e.code,
                    error=e,
                    retry_count=retry_count,
                )
                
                if retry_count < self.config.max_retries and self._should_retry(e, e.code):
                    retry_count += 1
                    delay = self._exponential_backoff(retry_count)
                    logger.warning(f"HTTP请求失败，状态码: {e.code}, 将在 {delay:.2f} 秒后重试 (尝试 {retry_count}/{self.config.max_retries})")
                    time.sleep(delay)
                else:
                    logger.error(f"HTTP请求失败，状态码: {e.code}, 错误: {e.reason}")
                    return response
                
            except Exception as e:
                # 其他错误
                response = RequestResponse(
                    success=False,
                    error=e,
                    retry_count=retry_count,
                )
                
                if retry_count < self.config.max_retries and self._should_retry(e):
                    retry_count += 1
                    delay = self._exponential_backoff(retry_count)
                    logger.warning(f"请求失败，错误: {str(e)}, 将在 {delay:.2f} 秒后重试 (尝试 {retry_count}/{self.config.max_retries})")
                    time.sleep(delay)
                else:
                    logger.error(f"请求失败，错误: {str(e)}")
                    return response
        
        # 理论上不会到达这里
        return RequestResponse(success=False, error=Exception("未知错误"), retry_count=retry_count)


class TransactionalRequest:
    """
    事务性请求类，用于处理需要保证原子性的一系列请求
    """
    def __init__(self, requestor: NetworkRequestor):
        """
        初始化事务性请求处理器
        
        Args:
            requestor: 网络请求器
        """
        self.requestor = requestor
        self._compensations = []
    
    def add_compensation(self, func: Callable, *args, **kwargs):
        """
        添加补偿操作，用于在事务失败时执行
        
        Args:
            func: 补偿函数
            args: 位置参数
            kwargs: 关键字参数
        """
        self._compensations.append((func, args, kwargs))
    
    def clear_compensations(self):
        """
        清除所有补偿操作
        """
        self._compensations = []
    
    def execute(self, operations: List[Callable]) -> Tuple[bool, List[Any]]:
        """
        执行事务性操作
        
        Args:
            operations: 操作列表，每个操作是一个函数，返回 (success, result)
            
        Returns:
            (事务是否成功, 操作结果列表)
        """
        results = []
        success = True
        
        try:
            # 执行所有操作
            for i, op in enumerate(operations):
                op_success, op_result = op()
                results.append(op_result)
                
                if not op_success:
                    success = False
                    logger.error(f"事务操作 {i+1} 失败，开始执行补偿操作")
                    break
            
            # 如果事务失败，执行补偿操作
            if not success:
                for func, args, kwargs in reversed(self._compensations):
                    try:
                        func(*args, **kwargs)
                        logger.info(f"补偿操作 {func.__name__} 执行成功")
                    except Exception as e:
                        logger.error(f"补偿操作 {func.__name__} 执行失败: {str(e)}")
            
            return success, results
            
        except Exception as e:
            logger.error(f"事务执行失败: {str(e)}, 开始执行补偿操作")
            
            # 执行补偿操作
            for func, args, kwargs in reversed(self._compensations):
                try:
                    func(*args, **kwargs)
                    logger.info(f"补偿操作 {func.__name__} 执行成功")
                except Exception as ce:
                    logger.error(f"补偿操作 {func.__name__} 执行失败: {str(ce)}")
            
            return False, results


# 便捷函数
def create_requestor(
    timeout: Tuple[float, float] = (10.0, 30.0),
    max_retries: int = 3,
    retry_delay_base: float = 1.0,
    retry_delay_max: float = 30.0,
) -> NetworkRequestor:
    """
    创建网络请求器实例
    
    Args:
        timeout: 超时时间元组
        max_retries: 最大重试次数
        retry_delay_base: 重试基础延迟时间
        retry_delay_max: 最大重试延迟时间
        
    Returns:
        网络请求器实例
    """
    config = RequestConfig(
        timeout=timeout,
        max_retries=max_retries,
        retry_delay_base=retry_delay_base,
        retry_delay_max=retry_delay_max,
    )
    return NetworkRequestor(config)


def make_simple_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Union[bytes, str, Dict[str, Any]]] = None,
    parse_json: bool = True,
    **config_kwargs,
) -> RequestResponse:
    """
    发送简单网络请求（创建临时请求器）
    
    Args:
        url: 请求URL
        method: 请求方法
        headers: 请求头
        data: 请求数据
        parse_json: 是否解析JSON
        config_kwargs: 请求器配置参数
        
    Returns:
        请求响应对象
    """
    requestor = create_requestor(**config_kwargs)
    return requestor.make_request(url, method, headers, data, parse_json)


# 示例用法
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # 创建请求器
    requestor = create_requestor(
        timeout=(5.0, 10.0),
        max_retries=3,
        retry_delay_base=1.0,
        retry_delay_max=10.0,
    )
    
    # 示例1: 简单GET请求
    print("示例1: 简单GET请求")
    response = requestor.make_request("https://jsonplaceholder.typicode.com/todos/1")
    if response.success:
        print(f"成功: {response.json_data}")
    else:
        print(f"失败: {response.error}")
    
    # 示例2: POST请求
    print("\n示例2: POST请求")
    response = requestor.make_request(
        "https://jsonplaceholder.typicode.com/posts",
        method="POST",
        data={"title": "foo", "body": "bar", "userId": 1},
    )
    if response.success:
        print(f"成功: {response.json_data}")
    else:
        print(f"失败: {response.error}")
    
    # 示例3: 事务性操作
    print("\n示例3: 事务性操作")
    transaction = TransactionalRequest(requestor)
    
    # 定义操作
    def op1():
        print("执行操作1: 删除数据")
        # 模拟成功
        return True, "操作1结果"
    
    def op2():
        print("执行操作2: 插入新数据")
        # 模拟失败
        return False, "操作2结果"
    
    # 定义补偿操作
    def compensation1():
        print("执行补偿操作1: 恢复删除的数据")
    
    # 添加补偿操作
    transaction.add_compensation(compensation1)
    
    # 执行事务
    success, results = transaction.execute([op1, op2])
    print(f"事务结果: {'成功' if success else '失败'}")
    print(f"操作结果: {results}")