from typing import Literal
from enum import Enum
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

from config import forcustomer as fc


class NyEnum(str, Enum):
    N = "N"
    Y = "Y"

class MaterialSchema(BaseModel):
    class LotsizeEnum(str, Enum):
        EX = "EX"
        FX = "FX"
        D1 = "D1"
        D2 = "D2"
        D3 = "D3"
        D4 = "D4"
        D5 = "D5"
        D6 = "D6"
        W1 = "W1"
        W2 = "W2"
        W3 = "W3"
        W4 = "W4"
        M1 = "M1"
        M2 = "M2"
        VB = "VB"

    materialno: str = Field(..., alias=fc.material_map.get("materialno", "materialno"), description="料号")
    description: str = Field(..., alias=fc.material_map.get("description", "description"), description="物料名称")
    size: str = Field(None, alias=fc.material_map.get("size", "size"), description="规格")
    plant: str = Field(fc.default_plant, alias=fc.material_map.get("plant", "plant"), description='工厂')
    planner: str = Field(fc.default_planner, alias=fc.material_map.get("planner", "planner"), description="计划员")
    fifo: int = Field(fc.default_fifo, alias=fc.material_map.get("fifo", "fifo"), ge=0, le=1, description='1-FIFO ,0-最近原则')
    leadday: int = Field(alias=fc.material_map.get("leadday", "leadday"), ge=0, description="交期（天）")
    expday: int = Field(alias=fc.material_map.get("expday", "expday"), ge=0, description="保质期（天）")
    grday: int = Field(alias=fc.material_map.get("grday", "grday"), ge=0, description="收货质检（天）")
    abc: Literal["A", "B", "C"] = Field(alias=fc.material_map.get("abc", "abc"), description="ABC分类")
    unit: str = Field(alias=fc.material_map.get("unit", "unit"), description='单位')
    price: Decimal = Field(alias=fc.material_map.get("price", "price"), description="价格")
    groupno: str = Field(alias=fc.material_map.get("groupno", "groupno"), description="型号")
    type: Literal["E", "F"] = Field(... if fc.myaps_is_pro else None, alias=fc.material_map.get("type", "type"), description="物料类型  E-自制件 F-采购件")
    phantom: NyEnum = Field(alias=fc.material_map.get("phantom", "phantom"), description='虚拟件')
    phantommin: int = Field(..., alias=fc.material_map.get("phantommin", "phantommin"), ge=0, description='虚拟时间(Minute)')
    firmday: int = Field(alias=fc.material_map.get("firmday", "firmday"), ge=0, description="固定天数")
    daygap: int = Field(alias=fc.material_map.get("daygap", "daygap"), ge=0, description='MTO拆分天数')
    candelay: NyEnum = Field(alias=fc.material_map.get("candelay", "candelay"), description='可否延迟')
    lotsize: LotsizeEnum = Field(alias=fc.material_map.get("lotsize", "lotsize"), max_length=2, description='批量')
    lotfix: float = Field(alias=fc.material_map.get("lotfix", "lotfix"), ge=0, description='固定批')
    lotmin: float = Field(alias=fc.material_map.get("lotmin", "lotmin"), ge=0, description='最小批')
    lotmax: float = Field(alias=fc.material_map.get("lotmax", "lotmax"), ge=0, description='最大批')
    lotround: float = Field(alias=fc.material_map.get("lotround", "lotround"), ge=0, description='取整')
    lotss: float = Field(alias=fc.material_map.get("lotss", "lotss"), ge=0, description='安全库存')
    lotpoint: float = Field(alias=fc.material_map.get("lotpoint", "lotpoint"), ge=0, description='重订货点')
    lottop: float = Field(alias=fc.material_map.get("lottop", "lottop"), ge=0, description='最大库存点')
    planitem: str = Field(alias=fc.material_map.get("planitem", "planitem"), description='产品组')
    preday: int = Field(alias=fc.material_map.get("preday", "preday"), ge=0, description='向前冲销(天)')
    subday: int = Field(alias=fc.material_map.get("subday", "subday"), ge=0, description='向后冲销(天)')
    memo: str = Field(None,alias=fc.material_map.get("memo", "memo"),  description='备注')
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