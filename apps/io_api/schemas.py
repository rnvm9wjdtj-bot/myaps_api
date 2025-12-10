from datetime import datetime
# import enum
from typing import Literal, Dict, Optional, Any#, List
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator, PrivateAttr#, ValidationError, field_validator

from globalobjects import globalconst as gc
from config.settings import MYAPS_MAIN_DB
from apps.data_opt.projects import project_default_value
# from .common import common_read_by_sql

def _cache_raw_input_data(cls, values: Dict[str, Any]) -> Dict[str, Any]:
    """
    在模型验证之前捕获原始输入数据。
    'values' 参数就是传入的原始值。
    """
    if isinstance(values, dict):
        cls._cached_raw_input_data = values.copy()
    return values

def _set_raw_input_data(self):
    if hasattr(self, "_cached_raw_input_data"):
        self._raw_input_data = self._cached_raw_input_data
        # delattr(self, "_cached_raw_input_data")
    return self

class AcceptMaterial(BaseModel):
    materialno: str = Field(..., description="料号", example="M001")
    description: str = Field(..., description="物料名称", example="测试物料A")
    size: str = Field(None, description="规格", example="100x100mm")
    plant: str = Field(..., example=project_default_value.MAT_PLANT, description='工厂')
    planner: str = Field(project_default_value.MAT_PLANNER, description="计划员", example="张三")
    fifo: int = Field(project_default_value.MAT_FIFO, ge=0, le=1, description='1-FIFO 0-最近原则')
    leadday: int = Field(..., ge=0, description="交期（天）", example=7)
    expday: int = Field(project_default_value.MAT_EXPDAY, ge=0, description="保质期（天）", example=365)
    grday: int = Field(..., ge=0, description="收货质检（天）", example=1)
    abc: str = Field(..., enum=["A", "B", "C"], example="A", description="ABC分类")
    unit: str = Field(..., description='单位', example="PCS")
    price: Decimal = Field(0, description="价格", example=100.50)
    groupno: str = Field(..., description="型号", example="G001")
    type: str = Field(... if project_default_value.myaps_is_pro else None, enum=["E", "F"], example="E", description="物料类型  E-自制件 F-采购件")
    phantom: str = Field(project_default_value.MAT_PHANTOM, enum=list(gc.YES_NO.keys()), example="N", description='虚拟件')
    phantommin: int = Field(project_default_value.MAT_PHANTOMMIN, ge=0, description='虚拟时间(Minute)', example=0)
    firmday: int = Field(project_default_value.MAT_FIRMDAY, ge=0, description="固定天数", example=0)
    daygap: int = Field(project_default_value.MAT_DAYGAP, ge=0, description='MTO拆分天数', example=1)
    candelay: str = Field(project_default_value.MAT_CANDELAY, enum=list(gc.YES_NO.keys()), example="N", description='可否延迟')
    lotsize: str = Field(
        project_default_value.MAT_LOTSIZE,
        enum=list(gc.LOT_SIZE.keys()),
        example="EX", description='批量')
    lotfix: float = Field(project_default_value.MAT_LOTFIX, ge=0, description='固定批', example=0.0)
    lotmin: float = Field(project_default_value.MAT_LOTMIN, ge=0, description='最小批', example=0.0)
    lotmax: float = Field(project_default_value.MAT_LOTMAX, ge=0, description='最大批', example=0.0)
    lotround: float = Field(project_default_value.MAT_LOTROUND, ge=0, description='取整', example=0.0)
    lotss: float = Field(project_default_value.MAT_LOTSS, ge=0, description='安全库存', example=0.0)
    lotpoint: float = Field(project_default_value.MAT_LOTPOINT, ge=0, description='重订货点', example=0.0)
    lottop: float = Field(project_default_value.MAT_LOTTOP, ge=0, description='最大库存点', example=0.0)
    planitem: str = Field(None, description='产品组', example="PI001")
    preday: int = Field(project_default_value.MAT_PREDAY, ge=0, description='向前冲销(天)', example=999)
    subday: int = Field(project_default_value.MAT_SUBDAY, ge=0, description='向后冲销(天)', example=999)
    free1: Optional[str] = Field(None, max_length=255, description='自定义1', example="自定义内容。。。")
    free2: Optional[str] = Field(None, max_length=255, description='自定义2', example="自定义内容。。。")
    free3: Optional[str] = Field(None, max_length=255, description='自定义3', example="自定义内容。。。")
    memo: str = Field(None,  description='备注', example="无特殊要求")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 物料"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "description": "测试物料A",
                "size": "100x100mm",
                "plant": project_default_value.MAT_PLANT,
                "planner": project_default_value.MAT_PLANNER,
                "fifo": project_default_value.MAT_FIFO,
                "leadday": 7,
                "expday": project_default_value.MAT_EXPDAY,
                "grday": 1,
                "abc": "A",
                "unit": "PCS",
                "price": 100.50,
                "groupno": "G001",
                "type": "E",
                "phantom": "N",
                "memo": "标准物料"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        if values.get("price") in gc.NONE_AND_EMPTY:
            values["price"] = 0.00
        _cache_raw_input_data(cls, values)
        if values.get("fifo", "") == "":  # ，
            values["fifo"] = project_default_value.MAT_FIFO
        if values.get("expday", "") == "":
            values["expday"] = project_default_value.MAT_EXPDAY
        if values.get("phantommin", "") == "":
            values["phantommin"] = 0
        if values.get("firmday", "") == "":
            values["firmday"] = project_default_value.MAT_FIRMDAY
        if values.get("lotfix", "") == "":
            values["lotfix"] = project_default_value.MAT_LOTFIX
        if values.get("lotmin", "") == "":
            values["lotmin"] = project_default_value.MAT_LOTMIN
        if values.get("lotmax", "") == "":
            values["lotmax"] = project_default_value.MAT_LOTMAX
        if values.get("lotround", "") == "":
            values["lotround"] = project_default_value.MAT_LOTROUND
        if values.get("lotss", "") == "":
            values["lotss"] = project_default_value.MAT_LOTSS
        if values.get("lotpoint", "") == "":
            values["lotpoint"] = project_default_value.MAT_LOTPOINT
        if values.get("lottop", "") == "":
            values["lottop"] = project_default_value.MAT_LOTTOP
        if values.get("preday", "") == "":
            values["preday"] = project_default_value.MAT_PREDAY
        if values.get("subday", "") == "":
            values["subday"] = project_default_value.MAT_SUBDAY
        if values.get("leadday", "") == "":
            values["leadday"] = project_default_value.MAT_LEADDAY_E if values.get("type") == "E" else project_default_value.MAT_LEADDAY_F
        if values.get("grday", "") == "":
            values["grday"] = project_default_value.MAT_GRDAY_E if values.get("type") == "E" else project_default_value.MAT_GRDAY_F
        if not values.get("abc"):
            values["abc"] = "A" if values.get("type") == "E" else "B"
        if values.get("plant", "") == "":
            values["plant"] = project_default_value.MAT_PLANT
        if values.get("planner", "") == "":
            values["planner"] = project_default_value.MAT_PLANNER
        return values
    
    @model_validator(mode="after")
    def model_valid_after(self):
        return _set_raw_input_data(self)


class AcceptWorkcenter(BaseModel):
    workcenter: str = Field(..., max_length=32, description="工作中心代码", example="WC001")
    workcentername: str = Field(..., max_length=255, description="工作中心名称", example="装配车间")
    pri_wc: int = Field(1, description='优先级', example=1)
    bottleneck: str = Field(None, enum=list(gc.YES_NO.keys()), example="N", description='瓶颈')
    sortno: str = Field(None, max_length=4, description="序号", example="0001")
    plant: str = Field(project_default_value.MAT_PLANT, max_length=32, description="工厂", example="1600")
    location: str = Field(None, max_length=32, description="车间", example="A区")
    finite: str = Field("Y", enum=list(gc.YES_NO.keys()), example="N", description='有限')
    type: str = Field("Y", enum=list(gc.YES_NO.keys()), example="N", description="首页显示")
    capnum: int = Field(None, gt=0, description="默认机台数", example=6)
    capmax: int = Field(None, gt=0, description="最大机台数", example=10)
    worker: float = Field(None, ge=0, description='工时', example=8.0)
    setupno: str = Field(None, max_length=6, description='切换组别', example="S001")
    grpno: str = Field(None, max_length=6, description='同组号', example="G001")
    memo: str = Field(None, max_length=255, description="备注", example="标准工作中心")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)
    
    class Config:
        title = "验证规则 - 工作中心"
        json_schema_extra = {
            "example": {
                "workcenter": "WC001",
                "workcentername": "装配线",
                "pri_wc": 1,
                "bottleneck": "N",
                "sortno": "0001",
                "plant": project_default_value.MAT_PLANT,
                "capnum": 6,
                "capmax": 10,
                "worker": 8.0,
                "memo": "标准工作中心"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        _cache_raw_input_data(cls, values)
        if values.get("sortno") is None:
            values["sortno"] = ""
        if values.get("bottleneck") in gc.NONE_AND_EMPTY:
            values["bottleneck"] = "N"
        if values.get("location") in gc.NONE_AND_EMPTY:
            values["location"] = project_default_value.MAT_LOCATION
        if values.get("worker") in gc.NONE_AND_EMPTY:
            values["worker"] = project_default_value.WC_WORKER
        if values.get("pri_wc") in gc.NONE_AND_EMPTY:
            values["pri_wc"] = project_default_value.WC_PRIORITY
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        return _set_raw_input_data(self)



class AcceptMatWc(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    matver: str = Field(..., max_length=4, example=project_default_value.MATVER, description='产线版本')
    itemno: str = Field(None, max_length=6, description='工序项目', example="0010")
    workcenter: str = Field(..., max_length=32, description='工作中心', example="WC001")
    sortno: int = Field(..., ge=0, le=999, description='序号', example=1)
    basesec: float = Field(..., ge=0, description='节拍T/T(秒/100)', example=600)
    fixqty: int = Field(0, ge=0, description='额定量', example=100)
    fixsec: int = Field(0, ge=0, description='额定时间(秒)', example=300)
    sf: str = Field(None, enum=["S", "F"], example="F", description='并行S/串行F')
    offsetsec: int = Field(0, description='偏置+/-(秒)', example=0)
    memo: str = Field(None, max_length=255, description='备注', example="标准工序")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 工序"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "matver": project_default_value.MATVER,
                "itemno": project_default_value.ITEMNO,
                "workcenter": "WC001",
                "sortno": 1,
                "basesec": 600,
                "fixqty": 100,
                "fixsec": 300,
                "sf": "F",
                "offsetsec": 0,
                "memo": "标准工序"
            }
        }
    
    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        try:
            values["sortno"] = int(values["sortno"])
        except:
            values["sortno"] = None
        if values.get("itemno") in gc.NONE_AND_EMPTY and values["sortno"]:
            values["itemno"] = f"{project_default_value.itemno_prefix}{values['sortno']:0{project_default_value.itemno_width}d}"
        try:
            values["basesec"] = float(values["basesec"])
        except:
            values["basesec"] = None
        if values.get("sf") in gc.NONE_AND_EMPTY:
            values["sf"] = "F"
        if values.get("offsetsec") in gc.NONE_AND_EMPTY:
            values["offsetsec"] = 0
        if values.get("fixqty") in gc.NONE_AND_EMPTY:
            values["fixqty"] = 0
        if values.get("fixsec") in gc.NONE_AND_EMPTY:
            values["fixsec"] = 0
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self


class AcceptMatVer(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    matver: str = Field(..., example=project_default_value.MATVER, max_length=4, description='产线版本号')
    lotfrom: int = Field(project_default_value.MATVER_LOTFROM, description='批量起点', example=1)
    lotto: int = Field(project_default_value.MATVER_LOTTO, description='批量终点', example=9999999)
    priority: int = Field(project_default_value.MATVER_PRIORITY, description='优先级', example=1)
    refno: str = Field(None, max_length=64, description='MTO订单号/认证线', example="SO123456")
    active: str = Field("Y", enum=list(gc.YES_NO.keys()), example="Y", description='生效')
    memo: str = Field(None, max_length=255, description='备注', example="标准版本")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 产线版本"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "matver": project_default_value.MATVER,
                "lotfrom": 1,
                "lotto": 9999999,
                "priority": 1,
                "active": "Y",
                "memo": "标准版本"
            }
        }
    
    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        if values.get("lotfrom") in gc.NONE_AND_EMPTY:
            values["lotfrom"] = project_default_value.MATVER_LOTFROM
        if values.get("lotto") in gc.NONE_AND_EMPTY:
            values["lotto"] = project_default_value.MATVER_LOTTO
        if values.get("priority") in gc.NONE_AND_EMPTY:
            values["priority"] = project_default_value.MATVER_PRIORITY
        if values.get("active") in gc.NONE_AND_EMPTY:
            values["active"] = "Y"
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self



class AcceptMatWcBom(BaseModel):
    productno: str = Field(..., max_length=64, description='产品料号', example="P001")
    matver: str = Field(..., example=project_default_value.MATVER, max_length=4, description='产线版本')
    itemno: str = Field(..., max_length=6, description='工序项目', example="0010")
    materialno: str = Field(..., max_length=64, description='子件料号', example="M001")
    qty: float = Field(..., ge=0, description='数量', example=2.0)
    offsethour: int = Field(0, description='偏置+/-(小时)', example=0)
    treeno: int = Field(None, description='层级', example=1)
    mto: str = Field("N", enum=list(gc.YES_NO.keys()), example="N", description='MTO')
    scrap: float = Field(0, description='报废率%', example=0.0)
    alt: str = Field("N", enum=list(gc.YES_NO.keys()), example="N", description='Y/N是否是替代')
    memo: str = Field(None, max_length=255, description='备注', example="标准BOM组件")
    denominator: Optional[float | str] = Field(None, description='用量分母', example=1)
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)
    
    class Config:
        title = "验证规则 - BOM"
        json_schema_extra = {
            "example": {
                "productno": "P001",
                "matver": project_default_value.MATVER,
                "itemno": project_default_value.ITEMNO,
                "materialno": "M001",
                "qty": 2.0,
                "offsethour": 0,
                "treeno": 1,
                "mto": "N",
                "scrap": 0.0,
                "alt": "N",
                    "memo": "标准BOM组件"
                }
            }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        if values.get("itemno", "") == "":
            values["itemno"] = project_default_value.ITEMNO
        denominator = values.get("denominator")
        if denominator:
            try:
                values["denominator"] = float(denominator) or 1
            except:
                values["denominator"] = 1
            values["qty"] /= values["denominator"]
            values.pop("denominator") # 删除 denominator ，避免在数据库中存储
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self


class AcceptMold(BaseModel):
    moldno: str = Field(..., max_length=64, description='模具编号', example="MOLD001")
    moldname: str = Field(..., max_length=64, description='模具名称', example="测试模具A")
    type: str = Field(..., example="T1", max_length=4, description='类型')
    status: str = Field(..., max_length=6, description='状态', example="AVL")
    moldnum: int = Field(..., ge=0, description='模具穴数', example=4)
    qty: int = Field(..., ge=0, description='模具台数', example=2)
    memo: str = Field(None, max_length=255, description="备注", example="标准模具")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)
    
    class Config:
        title = "验证规则 - 模具"
        json_schema_extra = {
            "example": {
                "moldno": "MOLD001",
                "moldname": "测试模具A",
                "type": "T1",
                "status": "AVL",
                "moldnum": 4,
                "qty": 2,
                "memo": "标准模具"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self


class AcceptMatWcMold(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    workcenter: str = Field(..., max_length=64, description='工作中心', example="WC001")
    moldno: str = Field('', max_length=64, description='模具编号', example="MOLD001")
    basesec: float = Field(..., ge=0, description='节拍T/T(秒/100)', example=600)
    fixsec: int = Field(..., ge=0, description='额定时间(秒)', example=300)
    priority: int = Field(..., description='优先级', example=1)
    memo: str = Field(None, max_length=255, description='备注', example="标准机台模具配置")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 机台模具"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "workcenter": "WC001",
                "moldno": "MOLD001",
                "basesec": 600,
                "fixsec": 300,
                "priority": 1,
                "memo": "标准机台模具配置"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        try:
            values["basesec"] = int(values["basesec"])  # 数据库该字段为整形
        except:
            values["basesec"] = None
        if values.get("moldno") is None:
            values["moldno"] = ''
        return values

    @model_validator(mode="after")
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self



class AcceptSupply(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    supplyno: str = Field(..., max_length=64, description='供应单号', example="MO123456")
    matver: Optional[str] = Field(None, max_length=32, example=project_default_value.MATVER, description='产线版本')
    itemno: str = Field(None, max_length=6, description='项目号', example="0010")
    type: str = Field(..., enum=list(gc.SUPPLY_TYPE.keys()), example="MO", description='类型 PL-生产计划 MO-生产工单 ST-库存 PO-采购订单')
    category: str = Field(None, enum=list(gc.PRODUCT_CATEGORY.keys()), example="MTO", description='分类(MTO/MTS)')
    priority: int = Field(..., description='优先级', example=1)
    status: str = Field(
        None, enum=list(gc.ORDER_STATUS.keys()),
        example="NEW", description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    avail_qty: float = Field(..., ge=0, description='可用数量', example=100.0)
    create_date: Optional[str] = Field(None, description='创建日期', example="2023-01-01")
    avail_date: str = Field(..., description='可用日期 / 开工日期', example="2023-01-01")
    dt_req: str = Field(..., description='需求日期 / 完工日期', example="2023-01-07")
    avail_end_date: Optional[str] = Field(None, description='可用结束日期', example="2023-01-07")
    batchno: Optional[str] = Field(None, max_length=64, description='批次号', example="BATCH001")
    vendorno: Optional[str] = Field(None, max_length=64, description='供应商编号', example="V001")
    partnerno: Optional[str] = Field(None, max_length=64, description='合作商编号', example="P001")
    partnername: Optional[str] = Field(None, max_length=255, description='合作商名称', example="合作伙伴A")
    free1: Optional[str] = Field(None, max_length=255, description='自定义1', example="自定义内容。。。")
    free2: Optional[str] = Field(None, max_length=255, description='自定义2', example="自定义内容。。。")
    free3: Optional[str] = Field(None, max_length=255, description='自定义3', example="自定义内容。。。")
    memo: Optional[str] = Field(None, max_length=255, description='备注', example="标准供应单")
    # plno: Optional[str] = Field(None, max_length=64, description='原PL（若传入此值则将对应的PL号改写成MO号，若索引不到原PL则新增MO）', example="PL123456")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)     # 使用PrivateAttr定义一个不参与序列化和验证的私有属性来保存原始值

    class Config:
        title = "验证规则 - 供应"
        extra = "allow"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "supplyno": "MO123456",
                "matver": project_default_value.MATVER,
                "itemno": project_default_value.ITEMNO,
                "type": "MO",
                "category": "MTO",
                "priority": 1,
                "status": "NEW",
                "avail_qty": 100.0,
                "avail_date": "2025-01-01",
                "dt_req": "2025-01-07",
                "memo": "标准生产工单"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        if values.get('itemno') in gc.NONE_AND_EMPTY:
            values['itemno'] = project_default_value.ITEMNO
        return values

    @model_validator(mode='after')
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self

class ConvertPl(BaseModel):
    type: str = Field(..., example="MO", description='类型 PL-生产计划 MO-生产工单 ST-库存 PO-采购订单')
    plno: str = Field(..., max_length=64, description='PL号', example="PL123456")
    mono: str = Field(None, max_length=64, description='MO号', example="MO123456")
    status: str = Field(None, enum=list(gc.ORDER_STATUS.keys()), example="CRE", description=f'状态 {gc.ORDER_STATUS}')
    memo: str = Field(None, max_length=255, description='备注', example="标准生产工单")
    is_execute_updates: bool = Field(True, description='是否执行更新操作')

    class Config:
        title = "验证规则 - 生产计划"
        extra = "allow"
        json_schema_extra = {
            "example": {
                "type": "MO",
                "plno": "PL123456",
                "mono": "MO123456",
                "status": "CRE"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        if values.get("mono") in gc.NONE_AND_EMPTY:
            values["mono"] = values["plno"]
        if values.get("status") not in gc.ORDER_STATUS.keys():
            values["status"] = "CRE"
        return values


class DeleteSupply(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    supplyno: str = Field(..., max_length=64, description='供应单号', example="MO123456")



class AcceptDemand(BaseModel):
    materialno: str = Field(..., max_length=64, description='料号', example="M001")
    demandno: str = Field(..., max_length=64, description='需求单号', example="SO123456")
    itemno: str = Field(..., max_length=6, description='项目号（若类型为SO则可传入订单号或其他标识符，不超过6位）', example="0010")
    type: str = Field(..., enum=list(gc.DEMAND_TYPE.keys()), example="SO", description='类型 SO-销售订单 DM-计划需求 RS-工单预留 FC-预测 SS-安全库存')
    category: str = Field(..., enum=list(gc.PRODUCT_CATEGORY.keys()), example="MTO", description='分类(MTO/MTS)')
    priority: int = Field(..., description='优先级', example=1)
    workcenter: str = Field(None, max_length=32, description='工作中心', example="WC001")
    status: str = Field(..., enum=list(gc.ORDER_STATUS.keys()), example="NEW", description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    req_qty: float = Field(..., description='需求数量（须为负数，若输入正数则自动转为负数）', example=-100.0)
    req_date: datetime = Field(..., description='需求日期', example="2023-01-07T10:00:00")
    refno: Optional[str] = Field(None, max_length=64, description='MTO订单号', example="MTO123456")
    partnerno: Optional[str] = Field(None, max_length=64, description='合作商编号', example="P001")
    partnername: Optional[str] = Field(None, max_length=255, description='合作商名称', example="客户A")
    ori_qty: Optional[float] = Field(None, ge=0, description='原始需求数量', example=100.0)
    memo: Optional[str] = Field(None, max_length=255, description='备注', example="标准销售订单")
    free1: Optional[str] = Field(None, max_length=255, description='自定义字段1', example="自定义字段1")
    free2: Optional[str] = Field(None, max_length=255, description='自定义字段2', example="自定义字段2")
    free3: Optional[str] = Field(None, max_length=255, description='自定义字段3', example="自定义字段3")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 需求"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "demandno": "SO123456",
                "itemno": f"{project_default_value.itemno_prefix}{1:0{project_default_value.itemno_width}d}",
                "type": "SO",
                "category": "MTO",
                "priority": 1,
                "workcenter": "WC001",
                "status": "NEW",
                "req_qty": -100.0,
                "req_date": "2025-01-07 10:00:00",
                "refno": "MTO123456",
                "ori_qty": 100.0,
                "memo": "标准销售订单"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        try:
            req_qty = float(values.get("req_qty"))
            if req_qty > 0:
                values["req_qty"] = -1 * req_qty
        except ValueError:
            req_qty = None
        # if values.get("status") in gc.NONE_AND_EMPTY:
        #     values["status"] = "NEW"
        # if values.get("category") in gc.NONE_AND_EMPTY:
        #     values["category"] = "MTO"
        # if values.get("priority") in gc.NONE_AND_EMPTY:
        #     values["priority"] = 0
        return values

    @model_validator(mode='after')
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self


class AcceptConfirm(BaseModel):
    supplyno: str = Field(..., max_length=64, description='供应单号', example="MO123456")
    itemno: str = Field(None, max_length=6, description='工序项目', example=project_default_value.ITEMNO)
    workcenter: str = Field(None, max_length=32, description='工作中心', example="WC001")
    recordqty: float = Field(..., description='报工数量', gt=0, example=100)
    recorddt: datetime = Field(..., description='报工日期', example="2025-01-07 10:00:00")
    status: str = Field("Y", enum=list(gc.YES_NO), example="Y", description='状态')
    sysuser: str = Field(None, max_length=32, description='系统用户', example="张三")
    _raw_input_data: Dict[str, Any] = PrivateAttr(default=None)

    class Config:
        title = "验证规则 - 报工"
        json_schema_extra = {
            "example": {
                "supplyno": "MO123456",
                "itemno": project_default_value.ITEMNO,
                "workcenter": "WC001",
                "recordqty": 100.0,
                "recorddt": "2025-01-07 10:00:00",
                "status": "Y",
                "sysuser": "张三"
            }
        }

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values):
        _cache_raw_input_data(cls, values)
        # 基本验证和默认值设置
        if values.get("status") in gc.NONE_AND_EMPTY:
            values["status"] = "Y"
        if values.get("recorddt") in gc.NONE_AND_EMPTY:
            values["recorddt"] = datetime.now()
        return values

    @model_validator(mode='after')
    def model_valid_after(self):
        _set_raw_input_data(self)
        return self
