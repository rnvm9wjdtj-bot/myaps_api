import pandas as pd


from datetime import datetime, timedelta
from typing import Literal, Dict, Any#NamedTuple, List#, Callable
# import requests

from ._base import (
    BaseConnection, get_session, wrap_data_response, flat_merge_parent_child_data, convert_timeunit, clean_value
)

from apps.io_api.schemas import (
    model_validator, AcceptMaterial, Field
)


class K3Material(AcceptMaterial):

    leadday: int = Field(None, ge=0, description="交期（天）")
    grday: int = Field(None, ge=0, description="收货质检（天）")
    groupno: str = Field(None, description="型号")

    class Config:
        extra = 'allow'
    
    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = {}
        cleaned_values['materialno'] = clean_value(values['编码'])
        cleaned_values['description'] = clean_value(values['名称'])
        cleaned_values['size'] = clean_value(values['规格型号'])
        # cleaned_values['plant'] = values['生产车间']
        cleaned_values['planner'] = clean_value(values['计划员'])
        # cleaned_values['fifo'] = values['']
        cleaned_values['leadday'] = convert_timeunit(int(values.get('固定提前期', 0)), values['固定提前期单位'], 'day')
        cleaned_values['expday'] = convert_timeunit(int(values.get('保质期', 0)), values['保质期单位'], 'day')
        cleaned_values['grday'] = convert_timeunit(int(values.get('检验提前期', 0)), values['检验提前期单位'], 'day')
        cleaned_values['abc'] = 'A' if values['物料属性'].replace(' ','') == '自制' else 'B'
        cleaned_values['unit'] = clean_value(values['生产单位'])
        cleaned_values['price'] = values['参考成本']
        # cleaned_values['groupno'] = values['']
        cleaned_values['type'] = 'E' if values['物料属性'].replace(' ','') == '自制' else 'F'
        cleaned_values['phantom'] = 'Y' if values['物料属性'].replace(' ','') == '虚拟' else 'N'
        # cleaned_values['phantommin'] = values['']
        # cleaned_values['firmday'] = values['']
        cleaned_values['daygap'] = values['批量拆分间隔天数']
        cleaned_values['candelay'] = 'Y' if values.get('允许延后天数', 0) > 0 else 'N'
        # cleaned_values['lotsize'] = values['']
        cleaned_values['lotfix'] = values['固定/经济批量']
        cleaned_values['lotmin'] = values['最小批量']
        cleaned_values['lotmax'] = values['最大批量']
        # cleaned_values['lotround'] = values['']
        cleaned_values['lotss'] = values['安全库存']
        cleaned_values['lotpoint'] = values['再订货点']
        cleaned_values['lottop'] = values['最大库存']
        # cleaned_values['planitem'] = values['']
        # cleaned_values['preday'] = values['']
        # cleaned_values['subday'] = values['']
        # cleaned_values['memo'] = values['']
        # cleaned_values['free1'] = values['']
        # cleaned_values['free2'] = values['']
        # cleaned_values['free3'] = values['']
        return cleaned_values


class K3Connection(BaseConnection):

    def __init__(cls, origin_url, acctid, username, password, lcid):
        # super().__init__(*args, **kwargs)
        cls.origin_url = origin_url
        cls.acctid = acctid
        cls.username = username
        cls.password = password
        cls.lcid = lcid
        cls._cookie = None
        cls._cookie_expire = None
        cls._session = get_session()


    def auth(cls):
        if cls._cookie is None or cls._cookie_expire is None or (datetime.now() + timedelta(minutes=15)) > cls._cookie_expire:
            response = cls._session.post(
                f"{cls.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc",
                data={
                    "acctid": cls.acctid,
                    "username": cls.username,
                    "password": cls.password,
                    "lcid": cls.lcid,
                },
            )
            # 处理cookie
            set_cookies = response.headers['Set-Cookie'].split(';')
            cls._cookie = set_cookies[0] + ';' + set_cookies[3].split(',')[1].strip()
            cls._cookie_expire = datetime.strptime(set_cookies[1].split('=')[1], "%a, %d-%b-%Y %H:%M:%S %Z")
            cls._session.headers.update({
                "Cookie": cls._cookie,
            })
        return cls._cookie


    def _get_paged_data(cls, form_id: str, field_keys_mapper: dict, page_size: int=1000, filter_string: str=None, only_today: bool=False):
        """
        分页获取数据，每次返回page_size条数据
        form_id: 表单ID
        field_keys_mapper: 字段键映射，键为K3 字段名，值为映射成的段名
        filter_string: 查询条件，格式为K3 格式
        only_today: 是否仅查询今天变动的数据
        """
        cls.auth()
        filter_string = filter_string or "1=1"
        if only_today:
            today = datetime.now().strftime('%Y-%m-%d')
            filter_string = f"{filter_string} AND (( fCreateDate >= '{today} 00:00:00' AND fCreateDate < '{today} 23:59:59' ) OR ( fModifyDate >= '{today} 00:00:00' AND fModifyDate < '{today} 23:59:59' ))"
            #`(( FCREATEDATE >= '${sliceStart}' AND FCREATEDATE < '${sliceEnd}' ) OR ( FMODIFYDATE >= '${sliceStart}' AND FMODIFYDATE < '${sliceEnd}'))`
        k3_fields = list(set(field_keys_mapper.keys()))
        to_fields = [field_keys_mapper[k] for k in k3_fields]
        # 发送请求
        start_row = 0
        while True:
            response = cls._session.post(
                url=f"{cls.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
                json={
                    "data": {
                        "FormId": form_id,
                        "FieldKeys": ",".join(k3_fields),
                        "FilterString": filter_string,
                        "StartRow": start_row,
                    "Limit": page_size,
                    "TopRowCount": 100000,
                    "SubSystemId": ""
                    }
                }
            )
            # 处理响应
            data = []
            if 'ErrorCode' in response.text:
                yield data
                break

            raw_data = response.json()
            row_count = len(raw_data)
            for row in raw_data:
                data.append({
                    to_fields[i]: row[i]
                    for i in range(len(k3_fields))
                })
            yield data
            if row_count < page_size:
                break
            start_row += page_size


    def material_list(cls, page_size: int=1000, filter_string: str=None, only_today: bool=False, pydantic_model: AcceptMaterial=K3Material):
        page_size = min(page_size, 1000)
        material_paged_data = cls._get_paged_data(
            form_id="BD_MATERIAL",
            field_keys_mapper={
                "fMaterialId": "id", "fNumber": "编码", "fName": "名称",
                "fWorkShopId.fName": "生产车间", "fPlanerId.fName": "计划员",
                "fSpecification": "规格型号", "fCategoryId.fName": "存货类别",
                "fErpClsId.fCaption": "物料属性", "fProduceUnitId.fName": "生产单位",
                "fFixLeadTime": "固定提前期", "fFixLeadTimeType.fCaption": "固定提前期单位",
                "fExpPeriod": "保质期", "fExpUnit.fCaption": "保质期单位",
                "fCheckLeadTime": "检验提前期", "fCheckLeadTimeType.fCaption": "检验提前期单位",
                "fPlanIntervalsDays": "批量拆分间隔天数", "fCanDelayDays": "允许延后天数",
                "fMaxStock": "最大库存", "fPlanSafeStockQty": "安全库存", "fReOrderGood": "再订货点",
                "fEOQ": "固定/经济批量", "fRefCost": "参考成本",
                "fMaxQty": "最大批量", "fMinQty": "最小批量",
                },
            filter_string=filter_string,
            page_size=page_size,
            only_today=only_today,
        )
        data = cls._merge_paged_data(material_paged_data)
        return [dict(pydantic_model(**item)) for item in data]


    def bom_list(cls, page_size: int=1000, filter_string: str=None):
        parent_data = cls._get_paged_data(
            form_id="ENG_BOM",
            field_keys_mapper={
                "fId": "id", "fMaterialId.fNumber": "productno", "fMaterialId.fName": "description",
                "fUnitId.fName": "unit", "fQty": "qty", "fBaseUnitId.fName": "baseunit", "FNumber": "matver"
            },
            filter_string=filter_string,
            page_size=page_size,
        )

        child_data = cls._get_paged_data(
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

