# API 数据校验报错排查指南

> 本文档供**外部系统**调用 MyAPS API 时，收到 422 校验错误后快速定位自身数据问题使用。

---

## 1. 如何读懂 422 报文

当请求数据校验失败时，API 返回 HTTP 422，响应格式如下：

```json
{
  "status_code": 422,
  "success": 0,
  "message": "数据验证错误",
  "meta": {
    "error_details": [
      {
        "field": "body->8->priority",
        "input": "高",
        "record_key": {
          "materialno": "M002",
          "matver": "V1",
          "itemno": "020"
        },
        "message": "Input should be a valid integer, unable to parse string as an integer",
        "type": "int_parsing"
      }
    ]
  },
  "data": null
}
```

**关键字段解读**：

| 字段 | 含义 | 示例 |
|------|------|------|
| `field` | 出错字段位置 | `body->8->priority` = 请求数组第 8 个元素的 `priority` 字段 |
| `type` | 错误类型代码 | `int_parsing` = 字符串无法解析为整数 |
| `message` | 错误描述 | `Input should be a valid integer...` |
| `input` | **出错字段的实际传入值** | `"高"` = 您传了 `"高"`，应为整数 |
| `record_key` | **出错记录的唯一标识** | `{"materialno":"M002","matver":"V1","itemno":"020"}` = 凭此业务键定位出错记录 |

> `body->索引->字段名` 中的索引从 0 开始，对应请求数组中的元素位置。
>
> **`input` 字段说明**：当 `type` 为 `missing`（必填字段缺失）时不携带此字段；字段级错误返回出错字段的实际传入值，跨字段业务规则错误（`field` 为 `body->索引` 级别、`type=value_error`）返回整条记录，方便您直接对照修正，无需回查原始请求体。
>
> **`record_key` 字段说明**：返回出错记录的唯一标识字段（如物料的 `materialno`、工序的 `materialno+matver+itemno`、供应的 `materialno+supplyno` 等）。若唯一标识中的某个字段本身缺失，则 `record_key` 中不包含该字段——此时结合 `field` 和 `type=missing` 即可判断是哪个标识字段未传。

---

## 2. 错误类型速查表

| type | 含义 | 应如何修正 |
|------|------|-----------|
| `int_type` | 字段需要整数，但传入了 `null` 或非整数类型 | 传整数数字，或省略该字段（若有默认值） |
| `int_parsing` | 字符串无法解析为整数 | 传纯整数字符串或整数，如 `"1"` 或 `1`，勿传 `"1.5"`、`"abc"` |
| `float_type` | 字段需要浮点数，但传入了 `null` 或非数字类型 | 传数字，或省略该字段 |
| `float_parsing` | 字符串无法解析为浮点数 | 传数字字符串或数字，如 `"1.5"` 或 `1.5` |
| `string_type` | 字段需要字符串，但传入了 `null`、数字、数组等 | 传字符串值，或省略可选字段 |
| `string_too_long` | 字符串超过最大长度 | 缩短字符串 |
| `enum` | 枚举字段传入了非法值 | 传本文档列出的合法值之一 |
| `greater_than_equal` | 数值小于允许的最小值 | 传大于等于最小值的数 |
| `less_than_equal` | 数值大于允许的最大值 | 传小于等于最大值的数 |
| `greater_than` / `less_than` | 数值未满足边界约束 | 调整数值至合法范围 |
| `missing` | 必填字段未提供 | 补充该字段 |
| `datetime_parsing` | 日期格式无法解析 | 传标准日期格式，如 `"2025-01-07 10:00:00"` |
| `decimal_parsing` | Decimal 字段传入了非数字字符串 | 传数字或数字字符串 |
| `value_error` | 业务规则校验失败 | 参考具体 message 描述 |

---

## 3. 排查步骤

1. **定位出错字段**：从 `field` 提取字段名和数组索引，找到请求数据中对应的元素
2. **判断错误类型**：查第 2 节速查表，了解错误原因
3. **查字段要求**：在本文档第 4 节找到对应 API，查看该字段的类型、约束、合法值
4. **修正数据**：按字段要求修改传入值，重新调用 API

---

## 4. 各 API 字段校验规则

> **通用规则**：
> - 数值字段（int/float）**请勿传 `null`**，应传数字或省略该字段（省略时使用默认值）
> - 枚举字段大小写不敏感（如 `"mo"` 等效 `"MO"`），但传非法值会报错
> - 未列出的可选字符串字段（如 `memo`、`free1` 等）可传字符串或省略，勿传 `null`
> - 请求体为 JSON 数组，如 `[{字段...}, {字段...}]`

### 4.1 POST /t_material — 新增或修改物料

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | — | 料号 |
| description | str | — | 物料名称 |
| leadday | int | ≥0 | 交期（天） |
| grday | int | ≥0 | 收货质检（天） |
| abc | 枚举 | A / B / C | ABC分类 |
| unit | str | — | 单位 |
| type | 枚举 | E / F | 物料类型（E=自制件, F=采购件） |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| fifo | int | 0 或 1 | 1=FIFO 0=最近原则 |
| expday | int | ≥0 | 保质期（天） |
| phantommin | int | ≥0 | 虚拟时间（分） |
| firmday | int | ≥0 | 固定天数 |
| daygap | int | ≥0 | MTO拆分天数 |
| preday | int | ≥0 | 向前冲销(天) |
| subday | int | ≥0 | 向后冲销(天) |
| price | Decimal | ≥0 | 价格 |
| lotfix | float | ≥0 | 固定批 |
| lotround | float | ≥0 | 取整 |
| lotss | float | ≥0 | 安全库存 |
| lotpoint | float | ≥0 | 重订货点 |
| lottop | float | ≥0 | 最大库存点 |
| phantom | 枚举 | Y / N | 虚拟件 |
| candelay | 枚举 | Y / N | 可否延迟 |
| lotsize | 枚举 | 见下方 | 批量 |

**lotsize 合法值**：`EX` `FX` `VB` `D1`-`D6` `W1`-`W4` `M1`-`M3`

**常见错误**：
- `fifo`/`leadday`/`grday`/`daygap` 等数值字段传 `null` → `int_type`，应传数字或省略
- `abc` 传 `"D"` → `enum`，应传 `A`/`B`/`C`
- `type` 传 `"X"` → `enum`，应传 `E`/`F`
- `leadday`/`grday` 缺失 → `missing`

### 4.2 POST /t_workcenter — 新增或修改工作中心

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| workcenter | str | ≤32字 | 工作中心代码 |
| workcentername | str | ≤255字 | 工作中心名称 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| pri_wc | int | — | 优先级 |
| capnum | int | >0 | 默认机台数 |
| capmax | int | >0 | 最大机台数 |
| worker | float | ≥0 | 工时 |
| finite | 枚举 | Y / N | 有限 |
| type | 枚举 | Y / N | 首页显示 |
| bottleneck | 枚举 | Y / N | 瓶颈 |

> 本接口数值字段容错性较好，传 `null` 或非数字字符串会自动使用默认值。

**常见错误**：
- `finite`/`type` 传 `"X"` → `enum`，应传 `Y`/`N`
- `workcenter`/`workcentername` 缺失或传 `null` → `missing` / `string_type`

### 4.3 POST /t_mat_wc — 新增或修改工序

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | ≤64字 | 料号 |
| matver | str | ≤4字 | 产线版本 |
| workcenter | str | ≤32字 | 工作中心 |
| basesec | float | ≥0 | 节拍T/T(秒/100) |
| sortno | int | 0-999 | 序号 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| fixqty | int | ≥0 | 额定量 |
| fixsec | int | ≥0 | 额定时间(秒) |
| offsetsec | int | — | 偏置+/-(秒) |
| lotsec | int | — | 批量时间(秒) |
| lotsize | float | — | 批量大小 |
| rate | float | ≥0 | 配比 |
| sf | 枚举 | S / F / Z | 并行S/串行F/并结Z |

**常见错误**：
- `sortno`/`basesec` 传 `null` 或 `"abc"` → `int_type`/`float_type`，应传数字
- `fixqty`/`fixsec` 传 `"abc"` → `int_type`，应传数字（传 `null` 或 `""` 可兜底为 0）
- `lotsec`/`lotsize`/`rate` 传 `null` 或 `"abc"` → 类型错误，应传数字
- `sf` 传 `"X"` → `enum`，应传 `S`/`F`/`Z`

### 4.4 POST /t_mat_ver — 新增或修改产线版本

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | ≤64字 | 料号 |
| matver | str | ≤4字 | 产线版本号 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| lotfrom | int | — | 批量起点 |
| lotto | int | — | 批量终点 |
| priority | int | — | 优先级 |
| active | 枚举 | Y / N | 生效 |

> 本接口数值字段容错性较好，传 `null` 或非数字字符串会自动使用默认值。

**常见错误**：
- `active` 传 `"X"` → `enum`，应传 `Y`/`N`
- `materialno`/`matver` 缺失 → `missing`

### 4.5 POST /t_mat_wc_bom — 新增或修改 BOM

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| productno | str | ≤64字 | 产品料号 |
| matver | str | ≤4字 | 产线版本 |
| itemno | str | ≤6字 | 工序项目 |
| materialno | str | ≤64字 | 子件料号 |
| qty | float | ≥0 | 数量 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| offsethour | int | — | 偏置+/-(小时) |
| scrap | float | ≥0 | 报废率% |
| mto | 枚举 | Y / N | MTO |
| alt | 枚举 | Y / N | 是否替代 |

> 本接口允许传入额外字段（不会报错）。

**常见错误**：
- `qty` 传 `null` 或 `"abc"` → `float_type`，应传数字
- `offsethour` 传 `null` 或 `"abc"` → `int_type`，应传数字
- `mto`/`alt` 传 `"X"` → `enum`，应传 `Y`/`N`

### 4.6 POST /t_mold — 新增或修改模具

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| moldno | str | ≤64字 | 模具编号 |
| moldname | str | ≤64字 | 模具名称 |
| type | str | ≤4字 | 类型 |
| status | str | ≤6字 | 状态 |
| moldnum | int | >0 | 模具穴数 |
| qty | int | >0 | 模具台数 |

**常见错误**：
- `moldnum`/`qty` 传 `null` 或 `"abc"` → `int_type`，应传正整数
- `moldnum`/`qty` 传 `0` 或负数 → `greater_than`，应传 ≥1
- `type`/`status` 传 `null` → `string_type`，应传字符串

### 4.7 POST /t_mat_wc_mold — 新增或修改机台模具配置

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | ≤64字 | 料号 |
| workcenter | str | ≤64字 | 工作中心 |
| itemno | str | ≤6字 | 工序项目 |
| basesec | float | ≥0 | 节拍T/T(秒/100) |
| priority | int | — | 优先级 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| fixsec | int | ≥0 | 额定时间(秒) |
| worker | float | ≥0 | 人员 |

**常见错误**：
- `basesec` 传 `null` 或 `"abc"` → `float_type`，应传数字
- `priority` 传 `null` 或 `"abc"` → `int_type`，应传整数
- `worker` 传 `null` 或 `"abc"` → `float_type`，应传数字

### 4.8 POST /t_supply — 新增或修改供应记录

> 供应来源包含：生产计划 PL、生产工单 MO、库存 ST、采购订单 PO

**写入行为**：按 `supplyno` 整条覆盖。系统先删除该 `supplyno` 在 `t_supply`、`t_orderwc`、`t_demand`、`t_peg` 四张表的全部存量记录，再插入本批数据；批内同一 `supplyno` 仅保留最后一条。调用方需知：推送某 `supplyno` 会一并清除其已有的工序 / 需求 / peg 关联记录。

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | ≤64字 | 料号 |
| supplyno | str | ≤64字 | 供应单号 |
| type | 枚举 | PL / MO / PR / PO / ST | 类型 |
| avail_qty | float | ≥0 | 可用数量 |
| avail_date | str | — | 可用日期 / 开工日期 |
| dt_req | str | — | 需求日期 / 完工日期 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| priority | int | — | 优先级 |
| status | 枚举 | 见下方 | 状态 |
| category | 枚举 | MTO / MTS | 分类（由系统按 vendorno 自动判定） |
| vendorno | str | ≤64字 | 源销售订单号 |

**status 合法值**：`NEW` `CRE` `SCH` `REL` `CNF` `CMP` `A2E` `E2A`

**跨字段业务规则**：
- `category` 最终由系统按 `vendorno` 是否有值自动判定（有值→MTO，空→MTS）；传入 `category=MTO` 仅用于在 `type` 为 `PL`/`MO` 时声明需校验 `vendorno` 非空
- 当 `type` 为 `PL` 或 `MO` 且 `category` 为 `MTO` 时，`vendorno` 必须有值

**常见错误**：
- **`priority` 传非空非数字字符串（如 `"高"`、`"N/A"`）→ `int_type`**，应传整数（传 `null` 或 `""` 可兜底为 0）
- `avail_qty` 传 `null` 或 `"abc"` → `float_type`，应传数字
- `type` 传 `"XX"` → `enum`，应传 `PL`/`MO`/`PR`/`PO`/`ST`
- `avail_qty` 传负数 → `greater_than_equal`，应传 ≥0
- **`type` 为 `PL`/`MO` 且 `category` 为 `MTO` 但 `vendorno` 为空 → `value_error`**，需补充 `vendorno` 或将 `category` 改为 `MTS`

### 4.9 PUT /t_supply/type/{type_} — 按类型替换供应记录

使用与 4.8 相同的字段规则，常见错误一致。

### 4.10 POST /t_demand — 新增或修改需求

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| materialno | str | ≤64字 | 料号 |
| demandno | str | ≤64字 | 需求单号 |
| itemno | str | ≤6字 | 项目号 |
| type | 枚举 | SO / DM / RS / FC / SS | 类型 |
| priority | int | — | 优先级 |
| req_qty | float | — | 需求数量（正数自动转负数） |
| req_date | datetime | — | 需求日期 |

**有约束的可选字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| status | 枚举 | 见下方 | 状态 |
| category | 枚举 | MTO / MTS | 分类 |
| ori_qty | float | ≥0 | 原始需求数量 |
| refno | str | ≤64字 | MTO订单号 |

**status 合法值**：`NEW` `CRE` `SCH` `REL` `CNF` `CMP` `A2E` `E2A`

**常见错误**：
- `priority` 传 `null` 或 `"abc"` → `int_type`，应传整数
- `req_qty` 传 `null` 或 `"abc"` → `float_type`，应传数字
- `req_date` 传非法日期格式 → `datetime_parsing`，应传如 `"2025-01-07 10:00:00"`
- `type` 传 `"XX"` → `enum`，应传 `SO`/`DM`/`RS`/`FC`/`SS`
- `category` 传 `"XX"` → `enum`，应传 `MTO`/`MTS`
- `status` 传 `"XX"` → `enum`，应传上述合法值
- **业务规则**：当 `category` 为 `MTO` 且 `refno` 为空时 → `value_error`（"MTO订单号refno不能为空"），需补充 refno

### 4.11 POST /t_confirm — 新增报工记录

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| supplyno | str | ≤64字 | 供应单号 |
| itemno | str | ≤6字 | 工序项目 |
| recordqty | float | >0 | 报工数量 |
| recorddt | datetime | — | 报工日期 |
| status | 枚举 | Y / N | 状态 |

> `recorddt` 支持日期字符串（如 `"2025-01-07 10:00:00"`）和时间戳（秒或毫秒）。`status` 由系统自动设置，传任何值均不会报错。

**常见错误**：
- `recordqty` 传 `null` 或 `"abc"` → `float_type`，应传正数
- `recordqty` 传 `0` 或负数 → `greater_than`，应传 >0
- `recorddt` 传非法格式 → `datetime_parsing`，应传日期字符串或时间戳
- `supplyno`/`itemno` 传 `null` → `string_type`，应传字符串

### 4.12 POST /t_checkqty_report — 新增或修改班次报工

**必填字段**：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| workcenter | str | ≤32字 | 工作中心代码 |
| materialno | str | — | 料号 |
| checktime | str | — | 班次时间 |
| reportqty | float | ≥0 | 数量 |

**常见错误**：
- `reportqty` 传 `null` 或 `"abc"` → `float_type`，应传数字
- `reportqty` 传负数 → `greater_than_equal`，应传 ≥0
- `workcenter`/`materialno`/`checktime` 传 `null` → `string_type`，应传字符串

---

## 5. 常见错误场景与修正示例

### 场景一：数值字段传了 null

**报错**：
```json
{ "field": "body->3->leadday", "input": null, "record_key": {"materialno": "M004"}, "type": "int_type", "message": "Input should be a valid integer" }
```

**原因**：`record_key` 标识出错记录为料号 `M004`，其 `leadday` 字段传了 `null`（`input` 显示为 `null`），该字段要求整数。

**修正**：传整数数字，或省略该字段（省略时使用默认值）：
```json
// 错误
{ "materialno": "M001", "leadday": null, ... }
// 正确
{ "materialno": "M001", "leadday": 7, ... }
// 或省略（使用默认值）
{ "materialno": "M001", ... }
```

### 场景二：数值字段传了非数字字符串

**报错**：
```json
{ "field": "body->8->priority", "input": "高", "record_key": {"materialno": "M002", "matver": "V1", "itemno": "020"}, "type": "int_parsing", "message": "Input should be a valid integer, unable to parse string as an integer" }
```

**原因**：`record_key` 标识出错记录为工序 `M002/V1/020`，其 `priority` 字段传了 `"高"`（`input` 直接显示传入值），非数字字符串无法解析为整数。

**修正**：传整数：
```json
// 错误
{ "priority": "高" }
// 正确
{ "priority": 1 }
```

### 场景三：枚举字段传了非法值

**报错**：
```json
{ "field": "body->0->type", "input": "XX", "record_key": {"materialno": "M001", "supplyno": "MO123"}, "type": "enum", "message": "..." }
```

**原因**：`record_key` 标识出错记录为供应 `M001/MO123`，其 `type` 字段传了 `"XX"`（`input` 显示传入值），不在合法值列表中。

**修正**：查本文档第 4 节对应 API 的枚举合法值，传合法值之一。枚举大小写不敏感，`"mo"` 等效 `"MO"`。

### 场景四：必填字段缺失

**报错**：
```json
{ "field": "body->2->materialno", "record_key": {}, "type": "missing", "message": "Field required" }
```

**原因**：第 2 个元素未传必填字段 `materialno`。注意：`missing` 类型**不携带 `input` 字段**（字段本身未提供，无值可展示）。`record_key` 为空对象 `{}` 表示唯一标识字段（此处为 `materialno`）本身缺失，无法定位具体记录——需结合 `field` 中的索引回查请求数组。

**修正**：补充该字段。

### 场景五：数值超出约束范围

**报错**：
```json
{ "field": "body->0->recordqty", "type": "greater_than", "message": "..." }
```

**原因**：`recordqty` 要求 >0，传了 0 或负数。

**修正**：传符合约束的值（如 ≥1 的正数）。

### 场景六：业务规则校验失败

**报错**：
```json
{
  "field": "body->0",
  "input": { "materialno": "M001", "supplyno": "MO123", "type": "PL", "category": "MTO", "vendorno": null, "...": "其余字段" },
  "record_key": { "materialno": "M001", "supplyno": "MO123" },
  "type": "value_error",
  "message": "type为PL或MO且category为MTO时，vendorno不能为空"
}
```

**原因**：`type` 为 `PL` 或 `MO` 且 `category` 为 `MTO` 时，`vendorno` 必须有值。`record_key` 标识出错记录为供应 `M001/MO123`，`input` 为该条完整记录。

**修正**：补充 `vendorno` 字段，或将 `category` 改为 `MTS`。

---

## 6. API 接口一览

| 接口 | 方法 | 说明 |
|------|------|------|
| /t_material | POST | 新增或修改物料 |
| /t_workcenter | POST | 新增或修改工作中心 |
| /t_mat_wc | POST | 新增或修改工序 |
| /t_mat_ver | POST | 新增或修改产线版本 |
| /t_mat_wc_bom | POST | 新增或修改 BOM |
| /t_mold | POST | 新增或修改模具 |
| /t_mat_wc_mold | POST | 新增或修改机台模具配置 |
| /t_supply | POST | 新增或修改供应记录 |
| /t_supply/type/{type_} | PUT | 按类型替换供应记录 |
| /t_demand | POST | 新增或修改需求 |
| /t_confirm | POST | 新增报工记录 |
| /t_checkqty_report | POST | 新增或修改班次报工 |

> 所有接口请求体均为 JSON 数组，如 `[{字段...}, {字段...}]`。校验错误中 `body->索引->字段名` 的索引对应数组元素位置（从 0 开始）。