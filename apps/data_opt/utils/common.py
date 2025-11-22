import os, base64, requests, json, ast, re

from typing import Optional, Dict, Union

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


def _is_json(s):
    try:
        json.loads(s)
        return True
    except ValueError as e:
        return False

def _python_dict_str_to_json_str(dict_str):
  json_str = json.dumps(ast.literal_eval(dict_str))
  return json_str

def _clean_json(json_str):
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