from datetime import datetime
import requests
from typing import NamedTuple, List


# origin_url = "http://129.211.172.205:12980"
# acctid = "65a48b111c0197"
# username = "demo2"
# password = "88888888"
# lcid = "2052"

class FieldInfo(NamedTuple):
    target_name: str
    target_desc: str
    this_name: str
    this_desc: str


class FormInfo(NamedTuple):
    form_id: str
    field_infos: List[FieldInfo]


# material = FormInfo()

form_infos = [
    FormInfo(
        form_id="BD_MATERIAL",
        field_infos=[
            FieldInfo("fNumber", "编码", "materialno", "*料号"),
            FieldInfo("fName", "名称", "description", "*物料名称"),
            FieldInfo("fWorkShopId.fName", "生产车间", "plant", "工厂"),
            FieldInfo("fFixLeadTime", "固定提前期", "fixLeadTime", "固定提前期"),
            FieldInfo("fFixLeadTimeType.fCaption", "固定提前期单位", "fixLeadTimeType", "固定提前期单位"),
            FieldInfo("fReOrderGood", "再订货点", "lotpoint", "重订货点"),
            FieldInfo("fErpClsId.fCaption", "物料属性", "erpCls", "物料属性"),
            FieldInfo("fCategoryId.fName", "存货类别", "planItem", "产品组"),
            FieldInfo("fProduceUnitId.fName", "生产单位", "unit", "单位"),
            FieldInfo("fSpecification", "规格型号", "size", "规格"),
            FieldInfo("fExpPeriod", "保质期", "expPeriod", "保质期"),
            FieldInfo("fExpUnit.fCaption", "保质期单位", "expunit", "质保期单位"),
            FieldInfo("fMaxPoQty", "最大订货量", "lotmax", "最大批"),
            FieldInfo("fMinPoQty", "最小订货量", "lotmin", "最小批"),
            FieldInfo("fCheckLeadTime", "检验提前期", "checkLeadTime", "检验提前期"),
            FieldInfo("fCheckLeadTimeType.fCaption", "检验提前期单位", "checkLeadTimeType", "检验提前期单位"),
            FieldInfo("fPlanerId.fName", "计划员", "planner", "计划员"),
            FieldInfo("fRefCost", "参考成本", "price", "单价"),
            FieldInfo("fPlanIntervalsDays", "批量拆分间隔天数", "daygap", "MTO拆分天数"),
            FieldInfo("fCanDelayDays", "允许延后天数", "candelay", "可否延迟"),
            FieldInfo("fMaxStock", "最大库存", "lottop", "最大库存"),
            FieldInfo("fEOQ", "固定/经济批量", "lotfix", "固定批"),
            FieldInfo("fPlanSafeStockQty", "安全库存", "lotss", "安全库存"),
            FieldInfo("fMaterialId", "🔑", "id", "ERP数据ID")
            ]),
    ]


class K3CloudApi():

    def __init__(self, origin_url, acctid, username, password, lcid, need_forms: List[str]):
        # super().__init__(*args, **kwargs)
        self.origin_url = origin_url
        self.acctid = acctid
        self.username = username
        self.password = password
        self.lcid = lcid
        self._cookie = None
        self._cookie_expire = None
        self._session = requests.Session()

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
        set_cookies = response.headers['Set-Cookie'].split(';')
        self._cookie = set_cookies[0] + ';' + set_cookies[3].split(',')[1].strip()
        self._cookie_expire = datetime.strptime(set_cookies[1].split('=')[1], "%a, %d-%b-%Y %H:%M:%S %Z")

    def get_data(self, *args, **kwargs):
        for form_info in form_infos:
            form_id = form_info.form_id
            field_infos = form_info.field_infos
            k3Fields = ",".join([field_info.target_name for field_info in field_infos])
            # 发送请求
            response = self._session.post(
                url=f"{self.origin_url}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
                headers={
                    "Content-Type": "application/json;charset=UTF-8",
                    "Cookie": self._cookie,
                },
                json={
                    "data": {
                        "FormId": form_id,
                        "FieldKeys": k3Fields,
                        "FilterString": None,
                        "StartRow": 0,
                        "Limit": 1000,
                        "TopRowCount": 100000,
                        "SubSystemId": ""
                    }
                },
            )
            # 处理响应
            data = response.json()
            print(data)


    def set_data(self):
        pass

    
k3_connector = K3CloudApi(origin_url="http://129.211.172.205:12980", acctid="65a48b111c0197", username="demo2", password="88888888", lcid="2052")
k3_connector.auth()
k3_connector.get_data()
