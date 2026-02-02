# HAP v2 模块使用说明

## 1. 模块简介

HAP v2 是一个为明道云 API v3 设计的 ORM 封装模块，提供了类似 Django ORM 或 Tortoise ORM 的使用体验，简化了与明道云工作表的交互操作。

### 主要特性

- **模型定义**：通过类定义方式创建明道云工作表模型
- **字段类型**：支持文本、数字、日期、关联等多种字段类型
- **查询功能**：支持链式查询、过滤、排序、分页等
- **批量操作**：支持批量创建、更新、删除记录
- **关联关系**：支持通过 `RelationField` 定义表之间的关联关系
- **自动关联更新**：通过 `follow_with` 参数实现基于特定字段的关联关系自动更新
- **缓存机制**：内置缓存机制，提高查询性能
- **Upsert 操作**：支持批量 upsert 操作（存在则更新，不存在则创建）
- **复杂查询**：支持使用 Q 函数构建复杂查询条件

## 2. 安装和配置

### 2.1 依赖

- Python 3.8+
- requests
- typing_extensions

### 2.2 配置

在使用前，需要配置 HAP 连接信息：

```python
from apps.data_opt.components.hapv2 import HapConnection

# 创建 HAP 连接
hap_conn = HapConnection(
    base_url="https://api.mingdao.com",  # 明道云 API 基础地址
    app_key="your_app_key",             # 应用 Key
    app_secret="your_app_secret",       # 应用 Secret
)
```

## 3. 基本使用方法

### 3.1 定义模型

```python
from apps.data_opt.components.hapv2 import Model, TextField, NumberField, DateField, RelationField

class Currency(Model):
    """币种模型"""
    class Meta:
        worksheet_id = "currency"
        conflict_fields = ["currency_code"]  # 冲突字段，用于 upsert 操作
    
    currency_code = TextField(description="币种代码")
    currency_name = TextField(description="币种名称")

class Company(Model):
    """公司模型"""
    class Meta:
        worksheet_id = "company"
    
    company_name = TextField(description="公司名称")
    currencyCode = TextField(description="币种代码")
    currency = RelationField(Currency, follow_with="currencyCode", description="币种")
```

### 3.2 查询记录

```python
# 获取所有公司
companies = hap_conn.rows(Company).all()

# 遍历结果
for company in companies.all():
    print(f"公司名称: {company.company_name}")
    print(f"币种代码: {company.currencyCode}")
    print(f"币种: {company.currency}")

# 条件查询
filtered_companies = hap_conn.rows(Company).filter("company_name__contains=科技").all()

# 排序
ordered_companies = hap_conn.rows(Company).order_by("company_name").all()

# 分页
paged_companies = hap_conn.rows(Company).offset(0).limit(10).all()

# 获取单条记录
first_company = hap_conn.rows(Company).first()
```

### 3.3 创建记录

```python
# 创建单个记录
new_company = hap_conn.rows(Company).create(
    company_name="科技有限公司",
    currencyCode="CNY"
)
print(f"创建的公司 ID: {new_company.row_id}")

# 批量创建
companies_data = [
    {"company_name": "公司 A", "currencyCode": "CNY"},
    {"company_name": "公司 B", "currencyCode": "USD"}
]
created_companies = hap_conn.rows(Company).bulk_create(companies_data)
print(f"创建了 {len(created_companies)} 个公司")
```

### 3.4 更新记录

```python
# 批量更新
companies = hap_conn.rows(Company).filter("company_name__contains=科技").all()
updated_companies = companies.update(company_name="新科技有限公司")
print(f"更新了 {len(updated_companies)} 个公司")
```

### 3.5 删除记录

```python
# 批量删除
companies = hap_conn.rows(Company).filter("company_name__contains=测试").all()
delete_results = companies.delete()
print(f"删除结果: {delete_results}")
```

### 3.6 Upsert 操作

```python
# 批量 upsert
upsert_data = [
    {"company_name": "公司 A", "currencyCode": "CNY"},
    {"company_name": "公司 B", "currencyCode": "USD"}
]
result_set = hap_conn.rows(Company).upsert(upsert_data)
print(f"处理了 {result_set.count()} 个记录")
```

## 4. 高级功能

### 4.1 复杂查询条件

使用 Q 函数构建复杂查询条件：

```python
from apps.data_opt.components.hapv2 import Q

# AND 条件
companies = hap_conn.rows(Company).filter(
    Q(company_name__contains="科技") & Q(currencyCode__eq="CNY")
).all()

# OR 条件
companies = hap_conn.rows(Company).filter(
    Q(company_name__contains="科技") | Q(company_name__contains="互联网")
).all()

# NOT 条件
companies = hap_conn.rows(Company).filter(
    ~Q(currencyCode__eq="CNY")
).all()

# 组合条件
companies = hap_conn.rows(Company).filter(
    (Q(company_name__contains="科技") & Q(currencyCode__eq="CNY")) | 
    (Q(company_name__contains="互联网") & Q(currencyCode__eq="USD"))
).all()
```

### 4.2 关联字段自动更新

通过 `follow_with` 参数实现关联字段的自动更新：

```python
class Company(Model):
    currencyCode = TextField()
    currency = RelationField(Currency, follow_with="currencyCode")
    
    class Meta:
        worksheet_id = "company"

# 当创建或更新公司记录时，会自动根据 currencyCode 查询 Currency 表
# 并将查询结果更新到 currency 字段
company = hap_conn.rows(Company).create(
    company_name="测试公司",
    currencyCode="CNY"  # 会自动查询 Currency 表中 currency_code 为 "CNY" 的记录
)
```

### 4.3 缓存机制

模块内置了缓存机制，提高查询性能：

```python
class Currency(Model):
    class Meta:
        worksheet_id = "currency"
        cache = ["currency_code", "currency_name"]  # 缓存的字段

# 第一次查询会从 API 获取数据并缓存
currencies = hap_conn.rows(Currency).all()

# 后续查询会优先使用缓存数据
currencies_from_cache = hap_conn.rows(Currency).all()
```

### 4.4 流式查询

对于大数据量查询，使用流式查询可以减少内存使用：

```python
# 流式获取所有记录
for company in hap_conn.rows(Company).stream():
    print(f"处理公司: {company.company_name}")
```

## 5. 字段类型

### 5.1 基本字段类型

- **TextField**：文本字段
- **NumberField**：数字字段
- **DateField**：日期字段
- **BooleanField**：布尔字段
- **RelationField**：关联字段

### 5.2 RelationField 参数

```python
RelationField(
    model: Type['Model'],           # 关联的模型类
    field_name: Optional[str] = None,  # 字段名称
    null: bool = False,             # 是否允许为空
    description: Optional[str] = None,  # 字段描述
    pk: bool = False,               # 是否为主键
    follow_with: Optional[str] = None  # 用于自动更新关联的字段名
)
```

## 6. 模型 Meta 配置

```python
class Meta:
    worksheet_id = "your_worksheet_id"  # 工作表 ID
    conflict_fields = ["field1", "field2"]  # 冲突字段，用于 upsert
    cache = ["field1", "field2"]  # 需要缓存的字段
    pk_field = "primary_key"  # 主键字段
```

## 7. API 参考

### 7.1 HapConnection

```python
HapConnection(
    base_url: str,       # 明道云 API 基础地址
    app_key: str,        # 应用 Key
    app_secret: str,     # 应用 Secret
    access_token: str    # 访问令牌
)

# 方法
rows(model: Type[ModelType]) -> HapRowsQuery[ModelType]  # 获取模型查询对象
```

### 7.2 HapRowsQuery

```python
# 方法
filter(filter_expr: Union[str, Q]) -> HapRowsQuery  # 添加过滤条件
order_by(field: str) -> HapRowsQuery  # 添加排序
offset(value: int) -> HapRowsQuery  # 设置偏移量
limit(value: int) -> HapRowsQuery  # 设置限制数量
all() -> HapRowSet  # 执行查询并返回所有结果
first() -> Optional[ModelType]  # 执行查询并返回第一条结果
count() -> int  # 执行查询并返回记录数
stream() -> Generator[ModelType, None, None]  # 流式获取所有结果
```

### 7.3 HapRowSet

```python
# 方法
all() -> List[ModelType]  # 获取所有模型实例
first() -> Optional[ModelType]  # 获取第一个模型实例
last() -> Optional[ModelType]  # 获取最后一个模型实例
count() -> int  # 获取模型实例数量
create(**kwargs) -> ModelType  # 创建新模型实例
bulk_create(data_list: List[Dict[str, Any]]) -> List[ModelType]  # 批量创建模型实例
update(**kwargs) -> List[ModelType]  # 批量更新模型实例
delete() -> List[bool]  # 批量删除模型实例
upsert(data_list: List[Dict[str, Any]], exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> HapRowSet  # 批量 upsert 操作
```

## 8. 示例代码

### 8.1 完整示例

```python
from apps.data_opt.components.hapv2 import Model, TextField, RelationField, HapConnection, Q

# 1. 定义模型
class Currency(Model):
    currency_code = TextField(description="币种代码")
    currency_name = TextField(description="币种名称")
    
    class Meta:
        worksheet_id = "currency"
        conflict_fields = ["currency_code"]
        cache = ["currency_code", "currency_name"]

class Company(Model):
    company_name = TextField(description="公司名称")
    currencyCode = TextField(description="币种代码")
    currency = RelationField(Currency, follow_with="currencyCode", description="币种")
    
    class Meta:
        worksheet_id = "company"

# 2. 创建连接
hap_conn = HapConnection(
    base_url="https://api.mingdao.com",
    app_key="your_app_key",
    app_secret="your_app_secret",
    access_token="your_access_token"
)

# 3. 查询操作
print("=== 查询操作 ===")
# 获取所有公司
all_companies = hap_conn.rows(Company).all()
print(f"总公司数量: {all_companies.count()}")

# 条件查询
filtered_companies = hap_conn.rows(Company).filter(Q(company_name__contains="科技")).all()
print(f"科技公司数量: {filtered_companies.count()}")

# 4. 创建操作
print("\n=== 创建操作 ===")
new_company = hap_conn.rows(Company).create(
    company_name="新科技有限公司",
    currencyCode="CNY"
)
print(f"创建的公司: {new_company.company_name}, ID: {new_company.row_id}")

# 5. 更新操作
print("\n=== 更新操作 ===")
company_to_update = hap_conn.rows(Company).filter(Q(company_name__eq="新科技有限公司")).all()
updated_companies = company_to_update.update(company_name="更新后的科技有限公司")
print(f"更新了 {len(updated_companies)} 个公司")

# 6. Upsert 操作
print("\n=== Upsert 操作 ===")
upsert_data = [
    {"company_name": "Upsert 公司 1", "currencyCode": "CNY"},
    {"company_name": "Upsert 公司 2", "currencyCode": "USD"}
]
upsert_result = hap_conn.rows(Company).upsert(upsert_data)
print(f"Upsert 结果数量: {upsert_result.count()}")

# 7. 删除操作
print("\n=== 删除操作 ===")
companies_to_delete = hap_conn.rows(Company).filter(Q(company_name__contains="Upsert")).all()
delete_results = companies_to_delete.delete()
print(f"删除结果: {delete_results}")
```

### 8.2 高级示例：复杂查询和关联更新

```python
from apps.data_opt.components.hapv2 import Model, TextField, RelationField, HapConnection, Q

# 定义模型
class Group(Model):
    group_id = TextField(description="分组 ID")
    group_name = TextField(description="分组名称")
    
    class Meta:
        worksheet_id = "group"
        conflict_fields = ["group_id"]

class Currency(Model):
    currency_code = TextField(description="币种代码")
    currency_name = TextField(description="币种名称")
    
    class Meta:
        worksheet_id = "currency"
        conflict_fields = ["currency_code"]

class Company(Model):
    company_name = TextField(description="公司名称")
    currencyCode = TextField(description="币种代码")
    currency = RelationField(Currency, follow_with="currencyCode", description="币种")
    groupId = TextField(description="分组 ID")
    group = RelationField(Group, follow_with="groupId", description="分组")
    
    class Meta:
        worksheet_id = "company"

# 创建连接
hap_conn = HapConnection(
    base_url="https://api.mingdao.com",
    app_key="your_app_key",
    app_secret="your_app_secret",
    access_token="your_access_token"
)

# 复杂查询
print("=== 复杂查询 ===")
# 组合条件查询
companies = hap_conn.rows(Company).filter(
    (Q(company_name__contains="科技") & Q(currencyCode__eq="CNY")) |
    (Q(company_name__contains="互联网") & Q(currencyCode__eq="USD"))
).order_by("company_name").all()

print(f"符合条件的公司数量: {companies.count()}")
for company in companies.all():
    print(f"公司: {company.company_name}, 币种: {company.currencyCode}, 分组: {company.groupId}")

# 批量创建带关联的数据
print("\n=== 批量创建带关联的数据 ===")
companies_data = [
    {"company_name": "批量公司 1", "currencyCode": "CNY", "groupId": "G001"},
    {"company_name": "批量公司 2", "currencyCode": "USD", "groupId": "G002"}
]
created_companies = hap_conn.rows(Company).bulk_create(companies_data)
print(f"批量创建了 {len(created_companies)} 个公司")

# 批量更新
print("\n=== 批量更新 ===")
companies_to_update = hap_conn.rows(Company).filter(Q(company_name__contains="批量公司")).all()
updated_companies = companies_to_update.update(company_name="更新后的批量公司")
print(f"批量更新了 {len(updated_companies)} 个公司")
```

## 9. 注意事项

1. **API 速率限制**：明道云 API 有速率限制，请合理使用批量操作和缓存机制
2. **权限问题**：确保使用的 access_token 有足够的权限操作相应的工作表
3. **字段映射**：确保模型字段与明道云工作表字段名称一致
4. **关联字段**：使用 RelationField 时，确保关联的模型已正确定义
5. **缓存管理**：对于频繁更新的数据，注意缓存的时效性

## 10. 故障排除

### 10.1 常见错误

- **401 Unauthorized**：访问令牌无效或已过期
- **403 Forbidden**：权限不足
- **404 Not Found**：工作表 ID 不存在
- **429 Too Many Requests**：API 请求过于频繁，超过速率限制

### 10.2 解决方案

- 检查 access_token 是否正确且未过期
- 确保应用有相应工作表的操作权限
- 验证工作表 ID 是否正确
- 对于大量数据操作，使用分批处理或增加请求间隔
- 合理使用缓存机制，减少 API 调用次数

## 11. 版本历史

### v2.0
- 初始版本
- 支持基本的 CRUD 操作
- 支持关联字段和自动更新
- 支持复杂查询条件
- 支持批量操作和 upsert
- 内置缓存机制

## 12. 联系和支持

如有任何问题或建议，请联系模块维护者。