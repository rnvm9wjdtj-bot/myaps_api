"""
全局常量
"""
from enum import Enum


NONE_AND_EMPTY = {None, ""}


class YesNoEnum(str, Enum):
    YES = "Y"
    NO = "N"

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


class ProductCategoryEnum(str, Enum):
    MTO = "MTO"   # MTO
    MTS = "MTS"   # MTS


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


class EfEnum(str, Enum):
    E = "E"
    F = "F"


class SfEnum(str, Enum):
    S = "S"
    F = "F"


class OtherEnum(Enum):
    RELEASE_SUCCESS = "✅"
    RELEASE_FAILED = "🚫"
    ASSERT_CONNECTION = "未获得连接对象，请先注册"
    MERGE_ENTRIY_KEY = "_entries_"



# LOT_SIZE = {
#     "EX": "一对一",
#     "FX": "固定批",
#     "VB": "重订货点",
#     "D1": "按1天合并",
#     "D2": "按2天合并",
#     "D3": "按3天合并",
#     "D4": "按4天合并",
#     "D5": "按5天合并",
#     "D6": "按6天合并",
#     "W1": "按1周合并",
#     "W2": "按2周合并",
#     "W3": "按3周合并",
#     "W4": "按4周合并",
#     "M1": "按1月合并",
#     "M2": "按2月合并",
#     "M3": "按3月合并",
# }


# SUPPLY_TYPE = {
#     'PL': '计划单',
#     'MO': '生产工单',
#     'PR': '采购申请',
#     'PO': '采购订单',
#     'ST': '库存',
# }

# DEMAND_TYPE = {
#     "SO": "销售订单",
#     "DM": "计划需求",
#     "RS": "工单预留",
#     "FC": "预测",
#     "SS": "安全库存",
# }

# 单据状态
# ORDER_STATUS = {
#     'NEW': '新建',
#     'CRE': '未排',
#     'SCH': '已排',
#     'REL': '释放',
#     'CNF': '报工',
#     'CMP': '已完成',
# }

