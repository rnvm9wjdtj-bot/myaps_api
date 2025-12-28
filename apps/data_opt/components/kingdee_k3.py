from datetime import datetime
from typing import NamedTuple, List, Callable
import requests


from . import TimedExecutionMixin, timed_execution



class FieldInfo(NamedTuple):
    src_name: str
    src_desc: str
    ctrl_name: str
    ctrl_desc: str
    # handle_func: Callable


class FormInfo(NamedTuple):
    form_id: str
    field_infos: List[FieldInfo]


form_infos = [
    FormInfo(
        form_id="BD_MATERIAL",
        field_infos=[
            FieldInfo("fNumber", "编码", "materialno", "*料号"),
            # FieldInfo("fName", "名称", "description", "*物料名称"),
            # FieldInfo("fWorkShopId.fName", "生产车间", "plant", "工厂"),
            # FieldInfo("fFixLeadTime", "固定提前期", "fixLeadTime", "固定提前期"),
            # FieldInfo("fFixLeadTimeType.fCaption", "固定提前期单位", "fixLeadTimeType", "固定提前期单位"),
            # FieldInfo("fReOrderGood", "再订货点", "lotpoint", "重订货点"),
            # FieldInfo("fErpClsId.fCaption", "物料属性", "erpCls", "物料属性"),
            # FieldInfo("fCategoryId.fName", "存货类别", "planItem", "产品组"),
            # FieldInfo("fProduceUnitId.fName", "生产单位", "unit", "单位"),
            # FieldInfo("fSpecification", "规格型号", "size", "规格"),
            # FieldInfo("fExpPeriod", "保质期", "expPeriod", "保质期"),
            # FieldInfo("fExpUnit.fCaption", "保质期单位", "expunit", "质保期单位"),
            # FieldInfo("fMaxPoQty", "最大订货量", "lotmax", "最大批"),
            # FieldInfo("fMinPoQty", "最小订货量", "lotmin", "最小批"),
            # FieldInfo("fCheckLeadTime", "检验提前期", "checkLeadTime", "检验提前期"),
            # FieldInfo("fCheckLeadTimeType.fCaption", "检验提前期单位", "checkLeadTimeType", "检验提前期单位"),
            # FieldInfo("fPlanerId.fName", "计划员", "planner", "计划员"),
            # FieldInfo("fRefCost", "参考成本", "price", "单价"),
            # FieldInfo("fPlanIntervalsDays", "批量拆分间隔天数", "daygap", "MTO拆分天数"),
            # FieldInfo("fCanDelayDays", "允许延后天数", "candelay", "可否延迟"),
            # FieldInfo("fMaxStock", "最大库存", "lottop", "最大库存"),
            # FieldInfo("fEOQ", "固定/经济批量", "lotfix", "固定批"),
            # FieldInfo("fPlanSafeStockQty", "安全库存", "lotss", "安全库存"),
            # FieldInfo("fMaterialId", "🔑", "id", "ERP数据ID")
            ]),
    ]


class K3Connection(TimedExecutionMixin):

    def __init__(self, origin_url, acctid, username, password, lcid):
        # super().__init__(*args, **kwargs)
        self.origin_url = origin_url
        self.acctid = acctid
        self.username = username
        self.password = password
        self.lcid = lcid
        self._cookie = None
        self._cookie_expire = None
        self._session = requests.Session()#get_session()#requests.Session()


    @timed_execution(interval_seconds=300)
    def auth(self):
        if self._cookie and self._cookie_expire and datetime.now() < self._cookie_expire:
            return
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
        print(response.json())
        set_cookies = response.headers['Set-Cookie'].split(';')
        self._cookie = set_cookies[0] + ';' + set_cookies[3].split(',')[1].strip()
        self._cookie_expire = datetime.strptime(set_cookies[1].split('=')[1], "%a, %d-%b-%Y %H:%M:%S %Z")
        self._session.headers.update({
            "Cookie": self._cookie,
        })

    def _get_data(self, form_id: str, field_keys_mapper: dict, filter_string: str=None):
        """
        获取Kingdee K3 Cloud数据
        form_id: 表单ID
        field_keys_mapper: 字段键映射，键为K3 Cloud字段名，值为自定义字段名
        filter_string: 查询条件，格式为"字段名1=值1 and 字段名2=值2"
        """
        field_keys = ",".join(field_keys_mapper.keys())
        # 发送请求
        response = self._session.post(
            url=f"{self.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
            json={
                "data": {
                    "FormId": form_id,
                    "FieldKeys": field_keys,
                    "FilterString": filter_string,
                    "StartRow": 0,
                    "Limit": 1000,
                    "TopRowCount": 100000,
                    "SubSystemId": ""
                }
            },
        )
        # 处理响应
        if 'ErrorCode' in response.text:
            return None
        data = response.json()
        if data:
            print(data)
            


    def _set_data(self):
        pass
