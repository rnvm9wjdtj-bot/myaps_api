# MyAPS API 接口知识库

> 本文档供 AI Agent 阅读使用。目标：用户用自然语言描述业务场景时，Agent 能据此精准定位应调用的接口。
>
> **使用方式**：先读「核心业务概念」建立心智模型，再用「场景速查表」做意图匹配，最后在「接口详解」确认参数与注意事项。
>
> **数据来源**：`apps/io_api/routers.py` + 《数据对接指引.pdf》。最后核对日期：2026-10-29。

## 〇、项目定位（必读）

- **我方角色**：APS 系统的**实施方**。
- **项目性质**：本系统用于**集成外部系统与 APS 系统**，仅做数据集成（写入/查询），**不含 APS 运算逻辑**。
- **数据库来源**：数据库结构由 APS 系统定义，本系统不建表、不运算，只读写 APS 已有数据。
- **文档受众**：《数据对接指引》面向**外部系统开发者**，指导其如何通过本系统 API 与 APS 交互。
- **MRP 运算产物**：`DM/RS/SS/PL/MO/PO/PR` 等 MRP 计算结果由 **APS 系统生成**，外部系统不应自行产生这些类型数据，只需通过查询接口读取或由 APS 推送。

---

## 一、核心业务概念（必读）

### 1. 需求 vs 供应

APS 把所有影响物料数量的行为抽象为两类：

| 类别 | 含义 | 类型码 | 来源 |
|---|---|---|---|
| **需求**（使物料↓） | 消耗物料的行为 | `SO`销售订单、`FC`预测、`DM`计划需求、`RS`工单预留、`SS`安全库存 | SO/FC 来自导入；DM/RS/SS 来自 MRP 运算 |
| **供应**（使物料↑） | 增加物料的行为 | `PL`生产计划、`MO`生产工单、`ST`库存、`PO`采购订单、`PR`采购申请 | ST 来自导入；PL/MO/PO/PR 来自 MRP 或外部系统 |

### 2. PL / MO / DM / RS 编号共用关系（关键）

```
SO/FC（销售/预测需求）
      ↓ MRP 初算
      PL（生产计划，供应）── 共用编号 ── DM（计划需求）
      ↓ 转正式工单
      MO（生产工单，供应）── 共用编号 ── RS（工单预留，需求）
```

- **PL 与 DM 共用同一编号**，**MO 与 RS 共用同一编号**
- **关联机制**：APS 算出的 demand 记录通过 `demandno` 字段与 MO 的 `supplyno` 形成关联（同编号）
- 因此"按工单号查领料"= 按工单号查需求记录
- 理解此关系是使用需求/供应接口的前提

### 3. 主数据与生产数据

- **主数据**：描述 APS 排程所需**静态基础信息**的数据，一经建立较少变动，是生产数据引用的前提。涉及API的主数据共 7 项：物料、工作中心、产线版本、工序、BOM、模具、机台模具，对应 7 个写入接口。
- **生产数据**：随生产计划**动态变化**的数据，包括供应（`t_supply`，PL/MO/ST/PO/PR）、需求（`t_demand`，SO/FC/DM/RS/SS）、报工（`t_confirm`）。
- 区分意义：主数据须先于生产数据建立，且主数据间存在依赖链（见下）；生产数据引用主数据（如工单引用物料+工序），主数据缺失会导致生产数据无法正常展示或写入。

### 4. 主数据依赖链

```
物料 ──┬──> 工序（需物料+产线版本+工作中心）
       │
产线版本 ─┘
工作中心 ──> 工序
工序 ──────> BOM（工序BOM，融合工序）
模具 ──> 机台模具（需模具+工序/工作中心）
```

物料、产线版本、工作中心是基础，缺失会导致工序/BOM 无法正常显示。

### 5. 多账套规则

- 主账套（如 `aps1`）+ 预测账套（如 `aps2`）
- **预测订单**只传预测账套；其余主数据/生产数据**同时传两个账套**
- 多账套写入：`db_name=aps1,aps2`
- ⚠️ **多账套仅对写入有效，GET 查询只支持单账套**

### 6. 通用约定

- 所有接口路径均以 `/api` 开头，调用时请勿遗漏该前缀
- 写入接口多为**整条覆盖**语义（先删后插），非局部字段更新
- 业务键路径参数（supplyno/itemno 等）经白名单校验：`^[A-Za-z0-9_.\-]+$`
- 鉴权由 HMAC 签名中间件统一处理，路由内不声明 api_key
- 响应统一格式：`{status_code, success, message, data, meta}`

---

## 二、场景速查表（意图 → 接口）

> Agent 收到用户问题后，先在此表匹配意图，再跳转「接口详解」。

### 主数据维护

| 用户场景 | 接口 |
|---|---|
| 新增/修改物料（存货、料号） | `POST /api/t_material` |
| 新增/修改产线版本 | `POST /api/t_mat_ver` |
| 新增/修改工作中心（机台/班组/瓶颈资源） | `POST /api/t_workcenter` |
| 新增/修改工序（工艺路线/制程/加工步骤） | `POST /api/t_mat_wc` |
| 新增/修改 BOM（工序BOM） | `POST /api/t_mat_wc_bom` |
| 新增/修改模具 | `POST /api/t_mold` |
| 新增/修改机台模具 | `POST /api/t_mat_wc_mold` |

### 主数据查询

| 用户场景 | 接口 |
|---|---|
| 分页查物料列表 | `GET /api/t_material/page` |
| 按料号查物料详情 | `GET /api/t_material/{materialnos}` |

### 供应（工单/计划/库存/采购）写入

| 用户场景 | 接口 |
|---|---|
| 新增或修改**单个/指定**工单(MO)/计划(PL)/库存(ST)/采购(PO) | `POST /api/t_supply` |
| **全量刷新**某类型所有供应记录（先清空该类型再插入） | `PUT /api/t_supply/type/{type_}` |
| 删除指定供应记录 | `DELETE /api/t_supply/{supplyno}` |

### 需求（销售订单/预测等）写入与查询

| 用户场景 | 接口 |
|---|---|
| 新增/修改销售订单(SO)/预测(FC)等需求 | `POST /api/t_demand` |
| 按需求号查需求详情（含 MO 关联信息） | `GET /api/v_demand/{demandno}` |
| 删除需求记录（按需求号+料号+项目号） | `DELETE /api/t_demand/{demandno}/{materialno}/{itemno}` |

### 报工

| 用户场景 | 接口 |
|---|---|
| 新增报工记录 | `POST /api/t_confirm` |
| 删除报工记录（按工单号+工序号） | `DELETE /api/t_confirm/{supplyno}/{itemno}` |
| 删除单条报工记录（按主键NoID） | `DELETE /api/t_confirm/{noid}` |
| 新增/修改班次报工 | `POST /api/t_checkqty_report` |

### 报表查询

| 用户场景 | 接口 |
|---|---|
| 工单报表（按开完工时间分页） | `GET /api/v_supply_mo/page` |
| 按工单号查工单报表 | `GET /api/v_supply_mo/{supplyno}` |
| 工序报表（支持分组、时间窗口） | `GET /api/v_orderwc/group` |
| 按工单号查工序报表 | `GET /api/v_orderwc/{supplyno}` |
| 查工单所需物料（领料/BOM需求） | `GET /api/v_mo_demand/{supplyno}` |
| pegging 关系分页查询 | `GET /api/v_peg/page` |
| 按日期分组的库存动态报表 | `GET /api/v_matdailyqtyreport` |

### 内部/调试（仅本地访问）

| 用户场景 | 接口 |
|---|---|
| 元数据查询 | `GET /api/meta` |
| Mock 推送 | `POST /api/mock/push` |

---

## 三、接口详解

### 主数据 · 写入

#### `POST /api/t_material` — 新增或修改物料
- **标签**：主数据 - 物料
- **入参**：`Body: List[DTO]`，`Query: db_name`（账套，默认主账套），`return_data`
- **语义**：upsert（按主键新增或覆盖）
- **注意**：物料是工序/BOM 的基础，缺失会导致关联信息无法显示

#### `POST /api/t_mat_ver` — 新增或修改产线版本
- **标签**：主数据 - 产线版本
- **入参**：`Body: List[DTO]`，`Query: db_name`
- **注意**：ERP 原生通常无此数据；被工序/BOM 引用

#### `POST /api/t_workcenter` — 新增或修改工作中心
- **标签**：主数据 - 工作中心
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data, source_system, dedup_strategy, update_mode`
- **注意**：APS 核心概念，颗粒度影响排程准确性。瓶颈设备宜单设工作中心；次要工序可合并

#### `POST /api/t_mat_wc` — 新增或修改工序
- **标签**：主数据 - 工序
- **入参**：`Body: List[DTO]`，`Query: db_name, drop`（`all|matched`）, `return_data, source_system, dedup_strategy`
- **注意**：维护某产品在某产线版本下、用某工作中心的生产节拍等时间参数，准确性直接影响排产

#### `POST /api/t_mat_wc_bom` — 新增或修改 BOM
- **标签**：主数据 - BOM
- **入参**：`Body: List[DTO]`，`Query: db_name, drop`（`all|matched`）, `return_data, source_system, dedup_strategy`
- **注意**：APS 的 BOM 是**工序 BOM**，融合工序以精确管控物料时间

#### `POST /api/t_mold` — 新增或修改模具
- **标签**：主数据 - 模具
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data, source_system, dedup_strategy, update_mode`

#### `POST /api/t_mat_wc_mold` — 新增或修改机台模具
- **标签**：主数据 - 机台模具
- **入参**：`Body: List[DTO]`，`Query: db_name, drop`（`all|matched`）, `return_data, source_system, dedup_strategy`

### 主数据 · 查询

#### `GET /api/t_material/page` — 物料分页
- **入参**：`Query: db_name, page_size, page_index` 及筛选条件
- **注意**：仅本地访问

#### `GET /api/t_material/{materialnos}` — 按料号查物料
- **入参**：`Path: materialnos`（料号），`Query: db_name`

### 供应 · 写入

#### `POST /api/t_supply` — 新增或修改供应记录 ⭐
- **标签**：生产数据 - 供应
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data`
- **覆盖类型**：PL 生产计划、MO 生产工单、ST 库存、PO 采购订单、PR 采购申请
- **语义**：按 `supplyno` **整条覆盖**——先删除该供应及其关联记录，再插入本批数据
- **并发保护**：分布式锁保护，Redis 不可用时自动降级无锁
- **去重**：同请求内按 supplyno 去重
- ⚠️ **不是局部更新**，需传完整工单数据；修改单个工单用此接口
- **PO 传入范围**：今天完结的 + 在途未完结的，`avail_qty` = 未入库数量

#### `PUT /api/t_supply/type/{type_}` — 按类型替换供应记录
- **入参**：`Path: type_`（`PL|MO|PR|PO|ST`），`Body: List[DTO]`
- **语义**：删除该类型**所有**记录，再插入本批
- ⚠️ **风险大**，会清空该类型全部数据，仅适合全量重推/批量刷新场景
- **校验**：数据中每条 type 必须与路径 type_ 一致，否则 400

#### `DELETE /api/t_supply/{supplyno}` — 删除供应记录
- **入参**：`Path: supplyno`，`Query: db_name`
- **注意**：supplyno 经白名单校验

### 需求 · 写入

#### `POST /api/t_demand` — 新增或修改需求记录 ⭐
- **标签**：生产数据 - 需求
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data`
- **覆盖类型**：SO 销售订单、DM 计划需求、RS 工单预留、FC 预测、SS 安全库存
- **语义**：按【需求号+料号+项目号】upsert
- **销售订单示例**：
  ```json
  [{
    "materialno": "料号",
    "demandno": "内部销售单号",
    "itemno": "行号（一单多物料时填行号，否则传01）",
    "type": "SO",
    "category": "MTO",
    "priority": 优先级,
    "status": "NEW",
    "req_qty": -10,
    "req_date": "需求日期",
    "refno": "客户订单号 or null"
  }]
  ```
- ⚠️ `req_qty` 须为**负数**

> **注**：原 PDF 文档中的 `GET /api/t_demand?demandno=...` 已由 `GET /api/v_demand/{demandno}` 替代（PDF 后续弃用，以本文档为准）。

#### `GET /api/v_demand/{demandno}` — 根据需求号获取物料需求详情 ⭐
- **标签**：生产数据 - 需求
- **入参**：`Path: demandno`（需求号），`Query: db_name`
- **语义**：按需求号查需求记录（不限需求类型）；并额外按同号查工单信息，合并到 `meta.mo`
- **用途**：按需求号查需求详情；因 APS pegging 算法需求号与供应号一致，亦可"根据工单 supplyno 获取原料需求"
- **业务键校验**：demandno 经白名单校验
- **与 `GET /api/v_mo_demand/{supplyno}` 的区别**：
  - `GET /api/v_demand/{demandno}` **不限需求类型**（SO/FC/DM/RS/SS 均可查），并合并 MO 信息
  - `GET /api/v_mo_demand/{supplyno}` **仅 MO 类型**（已过滤非 MO 数据）

#### `DELETE /api/t_demand/{demandno}/{materialno}/{itemno}` — 删除需求记录
- **标签**：生产数据 - 需求
- **入参**：`Path: demandno`（需求号）、`materialno`（料号）、`itemno`（项目号），`Query: db_name`
- **唯一键**：（需求号、料号、项目号）
- **占位符约定**：`materialno` 或 `itemno` 传 `...` 表示**不限制该字段**（如仅按需求号删除时，料号与项目号均传 `...`，将删除该需求号下所有记录）
- **业务键校验**：demandno 必校验；materialno/itemno 非 `...` 时校验
- **语义**：按构建的过滤条件物理删除需求记录

### 报工

#### `POST /api/t_confirm` — 新增报工记录
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data`
- **return_data**：返回含自增主键 NoID 的完整行

#### `DELETE /api/t_confirm/{supplyno}/{itemno}` — 删除报工记录
- **入参**：`Path: supplyno`（工单号）、`itemno`（工序号），均经白名单校验

#### `DELETE /api/t_confirm/{noid}` — 按主键删除单条报工
- **入参**：`Path: noid`

#### `POST /api/t_checkqty_report` — 新增或修改班次报工
- **入参**：`Body: List[DTO]`，`Query: db_name, return_data`

### 报表 · 查询

#### `GET /api/v_supply_mo/page` — 工单报表分页
- **入参**：`Query: db_name, start_time`（开工时间下界）, `end_time`（完工时间上界）, `page_size, page_index`
- **排序**：按料号、工单号排序
- **注意**：仅本地访问

#### `GET /api/v_supply_mo/{supplyno}` — 按工单号查工单报表
- **入参**：`Path: supplyno`，`Query: db_name`

#### `GET /api/v_orderwc/group` — 工序报表（分组）
- **入参**：`Query: db_name, start_time, end_time, group_by` 等
- **默认时间窗口**：均不传时为昨天至 +15 天；开工或完工至少一个落在窗口内即命中
- **分组**：支持按指定字段分组，datetime/timestamp 字段按日归组

#### `GET /api/v_orderwc/{supplyno}` — 按工单号查工序报表
- **入参**：`Path: supplyno`，`Query: db_name`

#### `GET /api/v_mo_demand/{supplyno}` — 查工单所需物料 ⭐
- **标签**：报表 - 工单需求
- **入参**：`Path: supplyno`（工单/供应号），`Query: db_name`
- **语义**：按工单号查工单所需物料
- **用途**：查某工单（MO）的领料/BOM 需求
- ⚠️ **重要限制**：该接口**仅返回 MO 类型**数据，只能查到 MO 所需物料。**SO/FC/DM/RS/SS 等其他类型的需求请改用 `GET /api/v_demand/{demandno}`**。

#### `GET /api/v_peg/page` — pegging 关系分页
- **入参**：`Query: db_name, page_size, page_index`
- **用途**：查询需求-供应的 pegging（挂钩）关系

#### `GET /api/v_matdailyqtyreport` — 库存动态日报表
- **入参**：`Query: db_name, period`（查询时间范围，天）, `groupdates`（分组日期，逗号分隔）, `materialno`（料号，多个逗号分隔）
- **用途**：按日期分组的库存动态

### 内部

#### `GET /api/meta` — 元数据（仅本地）
- **入参**：无

#### `POST /api/mock/push` — Mock 推送（仅本地）
- **入参**：无

---

## 四、DTO 字段定义

> 写入接口的 `Body: List[DTO]` 中 DTO 字段如下。**必填**列：✅必填、⚪可选、⚠️条件必填。约束栏标注枚举取值/数值范围/长度。

### 物料（`POST /api/t_material`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str | 料号 | `M001` |
| description | ✅ | str | 物料名称 | `测试物料A` |
| leadday | ✅ | int ≥0 | 交期（天） | `10` |
| grday | ✅ | int ≥0 | 收货质检（天） | `1` |
| abc | ✅ | 枚举 | ABC分类 | `A` |
| unit | ✅ | str | 单位 | `PCS` |
| type | ⚠️ | 枚举 | 物料类型；仅 `MYAPS_VERSION=P` 时必填 | `E` |
| size | ⚪ | str | 规格 | `100x100mm` |
| plant | ⚪ | str | 工厂（有默认） | `1600` |
| planner | ⚪ | str | 计划员 | `张三` |
| fifo | ⚪ | int 0\|1 | 1-FIFO 0-最近原则 | `0` |
| expday | ⚪ | int ≥0 | 保质期（天） | `365` |
| warehouse | ⚪ | str | 仓库 | `原料仓` |
| price | ⚪ | Decimal ≥0 | 价格 | `100.50` |
| groupno | ⚪ | str | 型号 | `G001` |
| phantom | ⚪ | 枚举 Y/N | 虚拟件 | `N` |
| phantommin | ⚪ | int ≥0 | 虚拟时间（分） | `0` |
| firmday | ⚪ | int ≥0 | 固定天数 | `0` |
| daygap | ⚪ | int ≥0 | MTO拆分天数 | `1` |
| candelay | ⚪ | 枚举 Y/N | 可否延迟 | `N` |
| lotsize | ⚪ | 枚举 | 批量 | `EX` |
| lotfix | ⚪ | float ≥0 | 固定批 | `0.0` |
| lotmin | ⚪ | float ≥0 | 最小批 | `0.0` |
| lotmax | ⚪ | float ≥0 | 最大批 | `0.0` |
| lotround | ⚪ | float ≥0 | 取整 | `0.0` |
| lotss | ⚪ | float ≥0 | 安全库存 | `0.0` |
| lotpoint | ⚪ | float ≥0 | 重订货点 | `0.0` |
| lottop | ⚪ | float ≥0 | 最大库存点 | `0.0` |
| planitem | ⚪ | str | 产品组 | `PI001` |
| preday | ⚪ | int ≥0 | 向前冲销(天) | `999` |
| subday | ⚪ | int ≥0 | 向后冲销(天) | `999` |
| free1/free2/free3 | ⚪ | str ≤255 | 自定义 | |
| memo | ⚪ | str | 备注 | |

### 工作中心（`POST /api/t_workcenter`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| workcenter | ✅ | str ≤32 | 工作中心代码 | `WC001` |
| workcentername | ✅ | str ≤255 | 工作中心名称 | `装配车间` |
| pri_wc | ⚪ | int | 优先级 | `1` |
| bottleneck | ⚪ | 枚举 Y/N | 瓶颈 | `N` |
| sortno | ⚪ | str ≤4 | 序号 | `0001` |
| plant | ⚪ | str ≤32 | 工厂 | `1600` |
| location | ⚪ | str ≤32 | 车间 | `A区` |
| finite | ⚪ | 枚举 Y/N | 有限 | `N` |
| type | ⚪ | 枚举 Y/N | 首页显示 | `N` |
| capnum | ⚪ | int >0 | 默认机台数 | `6` |
| capmax | ⚪ | int >0 | 最大机台数 | `10` |
| worker | ⚪ | float ≥0 | 工时 | `8.0` |
| setupno | ⚪ | str ≤6 | 切换组别 | `S001` |
| grpno | ⚪ | str ≤6 | 同组号 | `G001` |
| memo | ⚪ | str ≤255 | 备注 | |

### 产线版本（`POST /api/t_mat_ver`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str ≤64 | 料号 | `M001` |
| matver | ✅ | str ≤4 | 产线版本号 | `01` |
| lotfrom | ⚪ | int | 批量起点 | `1` |
| lotto | ⚪ | int | 批量终点 | `9999999` |
| priority | ⚪ | int | 优先级 | `1` |
| refno | ⚪ | str ≤64 | MTO订单号/认证线 | `SO123456` |
| active | ⚪ | 枚举 Y/N | 生效 | `Y` |
| memo | ⚪ | str ≤255 | 备注 | |

### 工序（`POST /api/t_mat_wc`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str ≤64 | 料号 | `M001` |
| matver | ✅ | str ≤4 | 产线版本 | `01` |
| workcenter | ✅ | str ≤32 | 工作中心 | `WC001` |
| sortno | ✅ | int 0-999 | 序号 | `1` |
| basesec | ✅ | float ≥0 | 节拍T/T(秒/100) | `600` |
| itemno | ⚪ | str ≤6 | 工序项目 | `01` |
| itemname | ⚪ | str ≤64 | 工序名称 | `装配` |
| fixqty | ⚪ | int ≥0 | 额定量 | `100` |
| fixsec | ⚪ | int ≥0 | 额定时间(秒) | `300` |
| sf | ⚪ | 枚举 S/F/Z | 并行S/串行F/并结Z | `F` |
| offsetsec | ⚪ | int | 偏置+/-(秒) | `0` |
| lotsize | ⚪ | float | 批量大小 | `0.0` |
| lotsec | ⚪ | int | 批量时间(秒) | `0` |
| rate | ⚪ | float ≥0 | 配比 | `1.0` |
| memo | ⚪ | str ≤255 | 备注 | |

### BOM（`POST /api/t_mat_wc_bom`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| productno | ✅ | str ≤64 | 产品料号 | `P001` |
| matver | ✅ | str ≤4 | 产线版本 | `01` |
| itemno | ✅ | str ≤6 | 工序项目 | `01` |
| materialno | ✅ | str ≤64 | 子件料号 | `M001` |
| qty | ✅ | float ≥0 | 数量 | `2.0` |
| offsethour | ⚪ | int | 偏置+/-(小时) | `0` |
| mto | ⚪ | 枚举 Y/N | MTO | `N` |
| scrap | ⚪ | float ≥0 | 报废率% | `0.0` |
| alt | ⚪ | 枚举 Y/N | 是否替代 | `N` |
| denominator | ⚪ | float/str | 用量分母 | `1` |
| memo | ⚪ | str ≤255 | 备注 | |

### 模具（`POST /api/t_mold`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| moldno | ✅ | str ≤64 | 模具编号 | `MOLD001` |
| moldname | ✅ | str ≤64 | 模具名称 | `测试模具A` |
| type | ✅ | str ≤4 | 类型 | `T1` |
| status | ✅ | str ≤6 | 状态 | `AVL` |
| moldnum | ✅ | int >0 | 模具穴数 | `4` |
| qty | ✅ | int >0 | 模具台数 | `2` |
| memo | ⚪ | str ≤255 | 备注 | |

### 机台模具（`POST /api/t_mat_wc_mold`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str ≤64 | 料号 | `M001` |
| workcenter | ✅ | str ≤64 | 工作中心 | `WC001` |
| itemno | ✅ | str ≤6 | 工序项目 | `01` |
| basesec | ✅ | float ≥0 | 节拍T/T(秒/100) | `600` |
| priority | ✅ | int | 优先级 | `1` |
| moldno | ⚪ | str ≤64 | 模具编号 | `MOLD001` |
| fixsec | ⚪ | int ≥0 | 额定时间(秒) | `300` |
| worker | ⚪ | float ≥0 | 人员 | `1.0` |
| memo | ⚪ | str ≤255 | 备注 | |

### 供应（`POST /api/t_supply` / `PUT /api/t_supply/type/{type_}`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str ≤64 | 料号 | `M001` |
| supplyno | ✅ | str ≤64 | 供应单号 | `MO123456` |
| type | ✅ | 枚举 | 类型：`PL`生产计划 `MO`生产工单 `ST`库存 `PO`采购订单 | `MO` |
| avail_qty | ✅ | float ≥0 | 可用数量 | `100.0` |
| avail_date | ✅ | str | 可用日期/开工日期 | `2023-01-01` |
| dt_req | ✅ | str | 需求日期/完工日期 | `2023-01-07` |
| category | ⚪ | 枚举 MTO/MTS | 分类 | `MTS` |
| priority | ⚪ | int | 优先级 | `0` |
| status | ⚪ | 枚举 | 状态：NEW/CRE/SCH/REL/PNF/CMP | `CRE` |
| matver | ⚪ | str ≤32 | 产线版本 | `01` |
| itemno | ⚪ | str ≤6 | 项目号 | `01` |
| create_date | ⚪ | str | 创建日期 | `2023-01-01` |
| avail_end_date | ⚪ | str | 可用结束日期 | `2023-01-07` |
| batchno | ⚪ | str ≤64 | 批次号 | `BATCH001` |
| vendorno | ⚪ | str ≤64 | 源销售订单号 | `SO001` |
| partnerno | ⚪ | str ≤64 | 合作商编号 | `P001` |
| partnername | ⚪ | str ≤255 | 合作商名称 | `合作伙伴A` |
| free1/free2/free3 | ⚪ | str ≤255 | 自定义 | |
| apiex_sn | ⚪ | str ≤32 | APS原生序列号 | `MO123456` |
| apiex_id | ⚪ | str ≤32 | 外部系统单据ID | `1` |
| apiex_entryid | ⚪ | str ≤32 | 外部系统条目ID | `1` |
| memo | ⚪ | str ≤255 | 备注 | |

> ⚠️ 供应 DTO 内部逻辑：若外部传入 `type=MO`，会强制转为 `PL` 以适配工单推送逻辑；并按 type 自动设置 status/category。

### 需求（`POST /api/t_demand`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| materialno | ✅ | str ≤64 | 料号 | `M001` |
| demandno | ✅ | str ≤64 | 需求单号 | `SO123456` |
| itemno | ✅ | str ≤6 | 项目号 | `01` |
| type | ✅ | 枚举 | 类型：`SO`销售订单 `DM`计划需求 `RS`工单预留 `FC`预测 `SS`安全库存 | `SO` |
| priority | ✅ | int | 优先级 | `1` |
| req_qty | ✅ | float | 需求数量（**须为负数**，正数自动转负） | `-100.0` |
| req_date | ✅ | datetime | 需求日期 | `2023-01-07T10:00:00` |
| category | ⚪ | 枚举 MTO/MTS | 分类 | `MTS` |
| workcenter | ⚪ | str ≤32 | 工作中心 | `WC001` |
| status | ⚪ | 枚举 | 状态：NEW/CRE/SCH/REL/PNF/CMP | `CRE` |
| create_date | ⚪ | str | 创建日期 | `2023-01-01` |
| refno | ⚪ | str ≤64 | MTO订单号 | `MTO123456` |
| partnerno | ⚪ | str ≤64 | 合作商编号 | `P001` |
| partnername | ⚪ | str ≤255 | 合作商名称 | `客户A` |
| ori_qty | ⚪ | float ≥0 | 原始需求数量 | `100.0` |
| apiex_sn | ⚪ | str ≤32 | APS原生序列号 | `SO123456` |
| apiex_id | ⚪ | str ≤32 | 外部系统单据ID | `1` |
| apiex_entryid | ⚪ | str ≤32 | 外部系统条目ID | `1` |
| free1/free2/free3 | ⚪ | str ≤255 | 自定义 | |
| memo | ⚪ | str ≤255 | 备注 | |

### 报工（`POST /api/t_confirm`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| supplyno | ✅ | str ≤64 | 供应单号 | `MO123456` |
| itemno | ✅ | str ≤6 | 工序项目 | `01` |
| recordqty | ✅ | float >0 | 报工数量 | `100` |
| recorddt | ✅ | datetime | 报工日期 | `2025-01-07 10:00:00` |
| status | ✅ | 枚举 Y/N | 状态 | |
| sysuser | ⚪ | str ≤32 | 系统用户 | `张三` |

### 班次报工（`POST /api/t_checkqty_report`）

| 字段 | 必填 | 约束/类型 | 说明 | 示例 |
|---|---|---|---|---|
| workcenter | ✅ | str ≤32 | 工作中心代码 | `WC001` |
| materialno | ✅ | str | 料号 | `M001` |
| checktime | ✅ | str | 班次 | `2026-07-10 07:30:00` |
| reportqty | ✅ | float ≥0 | 数量 | `600` |

---

## 五、Agent 决策指引

### 意图识别关键词映射

| 用户关键词 | 指向 |
|---|---|
| 物料/存货/料号 + 新增/修改 | `POST /api/t_material` |
| 物料 + 查/看 | `GET /api/t_material/page` 或 `GET /api/t_material/{materialnos}` |
| 工单/MO/生产工单 + 改/新增 | `POST /api/t_supply`（type=MO） |
| 工单 + 全量/批量刷新 | `PUT /api/t_supply/type/MO` |
| 工单 + 删除 | `DELETE /api/t_supply/{supplyno}` |
| 销售订单/SO/预测/FC + 新增 | `POST /api/t_demand`（type=SO/FC） |
| 需求 + 查/按需求号 | `GET /api/v_demand/{demandno}` |
| 需求 + 删除 | `DELETE /api/t_demand/{demandno}/{materialno}/{itemno}` |
| 工单 + 领料/所需物料/BOM需求 | `GET /api/v_mo_demand/{supplyno}`（仅MO）或 `GET /api/v_demand/{demandno}`（不限类型） |
| 工单 + 报表/看工单 | `GET /api/v_supply_mo/page` 或 `GET /api/v_supply_mo/{supplyno}` |
| 工序 + 报表 | `GET /api/v_orderwc/group` 或 `GET /api/v_orderwc/{supplyno}` |
| 报工 + 新增 | `POST /api/t_confirm` |
| 报工 + 删除 | `DELETE /api/t_confirm/{supplyno}/{itemno}` 或 `DELETE /api/t_confirm/{noid}` |
| 库存动态/日报 | `GET /api/v_matdailyqtyreport` |
| pegging/挂钩 | `GET /api/v_peg/page` |

### 常见歧义澄清

1. **"修改工单"** → 默认 `POST /api/t_supply`（整条覆盖）。若用户要"全量同步所有工单"则用 `PUT /api/t_supply/type/MO`。无局部 patch 接口。
2. **"查工单领料"** → 若只查 MO 工单消耗用 `GET /api/v_mo_demand/{supplyno}`（仅返回 MO 类型）；若需查 SO/FC/DM/RS 等任意类型需求用 `GET /api/v_demand/{demandno}`。
3. **"需求"歧义** → 若指销售订单/预测**写入**用 `POST /api/t_demand`；若指**按需求号查需求详情**用 `GET /api/v_demand/{demandno}`；若指**仅查 MO 工单领料**用 `GET /api/v_mo_demand/{supplyno}`。
4. **多账套** → 写入可 `db_name=aps1,aps2`；查询只能单账套。预测订单只传预测账套。
5. **type 取值** → 供应：`PL/MO/ST/PO/PR`；需求：`SO/FC/DM/RS/SS`。

### 回答规范

回答用户"该调哪个接口"时，应给出：
1. **接口**：方法 + 路径
2. **为什么**：一句话说明匹配理由
3. **关键参数**：必传的 path/body/query 参数
4. **注意事项**：覆盖语义、数量符号、多账套等易错点（若有）
---

## 六、附录：主数据关联与常见问题排障

> 本附录说明 7 项主数据间的关联关系，并重点解释前端 web 查询不到 BOM 数据的可能原因。外部系统写入主数据时应遵循维护顺序，避免"数据已写入但前端查不到"。

### 1. 主数据关联关系

各表主键与引用关系（箭头表示引用方 → 被引用方）：

| 表 | 主键 | 引用 |
|---|---|---|
| `t_material` | `MaterialNo` | —（基础） |
| `t_workcenter` | `WorkCenter` | —（基础） |
| `t_mat_ver` | `(MaterialNo, MatVer)` | → `t_material` |
| `t_mat_wc` | `(MaterialNo, MatVer, ItemNo)` | → `t_material` + `t_mat_ver` + `t_workcenter` |
| `t_mat_wc_bom` | `(ProductNo, MatVer, ItemNo, MaterialNo)` | → `t_material`（产品 + 子件）+ `t_mat_wc`（工序） |
| `t_mold` | `MoldNo` | —（基础） |
| `t_mat_wc_mold` | `(MaterialNo, ItemNo, WorkCenter, MoldNo)` | → `t_material` + `t_mat_wc` + `t_mold` |

### 2. 前端 BOM 列表数据源

前端 BOM 列表的数据源是 `v_mat_wc_bom`，它在 `t_mat_wc_bom` 基础上关联以下三处主数据以展示完整信息：

| 关联表 | 字段匹配条件 | 补充的展示字段 |
|---|---|---|
| `t_material`（子件） | `t_mat_wc_bom.MaterialNo = t_material.MaterialNo` | 子件 `Description`/`Planner`/`ABC`/`Warehouse`/`Type`/`LeadDay` |
| `t_material`（产品） | `t_mat_wc_bom.ProductNo = t_material.MaterialNo` | 产品描述 `Prod_DESC` |
| `t_mat_wc`（工序） | `ProductNo` + `MatVer` + `ItemNo` 三字段同时匹配 | `WorkCenter`（工作中心/机台） |

该数据源采用**严格关联**：以上三处关联**任一缺失，该 BOM 行不会出现在前端列表**（不是部分字段为空，而是整行不显示）。

### 3. 前端查询不到 BOM 数据的排查步骤

若已通过 `POST /api/t_mat_wc_bom` 写入 BOM，但前端列表查不到该条记录，按以下顺序排查：

**原因 1：子件物料缺失**——BOM 的 `MaterialNo`（子件料号）在 `t_material` 表不存在。
- 排查：`SELECT * FROM t_material WHERE MaterialNo = '<子件料号>'`
- 修复：先调 `POST /api/t_material` 写入子件物料。

**原因 2：产品物料缺失**——BOM 的 `ProductNo`（产品料号）在 `t_material` 表不存在。
- 排查：`SELECT * FROM t_material WHERE MaterialNo = '<产品料号>'`
- 修复：先调 `POST /api/t_material` 写入产品物料。

**原因 3：工序缺失**——BOM 的 `(ProductNo, MatVer, ItemNo)` 三元组在 `t_mat_wc` 表不存在。
- 排查：`SELECT * FROM t_mat_wc WHERE MaterialNo='<产品料号>' AND MatVer='<产线版本>' AND ItemNo='<工序号>'`
- 修复：先调 `POST /api/t_mat_wc` 写入工序。

**原因 4：产线版本 `MatVer` 不一致**——`t_mat_ver` 本身不参与 BOM 显示判断，但工序 `t_mat_wc` 的 `MatVer` 字段需与 BOM 的 `MatVer` 完全一致才能匹配上工序关联。若工序的 `MatVer` 与 BOM 不一致，效果同原因 3。

**原因 5（不影响显示）：工作中心缺失**——`t_workcenter` 不参与 BOM 显示判断。工序行只要存在于 `t_mat_wc` 即可，即使其 `WorkCenter` 在 `t_workcenter` 缺失，BOM 行仍会显示（仅 `WorkCenter` 字段值原样展示）。

### 4. 前端工序列表数据源

前端工序列表的数据源是 `v_mat_wc`，它以 `t_mat_wc` 为主表，**宽松关联**以下关联表补充展示字段（关联缺失则补充字段为空，工序行仍保留）：

| 关联表 | 字段匹配条件 | 补充的展示字段 | 缺失后果 |
|---|---|---|---|
| `t_workcenter` | `t_mat_wc.WorkCenter = t_workcenter.WorkCenter` | `WorkCenterName`/`GrpNo`/`Bottleneck` | 该工序行**仍显示**，这三个字段为空 |
| `t_mold`（经优先模具） | 通过 `t_mat_wc_mold` 取优先模具 `MoldNo` 关联 | `MoldName`/`MoldNum` | 该工序行**仍显示**，模具字段为空 |
| `t_mat_wc_mold` | `(MaterialNo, MatVer, WorkCenter)` | 优先模具 `MoldNo`/`BaseSec` | 该工序行**仍显示**，`BaseSec` 回退取 `t_mat_wc.BaseSec` |

> ⚠️ **与 BOM 的关键区别**：`v_mat_wc_bom` 是**严格关联**（缺一则 BOM 行**整行消失**）；`v_mat_wc` 是**宽松关联**，`t_mat_wc` 的每一行**必定出现在查询结果里**，关联缺失仅导致补充字段为空，**不会让工序行消失**。

### 5. 前端查询不到工序数据的排查步骤

由于 `v_mat_wc` 宽松关联不丢行，"明明已落库却查不到"的根因不在数据源关联，而在**前端对关联字段的筛选/搜索**：

**原因 1：按工作中心名称搜索**——`WorkCenterName` 来自 `t_workcenter`，缺失则为空，`空 LIKE '%关键词%'` 不成立。工序已落库但未建对应 `t_workcenter`，前端按工作中心名称搜索查不到。
- 排查：`SELECT * FROM t_workcenter WHERE WorkCenter = '<工序的 WorkCenter>'`
- 修复：先调 `POST /api/t_workcenter` 写入工作中心。

**原因 2：按瓶颈/分组筛选**——`Bottleneck`/`GrpNo` 来自 `t_workcenter`，缺失为空。前端筛"瓶颈=Y"或某分组时，工作中心缺失则空值不匹配。
- 修复同原因 1。

**原因 3：按模具名称/穴数筛选**——`MoldName`/`MoldNum` 来自 `t_mold`，缺失为空。前端按模具维度筛选时查不到。
- 排查：`SELECT * FROM t_mold WHERE MoldNo = '<优先模具编号>'`
- 修复：先调 `POST /api/t_mold` 写入模具（并确认 `t_mat_wc_mold` 已建立工序-模具关联）。

**原因 4（不影响显示）：模具关联缺失**——`t_mat_wc_mold` 无记录时，`MoldNo`/`MoldName`/`MoldNum` 为空，但 `BaseSec` 回退取 `t_mat_wc.BaseSec`，工序行仍正常显示节拍数据。仅当前端按模具字段筛选时才会查不到（同原因 3）。

**原因 5：非关联原因**——
- **账套错误**：工序写入 `aps1` 但前端查 `aps2`（多账套 GET 只支持单账套）。
- **分页/排序**：`SortNo` 为空或重复时，窗口函数排序不稳定，工序可能落到预期页外（不过滤行）。
- **事务未提交**：概率低，upsert 走自动提交。

### 6. 推荐维护顺序

```
物料 → 工作中心 → 产线版本 → 工序 → BOM → 模具 → 机台模具
```

先建被引用方再建引用方，可避免"数据已写入但前端查不到"的问题：
- **BOM**（`t_mat_wc_bom`）：关联缺失会**整行消失**，必须先建物料+工序。
- **工序**（`t_mat_wc`）：关联缺失**不丢行**，但按工作中心/模具名称检索时查不到，建议先建工作中心+模具。