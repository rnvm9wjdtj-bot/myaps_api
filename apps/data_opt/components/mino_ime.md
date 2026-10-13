# mino_ime.py 联调指南

> 本文档记录 MyAPS → 明珞智造家 MES (imefuture) 对接联调过程中的关键注意事项，供 AI Agent 在新项目复用模块时快速调试参考。

## 1. 鉴权机制

### 签名算法
```
sign = md5(json.dumps(body, ensure_ascii=False) + erptimestamp + access_key_secret).lower()
```
- **POST**：param = 完整 JSON body（`json.dumps` 后的字符串）
- **GET**：param = URL 参数按 ASCII 字典序排序拼接（`k1=v1&k2=v2`）
- Header 传 `sign` / `erptimestamp` / `Content-Type`，**不需要 memberId**
- `erptimestamp` 为毫秒级时间戳字符串

### 配置项（dev.json `ime` 节点）
| 配置键 | 说明 | 测试环境值 |
|--------|------|-----------|
| `base_url` | 网关地址 | `https://beta-tmgc2-gateway.imefuture.com` |
| `access_key_secret` | 签名密钥 | `2EE351BC3AC94730FC227F9DB4B73083` |
| `$siteCode` | 企业编号 | `A00046447`（**不带 NO. 前缀**） |
| `$departmentCode` | 部门编码 | （测试环境为空，工序任务单可能需要非空值） |
| `$createUser` | 创建人工号 | （测试环境为空） |

### 响应分层
- **网关层**：`{status, returnCode, returnMsg, memberId}`
  - `returnCode=0`：网关通过
  - `returnCode=11`：`access_key_secret` 错误（非 memberId 缺失）
  - `status=404`：`siteCode` 值错误或 endpoint 不存在
- **业务层**：`{success, errorCode, errorMessage, data}`
  - `success=true`：业务成功
  - `success=false`：业务失败，看 `errorMessage` 或 `data` 内嵌信息

## 2. 五个接口总览

| # | 接口 | APS 源表 | Endpoint | Payload 格式 | 联调状态 |
|---|------|---------|----------|-------------|---------|
| 1 | 作业单元类型 | `t_workcenter` | `erp/workUnitType/addWorkUnitTypeAndWorkUnitBatchToExternal` | `{"siteCode":..., "addVos":[...]}` | ✅ 已通 |
| 2 | 工序 | `t_mat_wc` (去重 itemno) | `erp/operation/addAndUpdateOperationBatchToExternal` | 裸列表 `[...]` | ✅ 已通 |
| 3 | 工艺路线 | `t_mat_wc` | `erp/process/addProcessBatchToExternal` | 裸列表 `[...]` | ✅ 已通 |
| 4 | 物料主数据 | 手动构造 | `erp/material/saveAndUpdateMaterial` | `{"entity":[{"zzjmaterial":{...}}]}` | ✅ 已通 |
| 5 | 工序任务单 | `t_supply` (Type=PL) | `erp/operationTaskOrder/api/create` | `[{"siteCode":..., "productionOrderVo":{...}}]` | ✅ 已通 |

> **⚠️ Payload 格式陷阱**：五个接口的 payload 包裹格式各不相同，极易混淆。上表已逐一标明，新增接口时务必先确认格式。

## 3. APS 表 → 明珞字段映射

### 3.1 作业单元类型（`t_workcenter` → `ImeWorkUnitTypePushModel`）

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| `workcenter` | `workUnitTypeCode` | 编号，同时作作业单元编号（1:1 自动创建） |
| `workcentername` | `workUnitTypeName` | 名称 |
| `location` | `workshopCode` | 车间编号 |
| `worker` | `standardCapacity` | 标准产能 |

- 接口自动创建同编号作业单元并建立 1:1 关联
- 编号已存在则幂等跳过（`reason` 标注"编号已存在"）
- 整批事务：任一条校验失败全批不入库

### 3.2 工序（`t_mat_wc` 去重 → `ImeOperationPushModel`）

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| `itemno` | `operationCode` | 工序编码 |
| `itemname` / `workcenter` | `operationName` | 工序名称（itemname 优先，兜底 workcenter） |
| — | `operationTypeCode` | 固定 `"PRODUCTION"` |
| `workcenter` | `workUnitTypeCode` | **必须引用明珞已存在的作业单元类型编号** |
| `avg_basesec` | `standardTime` | 标准用时（秒） |
| — | `standardTimeUnit` | 固定 `"SECOND"` |
| — | `standardCapacity` | 固定 `1`（**文档标选填但实际必填**，缺字段导致 500 NPE） |

- 数据源通过 `ApsPayloadSponsor.extract_unique_matwcitem(itemnos=...)` 去重提取
- `workUnitTypeCode` 必须先推送作业单元类型，否则明珞报错

### 3.3 工艺路线（`t_mat_wc` → `ImeRoutePushModel`）

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| `materialno` + `matver` | `processCode` | `f"{materialno}-{matver}"`（**带版本后缀**） |
| `materialno` + `matver` | `processName` | 同 processCode |
| `matver` | `outDockProcessVersion` | 外部对接工艺版本 |
| `itemno` | `operationInfoVos[].operationCode` | 工序编码 |
| `itemname` / `workcenter` | `operationInfoVos[].operationName` | 工序名称 |
| `workcenter` | `operationInfoVos[].workUnitTypeCode` | 作业单元类型编号 |
| `basesec` | `operationInfoVos[].standardTime` | `basesec / 100`（换算为秒） |

- 按 `(materialno, matver)` 分组，每组按 `sortno` 升序排列
- **宽松创建**：不校验工序是否存在，`data.value` 报 `PROCESS_OPERATION_NOT_EXIT` 属"假成功"
- 重复记录会返回 500，需先删后建（删除接口用 **DELETE** 方法，非 POST）

### 3.4 物料主数据（手动构造 → `ImeMaterialPushModel`）

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| `materialno` | `materialCode` | 物料编码（匹配键，存在更新否则新建） |
| `description` | `materialText` | 物料名称（兜底用 materialCode） |
| — | `materialUnitText` | 基本单位（**实际必填**，须传明珞已存在单位的**中文描述**） |

- **不在双方对接合同范围内**，仅用于辅助推送工序任务单依赖的缺失物料
- 不接入 binlog 事件流，需手动调用 `push_materials()`
- `materialUnitText` 传明珞系统中已存在单位的**中文描述/名称**（如"件"、"千克"），不是编码（如"PC"、"kg"）

> **⚠️ 当前为注释状态（2026-10-13）**
>
> 联调完成后，物料推送相关代码已全部注释，涉及三处：
> 1. `mino_ime.py`：`ImeMaterialPushModel` 类定义（L579-597）、`ImeMaterial` 类定义（L600-634）
> 2. `client.py` L16：`ImeMaterial` 的 import 行
> 3. `client.py` L22：`register_source(...)` 中的 `ImeMaterial` 参数
> 4. `client.py` L82-97：`push_materials()` 函数定义
>
> **启用步骤**（后续调试需推送物料时）：
> 1. 取消 `mino_ime.py` 中 `ImeMaterialPushModel` 和 `ImeMaterial` 的注释
> 2. 取消 `client.py` 中 `ImeMaterial` 的 import 注释
> 3. 取消 `client.py` 中 `register_source(...)` 的 `ImeMaterial` 参数注释
> 4. 取消 `client.py` 中 `push_materials()` 函数的注释
> 5. 调试完成后**恢复全部注释状态**
>
> **注意**：四处注释必须同时取消/恢复，遗漏任一处会导致 `ImportError` 或 `NameError`。

### 3.5 工序任务单（`t_supply` Type=PL → `MoPushModel`）

**productionOrderVo（订单头）：**

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| `dt_ordstart` | `plannedStartDateTime` | 计划开始时间 |
| `dt_ordend` | `plannedEndDateTime` | 计划结束时间 |
| — | `departmentCode` | 部门编码（配置注入，测试环境为空） |
| `supplyno` | `sourceNo` | 外部订单编号（**原映射 vendorno，null 时用 supplyno 兜底**） |
| `materialno` | `materialCode` | 物料编码（**不带 -V1 后缀**） |
| `avail_qty` | `plannedQuantity` | 计划数量 |
| — | `createUser` | 创建人（配置注入） |
| `create_date` | `createDateTime` | 创建时间 |
| — | `priority` | 固定 `"1"` |

**operationTaskOrderVoList（工序明细）：**

| APS 字段 | 明珞字段 | 说明 |
|----------|---------|------|
| — | `equipmentFlag` | 固定 `"1"`（设备报工标志） |
| `orderno` | `sourceNo` | 外部工序任务单编号 |
| `itemno` | `operationCode` | 工序编码 |
| `workcenter` | `workCenterCode` | **工作组(WorkingTeam)编码，非作业单元(WorkUnit)** |
| `sortno` | `rowNumText` | 工序顺序号 |
| `dt_start` | `plannedStartDateTime` | 计划开始时间 |
| `dt_end` | `plannedEndDateTime` | 计划结束时间 |
| `orderqty` | `plannedQuantity` | 计划数量 |
| `sys_stamp` | `createDateTime` | 创建时间 |
| BOM 查询 | `operationBomList` | `[{"materialCode":..., "quantity":...}]` |

- BOM 通过 `_production_cache.get_bom(productno, matver, itemno)` 获取

## 4. 数据勾稽完整性 — 前置依赖链

> **核心原则**：明珞侧的主数据必须按依赖顺序先建好，否则推送工序任务单时会逐层报错。

```
作业单元类型 (WorkUnitType)
    ↓ workUnitTypeCode 引用
工序 (Operation)
    ↓ operationCode 引用
工艺路线 (Process/Route)
    ↓ processCode/materialCode 匹配
物料主数据 (Material) ← 成品物料 + BOM 子物料
    ↓ materialCode 引用
工序任务单 (OperationTaskOrder)
```

### 4.1 推送顺序（`batch_handle_mat_wc_insert`）

`t_mat_wc` binlog 事件触发时，**必须先推工序再推工艺路线**：
```python
# client.py batch_handle_mat_wc_insert
await ImeOperation.create_or_update(operation_details)  # 先工序
await ImeRoute.create(data=event_data_list)             # 后工艺路线
```
原因：工艺路线引用工序编号，明珞宽松创建不校验工序存在，但后续工序任务单会校验。

### 4.2 工序任务单前置依赖（按报错顺序逐层暴露）

| 层级 | 缺失主数据 | 明珞报错信息 | 解决方式 |
|------|-----------|-------------|---------|
| 1 | 工作组 (WorkingTeam) | `远程内部接口调用失败:null` | 明珞方修复 `getWorkingTeamInfoByWorkingTeamCode` bug |
| 2 | 工艺路线匹配 | `系统中工艺不存在，请维护工艺!` | processCode 带 `-V1` 后缀 vs materialCode 不带后缀，需明珞方确认匹配逻辑 |
| 3 | 物料主数据 | `该物料[xxx]系统中不存在!` | 先推送物料主数据（成品 + BOM 子物料） |
| 4 | 未知 | `500 Internal Server Error` | 明珞方修复服务端校验规则后通过；最终 `departmentCode=LH`、`reportType` 注释、`createUser` 留空 |

> **⚠️ 关键区分**：`workCenterCode` 查的是**工作组 (WorkingTeam)**，不是**作业单元 (WorkUnit)**。推送作业单元类型不会创建工作组，二者是独立主数据。

## 5. 联调踩坑点与解决方式

### 5.1 siteCode 带前缀导致 404
- **现象**：siteCode 带 `NO.` 前缀时网关返回 404
- **解决**：直接用 dev.json 配置原值（如 `A00046447`），不带前缀

### 5.2 returnCode=11 是密钥错误
- **现象**：`returnCode=11`，曾误判为 memberId 缺失
- **解决**：检查 `access_key_secret` 是否正确

### 5.3 工序 standardCapacity 文档标选填但实际必填
- **现象**：不传 `standardCapacity` 时明珞 500 NPE
- **解决**：`ImeOperationPushModel` 显式声明 `standardCapacity: float = Field(1)`

### 5.4 工序/工艺路线 payload 用裸列表
- **现象**：误用 `{"entity":[...]}` 格式导致失败
- **解决**：工序和工艺路线都用裸列表 `[...]`，只有作业单元类型用 `{"siteCode":..., "addVos":[...]}`

### 5.5 物料 materialUnitText 须传中文描述
- **现象**：传 `PC`/`kg`/`个` 均报"物料单位描述不存在！"
- **解决**：传明珞系统中已存在单位的**中文描述**（如"件"、"千克"），不是编码
- **根因**：字段名 `materialUnitText`（Text），明珞按描述匹配而非编码

### 5.6 sourceNo 映射兜底
- **现象**：`vendorno` 为 null 时验证失败
- **解决**：`sourceNo` 改为 `supplyno` 兜底

### 5.7 工艺路线重复记录返回 500
- **现象**：重复推送已有工艺路线返回 500
- **解决**：先调删除接口（DELETE 方法）删后重建

### 5.8 processCode 与 materialCode 不匹配
- **现象**：工艺路线 `processCode=2100-011-300-V1`，工序任务单 `materialCode=2100-011-300`，明珞报"工艺不存在"
- **状态**：明珞方已修复匹配逻辑，但后续仍出现 500，需进一步确认

### 5.9 classmethod 中误用 self._CONNECTION
- **现象**：`ImeRoute`/`ImeOperation` 的 classmethod 中误用 `self` 导致 NameError 被 except 吞掉
- **解决**：改为 `cls._CONNECTION`

### 5.10 鉴权 await 遗漏
- **现象**：`auth()` 是 async 方法，漏写 await 导致签名未生成
- **解决**：所有 `self.auth()` / `cls._CONNECTION.auth()` 调用必须加 `await`

## 6. 事件流接入

### 6.1 binlog 事件注册（`project_files/__init__.py`）
| APS 表 | 事件类型 | Handler | 说明 |
|--------|---------|---------|------|
| `t_workcenter` | INSERT | `batch_handle_workcenter_insert` | → 作业单元类型 |
| `t_mat_wc` | INSERT | `batch_handle_mat_wc_insert` | → 工序 + 工艺路线 |
| `t_supply` | UPDATE (Type=PL, Status=A2E) | `batch_handle_pl_status_a2e` | → 工序任务单 |

### 6.2 事件链路
```
MySQL binlog → handle_insert_* → ApsEvent → EVENT_AGGREGATOR
→ Redis db_events → handle_redis_event → batch_handle_{event_type}
→ client.py handler → ImeXxx.create/create_or_update → 明珞 API
```

### 6.3 物料推送不接入事件流
物料主数据推送不在对接合同范围内，通过 `push_materials()` 手动调用：
```python
# client.py
async def push_materials(data: list[dict]):
    return await ImeMaterial.create_or_update(data)
```

## 7. 调试技巧

### 7.1 打印外发报文
联调时 patch `_post` 打印完整 payload（sign/erptimestamp + body），但**不打印 access_key_secret**：
```python
orig_post = ime_conn._post
async def patched_post(endpoint, data):
    headers = await ime_conn.auth("POST", body=data)
    print(f"URL: {ime_conn.base_url}{endpoint}")
    print(f"Headers: {headers}")  # sign/erptimestamp 可打印
    print(f"Body: {json.dumps(data, ensure_ascii=False, indent=2)}")
    result = await orig_post(endpoint, data)
    print(f"Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
    return result
ime_conn._post = patched_post
```

### 7.2 500 错误排查
明珞返回 500 Internal Server Error 时，响应体只有网关层信息（`requestId`/`timestamp`/`path`），无业务层 errorMessage。需：
1. 记录 `requestId` 提供给明珞方查服务端日志
2. 检查 payload 中是否有空字符串字段（如 `departmentCode`/`createUser`）可能导致 NPE
3. 检查前置主数据是否都已推送

### 7.3 测试脚本模板
```python
import os, sys, asyncio, json
from pathlib import Path

for line in Path('/opt/myaps_api/.env').read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, '/opt/myaps_api')

from apps.data_opt.components.mino_ime import ImeConnection, ImeXxx

async def main():
    ime_conn = ImeConnection()
    ime_conn.register_source(ImeXxx)
    result = await ImeXxx.create_or_update(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(main())
```
运行：`PROJECT_DIR=WXZJJX python3 /tmp/test_xxx.py`

### 7.4 Linux 环境用 python3
该环境 `python` 不在 PATH，运行脚本用 `python3`。

## 8. Pydantic DTO 约定

- 序列化统一用 `.model_dump(exclude_none=True)`，勿混用 `.dict()`
- 字段显式声明类型/默认值（如 `standardCapacity: float = Field(1)`），不依赖 `extra='allow'` 隐式承载
- 字段映射/清洗逻辑统一在 `@model_validator(mode="before")` 中完成
- `siteCode` 等配置值由 `CACHE_IME.get("$xxx", "")` 自动注入，无需在 data 中传入

## 9. 模块命名说明

模块原名为 `mino.py`，2026-10-11 重命名为 `mino_ime.py`（通用化命名，不绑定单一客户）。所有 `Mino*` 类名改为 `Ime*`，`CACHE_MINO` 改为 `CACHE_IME`，`dev.json` 配置键 `mino` 改为 `ime`。

---

**最后更新**: 2026-10-13  
**联调环境**: WXZJJX（测试租户）  
**联调状态**: 五个接口全部联调通过（2026-10-13）