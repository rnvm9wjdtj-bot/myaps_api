# 代码优化清单

**生成时间**: 2026-05-21  
**审查范围**: apps/io_api/routers.py, core/settings.py  
**优先级**: P0 > P1 > P2 > P3

---

## 🔴 P0 - 严重问题（必须修复）

### 1. 修复运行时导入失败风险

**位置**: `apps/io_api/routers.py:54-106`

**问题描述**:  
`dispatch_to_staging`函数内部动态导入`staging_cleaner`、`staging_routers`和`duplicate_checker`模块。这些模块依赖`tortoise-orm`和`pandas`等库。当项目依赖未完全安装时，这些导入会在函数调用时失败，而不是在模块加载时失败，导致运行时错误难以调试。

**影响范围**:  
- 生产环境可能崩溃
- 用户无法使用清洗功能
- 错误信息不友好，难以排查

**修复方案**:
```python
# 方案1: 将导入移到模块顶部
try:
    from apps.data_opt.mds.staging_cleaner import STAGING_TABLE_CONFIG, ensure_config_initialized
    from apps.data_opt.mds.staging_routers import insert_to_staging_table, delete_existing_records
    from apps.data_opt.mds.utils.duplicate_checker import apply_dedup_strategy, DedupStrategy
    STAGING_MODULES_AVAILABLE = True
except ImportError as e:
    STAGING_MODULES_AVAILABLE = False
    logger.warning(f"Staging modules not available: {e}")

# 方案2: 在函数中检查
async def dispatch_to_staging(...):
    if not STAGING_MODULES_AVAILABLE:
        return {
            "success": 0,
            "message": "清洗模块未安装，请检查依赖配置",
            "data": None,
            "meta": {}
        }
    # ... 继续处理
```

**验收标准**:
- [ ] 依赖缺失时有清晰的错误提示
- [ ] 不影响其他功能的正常使用
- [ ] 错误信息记录到日志

---

### 2. 统一API响应格式

**位置**: `apps/io_api/routers.py:96-106`

**问题描述**:  
`dispatch_to_staging`函数返回的响应结构（第96-106行）与路由函数原有的`standard_response`格式不一致：
- staging响应：`{"success": 1, "message": "...", "data": {...}, ...}`
- 标准响应：`{"success": 1, "message": "...", "data": None, "meta": {...}}`

**影响范围**:  
- 客户端需要处理两种不同的响应格式
- 增加前端代码复杂度
- 容易导致字段访问错误

**修复方案**:
```python
async def dispatch_to_staging(...):
    try:
        # ... 现有逻辑
        return {
            "success": 1,
            "message": f"导入完成: 新增{inserted_count - overwrite_count}条, 覆盖{overwrite_count}条, 跳过{skip_count}条",
            "data": None,  # 保持与标准响应一致
            "meta": {
                "total": len(data_list),
                "inserted": inserted_count,
                "overwritten": overwrite_count,
                "skipped": skip_count,
                "handled_details": handled_data[:20] if handled_data else []
            }
        }
    except Exception as e:
        logger.error(f"清洗模式处理失败: {str(e)}", exc_info=True)
        return {
            "success": 0,
            "message": f"清洗模式处理失败: {str(e)}",
            "data": None,
            "meta": {}
        }
```

**验收标准**:
- [ ] staging模式响应格式与标准格式一致
- [ ] 所有响应都包含data和meta字段
- [ ] 更新API文档说明

---

## 🟡 P1 - 高风险问题（强烈建议修复）

### 3. 添加参数验证

**位置**: `apps/io_api/routers.py:341-342`

**问题描述**:  
新增的Query参数`dedup_strategy`、`update_mode`未进行有效性验证，如果传入无效字符串会抛出`ValueError`。

```python
source_system: str = Query("unknown", description="来源系统")
dedup_strategy: str = Query("overwrite", description="去重策略: overwrite/skip/reject")
update_mode: str = Query("partial", description="更新模式: partial-部分更新/full-完整更新")
```

**影响范围**:  
- 无效参数导致运行时错误
- 用户无法理解参数取值范围
- API文档不清晰

**修复方案**:
```python
from enum import Enum
from fastapi import Query

class DedupStrategyEnum(str, Enum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    REJECT = "reject"

class UpdateModeEnum(str, Enum):
    PARTIAL = "partial"
    FULL = "full"

# 在路由函数中使用
@router.post("/material")
async def upload_material(
    data: List[MaterialData],
    db_name: str,
    source_system: str = Query("unknown", description="来源系统"),
    dedup_strategy: DedupStrategyEnum = Query(DedupStrategyEnum.OVERWRITE, description="去重策略"),
    update_mode: UpdateModeEnum = Query(UpdateModeEnum.PARTIAL, description="更新模式"),
):
    # FastAPI会自动验证参数并生成API文档
    pass
```

**验收标准**:
- [ ] 无效参数返回400错误
- [ ] API文档显示枚举值
- [ ] 错误信息清晰

---

### 4. 确保错误状态正确传播

**位置**: `apps/io_api/routers.py:44-51, 97`

**问题描述**:  
`dispatch_to_staging`函数始终返回`"success": 1`（第97行），即使操作过程中出现错误。这导致客户端无法感知真实的操作状态。

**影响范围**:  
- 客户端误认为操作成功
- 无法触发错误处理逻辑
- 监控系统无法捕获失败

**修复方案**:
```python
async def dispatch_to_staging(...):
    try:
        # ... 执行清洗操作
        
        # 检查是否有错误
        if not result or result.get("success") == 0:
            return {
                "success": 0,
                "message": result.get("message", "清洗操作失败"),
                "data": None,
                "meta": {}
            }
        
        # 成功响应
        return {
            "success": 1,
            "message": f"导入完成: 新增{inserted_count - overwrite_count}条, 覆盖{overwrite_count}条, 跳过{skip_count}条",
            "data": None,
            "meta": {...}
        }
        
    except Exception as e:
        logger.error(f"清洗模式处理失败", exc_info=True)
        return {
            "success": 0,
            "message": f"清洗模式处理失败: {str(e)}",
            "data": None,
            "meta": {}
        }
```

**验收标准**:
- [ ] 操作失败时返回success=0
- [ ] 错误信息记录到日志
- [ ] 客户端能正确识别失败状态

---

## 🟢 P2 - 中等问题（建议修复）

### 5. 消除代码重复

**位置**: 多个路由函数（第347-358行、第417-428行等）

**问题描述**:  
每个POST路由函数都有相同的staging模式检查代码块，违反DRY原则。

**重复代码示例**:
```python
# 第347-358行
db_name = db_name.replace(" ", "")
if is_staging_mode(db_name):
    logger.info(f"路由分发: upload_material -> 清洗模式 (db_name={db_name})")
    staging_response = await dispatch_to_staging(
        table_key="t_material",
        data=data,
        source_system=source_system,
        dedup_strategy=dedup_strategy,
        update_mode=update_mode
    )
    return map_staging_response_to_direct(staging_response)
```

**影响范围**:  
- 维护成本高
- 修改逻辑时容易遗漏
- 代码可读性差

**修复方案**:
```python
# 方案1: 创建装饰器
import functools

def staging_aware_endpoint(table_key: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(
            request: Request,
            data: List,
            db_name: str,
            source_system: str = "unknown",
            dedup_strategy: str = "overwrite",
            update_mode: str = "partial",
            **kwargs
        ):
            db_name = db_name.replace(" ", "")
            
            if is_staging_mode(db_name):
                logger.info(f"路由分发: {func.__name__} -> 清洗模式 (db_name={db_name})")
                staging_response = await dispatch_to_staging(
                    table_key=table_key,
                    data=data,
                    source_system=source_system,
                    dedup_strategy=dedup_strategy,
                    update_mode=update_mode
                )
                return map_staging_response_to_direct(staging_response)
            
            logger.info(f"路由分发: {func.__name__} -> 直接模式 (db_name={db_name})")
            return await func(request, data, db_name, **kwargs)
        
        return wrapper
    return decorator

# 使用装饰器
@router.post("/material")
@staging_aware_endpoint(table_key="t_material")
async def upload_material(data: List[MaterialData], db_name: str, ...):
    # 只处理直接模式逻辑
    pass

# 方案2: 创建中间件（略）
```

**验收标准**:
- [ ] 代码重复度降低
- [ ] 功能行为不变
- [ ] 单元测试通过

---

### 6. 添加类型检查和异常处理

**位置**: `apps/io_api/routers.py:74, 76, 93-94`

**问题描述**:  
关键操作缺少类型检查和异常处理：
- 第74行: `data_list = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in data]`
- 第76行: `strategy = DedupStrategy(dedup_strategy)` - 未验证枚举值
- 第93-94行: 假设`handled_data`是列表，但未验证类型

**影响范围**:  
- 边界情况可能崩溃
- 错误信息不友好
- 代码健壮性差

**修复方案**:
```python
# 第74行: 添加异常处理
try:
    data_list = []
    for item in data:
        if hasattr(item, "model_dump"):
            data_list.append(item.model_dump())
        elif isinstance(item, dict):
            data_list.append(item)
        else:
            raise ValueError(f"不支持的数据类型: {type(item)}")
except Exception as e:
    logger.error(f"数据转换失败: {str(e)}", exc_info=True)
    return {
        "success": 0,
        "message": f"数据转换失败: {str(e)}",
        "data": None,
        "meta": {}
    }

# 第76行: 添加枚举验证
try:
    strategy = DedupStrategy(dedup_strategy)
except ValueError:
    raise HTTPException(
        status_code=400,
        detail=f"无效的去重策略: {dedup_strategy}，有效值为: {[s.value for s in DedupStrategy]}"
    )

# 第93-94行: 添加类型检查
if not isinstance(handled_data, list):
    logger.warning(f"handled_data类型异常: {type(handled_data)}")
    handled_data = []
overwrite_count = len([h for h in handled_data if isinstance(h, dict) and h.get("action") == "overwrite"])
```

**验收标准**:
- [ ] 类型错误有友好提示
- [ ] 不影响正常流程
- [ ] 添加单元测试

---

## ⚪ P3 - 轻微问题（可选优化）

### 7. 移除冗余映射

**位置**: `apps/io_api/routers.py:29-37`

**问题描述**:  
`TABLE_KEY_MAPPING`字典包含重复映射，键和值相同：
```python
TABLE_KEY_MAPPING = {
    "t_material": "t_material",  # 冗余
    "t_material_staging": "t_material",
    "t_supplier": "t_supplier",  # 冗余
    "t_supplier_staging": "t_supplier",
    # ...
}
```

**影响范围**:  
- 代码冗余，影响可读性
- 维护时容易混淆

**修复方案**:
```python
# 方案1: 删除冗余项，保留有意义的映射
TABLE_KEY_MAPPING = {
    "t_material_staging": "t_material",
    "t_supplier_staging": "t_supplier",
    "t_customer_staging": "t_customer",
    # ...
}

# 方案2: 添加注释说明用途
TABLE_KEY_MAPPING = {
    # 直接表映射（可能用于兼容旧代码）
    "t_material": "t_material",
    # 暂存表映射
    "t_material_staging": "t_material",
    # ...
}
```

**验收标准**:
- [ ] 功能不受影响
- [ ] 添加必要注释

---

### 8. 配置化硬编码值

**位置**: `core/settings.py:164`

**问题描述**:  
`STAGING_DB_NAME = "--s"`硬编码在代码中，不够灵活。

**影响范围**:  
- 修改需要改代码
- 不利于环境区分
- 配置不够集中

**修复方案**:
```python
# core/settings.py
import os

# 从环境变量读取，提供默认值
STAGING_DB_NAME = os.getenv("STAGING_DB_NAME", "--s").strip()

# 或者从配置文件读取
from globalobjects.json_manager import JSONManager
config = JSONManager.load_config("staging_config.json")
STAGING_DB_NAME = config.get("staging_db_name", "--s")
```

**验收标准**:
- [ ] 支持环境变量配置
- [ ] 更新.env.example文件
- [ ] 更新AGENTS.md文档

---

## 执行计划

### 第一阶段（P0问题） - 预计2-4小时
1. 修复导入失败风险
2. 统一API响应格式
3. 编写单元测试验证

### 第二阶段（P1问题） - 预计2-3小时
4. 添加参数验证（使用枚举）
5. 修复错误状态传播
6. 更新API文档

### 第三阶段（P2问题） - 预计3-5小时
7. 重构代码消除重复
8. 添加类型检查和异常处理
9. 补充单元测试

### 第四阶段（P3问题） - 预计1小时
10. 清理冗余代码
11. 配置化硬编码值
12. 更新相关文档

---

## 风险评估

| 优先级 | 问题数量 | 总耗时 | 风险等级 |
|--------|---------|--------|---------|
| P0 | 2 | 2-4小时 | 🔴 高 - 可能导致生产事故 |
| P1 | 2 | 2-3小时 | 🟡 中高 - 影响用户体验 |
| P2 | 2 | 3-5小时 | 🟢 中 - 影响代码质量 |
| P3 | 2 | 1小时 | ⚪ 低 - 优化建议 |

**总预计工作量**: 8-13小时

---

## 验收标准

### 功能验收
- [ ] 所有单元测试通过
- [ ] 集成测试通过
- [ ] API功能正常

### 质量验收
- [ ] 代码审查通过
- [ ] 无新增linter警告
- [ ] 文档已更新

### 性能验收
- [ ] 响应时间无明显增加
- [ ] 内存使用无明显增加

---

**备注**: 
1. 建议按优先级顺序执行
2. 每完成一个阶段进行代码提交
3. P0问题修复后应立即部署测试环境验证
4. 所有修改应保持向后兼容