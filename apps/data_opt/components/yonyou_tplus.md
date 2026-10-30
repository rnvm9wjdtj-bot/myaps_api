# yonyou_tplus.py 对接操作指引

> 本文档为 MyAPS ↔ 用友畅捷通 T+ (chanjet) 对接模块的操作指引，供 AI Agent 在新环境复用时快速调试参考。文档仅包含通用规则与操作步骤，不含任何环境特定的阶段性状态。

## 1. 鉴权机制

### Token 刷新流程
T+ 采用 OAuth2 风格的 `refresh_token` 换 `access_token` 机制（非明珞的 MD5 签名）：

```
GET {base_url}/auth/v2/refreshToken?grantType=refresh_token&refreshToken={refresh_token}
Header: appKey / appSecret / Content-Type
→ {code:200, result:{access_token, refresh_token}}
```

- 业务请求 Header 传 `appKey` / `appSecret` / `openToken`（=access_token）/ `Content-Type`
- token 有效期默认 12 小时（`token_expire_seconds`），过期前命中缓存直接复用，过期后自动刷新
- 刷新成功后**回写 dev.json** 的 `access_token` / `refresh_token` / `_auth_at_`，下次启动直接复用
- 并发刷新用 `_auth_lock` + 锁后复检（double-check）防止多协程重复刷新
- 刷新失败按指数退避重试（`max_retries=5`，`2^retry_count` 秒间隔）

### 配置项（dev.json `erp` 节点）
| 配置键 | 说明 | 备注 |
|--------|------|------|
| `base_url` | 网关地址 | 默认 `https://openapi.chanjet.com` |
| `app_key` | 应用 Key | 由畅捷通开放平台分配 |
| `app_secret` | 应用 Secret | 由畅捷通开放平台分配 |
| `access_token` | 访问令牌 | 自动刷新回写，首次需手动换取 |
| `refresh_token` | 刷新令牌 | 自动刷新回写，长期有效 |
| `org_id` | 组织 ID | 读取后存实例属性，当前业务请求未直接使用 |
| `_auth_at_` | 上次认证时间 | 格式 `YYYY-MM-DD HH:MM:SS`，自动回写 |
| `token_expire_seconds` | token 有效期（秒） | 默认 `43200`（12 小时） |
| `max_page_size` | 分页大小上限 | 默认 `1000`，硬上限 1000 |
| `$MoBusiType` | MO 业务类型编码 | 注入 `MoPushModel.BusiType.Code` |
| `$MoDepartment` | MO 部门编码 | 代码中已注释，由租户 `CustomMoPushModel` 用 workcenter 覆盖 |
| `$RequisitionPerson` | 请购单请购人编码 | 注入 `PrPushModel.RequisitionPerson.Code` |

### 响应分层
- **认证响应**：`{code, result:{access_token, refresh_token}, message}`
  - `code=200`：认证成功
- **业务响应**：`{code, data, message}`
  - `code='0'`（字符串）：业务成功，看 `data`
  - `code!='0'`：业务失败，看 `message`
- **HTTP 状态码**：`_post` 对 `status_code >= 400` 统一抛 `Exception(HTTP 错误({status}): {msg})`，交由调用方/上层重试处理（旧版 4xx 曾被静默放过，把错误响应当数据）

## 2. 接口总览

T+ 对接分**拉取**（T+ → APS，主数据/库存同步）和**推送**（APS → T+，单据下达）两类。

### 2.1 拉取接口（T+ → APS）

| # | 接口 | APS 目标表 | Endpoint | 方法 | 说明 |
|---|------|-----------|----------|------|------|
| 1 | 物料主数据 | `t_material` | `/tplus/api/v2/inventory/Query` | `TplusMaterial.query_batch` | 支持按 Disabled/IsMaterial/Ts 过滤 |
| 2 | 工作中心 | `t_workcenter` | `/tplus/api/v2/WorkCenter/QueryPage` | `TplusWorkcenter.query_batch` | |
| 3 | 库存现存量 | `t_supply` (Type=ST) | `/tplus/api/v2/currentStock/Query` | `TplusStock.query_batch` | 支持 `exclude_warehouses` 排除仓库 |
| 4 | BOM | `t_mat_wc_bom` | `/tplus/api/v2/bom/QueryPage` | `TplusBom.query_batch` | PageSize=100（非 max_page_size），展开子件 |
| 5 | 工艺路线 | `t_mat_wc` | `/tplus/api/v2/bom/Query` | `TplusRouting.query_batch` | **依赖 BOM 先填充 `_BOM_CODES`**，按 BOM 编号逐个并发查询 |

### 2.2 推送接口（APS → T+）

| # | 接口 | APS 源 | Endpoint | 方法 | 说明 |
|---|------|--------|----------|------|------|
| 6 | 生产加工单 MO | `t_supply` (Type=PL, Status=A2E) | `/tplus/api/v2/ManufactureOrderOpenApi/Create` + `/Audit` | `TplusMo.create` | 创建后自动审批，回查详情取 entryid |
| 7 | 领料申请单 RS | `t_demand` | `/tplus/api/v2/MaterialRequestOpenApi/Create` | `TplusRs.create` | 依赖 MO 已在 T+ 创建 |
| 8 | 请购单 PR | `t_supply` (Type=PR, Status=A2E) | `/tplus/api/v2/PurchaseRequisitionOpenApi/Create` + `/Audit` | `TplusPr.create` | 按批次聚合，自动审批 |

> **⚠️ Payload 包裹格式**：所有推送接口统一用 `{"dto": {...}}` 包裹；拉取接口用 `{"param": {...}}` 包裹分页参数。

## 3. 字段映射

### 3.1 拉取方向（T+ → APS，在 `*PullModel.model_validator` 中完成）

#### 物料主数据（`MaterialPullModel`）
| T+ 字段 | APS 字段 | 说明 |
|---------|---------|------|
| `编码` | `materialno` | |
| `名称` | `description` | |
| `规格型号` | `size` | |
| `主计量单位Name` | `unit` | |
| `平均成本` | `price` | |
| `存货分类Name` | `groupno` | 转 str |
| `是否自制` | `abc` / `type` | True→A/E（自制），False→B/F（外购） |
| `是否虚拟件` | `phantom` | YES/NO |
| `是否需要检验` | `leadday` / `grday` | 检验→leadday_E/grday=1，不检验→leadday_F/grday=0 |
| `保质期` + `保质期单位` | `expday` | `convert_timeunit` 统一换算为天 |
| — | `plant` / `planner` / `fifo` | 由 `pdv` 全局配置注入 |

#### 工作中心（`WorkcenterPullModel`）
| T+ 字段 | APS 字段 |
|---------|---------|
| `编码` | `workcenter` |
| `名称` | `workcentername` |

#### 工艺路线（`RoutePullModel`）
| T+ 字段 | APS 字段 | 说明 |
|---------|---------|------|
| `父件编码` | `materialno` | |
| `工作中心` | `workcenter` | |
| `工序编码` | `itemno` | |
| `加工顺序` | `sortno` | |
| — | `matver` | **占位 `"🈳❗"`**（T+ 无版本概念，联合索引缺失字段用哨兵占位） |

#### BOM（`BomPullModel`）
| T+ 字段 | APS 字段 | 说明 |
|---------|---------|------|
| `父件编码` | `productno` | |
| `子件编码` | `materialno` | |
| `需用数量` | `qty` | |
| `损耗率` | `scrap` | |
| `生产数量` | `denominator` | |
| `计量单位` / `子件计量单位` | `pu` / `cu` | 空值兜底 `''` |
| — | `matver` / `itemno` | **占位 `"🈳❗"`** |

#### 库存（`StockPullModel`）
| T+ 字段 | APS 字段 | 说明 |
|---------|---------|------|
| `存货编码` | `materialno` / `supplyno` | 同一编码同时作物料号与供应号 |
| `现存量` | `avail_qty` | |
| — | `type` | 固定 `'ST'` |
| — | `itemno` | 固定 `'stock'` |
| — | `status` / `priority` / `category` | 固定 `'CRE'` / `0` / `'MTS'` |
| — | `create_date` / `avail_date` / `dt_req` | 取当前时间 |

### 3.2 推送方向（APS → T+，在 `*PushModel.model_validator` 中完成）

#### 生产加工单 MO（`MoPushModel`）
**单据头：**
| APS 字段 | T+ 字段 | 说明 |
|----------|---------|------|
| `supplyno` | `ExternalCode` | 外部编码 |
| `dt_ordstart` | `StartDate` / `VoucherDate` | |
| `dt_ordend` | `FinishDate` | |
| `vendorno` | `Memo` | |
| — | `BusiType.Code` | 配置 `$MoBusiType` 注入 |
| — | `IsMaterialRequest` | 固定 `true`（启用领料申请） |

**明细头 `ManufactureOrderDetails[0]`：**
| APS 字段 | T+ 字段 |
|----------|---------|
| `materialno` | `Inventory.Code` |
| `avail_qty` | `Quantity` |
| `dt_ordstart` / `dt_ordend` | `PreStartDate` / `PreFinishDate` |

**工序明细 `ManufactureOrderProcessDetails`（来自 `orderwc`）：**
| APS 字段 | T+ 字段 |
|----------|---------|
| `materialno` | `Inventory.Code` |
| `orderqty` | `Quantity` |
| `itemno` | `Process.Code` |
| `sortno` | `SequenceNumber` |

**用料明细 `ManufactureOrderMaterialDetails`（来自 `demand_list`）：**
| APS 字段 | T+ 字段 | 说明 |
|----------|---------|------|
| `materialno` | `Inventory.Code` | |
| `req_qty` | `Quantity` / `SonNeededQuantity` / `SonScaleQuantity` | **取负值**（领料为负） |
| — | `IsMaterialRequest` | 固定 `true` |

**销售订单关联**：若 `so` 存在，注入 `Customer.Code` + `idsourceVoucherType="43"` + `SourceVoucherDetailId`

#### 领料申请单 RS（`RsPushModel`）
| APS 字段 | T+ 字段 | 说明 |
|----------|---------|------|
| `demandno` | `ExternalCode` | |
| — | `VoucherType.Code` | 固定 `"ST1039"` |
| — | `BusiType.Code` | 固定 `"MR01"` |
| `req_date` | `VoucherDate` | 取合并明细首条 |
| — | `Department.Code` | 从 T+ MO 详情回查 |
| — | `IdSourceVoucherType` | 固定 `"69"`（关联 MO） |
| `tplus_mo_id` | `SourceVoucherId` | MO 在 T+ 的 ID |
| MO 明细 `ID` | `SourceVoucherDetailId` | MO 用料明细行 ID |
| `req_qty` | `BaseQuantity` | 取绝对值 |

#### 请购单 PR（`PrPushModel`）
| APS 字段 | T+ 字段 | 说明 |
|----------|---------|------|
| — | `ExternalCode` / `Code` | 自动生成（毫秒级时间戳） |
| — | `RequisitionPerson.Code` | 配置 `$RequisitionPerson` 注入 |
| `avail_date` | `VoucherDate` | **取最早需求日期**（单据日期不能晚于最早物料需求日期） |
| `materialno` | `Inventory.Code` | |
| `avail_qty` | `Quantity` | |
| `avail_date` | `RequireDate` | |

## 4. 数据勾稽完整性

### 4.1 拉取侧前置依赖
```
BOM (TplusBom.query_batch)        ← 先查，填充 _BOM_CODES
    ↓ _BOM_CODES 驱动
工艺路线 (TplusRouting.query_batch) ← 按 BOM 编号逐个并发查询
```
- `TplusRouting.query_batch` 断言 `_CONNECTION._BOM_CODES` 非空，未先查 BOM 直接报错
- 查询完成后清空 `_BOM_CODES = None`

### 4.2 推送侧前置依赖
```
APS t_supply (Type=PL, Status=A2E)
    ↓ binlog 事件
T+ MO (TplusMo.create + approve)
    ↓ 回查 T+ MO 详情取 ID/entryid
T+ RS (TplusRs.create)              ← 依赖 MO 已在 T+ 创建
```
- RS 推送需先 `TplusMo.query(index_value=tplus_mo_id)` 回查 MO 详情，取 `ManufactureOrderDetails[0].ID` 和 `ManufactureOrderMaterialDetails`
- **`mo_release_success` 必须最后调用**：它会变更工单号，工单号变更后用原生 supplyno 查询会失败

### 4.3 推送顺序约定
- MO 推送保留原生供应号（`remain_native_supplyno=True`），以维持 APS 内前后工单关系不断裂
- MO 创建后自动审批（`auto_approve=True`），审批后才允许创建领料申请

## 5. 分页机制与对账（关键）

> **⚠️ 核心踩坑点**：T+ Query 接口的 `Ts` 参数是**过滤条件**（返回 TS 不小于该值的记录集），**不是分页游标**。若翻页时同时递增 `PageIndex` 又回传 `Ts`，服务端会在不断收缩的集合上继续按页号取数，页码很快越过收缩后集合末尾返回空，导致大量记录被静默丢弃（实测现存量 7100 条时旧逻辑仅取到 3000 条）。

### 正确分页逻辑（`_pull_simple_data`）
1. **纯 `PageIndex` 递增**翻页，`Ts` 仅作调用方传入的静态过滤条件，不在翻页过程中更新
2. **提前终止**：用首页 `TotalCount` 快照作 `break_count`（避免拉取期间数据减少时提前 break 漏取）
3. **最终对账**：用每页最新 `total_count`（贴近拉取结束时刻的数据集大小，消除拉取期间数据增长导致的虚假告警）
4. **不一致告警**：`len(data_list) != total_count` 时 WARNING，建议重试
5. **防御性上限**：`max_pages=100000` 防接口异常死循环

### BOM 分页特殊处理
- `PageSize=100`（非 `max_page_size`，BOM 数据量大，单次不宜太多）
- **对账用原始记录数 `fetched`**，不能用展开后 `data_list` 长度（单个 BOM 展开成多行子件，展开后长度远大于原始记录数，会提前终止翻页丢数据）

## 6. 踩坑点与解决方式

### 6.1 Ts 误用为分页游标导致丢数据
- **现象**：同时传 PageIndex+Ts 翻页，现存量 7100 条仅取到 3000 条
- **解决**：纯 PageIndex 翻页，Ts 仅作静态过滤；已修复并实取 7100 条验证

### 6.2 TotalCount 拉取期间漂移
- **现象**：拉取期间并发写入，TotalCount 从 7613 漂移到 7614，导致对账误报
- **解决**：首页快照 `break_count` 提前终止 + 最新 `total_count` 对账，漂移仅告警不阻断

### 6.3 BOM 展开后长度对账错误
- **现象**：用展开后 `data_list` 长度对账，提前终止翻页丢数据
- **解决**：用原始记录数 `fetched` 对账

### 6.4 工艺路线未先查 BOM
- **现象**：`TplusRouting.query_batch` 断言失败 `请先拉取BOM数据，获取BOM CODES`
- **解决**：必须先调 `TplusBom.query_batch` 填充 `_BOM_CODES`

### 6.5 4xx 静默放过
- **现象**：旧版 `_post` 对 401/403/404/429 静默放过，调用方把错误响应当数据处理
- **解决**：`status_code >= 400` 统一抛异常，交由上层重试

### 6.6 token 并发刷新
- **现象**：多协程同时触发刷新，重复请求刷新接口
- **解决**：`_auth_lock` + 锁后复检（double-check locking）

### 6.7 MO 工单号变更后查询失败
- **现象**：`mo_release_success` 变更工单号后，再用原生 supplyno 查 APS 数据失败
- **解决**：`mo_release_success` 放在 create 方法最后一步，所有原生号查询完成后再调

### 6.8 BOM QueryPage PageSize 限制
- **现象**：BOM 数据量大，用 max_page_size=1000 单次返回过多导致处理慢/超时
- **解决**：BOM 硬编码 `PageSize=100`（官方默认 20，最大 500）

### 6.9 库存排除仓库过滤时机
- **现象**：排除仓库过滤放错位置导致 refresh_stock 聚合后仍含排除仓库数据
- **解决**：`exclude_warehouses` 在 `query_batch` 内、`_pull_simple_data` 之后过滤，返回前完成；支持 list 或逗号分隔字符串

### 6.10 领料申请明细行 IsMaterialRequest
- **现象**：倒冲料不应走领料申请，但默认所有明细行 `IsMaterialRequest=true`
- **解决**：租户 `CustomMoPushModel` 中对倒冲料（`free1='Y'`）`pop('IsMaterialRequest')`；`CustomRsPushModel` 中过滤掉倒冲料明细行

## 7. 事件流接入

### 7.1 接入方式（租户 `client.py`）
T+ 接入分**定时任务**（拉取）和**binlog 事件**（推送）两条链路：

```python
# 租户 client.py
from apps.data_opt.components.yonyou_tplus import (
    YonyouTplusConnection, TplusStock, TplusMo, TplusRs, TplusPr,
)

tplus_conn = YonyouTplusConnection()
tplus_conn.register_source(TplusStock, TplusMo, TplusRs, TplusPr)
```

### 7.2 定时任务（拉取）
| 任务 | 触发 | Handler | 说明 |
|------|------|---------|------|
| 刷新库存 | `@cron_task` 每日定时 | `task_refresh_stock` | `TplusStock.query_batch` → `ApsPayloadSponsor.refresh_stock` 先删后插写 t_supply |

### 7.3 binlog 事件（推送）
| APS 表 | 事件类型 | Handler | 说明 |
|--------|---------|---------|------|
| `t_supply` | UPDATE (Type=PL, Status=A2E) | `batch_handle_pl_status_a2e` | → `TplusMo.create_batch` 推送 MO |
| `t_supply` | UPDATE (Type=PR, Status=A2E) | `batch_handle_pr_status_a2e` | → `TplusPr.create` 推送请购单 |
| `t_supply` | MO_RELEASE_SUCCESS | `batch_handle_mo_release_success` | → `TplusRs.create_batch` 推送领料申请（**当前注释状态**） |

### 7.4 事件链路
```
MySQL binlog → handle_insert_* → ApsEvent → EVENT_AGGREGATOR
→ Redis db_events → handle_redis_event → batch_handle_{event_type}
→ client.py handler → TplusXxx.create/create_batch → T+ API
```

### 7.5 租户级定制
租户通过继承 PushModel 注入业务规则（见 HACYXS `client.py`）：
- `CustomMoPushModel`：用 workcenter 覆盖 Department、倒冲料仓库注入、后续工单关系写入动态字段
- `CustomRsPushModel`：过滤倒冲料明细行
- `mo_data_preprocessor` / `rs_data_preprocessor`：补充物料 free1 映射

## 8. 调试技巧

### 8.1 打印外发报文
联调时 patch `_post` 打印完整 payload（**不打印 app_secret**）：
```python
orig_post = tplus_conn._post
async def patched_post(endpoint, data):
    print(f"URL: {tplus_conn.base_url}{endpoint}")
    print(f"Body: {json.dumps(data, ensure_ascii=False, indent=2)}")
    result = await orig_post(endpoint, data)
    print(f"Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
    return result
tplus_conn._post = patched_post
```

### 8.2 token 过期排查
- 查看 dev.json `_auth_at_` 与当前时间差，超过 `token_expire_seconds`（默认 12h）会自动刷新
- 刷新失败看日志 `畅捷通认证失败（第N/5次）`，检查 `app_key`/`app_secret`/`refresh_token` 是否有效

### 8.3 业务失败排查
- `code != '0'`：看响应 `message` 字段
- HTTP 500：T+ 服务端异常，凭 `message` 联系畅捷通支持
- 拉取数量告警：`T+拉取[xxx]数量与TotalCount不一致`，多为拉取期间并发写入漂移，重试即可

### 8.4 测试脚本模板
```python
import os, sys, asyncio, json
from pathlib import Path

for line in Path('/opt/myaps_api/.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, '/opt/myaps_api')

from apps.data_opt.components.yonyou_tplus import YonyouTplusConnection, TplusStock

async def main():
    tplus_conn = YonyouTplusConnection()
    tplus_conn.register_source(TplusStock)
    data = await TplusStock.query_batch(exclude_warehouses=['ck04'])
    print(f"共 {len(data.raw_data)} 条")
    print(json.dumps(data.raw_data[:2], ensure_ascii=False, indent=2))

asyncio.run(main())
```
运行：`PROJECT_DIR=<租户目录> python3 /tmp/test_xxx.py`

### 8.5 Linux 环境用 python3
Linux 环境 `python` 可能不在 PATH，运行脚本用 `python3`。

## 9. Pydantic DTO 约定

- 序列化统一用 `.model_dump(exclude_none=True)`，勿混用 `.dict()`
- 字段显式声明类型/默认值，不依赖 `extra='allow'` 隐式承载（`extra='allow'` 保留作宽松兜底）
- 字段映射/清洗逻辑统一在 `@model_validator(mode="before")` 中完成
- **联合索引缺失字段用 `"🈳❗"` 哨兵占位**（如 `matver`/`itemno`，T+ 无版本/工序概念但 APS 联合索引要求非空）
- 配置值由 `CACHE_ERP.get("$xxx", "")` 自动注入，无需在 data 中传入

## 10. 模块命名说明

模块名为 `yonyou_tplus.py`，对应用友畅捷通 T+（chanjet）ERP。连接类 `YonyouTplusConnection`，配置类 `TplusConfig`，业务对象 `Tplus{Material|Workcenter|Stock|Bom|Routing|Mo|Rs|Pr}`。配置键为 dev.json 的 `erp` 节点。

## 11. 全量拉取操作

新环境首次对接或主数据重建时，需全量拉取 T+ 主数据写入 APS：

| 顺序 | T+ 接口 | 拉取方法 | APS 目标表 | 说明 |
|------|---------|---------|-----------|------|
| 1 | 物料主数据 | `TplusMaterial.query_batch()` | `t_material` | |
| 2 | 工作中心 | `TplusWorkcenter.query_batch()` | `t_workcenter` | |
| 3 | BOM | `TplusBom.query_batch()` | `t_mat_wc_bom` | **必须先于工艺路线**，填充 `_BOM_CODES` |
| 4 | 工艺路线 | `TplusRouting.query_batch()` | `t_mat_wc` | 依赖步骤 3 的 `_BOM_CODES` |
| 5 | 库存 | `TplusStock.query_batch()` | `t_supply` (ST) | 定时任务自动执行 |

全量拉取脚本模板：
```python
import asyncio
from apps.data_opt.components.yonyou_tplus import (
    YonyouTplusConnection, TplusMaterial, TplusBom, TplusRouting,
)
from apps.data_opt.components import ApsPayloadSponsor

async def main():
    tplus_conn = YonyouTplusConnection()
    tplus_conn.register_source(TplusMaterial, TplusBom, TplusRouting)

    material_data = await TplusMaterial.query_batch()
    await ApsPayloadSponsor.refresh_material(material_data)

    bom_data = await TplusBom.query_batch()       # 填充 _BOM_CODES
    await ApsPayloadSponsor.refresh_bom(bom_data)

    routing_data = await TplusRouting.query_batch()  # 消费 _BOM_CODES
    await ApsPayloadSponsor.refresh_routing(routing_data)

asyncio.run(main())
```

## 12. 官方文档参考

- T+ 开放平台总入口：https://open.chanjet.com/docs/file/apiFile/tcloud/
- 物料：https://open.chanjet.com/docs/file/apiFile/tcloud/t+jcda/t+ch?id=30878
- 工作中心：https://open.chanjet.com/docs/file/apiFile/tcloud/t+jcda/t+gzzx?id=33327
- 库存：https://open.chanjet.com/docs/file/apiFile/tcloud/tjqt/xcl?id=30875
- BOM：https://open.chanjet.com/docs/file/apiFile/tcloud/t+jcda/tcbom?id=32410
- 生产加工单：https://open.chanjet.com/docs/file/apiFile/tcloud/t+dj/t+scjgd?id=31949
- 领料申请单：https://open.chanjet.com/docs/file/apiFile/tcloud/t+dj/t+llsqd?id=33106
- 请购单：https://open.chanjet.com/docs/file/apiFile/tcloud/t%2Bdj/t%2Bqgd?id=32741