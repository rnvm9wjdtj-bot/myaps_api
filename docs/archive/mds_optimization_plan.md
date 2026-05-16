# MDS 模块优化计划

> **状态**：✅ 已完成（2026-05-16）
> **版本**：v1.1
> **日期**：2026-05-16
> **目标**：渐进式优化，低风险，不破坏现有功能
> **修订说明**：v1.1 针对兼容性风险、验证可执行性、依赖关系等问题进行修订
>
> **完成摘要**：所有四阶段目标已实现，并额外解决了 datetime 时区问题。

---

## 一、总体策略

### 核心原则

1. **向后兼容**：每个阶段都保留旧方式作为 fallback
2. **渐进式改造**：不强求一次性全部迁移
3. **功能等价**：优化不改变现有功能
4. **可回滚**：每个阶段都可独立回滚
5. **最小变更**：充分利用现有架构，尽可能不新增文件

### 前置条件

**在开始任何阶段前，必须完成：**
- [ ] 代码仓库处于干净状态（无未提交的修改）
- [ ] 已创建功能分支：`git checkout -b feature/mds-optimization`
- [ ] 数据库已备份

---

## 二、阶段一：状态元数据统一（最优先，低风险）

### 2.1 目标

消除前后端状态定义重复，状态从后端统一管理

### 2.2 前置验证

**在修改代码前，先创建兼容性测试脚本：**

**文件**：`tests/test_staging_status_compat.py`（临时测试文件，阶段完成后可删除）

```python
"""
StagingStatus 枚举兼容性测试
确保枚举改造后所有现有用法仍然有效
"""
import pytest
from apps.data_opt.mds._base import StagingStatus

class TestStagingStatusCompatibility:
    """测试现有代码对所有 StagingStatus 用法的兼容性"""
    
    def test_value_access(self):
        """测试 .value 访问"""
        assert StagingStatus.PENDING.value == "pending"
        assert StagingStatus.COMPLIANCE_PASS.value == "compliance_pass"
        assert StagingStatus.SYNCED.value == "synced"
    
    def test_string_conversion(self):
        """测试字符串转换"""
        assert str(StagingStatus.PENDING) == "pending"
        assert str(StagingStatus.SYNCED) == "synced"
    
    def test_equality_comparison(self):
        """测试相等比较"""
        assert StagingStatus.PENDING == "pending"
        assert StagingStatus.PENDING != "synced"
    
    def test_filter_usage(self):
        """测试 ORM filter 用法模拟"""
        status_value = StagingStatus.PENDING.value
        assert status_value == "pending"
        # 模拟 filter(_status=StagingStatus.PENDING)
        assert StagingStatus.PENDING == "pending"  # 直接传入枚举
    
    def test_json_serialization(self):
        """测试 JSON 序列化"""
        import json
        data = {"status": StagingStatus.PENDING.value}
        json_str = json.dumps(data)
        assert '"status": "pending"' in json_str
    
    def test_all_values_unique(self):
        """测试所有状态值唯一"""
        values = [s.value for s in StagingStatus]
        assert len(values) == len(set(values))
    
    def test_enum_iteration(self):
        """测试枚举遍历"""
        status_list = list(StagingStatus)
        assert len(status_list) == 7
```

**执行测试命令：**
```bash
pytest tests/test_staging_status_compat.py -v
```

### 2.3 实施内容

#### 2.3.1 后端：增强状态枚举

**文件**：`apps/data_opt/mds/_base.py`

**修改**：增强 `StagingStatus` 枚举，增加 `label` 和 `color`

```python
class StagingStatus(str, Enum):
    """缓冲表数据状态"""
    PENDING = ("pending", "待处理", "warning")
    COMPLIANCE_PASS = ("compliance_pass", "合规通过", "info")
    COMPLIANCE_ERROR = ("compliance_error", "合规错误", "danger")
    RELATION_PASS = ("relation_pass", "关联通过", "success")
    RELATION_ERROR = ("relation_error", "关联错误", "warning")
    APPROVED = ("approved", "已审批", "primary")
    SYNCED = ("synced", "已同步", "secondary")

    def __new__(cls, value, label, color):
        obj = str.__new__(cls)
        obj._value_ = value
        obj.label = label
        obj.color = color
        return obj
    
    @classmethod
    def get_meta(cls, value: str) -> Optional[Dict[str, str]]:
        """根据值获取元数据"""
        for status in cls:
            if status.value == value:
                return {
                    "value": status.value,
                    "label": status.label,
                    "color": status.color
                }
        return None
```

**关键兼容性说明：**
- `StagingStatus.PENDING.value` 返回 `"pending"`（与原来一致）
- `str(StagingStatus.PENDING)` 返回 `"pending"`（与原来一致）
- `StagingStatus.PENDING == "pending"` 返回 `True`（与原来一致）
- 新增 `StagingStatus.PENDING.label` 返回 `"待处理"`
- 新增 `StagingStatus.PENDING.color` 返回 `"warning"`

#### 2.3.2 后端：新增状态元数据 API

**文件**：`apps/data_opt/mds/staging_routers.py`

**修改**：在现有路由下方新增

```python
@rt.get("/status-meta", summary="获取状态元数据")
async def get_status_meta():
    """
    获取所有状态的元数据，包括值、标签、颜色

    Returns:
        List[Dict]: [
            {"value": "pending", "label": "待处理", "color": "warning"},
            ...
        ]
    """
    return standard_response(
        success=1,
        message="查询成功",
        data=[
            {
                "value": status.value,
                "label": status.label,
                "color": status.color
            }
            for status in StagingStatus
        ]
    )
```

#### 2.3.3 前端：兼容改造（可配置开关）

**文件**：`static/mds/js/common.js`

**修改**：在 `STAGING_STATUS` 定义下方新增兼容层

```javascript
// ==================== 状态元数据加载 ====================
let STAGING_STATUS_META = null;
let STAGING_META_LOADED = false;  // 新增：加载完成标志

/**
 * 从后端加载状态元数据
 * @param {boolean} forceReload - 强制重新加载
 * @returns {Promise<Object|null>}
 */
async function loadStatusMeta(forceReload = false) {
    if (STAGING_STATUS_META && !forceReload) {
        return STAGING_STATUS_META;
    }
    
    try {
        const response = await callApi('/status-meta');
        if (response && response.success === 1) {
            STAGING_STATUS_META = {};
            response.data.forEach(item => {
                STAGING_STATUS_META[item.value] = item;
            });
            STAGING_META_LOADED = true;
            console.log('状态元数据加载成功:', Object.keys(STAGING_STATUS_META));
        }
    } catch (e) {
        console.warn('加载状态元数据失败，使用硬编码 fallback', e);
        STAGING_META_LOADED = true;  // 即使失败也标记为已尝试
    }
    
    return STAGING_STATUS_META;
}

/**
 * 等待状态元数据加载完成
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<void>}
 */
async function waitForStatusMeta(timeout = 3000) {
    const startTime = Date.now();
    while (!STAGING_META_LOADED && (Date.now() - startTime) < timeout) {
        await new Promise(resolve => setTimeout(resolve, 50));
    }
}

/**
 * 获取状态信息（优先后端元数据，fallback到硬编码）
 * @param {string} status - 状态值
 * @returns {Object}
 */
function getStatusInfo(status) {
    // 兼容旧状态
    const normalizedStatus = LEGACY_STATUS_MAP[status] || status;
    
    // 优先使用后端元数据
    const meta = STAGING_STATUS_META?.[normalizedStatus];
    if (meta) {
        return {
            value: meta.value,
            label: meta.label,
            colorClass: `text-${meta.color}`,
            bgClass: `bg-${meta.color}`,
            badgeClass: `badge bg-${meta.color}`,
            icon: 'circle'
        };
    }
    
    // Fallback到旧的硬编码
    const config = STAGING_STATUS[normalizedStatus.toUpperCase()] || STAGING_STATUS.PENDING;
    return config || {
        value: status,
        label: STATUS_TEXTS[normalizedStatus] || status,
        colorClass: 'text-secondary',
        bgClass: 'bg-secondary',
        badgeClass: 'badge bg-secondary'
    };
}

/**
 * 获取状态文本（向后兼容）
 * @param {string} status
 * @returns {string}
 */
function getStatusText(status) {
    return getStatusInfo(status).label;
}

/**
 * 获取状态颜色类（向后兼容）
 * @param {string} status
 * @returns {string}
 */
function getStatusColorClass(status) {
    return getStatusInfo(status).colorClass;
}

// 页面加载时自动加载状态元数据（非阻塞）
document.addEventListener('DOMContentLoaded', () => {
    loadStatusMeta().catch(e => console.warn('自动加载状态元数据失败', e));
});
```

### 2.4 验证清单（可执行）

```bash
# 1. 后端单元测试
pytest tests/test_staging_status_compat.py -v

# 2. API 可访问性测试
curl -s http://localhost:8000/api/mds/status-meta | jq '.data | length'
# 期望输出: 7

# 3. API 响应结构验证
curl -s http://localhost:8000/api/mds/status-meta | jq '.data[0]'
# 期望输出包含: value, label, color

# 4. 前端页面状态显示检查（手动）
# 打开浏览器访问: http://localhost:8000/mds/staging/t_material
# 检查: 状态列显示正常，无 JS 错误

# 5. 前端 fallback 测试（模拟 API 失败）
# 在浏览器控制台执行:
# STAGING_STATUS_META = null;
# getStatusInfo('pending');  // 应返回硬编码结果
```

### 2.5 回滚方案

```bash
# 后端
git restore apps/data_opt/mds/_base.py
git restore apps/data_opt/mds/staging_routers.py

# 前端
git restore static/mds/js/common.js

# 删除测试文件
rm tests/test_staging_status_compat.py
```

---

## 三、阶段二：增强字段元数据 API（依赖阶段一）

### 3.1 目标

让 `/rules/{table_key}` 返回更完整的元数据，前端可完全依赖元数据

### 3.2 前置条件

- [ ] 阶段一已完成并验证通过
- [ ] `StagingStatus` 已包含 `label` 和 `color` 属性

### 3.3 实施内容

#### 3.3.1 后端：增强 `generate_validation_rules_doc`

**文件**：`apps/data_opt/mds/_base.py`

**修改**：在现有函数末尾增加 `fields` 和 `status_meta` 返回

```python
def generate_validation_rules_doc(table_key: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成完整的校验规则文档
    
    Args:
        table_key: 表配置键（如 "t_material"）
        config: 表配置字典（来自 STAGING_TABLE_CONFIG）
    
    Returns:
        结构化的校验规则文档
    """
    schema_class = config.get('schema')
    model_class = config.get('model')
    proto_model = config.get('proto_model')
    
    doc = {
        "table_name": extract_display_name_from_model(model_class) if model_class else table_key,
        "table_key": table_key,
        "fields": [],
        
        "required_fields": [],
        "enum_fields": [],
        "range_fields": [],
        "max_length_fields": [],
        "business_rules": [],
        "foreign_keys": [],
        "business_keys": [],
        
        # 新增
        "status_meta": []
    }
    
    # 完整字段元数据
    if schema_class and model_class:
        doc["fields"] = extract_all_fields(schema_class, model_class)
    
    # 必填字段
    if schema_class:
        required_fields = extract_required_fields(schema_class)
        doc["required_fields"] = [
            {"field": field, "description": desc}
            for field, desc in required_fields
        ]
        
        # 枚举字段
        enum_fields = extract_enum_fields(schema_class)
        doc["enum_fields"] = [
            {"field": field, "description": desc, "allowed_values": list(values)}
            for field, (desc, values) in enum_fields.items()
        ]
        
        # 范围字段
        range_fields = extract_range_fields(schema_class)
        doc["range_fields"] = [
            {"field": field, "description": desc, "ge": ge, "gt": gt, "le": le, "lt": lt}
            for field, (desc, ge, gt, le, lt) in range_fields.items()
        ]
        
        # 最大长度字段
        max_length_fields = extract_max_length_fields(schema_class)
        doc["max_length_fields"] = [
            {"field": field, "description": desc, "max_length": max_length}
            for field, (desc, max_length) in max_length_fields.items()
        ]
    
    # 外键约束
    foreign_keys = config.get('foreign_keys', [])
    doc["foreign_keys"] = [
        {"field": fk.get("field"), "description": f"引用 {fk.get('field')} 必须存在于正式表"}
        for fk in foreign_keys
    ]
    
    # 业务规则
    business_rules = config.get('business_rules', [])
    doc["business_rules"] = [
        {"name": rule.get("name", ""), "description": rule.get("description", "")}
        for rule in business_rules
    ]
    
    # 业务主键
    if proto_model:
        doc["business_keys"] = extract_business_keys_from_model(proto_model)
    
    # ========== 新增：状态元数据 ==========
    doc["status_meta"] = [
        {
            "value": status.value,
            "label": status.label,
            "color": status.color
        }
        for status in StagingStatus
    ]
    
    return doc
```

### 3.4 验证清单（可执行）

```bash
# 1. API 返回结构验证
curl -s http://localhost:8000/api/mds/rules/t_material | jq '.data | keys'
# 期望包含: fields, status_meta

# 2. 字段元数据验证
curl -s http://localhost:8000/api/mds/rules/t_material | jq '.data.fields | length'
# 期望输出: > 0

# 3. 状态元数据验证
curl -s http://localhost:8000/api/mds/rules/t_material | jq '.data.status_meta | length'
# 期望输出: 7

# 4. 所有表的 API 测试
for table in t_material t_workcenter t_mat_ver t_mat_wc t_mat_wc_bom t_mold t_mat_wc_mold; do
    echo "Testing $table..."
    curl -s http://localhost:8000/api/mds/rules/$table | jq '.success'
done
# 期望全部输出: 1
```

### 3.5 回滚方案

```bash
git restore apps/data_opt/mds/_base.py
```

---

## 四、阶段三：外键选项 API（依赖阶段二）

### 4.1 目标

提供外键选项，支持前端联动和自动完成

### 4.2 前置条件

- [ ] 阶段二已完成
- [ ] `/rules/{table_key}` 返回 `fields` 数组

### 4.3 实施内容

#### 4.3.1 后端：增强 STAGING_TABLE_CONFIG

**文件**：`apps/data_opt/mds/staging_cleaner.py`

**说明**：现有 `foreign_keys` 配置格式为列表 `[{field, model}]`，本次扩展为支持可选的 `value_field` 和 `label_field`。

**修改策略**：
- 保持现有列表格式不变（向后兼容）
- 外键选项 API 仅读取有 `value_field` 配置的外键
- 无 `value_field` 配置的外键字段，选项 API 返回空数组

```python
# 示例：为 t_mat_ver 的 materialno 外键添加选项配置
"t_mat_ver": {
    "schema": AcceptMatVer,
    "model": TMatVerStaging,
    "proto_model": TMatVer,
    "foreign_keys": [
        {
            "field": "materialno",
            "model": TMaterial,
            # 新增可选配置（用于外键选项 API）
            "value_field": "materialno",   # 选项值字段
            "label_field": "description"   # 选项显示字段
        }
    ],
    "display_name": "产线版本",
    # ...
},
```

**完整迁移配置**：

```python
STAGING_TABLE_CONFIG = {
    "t_material": {
        # ... 现有配置保持不变 ...
        "foreign_keys": [],  # 无外键
    },
    
    "t_workcenter": {
        # ... 现有配置保持不变 ...
        "foreign_keys": [],  # 无外键
    },
    
    "t_mat_ver": {
        "schema": AcceptMatVer,
        "model": TMatVerStaging,
        "proto_model": TMatVer,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterial,
                "value_field": "materialno",
                "label_field": "description"
            }
        ],
        "display_name": "产线版本",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_ver(data, staging_id),
        "business_rules": [
            {
                "name": "批量下限≤批量上限",
                "description": "批量下限不能大于批量上限",
                "validator": validate_mat_ver_rules,
            }
        ],
    },
    
    "t_mat_wc": {
        "schema": AcceptMatWc,
        "model": TMatWcStaging,
        "proto_model": TMatWc,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterial,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "workcenter",
                "model": TWorkcenter,
                "value_field": "workcenter",
                "label_field": "description"
            }
        ],
        "display_name": "工艺路线",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc(data, staging_id),
        "business_rules": [
            {
                "name": "复合外键校验（物料+版本）",
                "description": "关联的产线版本必须存在",
                "validator": validate_mat_wc_rules,
            }
        ],
    },
    
    "t_mat_wc_bom": {
        "schema": AcceptMatWcBom,
        "model": TMatWcBomStaging,
        "proto_model": TMatWcBom,
        "foreign_keys": [
            {
                "field": "productno",
                "model": TMaterial,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "materialno",
                "model": TMaterial,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "workcenter",
                "model": TWorkcenter,
                "value_field": "workcenter",
                "label_field": "description"
            },
            {
                "field": "itemno",
                "model": TMatWc,
                "value_field": "itemno",
                "label_field": "description"
            }
        ],
        "display_name": "物料清单",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc_bom(data, staging_id),
        "business_rules": [
            {
                "name": "父件≠子件",
                "description": "父件和子件不能为同一物料",
                "validator": validate_mat_wc_bom_rules,
            }
        ],
    },
    
    "t_mold": {
        # ... 现有配置保持不变 ...
        "foreign_keys": [],
    },
    
    "t_mat_wc_mold": {
        "schema": AcceptMatWcMold,
        "model": TMatWcMoldStaging,
        "proto_model": TMatWcMold,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterial,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "workcenter",
                "model": TWorkcenter,
                "value_field": "workcenter",
                "label_field": "description"
            },
            {
                "field": "moldno",
                "model": TMold,
                "value_field": "moldno",
                "label_field": "description"
            }
        ],
        "display_name": "机台模具关联",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc_mold(data, staging_id),
        "business_rules": [
            {
                "name": "复合外键校验（物料+工作中心+工序）",
                "description": "关联的工艺路线必须存在",
                "validator": validate_mat_wc_mold_rules,
            }
        ],
    },
}
```

#### 4.3.2 后端：新增外键选项 API

**文件**：`apps/data_opt/mds/staging_routers.py`

**修改**：新增 API

```python
from typing import Optional, Query
from fastapi import HTTPException

@rt.get("/fk-options/{table_key}/{field_name}", summary="获取外键选项")
async def get_fk_options(
    request: Request,
    table_key: str,
    field_name: str,
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, description="返回数量限制", le=500)
):
    """
    获取指定表指定字段的外键选项

    Args:
        table_key: 表键名（如 t_material）
        field_name: 字段名（如 materialno）
        search: 搜索关键词（可选，模糊匹配 label_field）
        limit: 返回数量限制（默认100，最大500）

    Returns:
        [{ "value": "...", "label": "..." }, ...]
    """
    config = STAGING_TABLE_CONFIG.get(table_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"表 {table_key} 不存在")

    # 查找外键配置
    foreign_keys = config.get("foreign_keys", [])
    fk_config = None
    for fk in foreign_keys:
        if fk.get("field") == field_name:
            fk_config = fk
            break
    
    if not fk_config:
        # 无外键配置，返回空
        return standard_response(
            success=1,
            message="无外键配置",
            data=[]
        )
    
    # 检查是否有选项配置
    value_field = fk_config.get("value_field")
    label_field = fk_config.get("label_field")
    
    if not value_field or not label_field:
        # 外键未配置选项字段，返回空
        return standard_response(
            success=1,
            message="外键未配置选项字段",
            data=[]
        )

    # 查询选项
    model = fk_config["model"]

    # 构建查询
    query = model.all()
    if search:
        try:
            # 动态构建过滤条件
            filter_kwargs = {f"{label_field}__contains": search}
            query = query.filter(**filter_kwargs)
        except Exception as e:
            logger.warning(f"外键选项搜索失败: {e}")

    items = await query.limit(limit)

    return standard_response(
        success=1,
        message=f"查询成功，共{len(items)}条",
        data=[
            {
                "value": getattr(item, value_field),
                "label": getattr(item, label_field) or getattr(item, value_field)
            }
            for item in items
        ]
    )
```

### 4.4 验证清单（可执行）

```bash
# 1. API 可访问性测试
curl -s "http://localhost:8000/api/mds/fk-options/t_mat_ver/materialno" | jq '.success'
# 期望输出: 1

# 2. 无外键配置测试
curl -s "http://localhost:8000/api/mds/fk-options/t_material/materialno" | jq '.data'
# 期望输出: []

# 3. 搜索参数测试
curl -s "http://localhost:8000/api/mds/fk-options/t_mat_ver/materialno?search=测试" | jq '.data | length'
# 期望输出: >= 0

# 4. 数量限制测试
curl -s "http://localhost:8000/api/mds/fk-options/t_mat_ver/materialno?limit=5" | jq '.data | length'
# 期望输出: <= 5

# 5. 性能测试（大数据量）
time curl -s "http://localhost:8000/api/mds/fk-options/t_mat_ver/materialno?limit=500" > /dev/null
# 期望: < 200ms
```

### 4.5 回滚方案

```bash
git restore apps/data_opt/mds/staging_cleaner.py
git restore apps/data_opt/mds/staging_routers.py
```

---

## 五、阶段四：业务规则配置化（最复杂，建议最后实施）

### 5.1 目标

将 `validate_xxx_rules` 函数迁移到配置化规则引擎，保留旧函数作为兼容 fallback

### 5.2 前置条件

- [ ] 阶段一、二、三已完成并稳定运行
- [ ] 有充足的时间进行测试（建议至少 3 天）

### 5.3 迁移策略

**重要说明**：现有 `validate_xxx_rules` 函数已完整实现且稳定运行，阶段四的目标是：
1. 为新增表提供零代码配置能力
2. 保留现有函数作为兜底（不删除）

**迁移原则**：
- 优先使用配置化规则
- 配置化规则无法覆盖的场景，回退到 `validate_xxx_rules` 函数
- 不强制迁移现有表

### 5.4 实施内容

#### 5.4.1 后端：新增业务规则引擎

**文件**：`apps/data_opt/mds/_base.py`

**修改**：在文件末尾新增

```python
# ==================== 业务规则引擎 ====================
from typing import Callable, Dict, Any, Optional, List

class BusinessRule:
    """业务规则基类"""
    
    def __init__(
        self,
        name: str,
        description: str,
        validate_func: Callable[[Dict[str, Any]], bool],
        error_message: str,
        error_type: ErrorType = ErrorType.BUSINESS_RULE
    ):
        self.name = name
        self.description = description
        self.validate_func = validate_func
        self.error_message = error_message
        self.error_type = error_type
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        校验数据（同步版本）
        
        Args:
            data: 待校验数据
        
        Returns:
            是否违反规则（True 表示违反）
        """
        try:
            return self.validate_func(data)
        except Exception as e:
            # 规则执行异常，不报错，记录日志
            import logging
            logging.getLogger(__name__).warning(f"业务规则执行异常: {self.name}, {e}")
            return False
    
    def create_error(self, staging_id: int) -> Dict[str, Any]:
        """创建错误记录"""
        return {
            "staging_id": staging_id,
            "error_type": self.error_type.value,
            "error_field": self.name,
            "error_value": None,
            "error_message": self.error_message
        }


def create_comparison_rule(
    field_a: str,
    field_b: str,
    comparator: str,
    error_message: str
) -> BusinessRule:
    """
    创建比较规则
    
    Args:
        field_a: 字段A
        field_b: 字段B
        comparator: 比较运算符 (">", ">=", "<", "<=", "==")
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        a = data.get(field_a)
        b = data.get(field_b)
        if a is None or b is None:
            return False  # 空值不触发规则
        
        if comparator == ">":
            return a > b
        if comparator == ">=":
            return a >= b
        if comparator == "<":
            return a < b
        if comparator == "<=":
            return a <= b
        if comparator == "==":
            return a == b
        return False
    
    return BusinessRule(
        name=f"{field_a}_{comparator}_{field_b}",
        description=f"{field_a} {comparator} {field_b}",
        validate_func=validate,
        error_message=error_message
    )


def create_range_rule(
    field_name: str,
    min_val: Any,
    max_val: Any,
    error_message: str
) -> BusinessRule:
    """
    创建范围规则
    
    Args:
        field_name: 字段名
        min_val: 最小值（包含）
        max_val: 最大值（包含）
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        val = data.get(field_name)
        if val is None:
            return False  # 空值不触发规则
        return val < min_val or val > max_val
    
    return BusinessRule(
        name=f"{field_name}_range",
        description=f"{field_name} 在 {min_val}-{max_val} 之间",
        validate_func=validate,
        error_message=error_message,
        error_type=ErrorType.INVALID_RANGE
    )


def create_positive_rule(field_name: str, error_message: str) -> BusinessRule:
    """
    创建正数规则
    
    Args:
        field_name: 字段名
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        val = data.get(field_name)
        if val is None:
            return False
        return val <= 0
    
    return BusinessRule(
        name=f"{field_name}_positive",
        description=f"{field_name} 必须大于 0",
        validate_func=validate,
        error_message=error_message,
        error_type=ErrorType.INVALID_RANGE
    )
```

#### 5.4.2 后端：在 STAGING_TABLE_CONFIG 中添加配置化规则（示例）

**文件**：`apps/data_opt/mds/staging_cleaner.py`

**说明**：仅为 t_material 添加配置化规则示例，其他表保持使用现有的 `validate_xxx_rules` 函数。

```python
from ._base import (
    BusinessRule,
    create_comparison_rule,
    create_range_rule,
    create_positive_rule
)

# 在 STAGING_TABLE_CONFIG["t_material"] 中添加：
"t_material": {
    "schema": AcceptMaterial,
    "model": TMaterialStaging,
    "proto_model": TMaterial,
    "foreign_keys": [],
    "display_name": "物料",
    "validator": lambda cleaner, data, staging_id: cleaner.validate_material(data, staging_id),
    "business_rules": [
        # 原有配置保持不变
        {
            "name": "最小批量≤最大批量",
            "description": "最小批量不能大于最大批量",
            "validator": validate_material_rules,  # 现有函数
        }
    ],
    # 新增：配置化规则（可选，用于新表或简单规则）
    "config_rules": [
        create_comparison_rule("lotmin", "lotmax", ">", "最小批量不能大于最大批量"),
    ]
},
```

#### 5.4.3 后端：DataCleaner 支持配置化规则

**文件**：`apps/data_opt/mds/staging_cleaner.py`

**修改**：在 `validate_from_config` 方法末尾增加配置化规则校验

```python
async def validate_from_config(self, table_key: str, data: Dict[str, Any], staging_id: int = None) -> List[Dict]:
    """
    根据配置自动执行所有标准校验
    """
    errors = []
    config = STAGING_TABLE_CONFIG.get(table_key)
    if not config:
        return errors

    schema_class = config["schema"]

    # 1-6: 现有校验逻辑保持不变
    self.validate_required_from_schema(errors, staging_id, data, schema_class)
    self.validate_enums_from_schema(errors, staging_id, data, schema_class)
    self.validate_ranges_from_schema(errors, staging_id, data, schema_class)
    self.validate_max_lengths_from_schema(errors, staging_id, data, schema_class)
    await self.validate_foreign_keys_from_config(errors, staging_id, data, table_key)
    
    is_unique, dup_errors = await self.check_duplicate(table_key, data, staging_id)
    errors.extend(dup_errors)

    # 7. 执行业务规则校验（现有方式）
    for rule in config.get("business_rules", []):
        rule_errors = await rule["validator"](self, data, staging_id)
        errors.extend(rule_errors)
    
    # ========== 新增：配置化规则校验 ==========
    for rule in config.get("config_rules", []):
        if rule.validate(data):
            errors.append(rule.create_error(staging_id))

    return errors
```

### 5.5 验证清单（可执行）

```bash
# 1. 配置化规则语法测试
python -c "
from apps.data_opt.mds._base import create_comparison_rule
rule = create_comparison_rule('lotmin', 'lotmax', '>', '错误')
print(rule.validate({'lotmin': 10, 'lotmax': 5}))  # True (违反)
print(rule.validate({'lotmin': 5, 'lotmax': 10}))  # False (通过)
"
# 期望输出: True False

# 2. 端到端测试：创建测试数据并校验
# （手动操作）在缓冲表插入一条 lotmin > lotmax 的记录，执行校验，检查是否报错

# 3. 兼容性测试：验证现有 validate_xxx_rules 仍生效
# （手动操作）检查校验错误记录中是否包含业务规则错误
```

### 5.6 回滚方案

```bash
git restore apps/data_opt/mds/_base.py
git restore apps/data_opt/mds/staging_cleaner.py
```

---

## 六、总体时间线

| 阶段 | 预计时间 | 风险 | 依赖 | 可并行 |
|------|---------|------|------|--------|
| 阶段一 | 1-2 天 | 低 | 无 | 否 |
| 阶段二 | 1-2 天 | 低 | 阶段一 | 否 |
| 阶段三 | 1-2 天 | 低 | 阶段二 | 否 |
| 阶段四 | 3-4 天 | 中 | 阶段一-三 | 否 |

**总预计时间**：7-10 天（保守估计）

---

## 七、关键验证点

### 7.1 兼容性验证（每阶段必做）

```bash
# 1. 运行所有现有测试
pytest tests/ -v

# 2. 校验功能测试
curl -X POST http://localhost:8000/api/mds/validate/t_material

# 3. 同步功能测试
curl -X POST http://localhost:8000/api/mds/sync/t_material

# 4. 前端页面冒烟测试（手动）
# 访问所有 MDS 页面，检查无 JS 错误
```

### 7.2 性能验证

```bash
# 1. API 响应时间测试
for api in status-meta "rules/t_material" "fk-options/t_mat_ver/materialno"; do
    echo "Testing $api..."
    time curl -s "http://localhost:8000/api/mds/$api" > /dev/null
done

# 2. 批量校验性能测试（1000条记录）
time curl -X POST "http://localhost:8000/api/mds/validate/t_material?batch_size=1000"
```

---

## 八、回滚方案汇总

### 完整回滚命令

```bash
# 回滚到优化前状态
git checkout main
git branch -D feature/mds-optimization

# 或逐阶段回滚
# 阶段一回滚
git restore apps/data_opt/mds/_base.py apps/data_opt/mds/staging_routers.py static/mds/js/common.js

# 阶段二回滚
git restore apps/data_opt/mds/_base.py

# 阶段三回滚
git restore apps/data_opt/mds/staging_cleaner.py apps/data_opt/mds/staging_routers.py

# 阶段四回滚
git restore apps/data_opt/mds/_base.py apps/data_opt/mds/staging_cleaner.py
```

---

## 九、总结

### 9.1 优化效果

完成所有阶段后：
- ✅ 前后端状态定义统一，消除重复
- ✅ 字段元数据完整，前端可完全依赖
- ✅ 外键选项 API，支持前端联动
- ✅ 业务规则配置化，新增表零代码
- ✅ 全程向后兼容，低风险

### 9.2 关键成功因素

1. **向后兼容**：每个阶段都保留旧方式作为 fallback
2. **渐进式改造**：不强求一次性全部迁移
3. **功能等价**：优化不改变现有功能
4. **最小变更**：充分利用现有架构，不新增文件
5. **充分测试**：每阶段都有可执行的验证清单

### 9.3 v1.1 修订内容

1. **新增前置验证**：阶段一增加兼容性测试脚本
2. **修正依赖关系**：阶段三依赖阶段二（原计划称可并行）
3. **细化验证清单**：所有验证项改为可执行的命令
4. **调整时间估算**：总时间从 5-7 天调整为 7-10 天
5. **明确迁移策略**：阶段四明确"不强制迁移现有表"
6. **前端时序处理**：增加 `waitForStatusMeta` 函数和加载完成标志
7. **外键配置兼容**：保持现有列表格式，扩展而非替换

---

## 附录：文件变更清单

| 阶段 | 变更文件 | 新增/修改 | 说明 |
|------|---------|-----------|------|
| 阶段一 | `_base.py` | 修改 | 枚举增加 label/color |
| 阶段一 | `staging_routers.py` | 修改 | 新增 /status-meta |
| 阶段一 | `common.js` | 修改 | 新增动态加载逻辑 |
| 阶段一 | `test_staging_status_compat.py` | 新增（临时） | 兼容性测试 |
| 阶段二 | `_base.py` | 修改 | 增强 generate_validation_rules_doc |
| 阶段三 | `staging_cleaner.py` | 修改 | foreign_keys 扩展配置 |
| 阶段三 | `staging_routers.py` | 修改 | 新增 /fk-options |
| 阶段四 | `_base.py` | 修改 | 新增 BusinessRule 类 |
| 阶段四 | `staging_cleaner.py` | 修改 | 支持 config_rules |

**实际新增文件：1 个临时测试文件（阶段完成后可删除）**
