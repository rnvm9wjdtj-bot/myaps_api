from typing import Literal#, List, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator#, ValidationError

from config import forcustomer as fc
# from .common import format_validation_error

# 

class MaterialInput(BaseModel):
    materialno: str = Field(..., alias=fc.t_material.get("materialno", "materialno"), description="料号")
    description: str = Field(..., alias=fc.t_material.get("description", "description"), description="物料名称")
    size: str = Field(None, alias=fc.t_material.get("size", "size"), description="规格")
    plant: str = Field(fc.default_plant, alias=fc.t_material.get("plant", "plant"), description='工厂')
    planner: str = Field(fc.default_planner, alias=fc.t_material.get("planner", "planner"), description="计划员")
    fifo: int = Field(fc.default_fifo, alias=fc.t_material.get("fifo", "fifo"), ge=0, le=1, description='1-FIFO ,0-最近原则')
    leadday: int = Field(alias=fc.t_material.get("leadday", "leadday"), ge=0, description="交期（天）")
    expday: int = Field(alias=fc.t_material.get("expday", "expday"), ge=0, description="保质期（天）")
    grday: int = Field(alias=fc.t_material.get("grday", "grday"), ge=0, description="收货质检（天）")
    abc: Literal["A", "B", "C"] = Field(alias=fc.t_material.get("abc", "abc"), description="ABC分类")
    unit: str = Field(alias=fc.t_material.get("unit", "unit"), description='单位')
    price: Decimal = Field(alias=fc.t_material.get("price", "price"), description="价格")
    groupno: str = Field(alias=fc.t_material.get("groupno", "groupno"), description="型号")
    type: Literal["E", "F"] = Field(... if fc.myaps_is_pro else None, alias=fc.t_material.get("type", "type"), description="物料类型  E-自制件 F-采购件")
    phantom: Literal["N", "Y"] = Field(alias=fc.t_material.get("phantom", "phantom"), description='虚拟件')
    phantommin: int = Field(..., alias=fc.t_material.get("phantommin", "phantommin"), ge=0, description='虚拟时间(Minute)')
    firmday: int = Field(alias=fc.t_material.get("firmday", "firmday"), ge=0, description="固定天数")
    daygap: int = Field(alias=fc.t_material.get("daygap", "daygap"), ge=0, description='MTO拆分天数')
    candelay: Literal["N", "Y"] = Field(alias=fc.t_material.get("candelay", "candelay"), description='可否延迟')
    lotsize: Literal["EX", "FX", "D1", "D2", "D3", "D4", "D5", "D6", "W1", "W2", "W3", "W4", "M1", "M2", "VB"] = Field(alias=fc.t_material.get("lotsize", "lotsize"), max_length=2, description='批量')
    lotfix: float = Field(alias=fc.t_material.get("lotfix", "lotfix"), ge=0, description='固定批')
    lotmin: float = Field(alias=fc.t_material.get("lotmin", "lotmin"), ge=0, description='最小批')
    lotmax: float = Field(alias=fc.t_material.get("lotmax", "lotmax"), ge=0, description='最大批')
    lotround: float = Field(alias=fc.t_material.get("lotround", "lotround"), ge=0, description='取整')
    lotss: float = Field(alias=fc.t_material.get("lotss", "lotss"), ge=0, description='安全库存')
    lotpoint: float = Field(alias=fc.t_material.get("lotpoint", "lotpoint"), ge=0, description='重订货点')
    lottop: float = Field(alias=fc.t_material.get("lottop", "lottop"), ge=0, description='最大库存点')
    planitem: str = Field(alias=fc.t_material.get("planitem", "planitem"), description='产品组')
    preday: int = Field(alias=fc.t_material.get("preday", "preday"), ge=0, description='向前冲销(天)')
    subday: int = Field(alias=fc.t_material.get("subday", "subday"), ge=0, description='向后冲销(天)')
    memo: str = Field(None,alias=fc.t_material.get("memo", "memo"),  description='备注')
    # free1: str = Field(alias='Free1', max_length=255)
    # free2: str = Field(alias='Free2', max_length=255)
    # free3: str = Field(alias='Free3', max_length=255)
    
    @field_validator("leadday")
    def leadday_valid(cls, v, values):
        if v is None:
            v = fc.default_leadday_e if values.get("type") == "E" else fc.default_leadday_f
        return v

    @field_validator("abc")
    def abc_valid(cls, v, values):
        if v is None:
            v = "A" if values.get("type") == "E" else "B"
        return v

    class Config:
        title = "验证规则 - 物料"
        


class WorkcenterInput(BaseModel):
    workcenter: str = Field(..., alias=fc.t_workcenter.get("workcenter", "workcenter"), max_length=32, description="工作中心代码")
    workcentername: str = Field(..., alias=fc.t_workcenter.get("workcentername", "workcentername"), max_length=255, description="工作中心名称")
    pri_wc: int = Field(None, alias=fc.t_workcenter.get("pri_wc", "pri_wc"), description='优先级')
    bottleneck: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("bottleneck", "bottleneck"), max_length=1, description='瓶颈')
    sortno: str = Field(None, alias=fc.t_workcenter.get("sortno", "sortno"), max_length=4, description="序号")
    plant: str = Field(None, alias=fc.t_workcenter.get("plant", "plant"), max_length=32, description="工厂")
    location: str = Field(None, alias=fc.t_workcenter.get("location", "location"), max_length=32, description="车间")
    finite: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("finite", "finite"), max_length=1, description='有限')
    type: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("type", "type"), max_length=32, description="首页显示")
    capnum: int = Field(None, alias=fc.t_workcenter.get("capnum", "capnum"), gt=0, description="默认机台数")
    capmax: int = Field(None, alias=fc.t_workcenter.get("capmax", "capmax"), gt=0, description="最大机台数")
    worker: float = Field(None, alias=fc.t_workcenter.get("worker", "worker"), ge=0, description='工时')
    setupno: str = Field(None, alias=fc.t_workcenter.get("setupno", "setupno"), max_length=6, description='切换组别')
    grpno: str = Field(None, alias=fc.t_workcenter.get("grpno", "grpno"), max_length=6, description='同组号')
    memo: str = Field(None, alias=fc.t_workcenter.get("memo", "memo"), max_length=255, description="备注")
    
    class Config:
        title = "验证规则 - 工作中心"


class MatWcInput(BaseModel):
    materialno: str = Field(..., alias=fc.t_mat_wc.get("materialno", "materialno"), max_length=64, description='料号')
    matver: str = Field(..., alias=fc.t_mat_wc.get("matver", "matver"), max_length=4, description='产线版本')
    itemno: str = Field(..., alias=fc.t_mat_wc.get("itemno", "itemno"), max_length=6, description='工序项目')
    workcenter: str = Field(..., alias=fc.t_mat_wc.get("workcenter", "workcenter"), max_length=32, description='工作中心')
    sortno: int = Field(..., alias=fc.t_mat_wc.get("sortno", "sortno"), ge=0, description='序号')
    basesec: int = Field(..., alias=fc.t_mat_wc.get("basesec", "basesec"), ge=0, description='节拍T/T(秒/100)')
    fixqty: int = Field(..., alias=fc.t_mat_wc.get("fixqty", "fixqty"), ge=0, description='额定量')
    fixsec: int = Field(..., alias=fc.t_mat_wc.get("fixsec", "fixsec"), ge=0, description='额定时间(秒)')
    sf: Literal["S", "F"] = Field(..., alias=fc.t_mat_wc.get("sf", "sf"), max_length=1, description='并行S/串行F')
    offsetsec: int = Field(..., alias=fc.t_mat_wc.get("offsetsec", "offsetsec"), ge=0, description='偏置+/-(秒)')
    memo: str = Field(None, alias=fc.t_mat_wc.get("memo", "memo"), max_length=255, description='备注')

    class Config:
        title = "验证规则 - 工序"


class MatVerInput(BaseModel):
    materialno: str = Field(alias='MaterialNo', max_length=64)
    matver: str = Field(alias='MatVer', max_length=4)
    lotfrom: int = Field(alias='LotFrom', description='')
    lotto: int = Field(alias='LotTo', description='')
    priority: int = Field(alias='Priority', description='')
    refno: str = Field(alias='RefNo', max_length=64, description='')
    active: str = Field(alias='Active', max_length=1, description='')
    memo: str = Field(None, alias='Memo', max_length=255, description='')

    class Config:
        title = "验证规则 - 产线版本"


class MatWcBomInput(BaseModel):
    productno: str = Field(alias='ProductNo', max_length=64, description='')
    matver: str = Field(alias='MatVer', max_length=4, description='')
    itemno: str = Field(alias='ItemNo', max_length=6, description='')
    materialno: str = Field(alias='MaterialNo', max_length=64, description='')
    qty: float = Field(alias='Qty', description='')
    offsethour: int = Field(alias='OffsetHour', description='')
    treeno: int = Field(alias='TreeNo', description='')
    mto: str = Field(alias='MTO', max_length=1, description='Y/N')
    scrap: float = Field(alias='Scrap', description='%')
    alt: str = Field(alias='Alt', max_length=1, description='Y/N是否是替代')
    memo: str = Field(None, alias='Memo', max_length=255)

    class Config:
        title = "验证规则 - BOM"