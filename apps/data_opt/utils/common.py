import base64, requests, json, ast, re#,os,

from globalobjects import logger as log_config


from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from typing import Optional, Dict, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.settings import LOG_LEVEL


# 获取日志器
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


def get_session(
    retries: int = 3,
    allowed_methods: list = ["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    connect_timeout: float = 15.0,
    read_timeout: float = 60.0,
    backoff_factor: float = 1.0,
):
    # 配置重试策略
    retry_strategy = Retry(
        total=retries,  # 总重试次数
        connect=retries,  # 连接错误重试次数
        read=retries,  # 读取错误重试次数
        redirect=retries,  # 重定向重试次数
        status=retries,  # 状态码错误重试次数
        backoff_factor=backoff_factor,  # 重试间隔因子，每次重试间隔 = backoff_factor * (2 ** (重试次数 - 1))
        status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
        allowed_methods=allowed_methods,  # 允许重试的HTTP方法
        respect_retry_after_header=True,  # 尊重服务器返回的Retry-After头
    )

    # 配置连接池
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_connections,  # 连接池中的最大连接数
        pool_maxsize=pool_maxsize,  # 连接池中每个主机的最大连接数
        pool_block=False  # 连接池满时不阻塞，而是创建新连接
    )

    # 创建Session实例
    request_session = requests.Session()

    # 设置默认超时时间（连接超时15秒，读取超时60秒）
    request_session.timeout = (connect_timeout, read_timeout)

    # 设置连接池参数
    request_session.keep_alive = True
    request_session.headers.update({
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, deflate',
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # 挂载适配器到HTTP和HTTPS协议
    request_session.mount("http://", adapter)
    request_session.mount("https://", adapter)

    return request_session


def get_optimized_session(
    retries: int = 3,
    allowed_methods: list = ["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
    enable_http2: bool = True,
    enable_warmup: bool = False,
):
    """获取优化的 Session 实例
    
    支持 HTTP/2 和连接池预热等优化功能。
    
    Args:
        retries: 重试次数
        allowed_methods: 允许重试的HTTP方法
        pool_connections: 连接池中的最大连接数
        pool_maxsize: 连接池中每个主机的最大连接数
        connect_timeout: 连接超时时间
        read_timeout: 读取超时时间
        enable_http2: 是否启用 HTTP/2 支持（默认 True）
        enable_warmup: 是否启用连接池预热（默认 False）
        
    Returns:
        requests.Session: Session 实例
    """
    # 尝试使用 httpx 启用 HTTP/2
    if enable_http2:
        try:
            import httpx
            logger.success("HTTP/2", "", "启用支持")
            client = httpx.Client(
                http2=True,
                timeout=httpx.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=read_timeout,
                    pool=connect_timeout
                ),
                limits=httpx.Limits(
                    max_keepalive_connections=pool_connections,
                    max_connections=pool_maxsize
                ),
                verify=False
            )
            # 包装为 requests.Session 兼容接口
            class HttpxSessionWrapper:
                def __init__(self, client):
                    self._client = client
                    self.headers = {}
                
                def request(self, method, url, **kwargs):
                    headers = {**self.headers, **kwargs.pop('headers', {})}
                    # 转换 requests 参数到 httpx 参数
                    if 'allow_redirects' in kwargs:
                        kwargs['follow_redirects'] = kwargs.pop('allow_redirects')
                    response = self._client.request(method, url, headers=headers, **kwargs)
                    return response
                
                def get(self, url, **kwargs):
                    return self.request('GET', url, **kwargs)
                
                def post(self, url, **kwargs):
                    return self.request('POST', url, **kwargs)
                
                def patch(self, url, **kwargs):
                    return self.request('PATCH', url, **kwargs)
                
                def delete(self, url, **kwargs):
                    return self.request('DELETE', url, **kwargs)
                
                def head(self, url, **kwargs):
                    return self.request('HEAD', url, **kwargs)
                
                def close(self):
                    self._client.close()
                
                def mount(self, *args, **kwargs):
                    pass
            
            return HttpxSessionWrapper(client)
        except ImportError:
            logger.warning_msg("HTTP/2", "", "httpx未安装，回退到requests")
        except Exception as e:
            logger.warning_msg("HTTP/2初始化", "", f"失败：{e}，回退到requests")
            import traceback
            logger.debug(f"httpx初始化失败详细错误：{traceback.format_exc()}")
    
    # 使用标准的 requests.Session
    request_session = get_session(
        retries=retries,
        allowed_methods=allowed_methods,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout
    )
    
    return request_session


def add_basic_auth_requests(
    session: Optional[Union[requests.Session, Dict[str, str]]] = None,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> Dict[str, str]:
    """
    为requests库添加Basic认证头部
    
    Args:
        session: requests.Session对象或headers字典
        username: 用户名
        password: 密码
    
    Returns:
        包含认证头的字典
    """
    if not username or not username.strip():
        return {}

    auth_string = f"{username}:{password or ''}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    auth_header = {'Authorization': f'Basic {encoded_auth}'}
    
    if isinstance(session, requests.Session):
        session.headers.update(auth_header)
    elif isinstance(session, dict):
        session.update(auth_header)
    
    return auth_header


def is_json(s):
    try:
        j = json.loads(s)
        return True, j
    except ValueError as e:
        return False, None


def python_dict_str_to_json_str(dict_str):
    json_str = json.dumps(ast.literal_eval(dict_str))
    return json_str


def clean_json(json_str):
    json_str = json_str.replace('\\t', '').replace('\\n', '').replace('\\r', '')
    # 替换所有非标准空白符（包括全角空格、不间断空格等）
    json_str = re.sub(r'[\xa0\u200b\u3000]', ' ', json_str)
    # 移除其他控制字符
    json_str = re.sub(r'[\x00-\x1f]', '', json_str)
    # 移除双引号内部首尾空白
    json_str = re.sub(r'"\s+', '"', json_str)
    json_str = re.sub(r'\s+"', '"', json_str)
    # 移除其他无意义的占位符
    json_str = re.sub(r'\\+<', '<', json_str) # 清除HTML尖括号前的连续斜杠
    # 移除连续奇数个斜杠\
    json_str = re.sub(r'\\{3,}(?<!\\)', lambda m: '\\\\' * (len(m.group()) // 2 + 1), json_str)
    # 移除非法转义
    json_str = re.sub(r'\\(?![\\/"bfnrtu]|u[0-9a-fA-F]{4})', r'\\\\', json_str)
    json_str = re.sub(r'\\(?![\\/"bfnrtu]|u[0-9a-fA-F]{4})', r'', json_str)
    return json_str


def map_dict_keys(dict_list, key_mapper):
    """
    将字典字符串中的键映射到新的键名
    
    Args:
        dict_list: 包含字典的列表
        key_mapper: 键名映射字典，例如 {'old_key': 'new_key'}
    
    Returns:
        映射后的字典列表
    """
    try:
        mapped_data_list = []
        # 解析原始字典字符串
        for data in dict_list:
            # 应用键名映射
            mapped_data_list.append({key_mapper.get(k, k): v for k, v in data.items()})
        # 返回映射后的字典字符串
        return mapped_data_list
    except (ValueError, SyntaxError) as e:
        logger.fail("键名映射", "", str(e))
        return None


def convert_timeunit(value, from_unit: str, to_unit: str = 'day'):
    """
    将时间单位转换为另一个单位
    Args:
        from_unit: 原始时间单位，例如 '天'
        to_unit: 目标时间单位，例如 '小时'
        value: 原始时间值
    
    Returns:
        转换后的时间值
    """
    # 定义单位转换因子
    unit_factors = {
        '日': 24, '天': 24, 'day': 24, 'd': 24,
        '小时': 1, '时': 1, 'hour': 1, 'hr': 1, 'h': 1,
        '分钟': 1/60, '分': 1/60, 'minute': 1/60, 'min': 1/60, 'm': 1/60,
        '秒': 1/3600, 'sec': 1/3600, 's': 1/3600
    }
    try:
        value = float(value)
        if value == 0:
            return 0
    except Exception:
        if value in ('', None):
            return 0
    from_unit = str(from_unit).lower()
    to_unit = str(to_unit).lower()
    if not from_unit in unit_factors:
        raise ValueError(f"无效的原始时间单位: {from_unit}")
    if not to_unit in unit_factors:
        raise ValueError(f"无效的目标时间单位: {to_unit}")
    if value < 0:
        raise ValueError("时间值必须非负")
    
    # 进行转换
    return value * unit_factors[from_unit] / unit_factors[to_unit]


def clean_value(value: Union[str, int, float, None], if_none_return='🈳❗'):
    if value is None:
        return if_none_return
    value_type = type(value)
    if value_type == str:
        return value.strip()
    return value


def parallel_executor(max_workers=10):
    """
    并行执行装饰器，用于将函数应用到多个项目上
    
    Args:
        max_workers: 线程池最大线程数
    
    Returns:
        装饰器函数
    """
    def decorator(func):
        def wrapper(items, *args, **kwargs):

            results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {executor.submit(func, item, *args, **kwargs): item for item in items}
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    try:
                        result = future.result()
                        if isinstance(result, list):
                            results.extend(result)
                        else:
                            results.append(result)
                    except Exception as exc:
                        logger.fail("并行处理", str(item), str(exc))
            return results
        return wrapper
    return decorator