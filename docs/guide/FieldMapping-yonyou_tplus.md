# 用友 T+ 与 APS 字段映射指引

> 本文档梳理用友畅捷通 T+ 系统与我方 APS 之间的字段映射关系，供我方及三方系统服务商共同进行系统对接，降低语义鸿沟带来的沟通成本。

---

## 〇、通用约定

| 约定 | 说明 |
|------|------|
| 联合索引占位 | T+ 无版本/工序概念的联合索引字段，统一用哨兵值 `"🈳❗"` 占位，保证联合索引完整，非真实业务值 |
| 配置注入 | `plant`/`planner`/`fifo` 等全局规划参数由我方项目配置注入，不从 T+ 获取 |
| 时间换算 | 保质期等带单位的时长字段统一换算为「天」 |
| 枚举转换 | T+ 布尔字段（是否自制/是否虚拟件/是否需要检验）转换为 APS 枚举值 |
| 空值兜底 | 计量单位等字段为空时兜底为空字符串 `''`，避免空值透传 |
| 客户补填 | 标注「需客户补填」的字段在 T+ 无对应来源，由客户在 APS 端手动维护 |

---

## 一、物料主数据

**T+ 接口**：`/tplus/api/v2/inventory/Query`
**APS 业务对象**：物料

| T+ 接口字段 | APS 字段 | 必填 | 说明 |
|------------|---------|------|------|
| `Code` | `materialno` | ✅ | 物料编码 |
| `Name` | `description` | ✅ | 物料名称 |
| `Specification` | `size` | ⚪ | 规格型号 |
| `BaseUnitName` | `unit` | ✅ | 主计量单位名称 |
| `AvagCost` | `price` | ⚪ | 平均成本 |
| `InventoryClassName` | `groupno` | ⚪ | 存货分类名称（转字符串） |
| `IsMadeSelf` | `abc` | ✅ | 是否自制：True→`A`，False→`B` |
| `IsMadeSelf` | `type` | ✅ | 是否自制：True→`E`（自制），False→`F`（外购） |
| `IsPhantom` | `phantom` | ✅ | 是否虚拟件：True→`YES`，False→`NO` |
| `IsNeedQualityInspection` | `leadday` | ✅ | 是否需要检验：True→检验提前期，False→免检提前期（值由配置注入） |
| `IsNeedQualityInspection` | `grday` | ✅ | 是否需要检验：True→`1`，False→`0`（检验天数） |
| `Expired` + `ExpiredUnitName` | `expday` | ⚪ | 保质期 + 保质期单位，换算为天 |
| — | `plant` | ✅ | 工厂（配置注入） |
| — | `planner` | ✅ | 计划员（配置注入） |
| — | `fifo` | ✅ | FIFO 标志（配置注入） |
| — | `size` | ⚪ | 需客户补填 |
| — | `candelay` | ⚪ | 需客户补填 |
| — | `lotsize` | ⚪ | 需客户补填 |

> **T+ 拉取但未映射字段**：`Disabled`/`IsMaterial`/`IsPurchase`/`IsMadeRequest`/`IsSuite`/`UnitName`/`UnitByManufactureName`/`InventoryClassCode`/`Ts` 等仅作过滤条件或留作扩展，不写入 APS。

---

## 二、工作中心

**T+ 接口**：`/tplus/api/v2/WorkCenter/QueryPage`
**APS 业务对象**：工作中心

| T+ 接口字段 | APS 字段 | 必填 | 说明 |
|------------|---------|------|------|
| `Code` | `workcenter` | ✅ | 工作中心编码 |
| `Name` | `workcentername` | ✅ | 工作中心名称 |

> **未映射字段**：`pri_wc`/`bottleneck`/`sortno`/`plant`/`location`/`finite`/`type`/`capnum`/`capmax`/`worker`/`setupno`/`grpno` 在 T+ 无对应来源，需客户在 APS 端按需补填。

---

## 三、工艺路线

**T+ 接口**：`/tplus/api/v2/bom/Query`（按 BOM 编号逐个查询，展开 `BOMProcessDTOs`）
**APS 业务对象**：工艺路线
**前置依赖**：必须先拉取 BOM 获取 BOM 编号列表

| T+ 接口字段 | APS 字段 | 必填 | 说明 |
|------------|---------|------|------|
| `Inventory / Code` | `materialno` | ✅ | 父件编码（BOM 所属物料） |
| `BOMProcessDTOs / Process / WorkCenter` | `workcenter` | ✅ | 工作中心 |
| `BOMProcessDTOs / Process / Code` | `itemno` | ✅ | 工序编码 |
| `BOMProcessDTOs / SequenceNumber` | `sortno` | ✅ | 加工顺序 |
| — | `matver` | ✅ | **占位 `"🈳❗"`**（T+ 无版本概念，联合索引要求非空） |
| — | `basesec` | ⚪ | 标准工时未映射，需客户补填 |

> **T+ 拉取但未映射字段**：`Inventory / Name`（父件名称）、`BOMProcessDTOs / Process / Name`（工序名称）、`KeyProcess`（是否关键工序）、`Workshop`（生产车间）、`Equipment`（生产设备）、`StandardWorkingHours`（标准工时）等留作扩展。

---

## 四、BOM

**T+ 接口**：`/tplus/api/v2/bom/QueryPage`（分页拉取，展开 `BOMChilds` 子件）
**APS 业务对象**：BOM

| T+ 接口字段 | APS 字段 | 必填 | 说明 |
|------------|---------|------|------|
| `Code` | `productno` | ✅ | 父件编码 |
| `BOMChilds / Code` | `materialno` | ✅ | 子件编码 |
| `BOMChilds / RequiredQuantity` | `qty` | ✅ | 需用数量 |
| `BOMChilds / WasteRate` | `scrap` | ⚪ | 损耗率 |
| `ProduceQuantity` | `denominator` | ✅ | 生产数量（BOM 基数） |
| `Unit / Name` | `pu` | ⚪ | 父件计量单位（空兜底 `''`） |
| `BOMChilds / Unit / Name` | `cu` | ⚪ | 子件计量单位（空兜底 `''`） |
| — | `matver` | ✅ | **占位 `"🈳❗"`**（T+ 无版本概念） |
| — | `itemno` | ✅ | **占位 `"🈳❗"`**（T+ BOM 不绑定具体工序） |

> **T+ 拉取但未映射字段**：`Name`（父件名称）、`Version`（版本号）、`IsPhantom`（是否虚拟）、`BOMChilds / Name`（子件名称）等留作扩展。

---

## 五、库存

**T+ 接口**：`/tplus/api/v2/currentStock/Query`
**APS 业务对象**：库存供应（Type=ST）

| T+ 接口字段 | APS 字段 | 必填 | 说明 |
|------------|---------|------|------|
| `InventoryCode` | `materialno` | ✅ | 存货编码 |
| `InventoryCode` | `supplyno` | ✅ | 存货编码（同时作供应号） |
| `ExistingQuantity` | `avail_qty` | ✅ | 现存量 |
| — | `itemno` | ✅ | 固定 `"stock"`（库存行标识） |
| — | `type` | ✅ | 固定 `"ST"`（库存类型） |
| — | `status` | ✅ | 固定 `"CRE"`（已创建） |
| — | `priority` | ✅ | 固定 `0` |
| — | `category` | ✅ | 固定 `"MTS"`（按库存生产） |
| — | `create_date` | ✅ | 拉取时刻当前时间 |
| — | `avail_date` | ✅ | 拉取时刻当前时间 |
| — | `dt_req` | ✅ | 拉取时刻当前时间 |

> **仓库过滤**：支持按 `WarehouseCode` 排除指定仓库（传入仓库编码列表或逗号分隔字符串），过滤在拉取完成后、写入 APS 前执行。
>
> **T+ 拉取但未映射字段**：`WarehouseCode`（仓库编码，仅用于排除过滤）、`TS`（时间戳，仅用于增量过滤）。

---

## 六、映射规则汇总

### 6.1 字段来源分类
| 来源 | 字段 | 说明 |
|------|------|------|
| T+ 直接映射 | `materialno`/`description`/`workcenter`/`qty` 等 | T+ 字段经清洗后直接写入 |
| 配置注入 | `plant`/`planner`/`fifo`/`leadday` | 由我方项目配置注入，不从 T+ 获取 |
| 枚举转换 | `abc`/`type`/`phantom`/`grday` | T+ 布尔字段转 APS 枚举 |
| 时间换算 | `expday` | 带单位时长统一换算为天 |
| 占位哨兵 | `matver`/`itemno`（BOM/工艺路线） | `"🈳❗"`，联合索引完整性保证 |
| 固定常量 | `type`/`status`/`priority`/`category`（库存） | 业务语义固定值 |
| 当前时间 | `create_date`/`avail_date`/`dt_req`（库存） | 拉取时刻时间戳 |

### 6.2 拉取顺序约束
```
BOM（获取 BOM 编号列表）
    ↓ 依赖 BOM 编号
工艺路线（按 BOM 编号逐个查询）
```
工艺路线拉取**必须晚于** BOM 拉取，否则无 BOM 编号驱动查询。

### 6.3 分页与对账
- 纯 `PageIndex` 递增翻页，`Ts` 仅作静态增量过滤条件（**非分页游标**，同时递增 PageIndex 与 Ts 会丢过半数据）
- 首页 `TotalCount` 快照作提前终止阈值，最新 `TotalCount` 作最终对账
- BOM 分页 `PageSize=100`（数据量大），其余默认 `1000`

---

**最后更新**：2026-10-30
