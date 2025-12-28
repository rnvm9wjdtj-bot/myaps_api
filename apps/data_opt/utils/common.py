import os, base64, requests, json, ast, re
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from typing import Optional, Dict, Union



def get_session(
    retries: int = 3,
    allowed_methods: list = ["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    connect_timeout: float = 10.0,
    read_timeout: float = 30.0,
):
    # 配置重试策略
    retry_strategy = Retry(
        total=retries,  # 总重试次数
        backoff_factor=0.5,  # 重试间隔因子，每次重试间隔 = backoff_factor * (2 ** (重试次数 - 1))
        status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
        allowed_methods=allowed_methods  # 允许重试的HTTP方法
    )

    # 配置连接池
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_connections,  # 连接池中的最大连接数
        pool_maxsize=pool_maxsize  # 连接池中每个主机的最大连接数
    )

    # 创建Session实例
    request_session = requests.Session()

    # 设置默认超时时间（连接超时10秒，读取超时30秒）
    request_session.timeout = (connect_timeout, read_timeout)

    # 挂载适配器到HTTP和HTTPS协议
    request_session.mount("http://", adapter)
    request_session.mount("https://", adapter)

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
        print(f"Error mapping keys: {e}")
        return None