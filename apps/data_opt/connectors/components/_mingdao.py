"""
明道云 API 封装
"""

import requests

class MingdaoApi:
    def __init__(self, app_key: str, sign: str, base_url: str='https://api.mingdao.com/v2'):
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
        self.session = requests.Session()

    def _post(self, path: str, data: dict):
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json"
        }
        response = self.session.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

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
            controls_list.append(row_controls_list)
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
                    row_controls_list.append({'controlId': control_id, 'value': json.dumps(v, ensure_ascii=False)})
                elif v_type in (int, float):
                    row_controls_list.append({'controlId': control_id, 'value': v, 'valueType': 2})
                elif v_type == str:
                    row_controls_list.append({'controlId': control_id, 'value': v, 'valueType': 2})
                else:
                    pass
        return controls_list

    def add_rows(self, worksheet_id: str, rows: list, trigger_workflow: bool=True):
        path = "/open/worksheet/addRows"
        chunk_size = min(len(rows), 1000)
        for i in range(0, len(rows), chunk_size):
            chunk = self._rows_data_to_controls_list(rows[i:i+chunk_size])
            print(chunk)
            data = {
                "appKey": self.api_key,
                "sign": self.sign,
                "worksheetId": worksheet_id,
                "rows": chunk,
                "triggerWorkflow": trigger_workflow
            }
            response = self._post(path, data)
            print(response)
