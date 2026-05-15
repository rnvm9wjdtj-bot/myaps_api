"""
全局常量
"""
from enum import Enum


NONE_AND_EMPTY = {None, ""}


class YesNoEnum(str, Enum):
    YES = "Y"
    NO = "N"
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "Y", "label": "是(Y)"},
            {"value": "N", "label": "否(N)"}
        ]


class LotSizeEnum(str, Enum):
    EX = "EX"   # 一对一
    FX = "FX"   # 固定批
    VB = "VB"   # 重订货点
    D1 = "D1"   # 按1天合并
    D2 = "D2"   # 按2天合并
    D3 = "D3"   # 按3天合并
    D4 = "D4"   # 按4天合并
    D5 = "D5"   # 按5天合并
    D6 = "D6"   # 按6天合并
    W1 = "W1"   # 按1周合并
    W2 = "W2"   # 按2周合并
    W3 = "W3"   # 按3周合并
    W4 = "W4"   # 按4周合并
    M1 = "M1"   # 按1月合并
    M2 = "M2"   # 按2月合并
    M3 = "M3"   # 按3月合并
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "EX", "label": "一对一(EX)"},
            {"value": "FX", "label": "固定批(FX)"},
            {"value": "VB", "label": "重订货点(VB)"},
            {"value": "D1", "label": "按1天合并(D1)"},
            {"value": "D2", "label": "按2天合并(D2)"},
            {"value": "D3", "label": "按3天合并(D3)"},
            {"value": "D4", "label": "按4天合并(D4)"},
            {"value": "D5", "label": "按5天合并(D5)"},
            {"value": "D6", "label": "按6天合并(D6)"},
            {"value": "W1", "label": "按1周合并(W1)"},
            {"value": "W2", "label": "按2周合并(W2)"},
            {"value": "W3", "label": "按3周合并(W3)"},
            {"value": "W4", "label": "按4周合并(W4)"},
            {"value": "M1", "label": "按1月合并(M1)"},
            {"value": "M2", "label": "按2月合并(M2)"},
            {"value": "M3", "label": "按3月合并(M3)"}
        ]


class ProductCategoryEnum(str, Enum):
    MTO = "MTO"   # MTO
    MTS = "MTS"   # MTS
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "MTO", "label": "按订单生产(MTO)"},
            {"value": "MTS", "label": "按库存生产(MTS)"}
        ]


class SupplyTypeEnum(str, Enum):
    PL = "PL"   # 计划单
    MO = "MO"   # 生产工单
    PR = "PR"   # 采购申请
    PO = "PO"   # 采购订单
    ST = "ST"   # 库存


class DemandTypeEnum(str, Enum):
    SO = "SO"   # 销售订单
    DM = "DM"   # 计划需求
    RS = "RS"   # 工单预留
    FC = "FC"   # 预测
    SS = "SS"   # 安全库存


class OrderStatusEnum(str, Enum):
    NEW = "NEW"   # 新建
    CRE = "CRE"   # 未排
    SCH = "SCH"   # 已排
    REL = "REL"   # 释放
    CNF = "CNF"   # 报工
    CMP = "CMP"   # 已完成
    A2E = "A2E"   
    E2A = "E2A"   


class AbcEnum(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "A", "label": "A类"},
            {"value": "B", "label": "B类"},
            {"value": "C", "label": "C类"}
        ]


class EfEnum(str, Enum):
    E = "E"
    F = "F"
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "E", "label": "自制件(E)"},
            {"value": "F", "label": "采购件(F)"}
        ]


class SfEnum(str, Enum):
    S = "S"
    F = "F"
    
    @classmethod
    def get_options(cls):
        return [
            {"value": "S", "label": "S"},
            {"value": "F", "label": "F"}
        ]


class StaticString(str, Enum):
    RELEASE_SUCCESS = "✅"
    RELEASE_FAILED = "🚫"
    ASSERT_CONNECTION = "未获得连接对象，请先注册"
    MERGE_ENTRIY_KEY = "_entries_"
    AUTH_AT = "_auth_at_"

