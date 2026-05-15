"""
MDS 页面配置生成器
阶段三：从 Schema 自动生成 stringFields 和 numberFields
"""
import json
from typing import Dict, Any, Optional, List, Union, get_origin, get_args
from enum import Enum
import inspect
from decimal import Decimal


def to_big_camel(s: str) -> str:
    """小驼峰转大驼峰"""
    return ''.join(word.capitalize() for word in s.split('_'))


def get_field_type(annotation) -> Optional[type]:
    """获取字段的实际类型（处理 Optional 等包装类型）"""
    origin = get_origin(annotation)
    
    if origin is Union:
        args = get_args(annotation)
        for arg in args:
            if arg is not type(None):
                return get_field_type(arg)
    
    return annotation


def get_enum_options_from_schema(schema_class, field_name: str) -> Optional[List[Dict[str, str]]]:
    """
    从 Schema 字段中获取枚举选项
    优先使用 Enum 类的 get_options() 方法
    """
    if field_name not in schema_class.model_fields:
        return None
    
    field_info = schema_class.model_fields[field_name]
    annotation = field_info.annotation
    
    # 获取实际的 Enum 类型
    field_type = get_field_type(annotation)
    
    # 检查是否有 get_options() 方法
    if hasattr(field_type, 'get_options') and callable(getattr(field_type, 'get_options')):
        return field_type.get_options()
    
    return None


def get_enum_label_map(schema_class, field_name: str) -> Optional[Dict[Any, str]]:
    """
    从 Schema 中获取枚举字段的标签映射
    优先从 Enum 类的 get_options() 获取，fallback 到手动映射
    """
    # 尝试从 Enum 类直接获取
    options = get_enum_options_from_schema(schema_class, field_name)
    if options:
        label_map = {}
        for opt in options:
            label_map[opt['value']] = opt['label']
        return label_map
    
    # 手动映射（作为 fallback，主要用于 fifo 等非 Enum 字段）
    MANUAL_LABEL_MAPS = {
        "fifo": {
            "0": "最近原则",
            "1": "FIFO"
        }
    }
    
    return MANUAL_LABEL_MAPS.get(field_name)


def auto_generate_enum_fields(schema_class) -> List[Dict[str, Any]]:
    """
    从 Schema 自动生成 enumFields 配置
    额外处理特殊字段（如 fifo，它是 int 但在筛选中表现为 enum）
    """
    from apps.data_opt.mds._base import extract_enum_fields
    
    enum_fields_data = extract_enum_fields(schema_class)
    enum_fields = []
    
    for field_name, (description, enum_values) in enum_fields_data.items():
        # 优先从 Enum 类的 get_options() 直接获取选项
        options = get_enum_options_from_schema(schema_class, field_name)
        
        # 如果没有，fallback 到 label_map 方式
        if not options:
            label_map = get_enum_label_map(schema_class, field_name)
            options = []
            for value in sorted(enum_values):
                label = label_map.get(str(value), str(value)) if label_map else str(value)
                options.append({"value": str(value), "label": label})
        
        enum_fields.append({
            "value": to_big_camel(field_name),
            "label": description,
            "options": options
        })
    
    # 额外添加 fifo 字段（它是 int 但在筛选中表现为 enum）
    fifo_field_info = schema_class.model_fields.get("fifo")
    if fifo_field_info:
        fifo_label_map = get_enum_label_map(schema_class, "fifo")
        if fifo_label_map:
            fifo_options = []
            for value, label in fifo_label_map.items():
                fifo_options.append({"value": value, "label": label})
            
            enum_fields.append({
                "value": "FIFO",
                "label": fifo_field_info.description or "FIFO",
                "options": fifo_options
            })
    
    return enum_fields


def auto_generate_filter_categories_from_extraction(
    schema_class, 
    model_class, 
    string_field_names: Optional[List[str]] = None, 
    number_field_names: Optional[List[str]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    从 Schema 和 Model 提取完整的字段信息，自动生成筛选分类配置
    使用 extract_all_fields 作为基础
    
    Args:
        schema_class: Pydantic Schema 类
        model_class: Tortoise Model 类
        string_field_names: 可选的 string 字段名称列表（用于筛选）
        number_field_names: 可选的 number 字段名称列表（用于筛选）
    
    Returns:
        筛选分类配置字典
    """
    from apps.data_opt.mds._base import extract_all_fields
    
    # 提取完整的字段信息
    all_fields = extract_all_fields(schema_class, model_class)
    
    # 自动分类
    string_fields = []
    number_fields = []
    
    for field_meta in all_fields:
        field_name = field_meta['field']
        title = field_meta['title']
        data_type = field_meta['data_type']
        
        # 如果是 enum，由 enumFields 处理
        if data_type == 'enum':
            continue
        
        # 根据字段类型分类
        if data_type == 'string':
            # 如果指定了字段列表，只包含指定的字段
            if string_field_names is None or field_name in string_field_names:
                string_fields.append({
                    "value": to_big_camel(field_name),
                    "label": title
                })
        elif data_type == 'number':
            # 如果指定了字段列表，只包含指定的字段
            if number_field_names is None or field_name in number_field_names:
                number_fields.append({
                    "value": to_big_camel(field_name),
                    "label": title
                })
    
    return {
        "stringFields": string_fields,
        "numberFields": number_fields,
        "enumFields": auto_generate_enum_fields(schema_class)
    }



# 页面键到表键的映射
_PAGE_KEY_TO_TABLE_KEY = {
    "material": "t_material",
    "workcenter": "t_workcenter",
    "mat-ver": "t_mat_ver",
    "mat-wc": "t_mat_wc",
    "mat-wc-bom": "t_mat_wc_bom",
    "mold": "t_mold",
    "mat-wc-mold": "t_mat_wc_mold"
}

# 前端配置（列配置等）
# TODO: 可以进一步优化，从模型中提取更多信息
_PAGE_COLUMNS_CONFIG = {
    "t_material": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "materialno", "title": "物料号", "width": "100px", "sortable": True, "readOnly": True},
        {"field": "description", "title": "物料描述", "width": "150px"},
        {"field": "size", "title": "规格"},
        {"field": "plant", "title": "工厂", "width": "70px"},
        {"field": "planner", "title": "计划员"},
        {"field": "fifo", "title": "FIFO", "width": "50px"},
        {"field": "leadday", "title": "提前期", "width": "60px"},
        {"field": "expday", "title": "保质期", "width": "60px"},
        {"field": "grday", "title": "质检期", "width": "60px"},
        {"field": "abc", "title": "ABC", "width": "50px"},
        {"field": "unit", "title": "单位", "width": "50px"},
        {"field": "price", "title": "价格", "width": "80px"},
        {"field": "groupno", "title": "型号"},
        {"field": "type", "title": "类型", "width": "50px"},
        {"field": "phantom", "title": "虚拟件", "width": "60px"},
        {"field": "phantommin", "title": "虚拟时间", "width": "70px"},
        {"field": "firmday", "title": "固定天数", "width": "60px"},
        {"field": "daygap", "title": "拆分天数", "width": "60px"},
        {"field": "candelay", "title": "可延迟", "width": "60px"},
        {"field": "lotsize", "title": "批量策略", "width": "70px"},
        {"field": "lotfix", "title": "固定批", "width": "60px"},
        {"field": "lotmin", "title": "最小批", "width": "60px"},
        {"field": "lotmax", "title": "最大批", "width": "60px"},
        {"field": "lotround", "title": "取整值", "width": "60px"},
        {"field": "lotss", "title": "安全库存", "width": "60px"},
        {"field": "lotpoint", "title": "订货点", "width": "60px"},
        {"field": "lottop", "title": "最大库存", "width": "60px"},
        {"field": "planitem", "title": "产品组"},
        {"field": "preday", "title": "向前冲销", "width": "60px"},
        {"field": "subday", "title": "向后冲销", "width": "60px"},
        {"field": "free1", "title": "自定义1"},
        {"field": "free2", "title": "自定义2"},
        {"field": "free3", "title": "自定义3"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_workcenter": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "workcenter", "title": "工作中心", "width": "120px", "sortable": True, "readOnly": True},
        {"field": "description", "title": "描述", "width": "200px"},
        {"field": "bottleneck", "title": "瓶颈", "width": "80px"},
        {"field": "finite", "title": "有限产能", "width": "100px"},
        {"field": "capacity", "title": "产能", "width": "100px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_mat_ver": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "materialno", "title": "物料号", "width": "120px", "sortable": True, "readOnly": True},
        {"field": "matver", "title": "版本号", "width": "80px", "sortable": True},
        {"field": "description", "title": "描述", "width": "200px"},
        {"field": "active", "title": "激活", "width": "80px"},
        {"field": "lotfrom", "title": "批量下限", "width": "100px"},
        {"field": "lotto", "title": "批量上限", "width": "100px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_mat_wc": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "materialno", "title": "物料号", "width": "120px", "sortable": True, "readOnly": True},
        {"field": "matver", "title": "版本号", "width": "80px"},
        {"field": "itemno", "title": "工序号", "width": "80px"},
        {"field": "workcenter", "title": "工作中心", "width": "100px"},
        {"field": "sf", "title": "串并行", "width": "80px"},
        {"field": "basesec", "title": "基础工时", "width": "100px"},
        {"field": "sortno", "title": "排序", "width": "80px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_mat_wc_bom": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "productno", "title": "父件号", "width": "100px", "readOnly": True},
        {"field": "matver", "title": "版本号", "width": "80px"},
        {"field": "itemno", "title": "工序号", "width": "80px"},
        {"field": "materialno", "title": "子件号", "width": "100px"},
        {"field": "workcenter", "title": "工作中心", "width": "100px"},
        {"field": "qty", "title": "用量", "width": "80px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_mold": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "moldno", "title": "模具号", "width": "120px", "sortable": True, "readOnly": True},
        {"field": "description", "title": "描述", "width": "200px"},
        {"field": "cavity", "title": "穴数", "width": "80px"},
        {"field": "count", "title": "台数", "width": "80px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ],
    "t_mat_wc_mold": [
        {"field": "_status", "title": "状态", "width": "80px", "readOnly": True},
        {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True, "readOnly": True},
        {"field": "materialno", "title": "物料号", "width": "100px", "readOnly": True},
        {"field": "workcenter", "title": "工作中心", "width": "100px"},
        {"field": "itemno", "title": "工序号", "width": "80px"},
        {"field": "moldno", "title": "模具号", "width": "100px"},
        {"field": "_source_system", "title": "来源", "width": "80px", "readOnly": True}
    ]
}

# 筛选字段配置
_PAGE_FILTER_CONFIG = {
    "t_material": {
        "string_fields": ["materialno", "description", "plant", "planner", "unit"],
        "number_fields": ["leadday", "expday", "grday", "price", "phantommin", "firmday", "daygap", "lotfix", "lotmin", "lotmax"]
    },
    "t_workcenter": {
        "string_fields": ["workcenter", "description"],
        "number_fields": ["capacity"]
    },
    "t_mat_ver": {
        "string_fields": ["materialno", "matver", "description"],
        "number_fields": ["lotfrom", "lotto"]
    },
    "t_mat_wc": {
        "string_fields": ["materialno", "matver", "itemno", "workcenter"],
        "number_fields": ["basesec", "sortno"]
    },
    "t_mat_wc_bom": {
        "string_fields": ["productno", "materialno", "workcenter", "matver", "itemno"],
        "number_fields": ["qty"]
    },
    "t_mold": {
        "string_fields": ["moldno", "description"],
        "number_fields": ["cavity", "count"]
    },
    "t_mat_wc_mold": {
        "string_fields": ["materialno", "workcenter", "itemno", "moldno"],
        "number_fields": []
    }
}

# 配置缓存
_config_cache = {}


def generate_generic_page_config(page_key: str) -> Optional[Dict[str, Any]]:
    """
    通用的页面配置生成函数
    
    Args:
        page_key: 页面键（如 "material", "workcenter"）
    
    Returns:
        页面配置字典，如果不支持该页面则返回 None
    """
    # 从页面键获取表键
    table_key = _PAGE_KEY_TO_TABLE_KEY.get(page_key)
    if not table_key:
        return None
    
    # 从 STAGING_TABLE_CONFIG 获取配置
    from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG
    if table_key not in STAGING_TABLE_CONFIG:
        return None
    
    table_config = STAGING_TABLE_CONFIG[table_key]
    schema_class = table_config["schema"]
    model_class = table_config["model"]
    display_name = table_config["display_name"]
    
    # 获取筛选配置
    filter_config = _PAGE_FILTER_CONFIG.get(table_key, {})
    string_fields = filter_config.get("string_fields")
    number_fields = filter_config.get("number_fields")
    
    # 生成筛选分类
    advanced_filter_categories = auto_generate_filter_categories_from_extraction(
        schema_class,
        model_class,
        string_fields,
        number_fields
    )
    
    # 获取列配置
    columns = _PAGE_COLUMNS_CONFIG.get(table_key, [])
    
    return {
        "tableKey": table_key,
        "tableDisplayName": display_name,
        "display": {
            "columns": columns,
            "defaultSortField": "_createtime",
            "defaultSortDir": "desc",
            "advancedFilterCategories": advanced_filter_categories
        }
    }


def get_cached_config(page_key: str) -> Dict[str, Any]:
    """获取缓存的配置"""
    if page_key not in _config_cache:
        _config_cache[page_key] = generate_generic_page_config(page_key)
    return _config_cache.get(page_key)


def clear_config_cache():
    """清除配置缓存（用于开发调试）"""
    _config_cache.clear()
