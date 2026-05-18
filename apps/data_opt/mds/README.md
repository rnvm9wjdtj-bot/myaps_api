# MDS 缓冲系统配置指南

> **版本**：v1.0  
> **更新日期**：2026-05-16  
> **适用范围**：新增主数据表到缓冲系统

---

## 目录

- [Summary：配置化能力总结](#summary配置化能力总结)
- [步骤概览](#步骤概览)
- [步骤一：定义 ProtoModel](#步骤一定义-protoModel表结构)
- [步骤二：定义 StagingModel](#步骤二定义-stagingmodel缓冲表模型)
- [步骤三：定义 Schema](#步骤三定义-schema校验规则)
- [步骤四：配置 STAGING_TABLE_CONFIG](#步骤四配置-staging_table_config)
- [步骤五：实现校验器](#步骤五实现校验器可选)
- [配置字段说明](#配置字段说明)
- [外键配置说明](#外键配置说明)
- [业务主键配置注意事项](#业务主键配置注意事项)
- [完整示例](#完整示例)

---

## Summary：配置化能力总结

### 已实现的配置化能力

| 能力 | 实现方式 | 配置化程度 |
|------|----------|------------|
| **表结构定义** | ProtoModel + StagingModel | ⚠️ 需编码定义类 |
| **字段校验** | 从 Schema 自动提取 | ✅ 零配置 |
| **外键校验** | foreign_keys 配置 | ✅ 纯配置 |
| **外键选项** | value_field/label_field 配置 | ✅ 纯配置 |
| **业务规则** | config_rules 配置化 | ✅ 纯配置 |
| **复杂规则** | business_rules + 自定义函数 | ⚠️ 需编码 |
| **状态管理** | StagingStatus 枚举 | ✅ 统一管理 |
| **元数据 API** | /status-meta, /rules, /fk-options | ✅ 自动生成 |

### 新增表的代码量

| 步骤 | 代码量 | 说明 |
|------|--------|------|
| ProtoModel | ~10 行 | 表结构定义 |
| StagingModel | ~5 行 | 继承即可 |
| Schema | ~20 行 | 字段校验定义 |
| STAGING_TABLE_CONFIG | ~15 行 | 配置字典 |
| **合计** | **~50 行** | 大部分是声明性代码 |

### 仍需手动处理的部分

1. **数据库表创建**：需通过 aerich 迁移或手动建表
2. **前端页面**：需创建对应的 HTML/JS 页面
3. **复杂业务规则**：如跨表关联、复合外键等需自定义函数

### 配置化程度评估

**后端校验层配置化程度：90%+**

**新增表流程**：
- 后端：~50 行声明性代码 + 数据库迁移
- 前端：需单独开发页面（可考虑后续模板化）

### 未来优化方向

如需进一步提升配置化程度，可考虑：
1. **前端页面模板化**：根据元数据自动生成列表页、编辑页
2. **数据库表自动创建**：根据 ProtoModel 生成 DDL 并自动执行

---

## 步骤概览

```
1. 定义 ProtoModel（表结构）
   ↓
2. 定义 StagingModel（缓冲表模型）
   ↓
3. 定义 Schema（校验规则）
   ↓
4. 配置 STAGING_TABLE_CONFIG
   ↓
5. 前端页面（可选）
```

---

## 步骤一：定义 ProtoModel（表结构）

**文件**：`apps/io_api/protomodels.py`

```python
class ProtoXxx(TortoiseBaseModel):
    """主数据表结构定义"""
    # 业务主键字段
    xxxno = fields.CharField(source_field='XxxNo', unique=True, max_length=64, description='编码')
    description = fields.CharField(source_field='Description', max_length=128, description='名称')
    
    # 其他业务字段...
    
    class Meta:
        abstract = True
        # 注意：ProtoModel 不指定 table，由正式模型继承时指定
```

**说明**：
- `source_field`：数据库列名（PascalCase）
- `description`：字段描述，用于生成校验错误信息
- `abstract = True`：抽象模型，不直接创建表

---

## 步骤二：定义 StagingModel（缓冲表模型）

**文件**：`apps/data_opt/mds/staging_models.py`

```python
class TXxxStaging(StagingBaseModel, pm.ProtoXxx):
    """XXX缓冲表"""
    class Meta:
        table = "t_xxx_staging"
        table_description = "XXX数据缓冲表"
```

**说明**：
- 继承 `StagingBaseModel`（自动包含 `_staging_id`、`_status`、`_createtime` 等内部字段）
- 继承 `pm.ProtoXxx`（继承业务字段定义）
- 表名规则：`t_{业务名}_staging`

**StagingBaseModel 包含的内部字段**：
- `_staging_id`：缓冲表主键
- `_status`：处理状态（pending/compliance_pass/compliance_error/relation_pass/relation_error/approved/synced）
- `_error_msg`：错误信息 JSON
- `_transform_rules`：应用的转换规则 JSON
- `_retry_count`：重试次数
- `_createtime`：创建时间
- `_updatetime`：更新时间
- `_synced_id`：同步后正式表 ID
- `_synced_time`：同步时间

---

## 步骤三：定义 Schema（校验规则）

**文件**：`apps/io_api/schemas.py`

```python
from pydantic import BaseModel, Field, field_validator

class AcceptXxx(BaseModel):
    """XXX数据接收校验"""
    xxxno: str = Field(..., description="编码（必填）")
    description: str = Field(..., max_length=128, description="名称（必填）")
    contact: Optional[str] = Field(None, max_length=64, description="联系人（可选）")
    
    @field_validator('xxxno')
    @classmethod
    def validate_xxxno(cls, v):
        if not v or not v.strip():
            raise ValueError('编码不能为空')
        return v.strip()
```

**说明**：
- 必填字段：使用 `Field(..., description="...")`
- 可选字段：使用 `Field(None, ...)`
- 枚举字段：配合 `field_validator` 进行值校验
- 范围字段：使用 `Field(..., ge=0, le=100)` 等

---

## 步骤四：配置 STAGING_TABLE_CONFIG

**文件**：`apps/data_opt/mds/staging_cleaner.py`

### 4.1 导入模型

在文件顶部导入区域添加：

```python
from .staging_models import TXxxStaging
from apps.io_api.models import TXxx
from apps.io_api.schemas import AcceptXxx
```

### 4.2 添加配置

在 `STAGING_TABLE_CONFIG` 字典中添加：

```python
STAGING_TABLE_CONFIG = {
    # ... 现有配置 ...
    
    "t_xxx": {
        "schema": AcceptXxx,                    # 校验 Schema
        "model": TXxxStaging,                   # 缓冲表模型
        "proto_model": TXxx,                    # 正式表模型（用于提取业务主键）
        "foreign_keys": [                       # 外键配置（可选）
            {
                "field": "materialno",          # 本表字段名
                "model": TMaterial,             # 引用的正式表模型
                "value_field": "materialno",    # 选项值字段
                "label_field": "description"    # 选项显示字段
            },
        ],
        "display_name": "XXX",                  # 显示名称
        "validator": lambda cleaner, data, staging_id: cleaner.validate_xxx(data, staging_id),
        
        # 配置化业务规则（推荐）
        "config_rules": [
            create_comparison_rule("field_a", "field_b", "<=", "字段A不能大于字段B"),
            create_positive_rule("qty", "数量必须大于0"),
            create_range_rule("rate", 0, 100, "比率必须在0-100之间"),
        ],
        
        # 复杂业务规则（config_rules 无法覆盖时使用）
        # "business_rules": [
        #     {
        #         "name": "规则名称",
        #         "description": "规则描述",
        #         "validator": validate_xxx_rules,
        #     }
        # ],
        
        # "business_keys": ["xxxno"],  # 可选：默认从 proto_model 自动提取
    },
}
```

---

## 步骤五：实现校验器（可选）

### 方案 A：使用配置化规则（推荐）

无需编写校验函数，使用 `config_rules` 即可覆盖常见规则。

**可用规则工厂函数**：

| 函数 | 说明 | 示例 |
|------|------|------|
| `create_comparison_rule(field_a, field_b, comparator, error_msg)` | 字段比较 | `create_comparison_rule("lotmin", "lotmax", "<=", "最小批量≤最大批量")` |
| `create_positive_rule(field, error_msg)` | 正数校验 | `create_positive_rule("qty", "数量必须大于0")` |
| `create_range_rule(field, min, max, error_msg)` | 范围校验 | `create_range_rule("scrap", 0, 100, "损耗率0-100")` |
| `create_not_equal_rule(field_a, field_b, error_msg)` | 不等校验 | `create_not_equal_rule("productno", "materialno", "父件≠子件")` |

**支持的比较运算符**：`>`, `>=`, `<`, `<=`, `==`

### 方案 B：自定义校验函数

**适用场景**：
- 复合外键存在校验
- 跨表关联校验
- config_rules 无法覆盖的复杂规则

**示例**：

```python
async def validate_xxx_rules(cleaner, data, staging_id):
    """复杂业务规则校验"""
    errors = []
    
    # 示例：复合外键存在校验
    if data.get("materialno") and data.get("matver"):
        exists = await TMatVer.filter(
            materialno=data["materialno"],
            matver=data["matver"]
        ).exists()
        if not exists:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.FK_NOT_FOUND, "matver",
                f"{data['materialno']}/{data['matver']}", "关联的产线版本不存在"
            ))
    
    return errors
```

**ErrorType 枚举值**：
- `REQUIRED_FIELD`：必填字段为空
- `INVALID_ENUM`：枚举值非法
- `INVALID_TYPE`：字段类型错误
- `INVALID_RANGE`：数值范围错误
- `INVALID_LENGTH`：字符串长度错误
- `FK_NOT_FOUND`：外键不存在
- `DUPLICATE_KEY`：主键重复
- `BUSINESS_RULE`：业务规则违反

---

## 配置字段说明

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `schema` | ✅ | Pydantic Model | 字段校验 Schema |
| `model` | ✅ | Tortoise Model | 缓冲表模型类 |
| `proto_model` | ✅ | Tortoise Model | 正式表模型类，用于提取业务主键 |
| `foreign_keys` | ❌ | List[Dict] | 外键配置列表，默认 `[]` |
| `display_name` | ❌ | str | 显示名称，默认使用 table_key |
| `validator` | ❌ | Callable | 自定义校验函数 |
| `config_rules` | ❌ | List[BusinessRule] | 配置化业务规则列表 |
| `business_rules` | ❌ | List[Dict] | 复杂业务规则列表（含 validator 函数） |
| `business_keys` | ❌ | List[str] | 业务主键字段列表，默认从 proto_model 自动提取 |

---

## 外键配置说明

### 配置结构

```python
{
    "field": "materialno",        # 本表字段名（snake_case）
    "model": TMaterial,           # 引用的正式表模型
    "value_field": "materialno",  # 选项值字段（用于 /fk-options API）
    "label_field": "description"  # 选项显示字段（用于 /fk-options API）
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `field` | ✅ | 本表外键字段名 |
| `model` | ✅ | 引用的正式表模型类 |
| `value_field` | ❌ | 选项值字段，用于 `/fk-options/{table}/{field}` API |
| `label_field` | ❌ | 选项显示字段，用于下拉选项显示 |

### 外键校验流程

1. **自动校验**：系统自动检查外键值是否在引用表中存在
2. **选项 API**：配置 `value_field` 和 `label_field` 后，可通过 `/fk-options/{table_key}/{field_name}` 获取下拉选项
3. **复合外键**：需要通过 `business_rules` 自定义校验函数

---

## 业务主键配置注意事项

### 自动提取逻辑

系统通过 `extract_business_keys_from_model()` 自动从正式表模型提取业务主键，优先级为：

1. **`unique_together` 约束**（最高优先级）
2. **`unique=True` 的字段**
3. **主键字段**（排除自增 `id`）

### 常见问题

#### 问题：去重失效，插入重复数据

**原因**：模型有自增主键（如 `vid`），自动提取返回 `['vid']` 而非业务主键。

**示例**：
```python
# apps/io_api/models.py
class TMatVer(TortoiseBaseModel):
    vid = fields.IntField(pk=True)  # 自增主键
    materialno = fields.CharField(max_length=64)
    matver = fields.CharField(max_length=4)
    
    class Meta:
        unique_together = [("materialno", "matver")]  # 业务主键
```

**错误提取**：`['vid']`（使用自增主键去重）  
**正确提取**：`['materialno', 'matver']`（使用业务主键去重）

#### 解决方案

**方案一：正确配置 `unique_together`**（推荐）

```python
class ProtoMatVer(TortoiseBaseModel):
    materialno = fields.CharField(max_length=64)
    matver = fields.CharField(max_length=4)
    
    class Meta:
        abstract = True
        unique_together = [("materialno", "matver")]  # 业务主键约束
```

**方案二：显式配置 `business_keys`**

```python
STAGING_TABLE_CONFIG["t_mat_ver"] = {
    ...
    "business_keys": ["materialno", "matver"],  # 覆盖自动提取
}
```

### 操作注意事项

1. **修改配置后需重启服务**
2. **检查日志确认提取结果**：
   ```python
   # 添加临时调试日志
   logger.info(f"pk_fields={config.get('business_keys', [])}")
   ```
3. **复合主键必须配置 `unique_together`**：
   - 单字段主键：`unique=True` 或 `pk=True`
   - 复合主键：`unique_together = [("field1", "field2")]`

---

## 去重检测与内容比对

### 去重策略

系统支持三种去重策略，通过 `dedup_strategy` 参数控制：

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `overwrite` | 覆盖已存在记录 | 默认策略，支持内容比对优化 |
| `skip` | 跳过已存在记录 | 不更新已有数据 |
| `reject` | 拒绝整个批次 | 严格模式，发现重复即拒绝 |

### 内容比对逻辑（overwrite策略）

**核心机制**：导入相同数据时，通过内容比对判断是否需要覆盖，避免无意义的数据更新。

**比对流程**：
```
1. 批量查询已存在记录（按业务主键）
   ↓
2. 逐条比对内容是否一致
   ↓
3. 内容相同 → 跳过覆盖，状态保持不变
   内容不同 → 执行覆盖
```

### 更新模式（update_mode）

通过 `update_mode` 参数控制字段比对范围：

| 模式 | 说明 | 行为示例 |
|------|------|----------|
| `partial`（默认） | 部分更新 | 只比对新数据中存在的字段，未传递字段保持不变 |
| `full` | 完整更新 | 所有字段都参与比对，未传递字段视为None |

**partial模式示例**：

```python
# 数据库已有记录
{
    "materialno": "M001",
    "description": "测试物料",
    "price": 100,
    "unit": "PCS"
}

# Excel/API只传递部分字段
{
    "materialno": "M001",
    "description": "测试物料"
}

# partial模式比对结果：相同
# - 未传递的 price、unit 字段被跳过
# - 只比对 materialno、description
# - 内容相同 → 跳过覆盖，price/unit 保持不变
```

**full模式示例**：

```python
# 同上场景
# full模式比对结果：差异
# - 未传递的 price、unit 视为 None
# - None ≠ 数据库值 → 触发覆盖
# - price、unit 被覆盖为 None
```

### 显式清空字段

如需清空某个字段，需显式传递空值：

```python
# 方式1：传递空字符串（Excel）
{
    "materialno": "M001",
    "description": "测试物料",
    "price": ""  # 显式清空
}

# 方式2：传递null（API）
{
    "materialno": "M001",
    "description": "测试物料",
    "price": null  # 显式清空
}

# 比对结果：差异
# - 空值被normalize为None
# - None ≠ 数据库值(100) → 触发覆盖
# - price 被清空为 None
```

### 与API行为的一致性

**Pydantic Schema的exclude_none行为**：

```python
# API接收数据后转换
data = AcceptMaterial(**request_data)
dict_data = data.model_dump(exclude_none=True)  # 排除未传递字段

# 比对时
# - exclude_none=True 排除了未传递字段
# - partial模式跳过不存在的字段
# - 行为一致：部分更新语义
```

**数据流转路径**：

```
API导入：
  Request → Pydantic验证 → model_dump(exclude_none=True) → 比对(partial) → 数据库
  
Excel导入：
  Excel → Dict → 比对(partial) → 数据库
  
两者行为一致：未传递字段不参与更新
```

### API参数说明

**导入接口**：

```python
POST /mds/{table_key}
POST /mds/upload/{table_name}

参数：
  - dedup_strategy: str = "overwrite"  # overwrite/skip/reject
  - update_mode: str = "partial"       # partial/full
```

**推荐配置**：

- **默认场景**：`dedup_strategy="overwrite"` + `update_mode="partial"`
  - 适合大部分场景，未传递字段保持不变
  
- **完整覆盖场景**：`dedup_strategy="overwrite"` + `update_mode="full"`
  - 需要清空未传递字段时使用
  
- **只导入新数据**：`dedup_strategy="skip"`
  - 不更新已有数据，只导入新数据

---

## 完整示例

### 新增供应商表（t_supplier）

#### 1. 定义 ProtoModel

**文件**：`apps/io_api/protomodels.py`

```python
class ProtoSupplier(TortoiseBaseModel):
    """供应商表结构"""
    supplierno = fields.CharField(source_field='SupplierNo', unique=True, max_length=64, description='供应商编码')
    name = fields.CharField(source_field='Name', max_length=128, description='供应商名称')
    contact = fields.CharField(source_field='Contact', max_length=64, null=True, description='联系人')
    phone = fields.CharField(source_field='Phone', max_length=32, null=True, description='电话')
    address = fields.CharField(source_field='Address', max_length=255, null=True, description='地址')
    
    class Meta:
        abstract = True
```

#### 2. 定义 StagingModel

**文件**：`apps/data_opt/mds/staging_models.py`

```python
class TSupplierStaging(StagingBaseModel, pm.ProtoSupplier):
    """供应商缓冲表"""
    class Meta:
        table = "t_supplier_staging"
        table_description = "供应商数据缓冲表"
```

#### 3. 定义 Schema

**文件**：`apps/io_api/schemas.py`

```python
class AcceptSupplier(BaseModel):
    """供应商数据接收校验"""
    supplierno: str = Field(..., min_length=1, max_length=64, description="供应商编码")
    name: str = Field(..., min_length=1, max_length=128, description="供应商名称")
    contact: Optional[str] = Field(None, max_length=64, description="联系人")
    phone: Optional[str] = Field(None, max_length=32, description="电话")
    address: Optional[str] = Field(None, max_length=255, description="地址")
    
    @field_validator('supplierno', 'name')
    @classmethod
    def validate_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('不能为空')
        return v.strip()
```

#### 4. 配置 STAGING_TABLE_CONFIG

**文件**：`apps/data_opt/mds/staging_cleaner.py`

```python
# 导入
from .staging_models import TSupplierStaging
from apps.io_api.models import TSupplier
from apps.io_api.schemas import AcceptSupplier

# 配置
STAGING_TABLE_CONFIG["t_supplier"] = {
    "schema": AcceptSupplier,
    "model": TSupplierStaging,
    "proto_model": TSupplier,
    "foreign_keys": [],
    "display_name": "供应商",
    "validator": lambda cleaner, data, staging_id: cleaner.validate_supplier(data, staging_id),
}
```

---

### 新增采购订单表（t_po，含外键）

#### 1. 定义 ProtoModel

```python
class ProtoPO(TortoiseBaseModel):
    """采购订单表结构"""
    pono = fields.CharField(source_field='PONo', unique=True, max_length=64, description='订单号')
    supplierno = fields.CharField(source_field='SupplierNo', max_length=64, description='供应商编码')
    materialno = fields.CharField(source_field='MaterialNo', max_length=64, description='物料编码')
    qty = fields.FloatField(source_field='Qty', description='数量')
    duedate = fields.DateField(source_field='DueDate', description='交货日期')
    
    class Meta:
        abstract = True
```

#### 2. 定义 StagingModel

```python
class TPOStaging(StagingBaseModel, pm.ProtoPO):
    """采购订单缓冲表"""
    class Meta:
        table = "t_po_staging"
        table_description = "采购订单数据缓冲表"
```

#### 3. 定义 Schema

```python
class AcceptPO(BaseModel):
    """采购订单数据接收校验"""
    pono: str = Field(..., description="订单号")
    supplierno: str = Field(..., description="供应商编码")
    materialno: str = Field(..., description="物料编码")
    qty: float = Field(..., gt=0, description="数量（必须大于0）")
    duedate: date = Field(..., description="交货日期")
```

#### 4. 配置 STAGING_TABLE_CONFIG

```python
STAGING_TABLE_CONFIG["t_po"] = {
    "schema": AcceptPO,
    "model": TPOStaging,
    "proto_model": TPO,
    "foreign_keys": [
        {
            "field": "supplierno",
            "model": TSupplier,
            "value_field": "supplierno",
            "label_field": "name"
        },
        {
            "field": "materialno",
            "model": TMaterial,
            "value_field": "materialno",
            "label_field": "description"
        },
    ],
    "display_name": "采购订单",
    "validator": lambda cleaner, data, staging_id: cleaner.validate_po(data, staging_id),
    "config_rules": [
        create_positive_rule("qty", "数量必须大于0"),
    ],
}
```

---

## 常见问题

### Q1: business_keys 如何确定？

**A**: 默认从 `proto_model` 自动提取（标记为 `unique=True` 的字段）。如需自定义：

```python
"business_keys": ["materialno", "matver"],  # 复合主键
```

### Q2: 外键校验失败时错误信息如何自定义？

**A**: 使用自定义校验函数：

```python
async def validate_po_rules(cleaner, data, staging_id):
    errors = []
    if data.get("supplierno"):
        supplier = await TSupplier.filter(supplierno=data["supplierno"]).first()
        if not supplier:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.FK_NOT_FOUND, "supplierno",
                data["supplierno"], f"供应商 {data['supplierno']} 不存在，请先导入供应商主数据"
            ))
    return errors
```

### Q3: config_rules 和 business_rules 有什么区别？

**A**:
- `config_rules`：零代码配置，适合简单规则（比较、范围、正数等）
- `business_rules`：需要编写校验函数，适合复杂规则（复合外键、跨表关联等）

### Q4: 如何跳过某些校验？

**A**: 在 `validator` 函数中返回空列表 `[]` 即跳过：

```python
"validator": lambda cleaner, data, staging_id: [],  # 跳过自定义校验
```

---

## 相关文档

- [MDS 优化计划（已归档）](../../docs/archive/mds_optimization_plan.md)
- [数据清洗模块设计文档](../../docs/data_cleaning_spec.md)
