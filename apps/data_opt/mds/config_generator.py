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



# ==============================================
# 表展示配置（用于前端导航和页面渲染）
# ==============================================

DEFAULT_SORT_CONFIG = {
    "defaultSortField": "_updatetime",
    "defaultSortDir": "desc",
}

SYSTEM_RUNTIME_CONFIG = {
    "defaultPageSize": 500,         # 默认每页显示条数，数据列表首次加载时显示的记录数量
    "validateBatchSize": 200,       # 校验批次大小，批量校验时每次请求处理的记录数，影响服务器负载
    "syncBatchSize": 200,           # 同步批次大小，推送数据时每次请求处理的记录数，影响数据库写入压力
    "fkOptionsLimit": 50,           # 外键选项下拉限制，外键字段下拉框显示的最大选项数量
    "selectAllPageSize": 10000,     # 全选获取数据量，点击"全选所有页"时一次性获取的最大记录数
}

TABLE_DISPLAY_CONFIG = {
    "t_material": {
        "route": "material",
        "icon": "bi-box-seam",
        "description": "物料主数据管理，包含物料基本信息、规格、工厂等",
        "gradient": ("#0d6efd", "#6610f0"),
        "page_title": "物料数据清洗管理",
        "keyword_placeholder": "搜索物料号或描述...",
        "keyword_fields": ["MaterialNo", "Description"],
        **DEFAULT_SORT_CONFIG,
    },

    "t_workcenter": {
        "route": "workcenter",
        "icon": "bi-building-gear",
        "description": "工作中心管理，包含产能、瓶颈标识等信息",
        "gradient": ("#198754", "#20c997"),
        "page_title": "工作中心数据清洗管理",
        "keyword_placeholder": "搜索工作中心或名称...",
        "keyword_fields": ["WorkCenter", "WorkCenterName"],
        **DEFAULT_SORT_CONFIG,
    },

    "t_mat_ver": {
        "route": "mat-ver",
        "icon": "bi-tags",
        "description": "物料版本管理，定义不同生产版本的批量范围",
        "gradient": ("#fd7e14", "#ffc107"),
        "page_title": "产线版本数据清洗管理",
        "keyword_placeholder": "搜索物料号或版本号...",
        "keyword_fields": ["MaterialNo", "MatVer"],
        **DEFAULT_SORT_CONFIG,
    },

    "t_mat_wc": {
        "route": "mat-wc",
        "icon": "bi-tools",
        "description": "工艺路线管理，定义物料生产的工序流程",
        "gradient": ("#6f42c1", "#d63384"),
        "page_title": "工艺路线数据清洗管理",
        "keyword_placeholder": "搜索物料号或工作中心...",
        "keyword_fields": ["MaterialNo", "WorkCenter"],
        **DEFAULT_SORT_CONFIG,
    },

    "t_mat_wc_bom": {
        "route": "mat-wc-bom",
        "icon": "bi-diagram-3",
        "description": "物料清单管理，定义产品的组成结构和用量",
        "gradient": ("#dc3545", "#fd7e14"),
        "page_title": "BOM数据清洗管理",
        "keyword_placeholder": "搜索父件或子件料号...",
        "keyword_fields": ["ProductNo", "MaterialNo"],
        **DEFAULT_SORT_CONFIG,
    },
    "t_mold": {
        "route": "mold",
        "icon": "bi-device-ssd",
        "description": "模具主数据管理，包含模具类型、状态、穴数等",
        "gradient": ("#343a40", "#6c757d"),
        "page_title": "模具数据清洗管理",
        "keyword_placeholder": "搜索模具编号或名称...",
        "keyword_fields": ["MoldNo", "MoldName"],
        **DEFAULT_SORT_CONFIG,
    },

    "t_mat_wc_mold": {
        "route": "mat-wc-mold",
        "icon": "bi-gear-wide-connected",
        "description": "机台与模具的关联关系管理",
        "gradient": ("#0dcaf0", "#20c997"),
        "page_title": "机台模具数据清洗管理",
        "keyword_placeholder": "搜索物料号或模具编号...",
        "keyword_fields": ["MaterialNo", "MoldNo"],
        **DEFAULT_SORT_CONFIG,
    },
}


# ==============================================
# 系统公共字段（每个表都显示）
# ==============================================

SYSTEM_COMMON_COLUMNS_PREFIX = [
    {"field": "_staging_id", "title": "ID", "width": "60px", "sortable": True},
    {"field": "_status", "title": "状态", "width": "100px"},
    # {"field": "_createtime", "title": "创建时间", "width": "180px", "sortable": True},
    {"field": "_updatetime", "title": "更新时间", "width": "180px", "sortable": True},
    # {"field": "_synced_time", "title": "同步时间", "width": "180px", "sortable": True},
]

SYSTEM_COMMON_COLUMNS_SUFFIX = [
    {"field": "_source_system", "title": "来源", "width": "80px"},
]


# 自动列生成配置（从 proto_model 自动生成基础列，叠加覆盖配置）
# 启用表 = _TABLES_COLUMNS_CONFIG 的 key：业务列从 proto_model._meta.fields_map 自动生成（field + title=description，顺序=字段定义顺序）
# 结构：{"override": {字段: {列属性}}, "exclude": [隐藏字段]}
#   override：列属性覆盖（title/sortable/readOnly/width/after 等，透传至前端；after 指定 extra field 插入位置）
#   exclude：该表隐藏字段列表（显式维护，含审计字段；未来开放某审计字段从此处移除即可）
# 约定：新增审计字段（如 sys_user/sys_date/sys_stamp/vid/treeno）到某 proto_model 时，必须同步在该表 exclude 里追加，否则会直接暴露到前端列

_TABLES_COLUMNS_CONFIG = {
    "t_material": {
        "override": {
            "materialno": {"sortable": True, "readOnly": True},
            "abc": {"title": "ABC"},
        },
        "exclude": ["memo", "sys_user", "sys_date", "sys_stamp"],
    },
    "t_mat_ver": {
        "override": {
            "materialno": {"sortable": True},
            "matver": {"sortable": True},
        },
        "exclude": ["vid"],
    },
    "t_workcenter": {
        "override": {
            "workcenter": {"sortable": True, "readOnly": True},
        },
        "exclude": [],
    },
    "t_mat_wc": {
        "override": {
            "materialno": {"sortable": True},
        },
        "exclude": ["vid", "sys_stamp"],
    },
    "t_mat_wc_bom": {
        "override": {
            "productno": {"sortable": True},
            "productunit": {"title": "父件单位", "after": "productno"},
            "materialunit": {"title": "子件单位", "after": "materialno"},
        },
        "exclude": ["vid", "sys_stamp", "treeno"],
    },
    "t_mold": {
        "override": {
            "moldno": {"sortable": True, "readOnly": True},
        },
        "exclude": [],
    },
    "t_mat_wc_mold": {
        "override": {
            "materialno": {"sortable": True},
        },
        "exclude": ["vid"],
    },
}


def _generate_columns_from_proto(proto_model, table_key):
    """从 proto_model 自动生成列配置，叠加覆盖配置。

    业务列顺序 = proto_model 字段定义顺序；title = field.description（缺失则用字段名）。
    系统前缀/后缀列由 SYSTEM_COMMON_COLUMNS_PREFIX/SUFFIX 拼接。
    override：列属性覆盖；exclude：该表隐藏字段（显式维护，含审计字段）；
    override 中不在 fields_map 且未 exclude 的字段为 extra field，按 after 定位插入。
    """
    cfg = _TABLES_COLUMNS_CONFIG.get(table_key, {})
    overrides = cfg.get("override", {})
    exclude = set(cfg.get("exclude", []))
    fields_map = proto_model._meta.fields_map
    extra_by_after = {}
    extra_tail = []
    for k, v in overrides.items():
        if k in fields_map or k in exclude:
            continue
        after = v.get("after")
        if after:
            extra_by_after.setdefault(after, []).append(k)
        else:
            extra_tail.append(k)
    columns = []
    for field_name, field_obj in fields_map.items():
        if field_name in exclude:
            continue
        col = {"field": field_name, "title": field_obj.description or field_name}
        col.update(overrides.get(field_name, {}))
        columns.append(col)
        for extra_field in extra_by_after.get(field_name, []):
            eo = overrides[extra_field]
            ec = {"field": extra_field, "title": eo.get("title", extra_field)}
            ec.update({k: v for k, v in eo.items() if k != "after"})
            columns.append(ec)
    for extra_field in extra_tail:
        eo = overrides[extra_field]
        ec = {"field": extra_field, "title": eo.get("title", extra_field)}
        ec.update({k: v for k, v in eo.items() if k != "after"})
        columns.append(ec)
    return SYSTEM_COMMON_COLUMNS_PREFIX + columns + SYSTEM_COMMON_COLUMNS_SUFFIX

# 筛选字段配置
_PAGE_FILTER_CONFIG = {
    "t_material": {
        "string_fields": ["materialno", "description", "plant", "planner", "unit"],
        "number_fields": ["leadday", "expday", "grday", "price", "phantommin", "firmday", "daygap", "lotfix", "lotmin", "lotmax"]
    },
    "t_workcenter": {
        "string_fields": ["workcenter", "workcentername"],
        "number_fields": ["capnum"]
    },
    "t_mat_ver": {
        "string_fields": ["materialno", "matver"],
        "number_fields": ["lotfrom", "lotto"]
    },
    "t_mat_wc": {
        "string_fields": ["materialno", "matver", "itemno", "workcenter"],
        "number_fields": ["basesec", "sortno"]
    },
    "t_mat_wc_bom": {
        "string_fields": ["productno", "materialno", "matver", "itemno"],
        "number_fields": ["qty"]
    },
    "t_mold": {
        "string_fields": ["moldno", "moldname"],
        "number_fields": ["moldnum", "qty"]
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
    # 从页面键获取表键（通过 route 匹配）
    table_key = None
    for tk, config in TABLE_DISPLAY_CONFIG.items():
        if config["route"] == page_key:
            table_key = tk
            break
    
    if not table_key:
        return None
    
    # 从 STAGING_TABLE_CONFIG 获取配置
    from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG
    from apps.data_opt.mds._base import extract_display_name_from_model
    if table_key not in STAGING_TABLE_CONFIG:
        return None
    
    table_config = STAGING_TABLE_CONFIG[table_key]
    schema_class = table_config["schema"]
    model_class = table_config["model"]
    proto_model = table_config.get("proto_model")  # 正式表模型，用于提取业务主键
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
    if table_key in _TABLES_COLUMNS_CONFIG and proto_model:
        columns = _generate_columns_from_proto(proto_model, table_key)
    else:
        columns = []
    
    # 处理外键配置
    foreign_keys = []
    if table_config.get("foreign_keys"):
        for fk in table_config["foreign_keys"]:
            field_name = fk.get("field")
            ref_model = fk.get("model")
            
            # 获取外键字段的描述
            field_description = field_name
            if field_name in schema_class.model_fields:
                field_description = schema_class.model_fields[field_name].description or field_name
            
            # 获取引用表的显示名称
            ref_table_display_name = extract_display_name_from_model(ref_model)
            
            fk_config = {
                "field": field_name,
                "title": field_description,
                "refTable": ref_model.__name__ if ref_model else None,
                "refTableDisplayName": ref_table_display_name
            }
            # 传递 conditions 信息
            if fk.get("conditions"):
                fk_config["conditions"] = fk["conditions"]
            # 传递 value_field 和 label_field（用于单约束）
            if fk.get("value_field"):
                fk_config["value_field"] = fk["value_field"]
            if fk.get("label_field"):
                fk_config["label_field"] = fk["label_field"]
            
            foreign_keys.append(fk_config)
    
    # 获取主键字段列表（从正式表模型提取业务主键）
    from apps.data_opt.mds._base import extract_business_keys_from_model
    primary_key_fields = extract_business_keys_from_model(proto_model) if proto_model else []
    
    return {
        "tableKey": table_key,
        "tableDisplayName": display_name,
        "foreignKeys": foreign_keys,
        "primaryKeyFields": primary_key_fields,
        "runtimeConfig": SYSTEM_RUNTIME_CONFIG,
        "display": {
            "columns": columns,
            "defaultSortField": TABLE_DISPLAY_CONFIG.get(table_key, {}).get("defaultSortField", "_createtime"),
            "defaultSortDir": TABLE_DISPLAY_CONFIG.get(table_key, {}).get("defaultSortDir", "desc"),
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
