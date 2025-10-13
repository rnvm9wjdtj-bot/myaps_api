myaps_is_pro = True     # myaps是否专业版

# 主数据默认值
# 物料
default_plant = "1600"   # 默认工厂
default_planner = "haida"   # 默认计划员
default_fifo = 1   # 默认FIFO原则
default_leadday_e = 10  # 自制件默认提前期
default_leadday_f = 1  # 采购件默认提前期


# 前后端字段映射关系，某些客户可能需要
#  {model字段: 客户字段}
material_map = {
    "materialno": "materialno",
    "description": "description",
    "size": "size",
    "unit": "unit",
    "price": "price",
    "remark": "remark",
}