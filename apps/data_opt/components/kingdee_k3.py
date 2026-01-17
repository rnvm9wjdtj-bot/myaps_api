# import pandas as pd

from dataclasses import dataclass
import http.cookies

from datetime import datetime, timedelta, timezone
from typing import Dict, Any#NamedTuple, List#, Callable, Literal, 
# import requests

from ._base import (
    BaseConnection, wrap_data_response, convert_timeunit, clean_value
)

from apps.io_api.schemas import (
    BaseModel as PydanticModel,
    model_validator, AcceptMaterial, Field
)



class K3Material(AcceptMaterial):

    leadday: int = Field(None, ge=0, description="交期（天）")
    grday: int = Field(None, ge=0, description="收货质检（天）")
    groupno: str = Field(None, description="型号")
    fifo: int = Field(None, description="先进先出")

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
        cleaned_values['leadday'] = convert_timeunit(values.get('固定提前期', 0), values['固定提前期单位'], 'day')
        cleaned_values['expday'] = convert_timeunit(values.get('保质期', 0), values['保质期单位'], 'day')
        cleaned_values['grday'] = convert_timeunit(values.get('检验提前期', 0), values['检验提前期单位'], 'day')
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



class K3Config:
    """K3基础配置"""
    BASE_URL = "http://129.211.172.205:12980"
    ACCTID = "65a48b111c0197"
    LCID = "2052"
    USERNAME = "demo2"
    PASSWORD = "88888888"

    AUTH_ENDPOINT = "/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
    QUERY_ENDPOINT = "/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
    
    # 默认分页大小，注意最大不得超过1000
    PAGE_SIZE = 1000

    # 最大返回行数，注意最大不得超过100000
    TOP_ROW_COUNT = 100000

    # 表单ID及字段映射
    FORMS = {
        'material': {
            'form_id': 'BD_MATERIAL',
            'field_map': {
                "fMaterialId": "id", "fNumber": "编码", "fName": "名称",
                "fWorkShopId.fName": "生产车间", "fPlanerId.fName": "计划员",
                "fSpecification": "规格型号", "fCategoryId.fName": "存货类别",
                "fErpClsId.fCaption": "物料属性", "fProduceUnitId.fName": "生产单位",
                "fFixLeadTime": "固定提前期", "fFixLeadTimeType.fCaption": "固定提前期单位",
                "fExpPeriod": "保质期", "fExpUnit.fCaption": "保质期单位",
                "fCheckLeadTime": "检验提前期", "fCheckLeadTimeType.fCaption": "检验提前期单位",
                "fPlanIntervalsDays": "批量拆分间隔天数", "fCanDelayDays": "允许延后天数",
                "fMaxStock": "最大库存", "fPlanSafeStockQty": "安全库存", "fReOrderGood": "再订货点",
                "fEOQ": "固定/经济批量", "fRefCost": "参考成本", "fMaxQty": "最大批量", "fMinQty": "最小批量",
            },
            'base_filter': '',#'fUserOrgId=1',
            'pydantic_model': K3Material,
        },

        'bom': {
            'form_id': 'ENG_BOM',
            'field_map': {
                "fID": "父项id", "fNumber": "BOM版本", "fMaterialId.fNumber": "父项物料编码", "fMaterialId.fName": "父项物料名称",
                "fUnitId.fName": "父项物料单位", "fQty": "批量", "fBaseUnitId.fName": "父项基本单位",
                "fTreeEntity_fEntryId": "子项明细id",
                "fMaterialIdChild.fNumber": "子项物料编码", "fChildBaseUnitID.fName": "子项基本单位",
                "fChildUnitId.fName": "子项单位", "fNumerator": "用量:分子", "fDenominator": "用量:分母",
                "fBaseFixscrapQty": "基本单位固定损耗", "fBaseFixscrapQtyLot": "基本单位固定损耗数量"
            },
            'pydantic_model': None,
        },

        'workcenter': {
            'form_id': 'ENG_WORKCENTER',
            'field_map': {
                "fID": "id", "fNumber": "编码", "fName": "名称", "fDeptId.fName": "所属部门"
            },
            'pydantic_model': None,
        },

        'route': {
            'form_id': 'ENG_ROUTE',
            'field_map': {
                "fID": "父项id", "fNumber": "编码", "fName": "名称", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fProduceType.fCaption": "生产类型", "fApproveDate": "审核日期", "fForbidDate": "禁用日期",
                "fUnitId.fName": "单位", "fRouteGroupId.fName": "工艺路线分组",
                "fSubEntity_fDetailId": "子项明细id",
                "fWorkCenterId.fNumber": "工作中心", "fWorkCenterId.fName": "工作中心名称",
                "fOperNumber": "工序号", "fProcessId.fNumber": "工序编码", "fProcessId.fName": "工序名称"
            },
            'pydantic_model': None,
        },

        "so": {
            'form_id': 'SAL_SALEORDER',
            'field_map': {
                "fSaleOrderEntry_fEntryId": "子项明细id", "fSaleOrderEntry_fSeq": "序号", "fBillNo": "单据编号", "fModifyDate": "最后修改日期",
                "fCloseStatus.fCaption": "关闭状态", "fMrpCloseStatus.fCaption": "业务关闭", "fDocumentStatus.fCaption": "单据状态",
                "fDate": "日期", "fDeliveryDate": "要货日期", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fQty": "销售数量", "fUnitID.fName": "销售单位", "fBaseUnitId.fName": "基本单位",
            },
            'pydantic_model': None,
        },

        "mo": {
            'form_id': 'PRD_MO',
            'field_map': {
                "fId": "id", "fBillNo": "单据编号", "fDocumentStatus.fCaption": "单据状态", "fDate": "日期",
                "fTreeEntity_fEntryId": "子项明细id",
                "fTreeEntity_fSeq": "序号", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fQty": "数量", "fUnitId.fName": "单位", "fWorkshopId.fName": "生产车间",
                "fPlanStartDate": "计划开工时间", "fPlanFinishDate": "计划完工时间",
                "fScheduleStartTime": "排程开工时间", "fScheduleFinishTime": "排程完工时间",
                "fCancelDate": "作废日期",
                "fStatus.fCaption": "业务状态", "fPickMtrlStatus.fCaption": "领料状态",
                "fReqSrc.fCaption": "需求来源", "fSaleOrderId": "销售订单ID",
                "fSaleOrderEntryId": "销售订单子项ID", "fSaleOrderNo": "销售订单编号", "fSaleOrderEntrySeq": "需求单据行号",
                "fSrcBillNo": "源单编号", "fSrcSplitBillNo": "源拆分订单编号",
                "fMemoItem": "备注", "fBillType.fName": "单据类型",
            },
            'pydantic_model': None,
        },

        "stock": {
            'form_id': 'STK_Inventory',
            'field_map': {
                "fID": "id", "fMaterialId.fNumber": "物料编码", "fMaterialId.fName": "物料名称",
                "fStockLocId": "仓位", "fLot": "批号", "fStockOrgId": "库存组织", "fBomId.fNumber": "BOM版本",
                "fBaseUnitId.fName": "基本单位", "fStockUnitId.fName": "库存主单位", "fSecUnitId.fName": "库存辅单位",
                "fBaseQty": "库存量(基本单位)", "fQty": "库存量(主单位)", "fSecQty": "库存量(库存辅单位)",
                "fAvbQty": "可用量(主单位)", "fBaseAvbQty": "可用量(基本单位)", "fSecAVBQty": "可用量(库存辅单位)",
                "fUpdateTime": "最后更新时间",
                
            },
            'pydantic_model': None,
        },
    }

    @classmethod
    def regist_pydantic_model(cls, form_name: str, pydantic_model: PydanticModel):
        """注册Pydantic模型"""
        cls.FORMS[form_name]['pydantic_model'] = pydantic_model



class K3Connection(BaseConnection):

    def __init__(self, config: K3Config=K3Config):
        self.base_url = config.BASE_URL
        self.acctid = config.ACCTID
        self.username = config.USERNAME
        self.password = config.PASSWORD
        self.lcid = config.LCID
        self.config = config
        self._cookie = None
        self._cookie_expire = None
        super().__init__()


    @staticmethod
    def _parse_cookies(set_cookie_header: str) -> tuple[str, datetime]:
        try:
            cookie_jar = http.cookies.SimpleCookie()
            cookie_jar.load(set_cookie_header)
            # 提取主要Cookie值
            cookie_parts = set_cookie_header.split(';')
            if len(cookie_parts) < 4:
                raise ValueError("Cookie格式不正确")
            cookie_value = cookie_parts[0] + ';' + cookie_parts[3].split(',')[1].strip()
            # 解析过期时间
            expire_str = cookie_parts[1].split('=')[1]
            # 解析为GMT时间
            gmt_time = datetime.strptime(expire_str, "%a, %d-%b-%Y %H:%M:%S %Z")
            # 添加GMT时区信息
            gmt_timezone = timezone(timedelta(hours=0), name='GMT')
            gmt_time = gmt_time.replace(tzinfo=gmt_timezone)
            # 转换为系统默认时区时间
            expire_time = gmt_time.astimezone()
            print(f"Cookie解析成功，GMT过期时间: {gmt_time}, 系统时区过期时间: {expire_time}")
            return cookie_value, expire_time
        except (IndexError, ValueError, http.cookies.CookieError) as e:
            raise ConnectionError(f"Cookie解析失败: {e}")

    
    # def _post(self, endpoint: str, data: dict=None, params: dict=None, timeout: int=30):
    #     """POST请求"""
    #     self.auth()
    #     response = self._session.post(
    #         f"{self.base_url}{endpoint}",
    #         json=data,
    #         params=params,
    #         timeout=timeout
    #     )
    #     response.raise_for_status()
    #     return response.json()
        

    def auth(self):
        try:
            # 获取当前系统时区时间
            current_time = datetime.now().astimezone()
            if self._cookie is None or self._cookie_expire is None or (current_time + timedelta(minutes=15)) > self._cookie_expire:
                response = self._session.post(
                    f"{self.base_url}{self.config.AUTH_ENDPOINT}",
                    data={
                        "acctid": self.acctid,
                        "username": self.username,
                        "password": self.password,
                        "lcid": self.lcid,
                    },
                    timeout=30
                )
                response.raise_for_status()

                cookie_value, expire_time = self._parse_cookies(response.headers['Set-Cookie'])
                self._cookie = cookie_value
                self._cookie_expire = expire_time

                self._session.headers.update({
                    "Cookie": self._cookie,
                })
        except Exception as e:
            raise ConnectionError(f"认证失败: {e}")
        return self._cookie


    def _get_paged_data(self, form_id: str, field_map: dict, filter_string: str=None, only_today: bool=False):
        """
        分页获取数据
        form_id: 表单ID
        field_map: 字段键映射，键为K3 字段名，值为映射成的段名
        filter_string: 查询条件，格式为K3 格式
        only_today: 是否仅查询今天变动的数据
        """
        self.auth()
        filter_string = filter_string or "1=1"
        if only_today:
            today = datetime.now().strftime('%Y-%m-%d')
            filter_string = f"{filter_string} AND (( `fCreateDate` >= '{today} 00:00:00' AND `fCreateDate` <= '{today} 23:59:59' ) OR ( `fModifyDate` >= '{today} 00:00:00' AND `fModifyDate` <= '{today} 23:59:59' ))"
        k3_fields = set(field_map.keys())
        to_fields = [field_map[k] for k in k3_fields]
        # 发送请求
        start_row = 0
        page_size = self.config.PAGE_SIZE
        while True:
            response = self._session.post(
                url=f"{self.base_url}{self.config.QUERY_ENDPOINT}",
                json={
                    "data": {
                        "FormId": form_id,
                        "FieldKeys": ",".join(k3_fields),
                        "FilterString": filter_string,
                        "StartRow": start_row,
                        "Limit": page_size,
                        "TopRowCount": self.config.TOP_ROW_COUNT,
                    "SubSystemId": ""
                    }
                }
            )
            # 处理响应
            data = []
            if 'ErrorCode' in response.text:
                print(f"查询失败: {response.text}")
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


    def data_list(self, form_name: str, filter_string: str=None, only_today: bool=False, pydantic_model: PydanticModel=None):
        base_filterstring = self.config.FORMS[form_name].get('base_filter') or "1=1"
        if filter_string:
            filter_string = f"{filter_string} AND {base_filterstring}"
        else:
            filter_string = base_filterstring

        data_paged_data = self._get_paged_data(
            form_id=self.config.FORMS[form_name]['form_id'],
            field_map=self.config.FORMS[form_name]['field_map'],
            filter_string=filter_string,
            only_today=only_today,
        )
        data = self._merge_paged_data(data_paged_data)
        pydantic_model = pydantic_model or self.config.FORMS[form_name].get('pydantic_model')
        if not pydantic_model:
            return data
        return [dict(pydantic_model(**item)) for item in data]


    def __repr__(self) -> str:
            """字符串表示"""
            return (f"K3Connection(url='{self.base_url}', "
                    f"user='{self.username}', acctid='{self.acctid}')")