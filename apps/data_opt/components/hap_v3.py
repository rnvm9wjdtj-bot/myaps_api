"""
明道云 API 封装
"""

import requests, json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class HapApiV3:
    def __init__(self, app_key: str, sign: str, base_url: str=('https://api.mingdao.com', 'http://127.0.0.1:8080/api')[0]):
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
        self.headers = {
            'HAP-Appkey': app_key,
            'HAP-Sign': sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        
        # 初始化Session并配置性能参数
        self.session = requests.Session()
        
        # 在Session对象上存储API基本URL
        self.session.base_url = base_url
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 总重试次数
            status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],  # 允许重试的请求方法
            backoff_factor=1  # 重试间隔因子（1秒，2秒，4秒...）
        )
        
        # 配置连接池
        adapter = HTTPAdapter(
            pool_connections=20,  # 连接池中的连接数
            pool_maxsize=20,  # 每个主机的最大连接数
            max_retries=retry_strategy
        )
        
        # 为HTTP和HTTPS添加适配器
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 设置默认超时时间（连接超时3秒，读取超时30秒）
        self.session.timeout = (3, 30)

    @classmethod
    def _rows_data_to_controls_list(cls, rows_data_list: list[dict], ignore_fields=[], controls_reflection={}, remain_irrelevant_fields=True):
        """
        将行数据字典转换为工作表API字段值list
        controls_reflection 是一个可选参数，用于将row_data_dict中的字段名称（键）映射为目标工作表control_id
        remain_irrelevant_fields 是否保留 controls_reflection 未提及的字段
        """
        controls_list = []
        for data_dict in rows_data_list:
            row_controls_list = []
            controls_list.append({'fields': row_controls_list})
            for k, v in data_dict.items():
                if k in ignore_fields: 
                    continue
                try:
                    control_id = controls_reflection[k]
                except:
                    if remain_irrelevant_fields:
                        control_id = k
                    else:
                        continue
                control_id = controls_reflection.get(k, k)
                v_type = type(v)
                if v_type in (dict, list):
                    row_controls_list.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False)})
                elif v_type in (int, float):
                    row_controls_list.append({'id': control_id, 'value': v, 'type': 2})
                elif v_type == str:
                    row_controls_list.append({'id': control_id, 'value': v, 'type': 2})
                else:
                    pass
        return controls_list


    def _post(self, path: str, data: dict):
        url = f"{self.session.base_url}{path}"
        response = self.session.post(url, headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()


    def _get(self, path: str, params: dict=None):
        url = f"{self.session.base_url}{path}"
        response = self.session.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()


    def add_rows(self, worksheet_id: str, rows: list, trigger_workflow: bool=True):
        path = f"/v3/app/worksheets/{worksheet_id}/rows/batch"
        chunk_size = min(len(rows), 1000)
        for i in range(0, len(rows), chunk_size):
            chunk = self._rows_data_to_controls_list(rows[i:i+chunk_size])
            print(chunk)
            data = {
                "rows": chunk,
                "triggerWorkflow": trigger_workflow
            }
            response = self._post(path, data)
            print(response)


    def get_row_dict(self, worksheet_id: str, row_id: str, show_fields: list | str=None):
        path = f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}?includeSystemFields=false"
        response = self._get(path)
        row_dict = {}
        if response['success']:
            data = response['data']
            for k, v in data.items():
                if k not in ('rowid', 'ctime', 'utime', 'caid', 'uaid', 'ownerid'):
                    if type(v) == list:
                        v = [item['value'] for item in v]
                        row_dict[k] = ','.join(v)
                    else:
                        row_dict[k] = v
            if show_fields:
                if type(show_fields) == str:
                    show_fields = show_fields.split(',')
                row_dict = {k: v for k, v in row_dict.items() if k in show_fields}
        return row_dict
