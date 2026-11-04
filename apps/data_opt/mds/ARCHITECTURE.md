# MDS 缓冲系统架构与设计文档

> **版本**：v1.0
> **更新日期**：2026-11-03
> **适用范围**：MDS 模块源码维护者 / 二次开发者
> **配套文档**：[README.md](./README.md)（新增表配置指南）

---

## 目录

- [1. 模块定位与边界](#1-模块定位与边界)
- [2. 分层架构](#2-分层架构)
- [3. 数据流与状态机](#3-数据流与状态机)
- [4. 核心设计理念](#4-核心设计理念)
- [5. 核心组件](#5-核心组件)
- [6. 校验体系](#6-校验体系)
- [7. 去重与覆盖机制](#7-去重与覆盖机制)
- [8. 同步机制](#8-同步机制)
- [9. 删除机制](#9-删除机制)
- [10. 迁移机制](#10-迁移机制)
- [11. 前端配置生成](#11-前端配置生成)
- [12. API 接口清单](#12-api-接口清单)
- [13. 文件结构](#13-文件结构)
- [14. 关键约定与规范](#14-关键约定与规范)
- [15. 维护操作手册](#15-维护操作手册)

---

## 1. 模块定位与边界

MDS（Master Data Staging）是 **APS 主数据从外部系统到正式表之间的清洗缓冲层**。

**解决的问题**：
- 外部系统数据质量参差，需校验后才能写入 APS 正式表
- 主数据间存在外键依赖，需按依赖顺序导入
- 多账套同步需求（一份清洗后数据可推到多个 APS 账套）
- 数据变动需可追溯、可重试、可撤销

**不解决的问题**：
- 业务数据（生产订单、工单等）的清洗——仅处理 7 张主数据表
- 正式表之间的业务联动——MDS 只负责 staging → 正式表的单向推送

**7 张主数据表**（按依赖顺序）：

| 顺序 | 表键 | 显示名 | 依赖 |
|------|------|--------|------|
| 1 | `t_material` | 物料 | — |
| 2 | `t_mat_ver` | 产线版本 | 物料 |
| 3 | `t_workcenter` | 工作中心 | — |
| 4 | `t_mat_wc` | 工艺路线 | 物料、工作中心、产线版本 |
| 5 | `t_mat_wc_bom` | BOM | 物料、产线版本、工艺路线 |
| 6 | `t_mold` | 模具 | — |
| 7 | `t_mat_wc_mold` | 机台模具关联 | 物料、工作中心、模具、工艺路线 |

顺序常量定义于 `_base.TABLE_PROCESS_ORDER`，`/validate_all` 与 `/sync_all` 按此顺序处理。

---

## 2. 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    staging_routers.py                       │  API 层
│   接收 / 校验触发 / 同步触发 / 列表查询 / 删除 / 迁移         │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                   staging_cleaner.py                        │  业务层
│   StagingProcessor  DataCleaner  DataTransformer            │
│   STAGING_TABLE_CONFIG（统一配置中心）                       │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│  _base.py          staging_models.py    validators.py        │  模型层
│  状态枚举/工具函数  StagingModel 定义   业务规则/结构校验钩子 │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│  config_generator.py    utils/duplicate_checker.py          │  支撑层
│  前端配置生成            去重检测 + 内容比对                  │
│  utils/excel_parser.py  migrations/                         │
│  Excel 解析             差异检测 + ALTER TABLE 生成          │
└─────────────────────────────────────────────────────────────┘
```

**数据库分工**：
- **PostgreSQL（`THIS_DB_NAME`）**：所有 `t_xxx_staging` 缓冲表 + `t_validation_error` + `t_transform_rule`
- **MySQL（`MYAPS_DBSET_LIST` 多账套）**：APS 正式表（`t_material` 等），同步目标

---

## 3. 数据流与状态机

### 3.1 端到端数据流

```
外部系统 / Excel
    │  POST /mds/{table_key}  或  POST /mds/upload/{table_name}
    ▼
apply_dedup_strategy（去重 + 内容比对）
    │  overwrite: 删旧 → 插新；skip: 跳过；reject: 拒绝整批
    ▼
insert_to_staging_table（INSERT 到 t_xxx_staging，状态=pending）
    │  POST /mds/validate/{table_name}  或  /validate_all
    ▼
StagingProcessor.process_staging
    │  pre_batch_hook（表级，如 BOM 结构校验）
    │  └─ 逐条：fill_defaults → validate_from_config → 写回状态
    │     pre_validate_hook → Schema 校验 → 外键 → 重复 → business_rules → config_rules → post_validate_hook
    │  post_batch_hook（表级）
    ▼
relation_pass / compliance_error / relation_error
    │  POST /mds/sync/{table_name}  或  /sync_all
    ▼
StagingProcessor.sync_to_production
    │  先处理 removing（删正式表 + 删缓冲表）
    │  mode=refresh: TRUNCATE 正式表
    │  relation_pass + sync_error（重试 < max_retries）→ db_bupsert → 正式表
    ▼
synced / sync_error
```

### 3.2 状态枚举（`StagingStatus`）

定义于 `_base.py:20`，8 个状态：

| 值 | 标签 | 颜色 | 含义 |
|----|------|------|------|
| `pending` | 待处理 | warning | 刚导入或被编辑重置，等待校验 |
| `compliance_pass` | 初检通过 | info | Schema 校验通过（当前代码中未实际写入，校验直接进 relation_pass） |
| `compliance_error` | 初检错误 | danger | 合规校验失败（必填/枚举/范围/长度/结构错误） |
| `relation_pass` | 联检通过 | success | 全部校验通过，可同步 |
| `relation_error` | 联检错误 | warning | 外键校验失败 |
| `sync_error` | 推送失败 | warning | 同步正式表失败，可重试 |
| `synced` | 已推送 | secondary | 同步成功 |
| `removing` | 待删除 | secondary | 标记删除，下次同步时真正删除 |

**状态优先级**（同条记录多种错误时）：`compliance_error` > `relation_error` > `relation_pass`（仅警告时）。

### 3.3 手动删除模式（`ManualRemoveMode`）

定义于 `_base.py:54`，由环境变量 `MDS_MANUAL_REMOVE` 控制：

| 值 | 含义 | 行为 |
|----|------|------|
| `never` | 禁止删除 | 所有删除接口直接返回失败 |
| `now` | 立即删除 | DELETE 物理删除缓冲表记录 |
| `next` | 延迟删除 | UPDATE 状态为 `removing`，下次 `/sync` 时统一处理 |

---

## 4. 核心设计理念

### 4.1 三段式清洗

**导入 → 校验 → 同步** 三阶段完全解耦，每阶段独立 API、独立事务、可重复执行。
- 导入只写 staging 表，不触发校验
- 校验只改 staging 表状态，不碰正式表
- 同步只读 `relation_pass` 状态记录写正式表

### 4.2 配置化（STAGING_TABLE_CONFIG）

**单一配置源**：`staging_cleaner.py:40` 的 `STAGING_TABLE_CONFIG` 字典是所有表配置的唯一入口，校验器、同步器、路由器、前端配置生成器都从此读取。

配置化程度评估：

| 能力 | 配置化程度 |
|------|-----------|
| 字段校验（必填/枚举/范围/长度） | ✅ 零配置（从 Schema 自动提取） |
| 外键校验（单约束/多维约束） | ✅ 纯配置 |
| 简单业务规则（比较/范围/正数/不等） | ✅ 纯配置（`config_rules`） |
| 复杂业务规则（跨表/复合外键） | ⚠️ 需编码（`business_rules`） |
| 表结构定义 | ⚠️ 需编码定义 ProtoModel + StagingModel |
| 前端列展示 | ✅ 自动生成 + 例外覆盖 |

### 4.3 Schema 驱动

Pydantic Schema 是字段元数据的**唯一来源**：必填、枚举、范围（ge/gt/le/lt）、max_length、description 全部从 `schema.model_fields` 自动提取，不重复声明。

### 4.4 解耦原则

- **迁移与列配置解耦**：迁移链路读 `StagingModel._meta.fields_map`，前端列配置读 `ProtoModel._meta.fields_map`，两者独立
- **校验与业务规则分离**：标准校验（Schema 提取）零代码，业务规则走 `config_rules`/`business_rules`/钩子
- **正式表 ORM 不参与迁移**：`proto_model` 仅用于业务主键提取和列配置，迁移只 diff Staging 表

### 4.5 内容比对优化

`overwrite` 策略下不盲目覆盖：导入相同数据时通过 `compare_content` 逐字段比对，内容一致则跳过，避免无意义的 DELETE + INSERT 抖动正式表。

---

## 5. 核心组件

### 5.1 StagingBaseModel（`_base.py:77`）

所有缓冲表的抽象基类，提供 11 个内部字段：

| 字段 | 用途 |
|------|------|
| `_staging_id` | 缓冲表主键（SERIAL） |
| `_source_system` | 来源系统标识（如 `excel`、`unknown`） |
| `_source_id` | 源系统中的 ID |
| `_status` | 处理状态（StagingStatus 枚举） |
| `_error_msg` | 错误信息 JSON |
| `_transform_rules` | 应用的转换规则 JSON |
| `_retry_count` | 同步E重试次数 |
| `_createtime` / `_updatetime` | 创建/更新时间 |
| `_synced_id` / `_synced_time` | 同步后正式表 ID / 同步时间 |

### 5.2 STAGING_TABLE_CONFIG（`staging_cleaner.py:40`）

每张表的配置项：

| 字段 | 必填 | 说明 |
|------|------|------|
| `schema` | ✅ | Pydantic 校验 Schema |
| `model` | ✅ | StagingModel 类（缓冲表） |
| `proto_model` | ✅ | 正式表模型（提取业务主键、生成列配置） |
| `foreign_keys` | ❌ | 外键配置列表 |
| `display_name` | ❌ | 显示名称 |
| `validator` | ❌ | 自定义校验入口函数 |
| `config_rules` | ❌ | 配置化业务规则列表 |
| `business_rules` | ❌ | 复杂业务规则列表（含 validator 函数） |
| `business_keys` | ❌ | 业务主键字段（默认从 proto_model 自动提取） |
| `pre_batch_hook` / `post_batch_hook` | ❌ | 表级钩子 |
| `pre_validate_hook` / `post_validate_hook` | ❌ | 行级钩子 |
| `drop_fields` | ❌ | 外键校验时跳过的字段 |

### 5.3 DataCleaner（`staging_cleaner.py:323`）

无状态校验器，提供 7 类校验方法：
- `validate_required_from_schema` / `validate_enums_from_schema` / `validate_ranges_from_schema` / `validate_max_lengths_from_schema`：从 Schema 自动提取
- `validate_foreign_keys_from_config`：从配置提取，支持单约束与多维约束（`conditions`）
- `check_duplicate`：缓冲表内重复检测
- `validate_from_config`：编排上述所有校验 + 钩子 + business_rules + config_rules

### 5.4 StagingProcessor（`staging_cleaner.py:829`）

清洗编排器，两个核心方法：
- `process_staging(table_name, batch_size)`：校验循环，分批处理 pending 记录直到清空或达 max_batches
- `sync_to_production(table_name, ..., mode, target_db)`：同步到正式表，处理 removing + TRUNCATE + db_bupsert + 状态回写

### 5.5 DataTransformer（`staging_cleaner.py:766`）

基于 `t_transform_rule` 表的运行时数据转换，支持字段映射、默认值填充、枚举值映射。当前代码中保留但未在主链路使用。

---

## 6. 校验体系

### 6.1 校验执行顺序（`validate_from_config`）

| 步骤 | 内容 | 来源 |
|------|------|------|
| 0 | `pre_validate_hook`（行级前置） | 配置 |
| 1 | 必填字段 | Schema 自动提取 |
| 2 | 枚举值 | Schema 自动提取 |
| 3 | 数值范围（ge/gt/le/lt） | Schema 自动提取 |
| 4 | 字符串长度（max_length） | Schema 自动提取 |
| 5 | 外键存在性 | `foreign_keys` 配置 |
| 6 | 缓冲表内重复 | `business_keys` |
| 7 | `business_rules`（复杂规则） | 配置 + 自定义函数 |
| 8 | `config_rules`（简单规则） | 配置化工厂函数 |
| 9 | `post_validate_hook`（行级后置） | 配置 |

表级钩子 `pre_batch_hook` 在 `process_staging` 开始时执行一次，`post_batch_hook` 在结束时执行一次。

### 6.2 外键校验两种模式

**单约束**（向后兼容）：
```python
{"field": "materialno", "model": TMaterialStaging,
 "value_field": "materialno", "label_field": "description"}
```

**多维约束**（复合外键）：
```python
{"field": "matver", "model": TMatVerStaging,
 "conditions": [
     {"local": "materialno", "foreign": "materialno"},
     {"local": "matver",    "foreign": "matver"}
 ]}
```
多维约束通过 `conditions` 指定本地字段与外键字段的映射，全部条件字段都有值才校验。`value_field`/`label_field` 缺省时由 `/fk-options` 推导。

**removing 排除**：外键校验自动 `.exclude(_status=StagingStatus.REMOVING)`，待删除记录不作为有效外键。

### 6.3 config_rules 工厂函数（`_base.py:647`）

| 工厂 | 用途 | 示例 |
|------|------|------|
| `create_comparison_rule(a, b, op, msg)` | 字段比较（>`>=`<`<=`==`） | `create_comparison_rule("lotmin", "lotmax", ">", "最小批量不能大于最大批量")` |
| `create_range_rule(field, min, max, msg)` | 范围校验 | `create_range_rule("scrap", 0, 100, "损耗率0-100")` |
| `create_positive_rule(field, msg)` | 正数校验 | `create_positive_rule("qty", "数量必须大于0")` |
| `create_not_equal_rule(a, b, msg)` | 不等校验 | `create_not_equal_rule("productno", "materialno", "父件≠子件")` |

### 6.4 ErrorType 枚举（`_base.py:61`）

8 种错误类型：`REQUIRED_FIELD` / `INVALID_ENUM` / `INVALID_TYPE` / `INVALID_RANGE` / `INVALID_LENGTH` / `FK_NOT_FOUND` / `DUPLICATE_KEY` / `BUSINESS_RULE`。

错误记录写入 `t_validation_error` 表，含 `suggestion` 修复建议字段。

### 6.5 内置结构校验钩子（`validators.py`）

| 钩子 | 校验内容 |
|------|---------|
| `bom_structure_check_hook` | BOM 循环引用、父子同号、孤立项、多父项、单位一致性 |
| `mat_wc_route_check_hook` | 工序项重复、顺序号非整数、物料号为空、工作中心为空、顺序号重复、工作中心重复 |
| `validate_material_type_e_rules` | E 类（自制件）物料必须有工艺路线 + BOM + 产线版本（缺产线版本时 `pdv.auto_matver` 可自动生成） |

钩子产出的错误通过 `context['batch_errors']` 传递给 `process_staging`，与逐条校验错误合并。`bom_structure_error` 视为合规错误（阻断同步），`bom_structure_warning` 仅警告不阻断。

### 6.6 产线版本自动补充

#### 6.6.1 两条路径

| 路径 | 配置开关 | 触发位置 | 行为 |
|------|----------|----------|------|
| **缓冲表校验** | `staging_auto_matver` | `t_material` 的 `post_batch_hook`（`auto_matver_from_refs_hook`） | 扫描 `t_mat_wc_staging`/`t_mat_wc_bom_staging` 的产线版本组合，批量补充到 `t_mat_ver_staging` |
| **直接写正式表** | `auto_matver` | `post_material` 路由（`routers.py:513`） | 用预设值 `pdv.MATVER`（如 `V1`）为 E 类物料生成产线版本，异步写正式表 |

两个开关独立，互不影响。`auto_matver` 仅路由直接模式生效，`staging_auto_matver` 仅缓冲表校验生效。

**互斥机制**：`post_material` 路由在 staging 模式下（`routers.py:499` 的 `is_staging_mode` 分支）已 `return`，`auto_matver` 分支（`routers.py:513`）只在直接模式执行；`staging_auto_matver` 钩子只在 `process_staging` 路径触发，直接模式不调 `process_staging`。两条路径写不同的表（`t_mat_ver` 正式表 vs `t_mat_ver_staging` 缓冲表），**两开关同时为 true 不会重复创建产线版本**，无需互斥防护。

#### 6.6.2 缓冲表自动补充机制（`staging_auto_matver`）

**触发条件**：`pdv.staging_auto_matver == True`，在 `t_material` 批量校验完成后（`post_batch_hook`）执行。

**钩子位置选择**：挂在 `t_material` 而非 `t_mat_wc_bom`（顺序末尾）。因 `TABLE_PROCESS_ORDER` 为 `t_material → t_mat_ver → t_workcenter → t_mat_wc → t_mat_wc_bom`，钩子须在 `t_mat_ver` 校验与 `t_mat_wc` 外键校验**之前**补充 `t_mat_ver_staging`，否则 `t_mat_wc` 外键校验 `(materialno, matver) ∈ t_mat_ver_staging` 会失败。

**前置条件**：钩子扫描 `t_mat_wc_staging`/`t_mat_wc_bom_staging` 已导入数据。基于三阶段解耦设计（导入→校验→同步，见 4.1），推荐通过 `/validate_all` 整体校验。单表 `/validate?table_name=t_material` 时若 `t_mat_wc_staging` 尚未导入，钩子静默补 0 条（不报错），后续单表校验 `t_mat_wc` 时外键校验会暴露缺失，不会静默错同步。

**执行流程**：

```
1. 查 t_material_staging 中 type=="E" 的料号集合
2. 扫描 t_mat_wc_staging WHERE materialno IN (E型料号) → DISTINCT (materialno, matver)
3. 扫描 t_mat_wc_bom_staging WHERE productno IN (E型料号) → DISTINCT (productno, matver)
4. 合并组合 → 正则过滤 ^[A-Za-z0-9\-]+$ → 去重
5. 查 t_mat_ver_staging 已有组合 → 差集
6. 批量 bulk_create（_source_system="SYS_AUTO"）
```

**与逐条校验的关系**：`validate_material_type_e_rules` 中，`staging_auto_matver=True` 时不报"缺产线版本"错误（批量钩子会补充）；`False` 时报 `BUSINESS_RULE` 错误。

**正则过滤**：`matver` 需匹配 `^[A-Za-z0-9\-]+$`（字母、数字、杠），不匹配的跳过（如空值、占位符 `"🈳❗"`）。

**幂等性**：已存在于 `t_mat_ver_staging` 的组合跳过，不重复创建。

**自动生成的记录字段**：

| 字段 | 值 | 来源 |
|------|----|------|
| `materialno` | 扫描出的料号 | `t_mat_wc_staging.materialno` / `t_mat_wc_bom_staging.productno` |
| `matver` | 扫描出的版本号 | `t_mat_wc_staging.matver` / `t_mat_wc_bom_staging.matver` |
| `lotfrom` | `pdv.MATVER_LOTFROM`（默认 `0`） | `defaults.lotfrom` |
| `lotto` | `pdv.MATVER_LOTTO`（默认 `9999999`） | `defaults.lotto` |
| `priority` | `pdv.MATVER_PRIORITY`（默认 `0`） | `defaults.priority` |
| `_source_system` | `"SYS_AUTO"` | 常量，标记系统自动生成 |

#### 6.6.3 激活配置

编辑租户配置文件 `project_files/{PROJECT_DIR}/{PROJECT_JSON}.json`，在 `defaults` 节添加 `"staging_auto_matver": true`：

```json
{
  "defaults": {
    "staging_auto_matver": true,
    "lotfrom": 0,
    "lotto": 9999999,
    "priority": 0
  }
}
```

重启服务使配置生效。`auto_matver`（直接模式）保持独立配置，不受影响。

---

## 7. 去重与覆盖机制

实现于 `utils/duplicate_checker.py`。

### 7.1 三种去重策略（`DedupStrategy`）

| 策略 | 行为 |
|------|------|
| `overwrite`（默认） | 内容不同 → 删旧插新；内容相同 → 跳过 |
| `skip` | 已存在 → 跳过，不更新 |
| `reject` | 发现任何重复 → 拒绝整批 |

### 7.2 内容比对（`compare_content`）

- **partial 模式**（默认）：`new_data` 中不存在的字段跳过比对（部分更新语义，与 API `model_dump(exclude_none=True)` 一致）
- **full 模式**：所有字段参与比对，未传递字段视为 None
- 空字符串与 None 等价（`normalize_value`）
- 字符串比较忽略大小写
- 数值型字符串自动转 float 比较

### 7.3 removing 状态恢复

`overwrite` 策略下，若已存在记录处于 `removing` 状态，自动恢复为 `pending` 再覆盖，避免"先删后导同一条数据"导致数据丢失。

### 7.4 内部重复处理

同一批次内含相同业务主键的多条记录：
- `overwrite`：保留最后一条，前面的跳过
- `skip` / `reject`：全部视为重复

---

## 8. 同步机制

### 8.1 两种同步模式

| 模式 | 行为 |
|------|------|
| `incremental`（默认） | 仅同步 `relation_pass` + `sync_error`（重试 < max_retries）的记录 |
| `refresh` | 先 TRUNCATE 正式表，再同步全部记录（`skip_truncate` 用于分批调用时后续批次跳过 TRUNCATE） |

### 8.2 多账套同步（`/sync` 路由）

`target_dbs` 为空时同步到 `MYAPS_DBSET_LIST` 全部账套。多账套策略：
1. **第一步**：逐账套同步，`update_status=False`（不更新缓冲表状态）
2. **第二步**：汇总所有账套的 `synced_staging_ids`，统一更新缓冲表状态为 `synced`

避免某账套成功后状态被改，另一账套失败时无法重试。

### 8.3 removing 处理（`sync_to_production` 步骤 1）

同步前先处理 `removing` 状态记录：
- **incremental 模式**：按 `business_keys` 删除正式表对应记录，再删缓冲表记录
- **refresh 模式**：正式表已被 TRUNCATE，直接删缓冲表记录

### 8.4 冲突键去重追踪

同步前计算每条数据的冲突键（`DbManager._get_conflict_fields`），若同一批次内存在相同冲突键，除最后一条外其余标记为 `sync_error`（`duplicate_key`），避免 `db_bupsert` 静默去重导致状态错乱。

### 8.5 失败重试

- 同步失败 → `_retry_count += 1`，状态置 `sync_error`
- 重试超过 `max_retries`（默认 3）的记录不再参与同步
- `/retry_failed/{table_name}` 接口可重置失败记录为 `pending` 重新校验
- `/sync` 接口的 `reset_retry=true` 可重置所有 `relation_pass` 记录的 retry_count

---

## 9. 删除机制

### 9.1 三种删除接口

| 接口 | 范围 | 行为 |
|------|------|------|
| `DELETE /mds/delete/{table_name}/{staging_id}` | 单条 | 按 `MDS_MANUAL_REMOVE` 模式处理 |
| `POST /mds/batch_delete/{table_name}` | 批量（传 staging_ids） | 按 `MDS_MANUAL_REMOVE` 模式处理 |
| `DELETE /mds/clear/{table_name}` | 全表（可按 status_filter 过滤） | 按 `MDS_MANUAL_REMOVE` 模式处理 |

### 9.2 三种删除模式（`ManualRemoveMode`）

| 模式 | 行为 |
|------|------|
| `never` | 所有删除接口返回失败 |
| `now` | 立即物理删除（DELETE FROM） |
| `next` | 标记为 `removing`，下次 `/sync` 时统一删除正式表 + 缓冲表记录 |

### 9.3 removing 状态的保护

- `removing` 状态记录**禁止编辑**：`/update` 和 `/batch_update` 接口检测到 `removing` 直接返回失败
- 外键校验排除 `removing` 记录：不作为有效外键存在
- `overwrite` 导入时自动恢复 `removing` 为 `pending`（见 7.3）

### 9.4 编辑重置状态

`/update` 和 `/batch_update` 修改记录后自动将状态重置为 `pending`、清空 `_error_msg`，触发重新校验。

### 9.5 ExternalDataSet.persist 的 drop 参数

`apps/data_opt/components/_base.py` 的 `ExternalDataSet.persist()` 方法支持 `drop` 参数，透传给路由后按模式分流：

| 模式 | 调用链 | 操作对象 | 行为 |
|------|--------|----------|------|
| **清洗模式**（db_name=staging） | `persist` → `post_mat_wc` → `dispatch_to_staging` → `mark_as_removing` | **缓冲表**（如 `t_mat_wc_staging`） | 将匹配记录 `_status` 标记为 `removing`（软删除），不物理删除 |
| **直接模式**（db_name=账套） | `persist` → `post_mat_wc` → `drop_matched_data` | **正式表**（如 `t_mat_wc`） | 物理删除匹配记录（`db_delete`） |

**仅三表支持**（`_DROP_SUPPORTED_TABLES`）：`t_mat_wc` / `t_mat_wc_bom` / `t_mat_wc_mold`，其余表静默忽略 `drop`。

**匹配字段**（`STAGING_TABLE_CONFIG` 的 `drop_fields`）：

| 表 | drop_fields |
|----|-------------|
| `t_mat_wc` | `["materialno", "matver"]` |
| `t_mat_wc_bom` | `["productno", "matver"]` |
| `t_mat_wc_mold` | `["materialno", "itemno"]` |

**清洗模式下的完整流程**：`mark_as_removing` 标记匹配记录为 `removing` → 随后 `insert_to_staging_table` 写入新数据 → 新数据状态为 `pending`。被标记的旧记录受 9.3 保护机制约束（禁止编辑、外键排除、overwrite 可恢复）。

---

## 10. 迁移机制

实现于 `migrations/` 子目录。

### 10.1 ModelDiffer（`model_diff.py`）

对比 ORM 模型与数据库实际表结构，生成 ALTER TABLE 语句。

**两种侦测路径**：

| 场景 | 行为 |
|------|------|
| 表不存在 | 优先从 `scripts/migrate/staging/staging_tables.sql` 加载完整建表脚本（含索引/注释/触发器）；脚本不可用时降级到动态生成 CREATE TABLE |
| 表已存在 | 逐字段对比 `_meta.fields_map` 与 `information_schema.columns`，新增字段生成 `ALTER TABLE ADD COLUMN` |

**字段类型映射**（`FIELD_TYPE_MAPPING`）：
- `CharField` → `VARCHAR(max_length)`
- `IntField` → `INTEGER`
- `FloatField` → `DOUBLE PRECISION`
- `DecimalField` → `DECIMAL(max_digits, decimal_places)`
- `DatetimeField` → `TIMESTAMP`
- `TextField` → `TEXT`
- `JSONField` → `JSONB`
- 其他 → `VARCHAR(255)` 兜底

### 10.2 迁移链路

```
/migrate/diff  →  ModelDiffer.diff_all(STAGING_MODEL_MAPPING)
                   │  STAGING_MODEL_MAPPING = {table_key: config["model"]}  ← 取 Staging 模型
                   ▼
                   逐表 diff(model_class)
                   │  读 model_class._meta.fields_map
                   │  对比 information_schema.columns
                   ▼
                   生成 AlterStmt 列表
/migrate/execute → 逐条执行 ALTER TABLE，记录版本号 V{yyyyMMddHHmmss}
```

### 10.3 迁移与列配置解耦

| 层 | 依赖 | 用途 |
|----|------|------|
| 迁移链路 | `STAGING_MODEL_MAPPING` → Staging 模型 `_meta.fields_map` | 侦测表结构变动，生成 DDL |
| 前端列配置 | `_TABLES_COLUMNS_CONFIG` + `_generate_columns_from_proto()` | 前端列名/顺序/隐藏 |

修改列配置（`_TABLES_COLUMNS_CONFIG`）**不触发迁移**；修改 ORM 字段不影响列配置（列配置自动跟随 ProtoModel 的 `description` 和字段顺序）。

### 10.4 SchemaVersionManager（`version_manager.py`）

通过 `t_schema_version` 表记录迁移版本，提供 `ensure_table_exists` / `record_version` / `version_exists` 等方法。当前 `migrate_router.py` 的 `/versions` 接口返回空列表，完整版本记录需启用此管理器。

---

## 11. 前端配置生成

实现于 `config_generator.py`。

### 11.1 三大配置字典

| 字典 | 用途 |
|------|------|
| `TABLE_DISPLAY_CONFIG` | 表展示元数据（路由、图标、渐变色、关键词搜索字段、默认排序） |
| `_TABLES_COLUMNS_CONFIG` | 列覆盖与隐藏（override + exclude） |
| `_PAGE_FILTER_CONFIG` | 筛选字段分类（string_fields / number_fields） |
| `SYSTEM_RUNTIME_CONFIG` | 运行时参数（分页大小、批大小、外键选项限制） |

### 11.2 列配置自动生成（`_generate_columns_from_proto`）

```
列顺序 = ProtoModel 字段定义顺序
列标题 = field.description（缺失则用字段名）
override：列属性覆盖（title/sortable/readOnly/width/after）
exclude：隐藏字段（显式维护，含审计字段）
extra field（不在 proto_model 中）：按 after 定位插入，未指定 after 追加到列尾
```

最终列 = `SYSTEM_COMMON_COLUMNS_PREFIX` + 业务列 + `SYSTEM_COMMON_COLUMNS_SUFFIX`。

### 11.3 SYSTEM_RUNTIME_CONFIG

| 参数 | 默认 | 用途 |
|------|------|------|
| `defaultPageSize` | 500 | 列表默认每页条数 |
| `validateBatchSize` | 200 | 校验批次大小 |
| `syncBatchSize` | 200 | 同步批次大小 |
| `fkOptionsLimit` | 50 | 外键下拉选项上限 |
| `selectAllPageSize` | 10000 | 全选所有页时一次获取上限 |

### 11.4 Excel 模板同源

`utils/excel_parser.py` 的 `get_table_field_mappers()` 从 `_generate_columns_from_proto` 生成字段映射，**Excel 导入模板、Excel 导出模板、前端列展示三者同源**，均从 ProtoModel 自动生成。

---

## 12. API 接口清单

路由前缀 `/mds`，定义于 `staging_routers.py`。

### 12.1 数据导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/{table_key}` | 接收数据列表，支持 `dedup_strategy` / `update_mode` |
| POST | `/upload/{table_name}` | Excel/CSV 上传，参数同上 |

### 12.2 校验与同步

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/validate/{table_name}` | 校验单表 |
| POST | `/validate_all` | 按依赖顺序校验全部（可指定 `table_name`） |
| POST | `/sync/{table_name}` | 同步单表到正式表，支持 `mode`/`target_dbs`/`reset_retry` |
| POST | `/sync_all` | 按依赖顺序同步全部 |
| POST | `/retry_failed/{table_name}` | 重置失败记录为 pending 重试 |

### 12.3 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/list/{table_name}` | 分页查询（支持状态/来源/关键词/精准筛选/排序） |
| GET | `/detail/{table_name}/{staging_id}` | 单条详情 |
| GET | `/errors/{table_name}` | 校验错误记录 |
| GET | `/status/{table_name}` | 状态统计 |
| GET | `/monitor/summary` | 全表监控汇总 |
| GET | `/index-config` | 首页模块配置 |
| GET | `/index-stats` | 首页统计数据（并发查询） |

### 12.4 元数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/rules/{table_key}` | 完整校验规则文档 |
| GET | `/rules/list` | 所有表列表 |
| GET | `/status-meta` | 状态元数据（value/label/color） |
| GET | `/fk-options/{table_key}/{field_name}` | 外键下拉选项（支持 `conditions` 多维约束前置条件） |
| GET | `/dblist` | 账套列表 |

### 12.5 编辑与删除

| 方法 | 路径 | 说明 |
|------|------|------|
| PATCH | `/update/{table_name}/{staging_id}` | 更新单条（重置为 pending） |
| POST | `/batch_update/{table_name}` | 批量更新（跳过 removing 记录） |
| DELETE | `/delete/{table_name}/{staging_id}` | 删除单条 |
| POST | `/batch_delete/{table_name}` | 批量删除 |
| DELETE | `/clear/{table_name}` | 清空（可按 status 过滤） |

### 12.6 迁移（`/mds/migrate`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/migrate/check-permission` | 校验 DDL 权限 |
| GET | `/migrate/diff` | 检测差异 |
| POST | `/migrate/execute` | 执行迁移 |
| GET | `/migrate/versions` | 迁移历史 |

---

## 13. 文件结构

```
apps/data_opt/mds/
├── README.md                    # 新增表配置指南（用户面向）
├── ARCHITECTURE.md              # 本文档（架构与设计）
├── __init__.py
├── _base.py                     # 状态枚举、StagingBaseModel、工具函数、BusinessRule 工厂
├── staging_models.py            # 7 张 StagingModel 定义 + ValidationError + TransformRule
├── staging_cleaner.py           # STAGING_TABLE_CONFIG + DataCleaner + StagingProcessor + DataTransformer
├── staging_routers.py           # 所有 /mds API 路由
├── validators.py                # 业务规则校验函数 + BOM/工艺路线结构校验钩子
├── config_generator.py          # 前端配置生成（列/筛选/展示）
├── utils/
│   ├── duplicate_checker.py     # 去重策略 + 内容比对
│   └── excel_parser.py          # Excel/CSV 解析 + 导出
└── migrations/
    ├── migrate_router.py        # /mds/migrate 路由
    ├── model_diff.py            # ORM vs DB 差异检测 + ALTER/CREATE 生成
    └── version_manager.py       # 迁移版本记录管理
```

---

## 14. 关键约定与规范

### 14.1 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 缓冲表名 | `t_{业务名}_staging` | `t_material_staging` |
| StagingModel 类 | `T{业务名}Staging` | `TMaterialStaging` |
| ProtoModel 类 | `Proto{业务名}` | `ProtoMaterial` |
| Python 字段名 | snake_case | `materialno` |
| 数据库列名 | PascalCase（`source_field`） | `MaterialNo` |
| 内部字段 | `_` 前缀 | `_staging_id`、`_status` |

### 14.2 业务主键提取优先级（`extract_business_keys_from_model`）

1. `unique_together` 约束（最高优先级，复合主键）
2. `unique=True` 的字段（单字段主键）
3. 主键字段（排除自增 `id` / `vid`）

**常见陷阱**：模型有自增主键 `vid` 时，自动提取返回 `['vid']` 导致去重失效。解决：在 ProtoModel 配置 `unique_together` 或在 `STAGING_TABLE_CONFIG` 显式配置 `business_keys`。

### 14.3 审计字段隐藏约定

新增审计字段（`sys_user` / `sys_date` / `sys_stamp` / `vid` / `treeno`）到 ProtoModel 时，**必须同步在 `_TABLES_COLUMNS_CONFIG` 的 `exclude` 中追加**，否则会暴露到前端列。`override` 中写 `hidden` 不生效（会被透传到前端但不保证隐藏），隐藏一律走 `exclude`。

### 14.4 表处理顺序

`TABLE_PROCESS_ORDER` 固定为：`t_material → t_mat_ver → t_workcenter → t_mat_wc → t_mat_wc_bom → t_mold → t_mat_wc_mold`。`/validate_all` 和 `/sync_all` 按此顺序处理，确保外键依赖先于引用方就绪。

### 14.5 状态重置约定

- 编辑记录（`/update`、`/batch_update`）→ 状态重置为 `pending`、`_error_msg` 清空
- 重新校验前清空本批记录的旧 `_error_msg`，防止旧错误影响新校验结果
- `removing` 状态记录禁止编辑

### 14.6 配置初始化延迟

`STAGING_TABLE_CONFIG` 在模块加载时不完整（`table_name`、`defaults`、`business_keys` 待 Tortoise 连接建立后才能提取）。`ensure_config_initialized()` 提供延迟初始化，所有读取配置的入口必须先调用此函数。

### 14.7 多账套同步状态更新

多账套同步时，**先同步所有账套（不更新状态），再统一更新缓冲表状态**。避免某账套成功后状态被改，另一账套失败时无法重试。

---

## 15. 维护操作手册

> 本章面向 AI agent 与二次开发者，提供常见扩展的步骤清单、环境变量集中表、排障路径、联动检查表、代码陷阱索引，使 agent 能据此自主扩展维护。

### 15.1 环境变量集中清单

| 变量 | 默认 | 定义位置 | 用途 |
|------|------|----------|------|
| `THIS_DB_NAME` | `appsmith` | `core/settings.py` | PostgreSQL 缓冲库连接名（所有 staging 表所在） |
| `THIS_DB_HOST` / `THIS_DB_PORT` / `THIS_DB_USER` / `THIS_DB_PASSWORD` | — | `.env` | PostgreSQL 连接参数 |
| `MYAPS_DB_SET` | — | `core/settings.py` | MySQL 账套列表，逗号分隔 |
| `MYAPS_DBSET_LIST` | 派生 | `core/settings.py` | `MYAPS_DB_SET.split(",")`，同步目标账套 |
| `MYAPS_MAIN_DB` | `DBSET_LIST[0]` | `core/settings.py` | 主账套，`sync_to_production` 默认目标 |
| `MYAPS_DB_HOST` / `MYAPS_DB_PORT` / `MYAPS_DB_USER` / `MYAPS_DB_PASSWORD` | — | `.env` | MySQL 连接参数（多账套共用） |
| `MDS_MANUAL_REMOVE` | `never` | `core/settings.py:231` | 删除模式：`never`/`now`/`next`（见 9.2） |

**注意**：`MDS_MANUAL_REMOVE` 在 `settings.py` 中以 `str.lower()` 解析，与 `ManualRemoveMode` 枚举值字符串直接 `==` 比较，未做 `ManualRemoveMode()` 构造，新增枚举值时只需保证字符串一致。

### 15.2 五类常见扩展步骤

#### A. 新增一张主数据表

详见 [README.md](./README.md) 六步流程。联动检查：见 15.4 联动表第 1 行。

#### B. 新增一种 config_rules 工厂函数

**适用**：简单字段级规则（如正则、字符串前缀、字段间算术关系）。

1. 在 `_base.py` 末尾 `create_*_rule` 工厂区新增函数，签名 `(field..., error_message) -> BusinessRule`
2. 内部 `validate(data) -> bool` 返回 **True 表示违反规则**
3. 选择合适的 `error_type`（默认 `BUSINESS_RULE`，范围类用 `INVALID_RANGE`）
4. 在 `STAGING_TABLE_CONFIG` 对应表的 `config_rules` 列表中引用
5. 无需改其他文件——`validate_from_config` 步骤 8 自动遍历 `config_rules`

**反例**：跨表查询、复合外键存在性校验——走 `business_rules` + 自定义 async 函数，不要塞进 `config_rules`（`config_rules.validate` 是同步的，无法 await）。

#### C. 新增一种去重策略

1. 在 `utils/duplicate_checker.py` 的 `DedupStrategy` 枚举新增成员
2. 在 `apply_dedup_strategy` 函数新增 `elif strategy == DedupStrategy.XXX:` 分支，返回 `(processed_data, handled_data)`
3. 在 `staging_routers.py` 的 `staging_endpoint` 与 `upload_excel` 的 `dedup_strategy` Query 描述里补充新值
4. 测试：构造已存在 + 新数据 + 内部重复三种场景验证

**注意**：`apply_dedup_strategy` 内 `OVERWRITE` 分支会自动恢复 `removing` 状态记录为 `pending`（`duplicate_checker.py:516`），新策略若涉及覆盖语义需保留此行为。

#### D. 新增一种同步模式

1. 在 `StagingProcessor.sync_to_production` 的 `mode` 参数文档补充新值
2. 在 `staging_routers.py` 的 `sync_to_production` 路由 `mode` Query 描述补充
3. 在 `sync_to_production` 方法内分支处理：
   - `removing` 处理（步骤 1）通常复用，按新模式决定是否先 TRUNCATE
   - 查询待同步记录的 `_status` 条件可能不同
4. 多账套同步逻辑（`staging_routers.py:341`）通常无需改——它按 `update_status` 参数控制状态回写

#### E. 新增表级/行级钩子

1. 在 `validators.py` 编写 `async def hook(processor/cleaner, table_name/data, context/staging_id[, errors]) -> dict/list`
   - 表级前置：`async (processor, table_name, context) -> dict`
   - 表级后置：`async (processor, table_name, context, stats) -> dict`
   - 行级前置：`async (cleaner, data, staging_id) -> list[dict]`
   - 行级后置：`async (cleaner, data, staging_id, errors) -> list[dict]`
2. 在 `STAGING_TABLE_CONFIG` 对应表配置 `pre_batch_hook` / `post_batch_hook` / `pre_validate_hook` / `post_validate_hook`，单函数直接挂、多函数用列表
3. 表级钩子产出错误通过 `context['batch_errors']` 传递给 `process_staging` 合并；`bom_structure_error` 视为合规错误阻断同步，`bom_structure_warning` 仅警告

### 15.3 排障路径

#### 现象：记录卡在 `pending` 不进入校验

1. 查 `GET /mds/status/{table_name}` 确认 pending 数量
2. 手动触发 `POST /mds/validate/{table_name}` 看返回 stats
3. 若 stats 全 0：检查 `STAGING_MODEL_MAPPING` 是否含该 table_key（`staging_cleaner.py:251`）
4. 若报"未知的缓冲表"：`STAGING_TABLE_CONFIG` 缺配置或 `ensure_config_initialized()` 未调用

#### 现象：记录 `relation_error` 但看不出原因

1. `GET /mds/errors/{table_name}?staging_id=xxx` 查 `t_validation_error` 表
2. 或直接查 staging 表 `_error_msg` JSON 字段（含完整错误列表）
3. `error_type=fk_not_found` → 外键表无对应记录，或外键表记录处于 `removing` 状态（被排除）
4. `error_type=bom_structure_error` → `pre_batch_hook` 检出，看 `context['batch_errors']`

#### 现象：同步失败 `sync_error` 反复

1. `GET /mds/status/{table_name}` 看 `retry_exceeded`（`_retry_count >= 3`）
2. 查 staging 表 `_error_msg`，常见原因：
   - `schema_error`：Schema 转换失败（字段类型不符）
   - `duplicate_key`：同批次内冲突键重复，被 `db_bupsert` 去重
   - `sync_error`：`db_bupsert` 抛异常，看 message
3. 修复数据后 `POST /mds/retry_failed/{table_name}` 重置为 pending 重新校验
4. 或 `POST /mds/sync/{table_name}?reset_retry=true` 重置 retry_count 后重试

#### 现象：迁移 `/migrate/diff` 检测不到新增字段

1. 确认字段加在 **StagingModel** 或 **ProtoModel**（继承会传导到 Staging）
2. 确认 `STAGING_MODEL_MAPPING` 用的是 `config["model"]`（Staging 模型）非 `proto_model`
3. 确认字段名不以 `_` 开头且不在 `model_diff.py:418` 的跳过列表
4. 表不存在时走 `staging_tables.sql` 脚本，不会 diff 字段——需先建表

#### 现象：前端列暴露了审计字段

1. 该字段在 `_TABLES_COLUMNS_CONFIG[table_key]["exclude"]` 里吗？
2. `override` 里写 `hidden` 无效——隐藏一律走 `exclude`
3. 新增审计字段到 ProtoModel 后必须同步追加到 `exclude`（见 14.3）

### 15.4 联动检查表

改 X 后必须同步检查 Y、Z：

| 改动 X | 必须同步检查 |
|--------|-------------|
| ProtoModel 新增/删除字段 | ① StagingModel（继承自动传导，无需改）② `_TABLES_COLUMNS_CONFIG.exclude`（审计字段要追加）③ Schema（对应字段声明）④ `foreign_keys.conditions` 中引用该字段处 ⑤ 迁移 `/migrate/diff` + `/execute` ⑥ Excel 模板（自动同源，无需改） |
| StagingModel 自身新增字段 | ① `_TABLES_COLUMNS_CONFIG.override` 用 `after` 定位插入 ② 迁移 diff ③ Schema（若需校验） |
| `STAGING_TABLE_CONFIG` 新增表 | ① `staging_models.py` 定义 StagingModel ② `TABLE_PROCESS_ORDER` 追加（按依赖顺序）③ `TABLE_DISPLAY_CONFIG` 追加（前端展示）④ `_TABLES_COLUMNS_CONFIG` 追加（列配置）⑤ `_PAGE_FILTER_CONFIG` 追加（筛选字段） |
| `business_keys` 改动 | ① 去重逻辑（`DuplicateChecker`）② 重复检测（`check_duplicate`）③ 同步冲突键（`DbManager._get_conflict_fields`）④ removing 删除条件（`sync_to_production` 步骤 1） |
| `foreign_keys` 改动 | ① `/fk-options` 接口（`value_field`/`label_field`/`conditions`）② 前端外键配置（`config_generator.py:482`）③ 校验顺序（`validate_from_config` 步骤 5） |
| `StagingStatus` 新增状态 | ① `StagingStatus.get_meta` ② `MONITOR_STATUS_FIELDS`（`staging_routers.py:30`）③ 监控 SQL（`get_monitor_summary`/`get_index_stats` 的 FILTER 子句）④ 前端状态映射 |
| `ManualRemoveMode` 新增模式 | ① 三个删除接口（`/clear`、`/delete`、`/batch_delete`）的分支 ② `.env.example` 文档 |
| `TABLE_PROCESS_ORDER` 调整 | ① `/validate_all` 与 `/sync_all` 顺序 ② 确保外键依赖先于引用方 |
| `SYSTEM_RUNTIME_CONFIG` 改动 | ① 各路由的 `batch_size`/`page_size`/`limit` 默认值兜底 ② 前端运行时配置 |

### 15.5 代码陷阱索引

| 陷阱 | 位置 | 说明 |
|------|------|------|
| 配置延迟初始化 | `staging_cleaner.py:257` `_config_initialized` | 模块加载时 `STAGING_TABLE_CONFIG` 不完整，`table_name`/`defaults`/`business_keys` 待 Tortoise 连接建立后填充。读取配置前必须调 `ensure_config_initialized()` |
| removing 状态自动恢复 | `duplicate_checker.py:516,586` | `overwrite` 策略下，已存在记录若处于 `removing`，自动 `update_from_dict({_status: PENDING}).save()` 恢复后再覆盖。改去重逻辑时勿破坏此行为，否则"先删后导同一条"会丢数据 |
| 状态优先级判断 | `staging_cleaner.py:979` | 同条记录多种错误时：`compliance_error` > `relation_error` > `relation_pass`（仅警告）。`has_compliance_error` 排除 `fk_not_found` 和 `bom_structure_warning` |
| `drop_fields` 作用 | `STAGING_TABLE_CONFIG` 各表 | 外键校验时跳过的字段（如 `t_mat_wc` 的 `["materialno", "matver"]`），避免复合外键的局部字段被单独校验。当前代码中未实际消费此配置（外键校验由 `foreign_keys` 控制），保留作扩展 |
| `_error_msg` 清空时机 | `staging_cleaner.py:903` | 每批 pending 记录处理前先清空旧 `_error_msg`，防止旧错误影响新校验结果。改批处理逻辑时勿移除 |
| `db_bupsert` 静默去重 | `staging_cleaner.py:1275` | 同批次内相同冲突键会被 `db_bupsert` 去重，`distinct_total < len(staging_ids)` 时多余记录标记为 `sync_error`。改同步逻辑时需保留此去重追踪 |
| 多账套两步提交 | `staging_routers.py:341` | 多账套同步先全部 `update_status=False` 同步，再统一回写状态。改为单步提交会导致某账套失败时其他账套已成功记录无法回滚 |
| `MDS_MANUAL_REMOVE` 字符串比较 | `core/settings.py:231` + `staging_routers.py:785` 等 | 该变量是 `str` 类型，与 `ManualRemoveMode.NEVER`（`str` Enum）直接 `==` 比较，未做 Enum 构造。新增枚举值时字符串必须完全一致（已 `.lower()`） |
| `extract_business_keys_from_model` 自增主键 | `_base.py:275` | 模型有 `vid`/`id` 自增主键且无 `unique_together`/`unique=True` 时，提取返回 `['vid']` 导致去重失效。新表必须配 `unique_together` 或显式 `business_keys` |
| `compare_content` 大小写不敏感 | `duplicate_checker.py:84` | 字符串字段比对 `.lower()`，数值型字符串自动转 float。改比对逻辑时注意此规范化 |
| `staging_tables.sql` 优先 | `model_diff.py:382` | 表不存在时优先从 `scripts/migrate/staging/staging_tables.sql` 加载完整建表脚本（含索引/注释/触发器），脚本不存在才降级动态生成。新增表时建议同步更新此 SQL 文件 |
| `_TABLES_COLUMNS_CONFIG` extra field `after` | `config_generator.py:366` | 不在 `proto_model._meta.fields_map` 的字段（如 StagingModel 自身新增）需在 `override` 用 `after` 定位插入，未指定 `after` 追加到列尾。漏配会丢失列 |

### 15.6 测试入口

当前 `tests/` 目录**无 MDS 模块专属测试**，仅有间接相关的业务键校验测试：
- `tests/test_business_key_validation.py`
- `tests/test_get_mo_by_supplyno_validation.py`
- `tests/test_validation_error_record_key.py`

**新增 MDS 测试建议**：
- 校验逻辑：mock `STAGING_TABLE_CONFIG` + `DataCleaner.validate_from_config`，覆盖必填/枚举/范围/外键/重复/钩子
- 去重策略：`apply_dedup_strategy` 三策略 × partial/full 两模式，含 removing 恢复场景
- 同步：mock `db_bupsert`，覆盖 incremental/refresh、单/多账套、removing 处理、冲突键去重
- 迁移：`ModelDiffer.diff` 表不存在/表已存在/字段新增三场景

**手动验证流程**（无单测时）：
1. 启动服务：`./scripts/dev_server.sh restart`
2. 导入测试数据：`POST /mds/{table_key}` 或 `POST /mds/upload/{table_name}`
3. 校验：`POST /mds/validate/{table_name}`，查 `GET /mds/status/{table_name}`
4. 同步：`POST /mds/sync/{table_name}`，查正式表数据
5. 查日志：`./scripts/dev_server.sh logs -f`，关注 `[校验]`、`[BOM校验钩子]`、`同步统计` 关键词

### 15.7 修改后重启提醒

MDS 模块改动涉及 `STAGING_TABLE_CONFIG` / `STAGING_MODEL_MAPPING` / `_TABLES_COLUMNS_CONFIG` / `TABLE_DISPLAY_CONFIG` 等模块级常量，**修改后必须重启服务**才能生效（`./scripts/dev_server.sh restart`）。热重载可能因 Tortoise 连接已建立而不会重新初始化配置。

---

**维护者**：MDS 模块开发团队
**最后更新**：2026-11-03