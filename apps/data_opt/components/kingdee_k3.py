from datetime import datetime, timedelta
# from typing import NamedTuple, List#, Callable
# import requests

from ._base import get_session, wrap_data_response, flat_merge_parent_child_data



class K3Connection():

    def __init__(self, origin_url, acctid, username, password, lcid):
        # super().__init__(*args, **kwargs)
        self.origin_url = origin_url
        self.acctid = acctid
        self.username = username
        self.password = password
        self.lcid = lcid
        self._cookie = None
        self._cookie_expire = None
        self._session = get_session()


    def auth(self):
        if self._cookie is None or self._cookie_expire is None or (datetime.now() + timedelta(minutes=15)) > self._cookie_expire:
            response = self._session.post(
                f"{self.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc",
                data={
                    "acctid": self.acctid,
                    "username": self.username,
                    "password": self.password,
                    "lcid": self.lcid,
                },
            )
            # 处理cookie
            set_cookies = response.headers['Set-Cookie'].split(';')
            self._cookie = set_cookies[0] + ';' + set_cookies[3].split(',')[1].strip()
            self._cookie_expire = datetime.strptime(set_cookies[1].split('=')[1], "%a, %d-%b-%Y %H:%M:%S %Z")
            self._session.headers.update({
                "Cookie": self._cookie,
            })
        return self._cookie


    def _get_data(self, form_id: str, field_keys_mapper: dict, page_size: int=1000, filter_string: str=None):
        """
        获取Kingdee K3 Cloud数据
        form_id: 表单ID
        field_keys_mapper: 字段键映射，键为K3 字段名，值为映射成的段名
        filter_string: 查询条件，格式为
        """
        k3_fields = list(field_keys_mapper.keys())
        to_fields = list(field_keys_mapper.values())
        field_keys = ",".join(k3_fields)
        # 发送请求
        start_row = 0
        while True:
            response = self._session.post(
                url=f"{self.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
                json={
                    "data": {
                        "FormId": form_id,
                        "FieldKeys": field_keys,
                        "FilterString": filter_string,
                        "StartRow": start_row,
                    "Limit": page_size,
                    "TopRowCount": 100000,
                    "SubSystemId": ""
                    }
                },
            )
        
            # 处理响应
            data = []
            if 'ErrorCode' in response.text:
                return [{"row_count": 0, "data": data}]

            raw_data = response.json()
            row_count = len(raw_data)
            for row in raw_data:
                data.append({
                    to_fields[i]: row[i]
                    for i in range(len(k3_fields))
                })
            yield {"row_count": row_count, "data": data}
            if row_count < page_size:
                break
            start_row += page_size


    def _set_data(self):
        pass


    def material_list(self, page_size: int=1000, filter_string: str=None):
        return self._get_data(
            form_id="BD_MATERIAL",
            field_keys_mapper={
                "fNumber": "materialno", "fName": "description", "fWorkShopId.fName": "plant",
                "fFixLeadTime": "fixleadtime", "fReOrderGood": "reorder", "fErpClsId.fCaption": "erpCls",
                "fCategoryId.fName": "planItem", "fProduceUnitId.fName": "unit", "fSpecification": "size",
                "fExpPeriod": "expPeriod", "fExpUnit.fCaption": "expUnit", "fCheckLeadTime": "checkleadt",
                "fCheckLeadTimeType.fCaption": "checkleadttype", "fPlanerId.fName": "planner", "fRefCost": "price",
                "fPlanIntervalsDays": "daygap", "fCanDelayDays": "candelay", "fMaxStock": "lottop",
                "fEOQ": "lotfix", "fPlanSafeStockQty": "lotss", "fMaterialId": "id",
                },
            filter_string=filter_string,
            page_size=page_size,
        )

    def bom_list(self, page_size: int=1000, filter_string: str=None):
        parent_data = self._get_data(
            form_id="ENG_BOM",
            field_keys_mapper={
                "fId": "id", "fMaterialId.fNumber": "productno", "fMaterialId.fName": "description",
                "fUnitId.fName": "unit", "fQty": "qty", "fBaseUnitId.fName": "baseunit", "FNumber": "matver"
            },
            filter_string=filter_string,
            page_size=page_size,
        )

        child_data = self._get_data(
            form_id="ENG_BOM",
            field_keys_mapper={
                "fTreeEntity_fEntryId": "id", "fID": "parentid", "fMaterialIdChild.fNumber": "materialno",
                "fChildUnitId.fName": "unit", "fNumerator": "numerator", "fDenominator": "denominator",
                "FNumber": "matver"
            },
            filter_string=filter_string,
        )
        return flat_merge_parent_child_data(
            parent_data=parent_data,
            child_data=child_data
        )

