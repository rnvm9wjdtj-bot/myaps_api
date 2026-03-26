"""
以下模型适用于 清洗转换 从 ERP 获取的数据用于向HAP发送
需要客户在HAP中填写的字段统一设为 Optional[str/int/...] = Field(None)。
在 @model_validator 中需要将：
无法通过处理原生数据获取的联合索引字段设为  "🈳❗"  占位，以保证能构成完整的联合索引
"""


from ._base import (
    logger,
    DataProcessor, globalconst,
    BaseConnection, convert_timeunit, clean_value, #reset_default_values,
    BaseModel as PydanticModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold
)