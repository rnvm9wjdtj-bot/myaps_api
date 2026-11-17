import hashlib
import urllib.parse
import time
import json
import requests


def generate_auth_headers(method, url=None, body=None, access_key_secret=None):
    """
    生成智造家API鉴权所需的headers
    
    Args:
        method (str): HTTP方法，如GET, POST, PUT, DELETE
        url (str, optional): GET请求的完整URL，包含查询参数
        body (dict, list or str, optional): POST/PUT/DELETE请求的JSON数据
        access_key_secret (str): 签名所需的密钥

    Returns:
        dict: 包含sign和erptimestamp的headers字典
    """
    # 生成时间戳（毫秒）
    erptimestamp = str(int(time.time() * 1000))

    # 处理param
    if method.upper() == 'GET' and url:
        # 解析URL获取查询参数
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 将参数按ASCII码排序，处理重复key的情况
        sorted_params = []
        for key in sorted(query_params.keys()):
            values = query_params[key]
            for value in values:
                sorted_params.append(f"{key}={value}")

        # 拼接成param字符串
        param = '&'.join(sorted_params)

    elif method.upper() in ['POST', 'PUT', 'DELETE'] and body:
        # 处理JSON请求体
        if isinstance(body, (dict, list)):
            # 转换为JSON字符串，确保无空格（与示例一致）
            param = json.dumps(body, separators=(',', ':'))
        elif isinstance(body, str):
            # 如果已经是字符串，直接使用
            param = body
        else:
            raise ValueError("body必须是dict、list或JSON字符串")

    else:
        raise ValueError("不支持的HTTP方法或缺少必要参数")

    # 生成签名
    sign_str = f"{param}{erptimestamp}{access_key_secret}"
    md5 = hashlib.md5()
    md5.update(sign_str.encode('utf-8'))
    sign = md5.hexdigest().lower()

    # 构建headers
    headers = {
        'erptimestamp': erptimestamp,
        'sign': sign
    }

    # 如果是JSON请求，添加Content-Type
    if method.upper() in ['POST', 'PUT', 'DELETE']:
        headers['Content-Type'] = 'application/json'

    return headers


def send_request(method, url, body=None, access_key_secret=None):
    """
    发送带有鉴权headers的HTTP请求
    
    Args:
        method (str): HTTP方法，如GET, POST, PUT, DELETE
        url (str): 请求的完整URL
        body (dict, list or str, optional): POST/PUT/DELETE请求的JSON数据
        access_key_secret (str): 签名所需的密钥
    
    Returns:
        requests.Response: 请求响应对象
    """
    # 生成鉴权headers
    headers = generate_auth_headers(method, url, body, access_key_secret)

    # 发送请求
    method = method.upper()
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=30)

        elif method in ['POST', 'PUT', 'DELETE']:
            # 处理请求体
            if isinstance(body, (dict, list)):
                json_body = body
            elif isinstance(body, str):
                json_body = json.loads(body)
            else:
                json_body = None

            if method == 'POST':
                response = requests.post(url, json=json_body, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=json_body, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, json=json_body, headers=headers, timeout=30)

        else:
            raise ValueError(f"不支持的HTTP方法: {method}")

        # 返回响应
        return response

    except Exception as e:
        print(f"请求发送失败: {e}")
        raise


def get_request(url, access_key_secret=None):
    """
    发送带鉴权的GET请求

    Args:
        url (str): 请求的完整URL，包含查询参数
        access_key_secret (str): 签名所需的密钥

    Returns:
        requests.Response: 请求响应对象
    """
    return send_request('GET', url, access_key_secret=access_key_secret)


def post_request(url, body=None, access_key_secret=None):
    """
    发送带鉴权的POST请求

    Args:
        url (str): 请求的完整URL
        body (dict, list or str): JSON请求体
        access_key_secret (str): 签名所需的密钥

    Returns:
        requests.Response: 请求响应对象
    """
    return send_request('POST', url, body=body, access_key_secret=access_key_secret)


# 示例用法
if __name__ == "__main__":
    access_key = "2EE351BC3AC94730FC227F9DB4B73083"
    api_url = "https://beta-tmgc2-gateway.imefuture.com/tmgc2-api/api-proxy/erp/operation/addAndUpdateOperationBatchToExternal"


    def print_response(tag, response):
        """打印响应结果"""
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")


    # # ===== GET请求示例 =====
    # print("=" * 50)
    # print("GET请求")
    # print(f"URL: {api_url}")
    # print("=" * 50)
    # try:
    #     resp = get_request(api_url, access_key_secret=access_key)
    #     print_response("GET", resp)
    # except Exception as e:
    #     print(f"GET请求失败: {e}")

    # ===== POST请求示例 =====
    # 请求体：按实际接口文档填写字段
    post_body = [
        {"siteCode": "A00046447", "operationCode": "A001", "operationName": "Q3", "operationTypeCode": "PRODUCTION",
         "workUnitTypeCode": "Q3", "standardTime": 864.59, "standardTimeUnit": "SECOND"},
        {"siteCode": "A00046447", "operationCode": "A002", "operationName": "Q2", "operationTypeCode": "PRODUCTION",
         "workUnitTypeCode": "Q2", "standardTime": 864.59, "standardTimeUnit": "SECOND"},
        {"siteCode": "A00046447", "operationCode": "A003", "operationName": "Q1", "operationTypeCode": "PRODUCTION",
         "workUnitTypeCode": "Q1", "standardTime": 790.51, "standardTimeUnit": "SECOND"}
    ]

    print("\n" + "=" * 50)
    print("POST请求")
    print(f"URL: {api_url}")
    print(f"请求体: {json.dumps(post_body, ensure_ascii=False, separators=(',', ':'))}")
    print("=" * 50)
    try:
        resp = post_request(api_url, body=post_body, access_key_secret=access_key)
        print_response("POST", resp)
    except Exception as e:
        print(f"POST请求失败: {e}")
