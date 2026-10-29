# api-interface-guide.md 维护交接指南

> 本文档供后续接手维护 `docs/guide/api-interface-guide.md` 的 AI Agent 阅读。读完本指南即可无缝接手该知识库文档的新增/修改/校验工作。
>
> **维护目标**：保持 `api-interface-guide.md` 与源码（`routers.py` + `schemas.py` + `protomodels.py`）一致，使其能准确回答"哪种场景调哪个接口"。

---

## 一、项目定位（不可漂移）

- **我方角色**：APS 系统的**实施方**。
- **项目性质**：本系统用于**集成外部系统与 APS**，仅做数据集成（写入/查询），**不含 APS 运算逻辑**。
- **数据库来源**：schema 由 APS 系统 inspect 而来，本系统不建表、不运算，只读写 APS 已有表/视图。
- **文档受众分工（重要）**：
  - `docs/guide/api-interface-guide.md`（接口知识库）面向**外部三方调用方**，供其调用接口备查，**不得出现任何源码/技术细节**（表名、视图名、PascalCase 列名、存储过程名、装饰器参数、锁键格式、内部函数/类名等）。
  - `docs/guide/api-interface-guide-maintenance.md`（本维护指南）面向**我方人员及 AI agent**，便于快速接手维护，**可含技术细节**（源码文件名、类名、表名、字段映射等）。
- **权威性**：原《数据对接指引.pdf》已弃用，**以本 md 文档为准**。PDF 中 `GET /t_demand` 已由 `GET /api/v_demand/{demandno}` 替代。
- **MRP 产物**：`DM/RS/SS/PL/MO/PO/PR` 由 APS 生成，外部系统不应自行产生，只读或由 APS 推送。

---

## 二、文档结构（六章，顺序固定）

| 章节 | 内容 | 数据来源 |
|---|---|---|
| 〇、项目定位 | 实施方/集成/inspect/受众 | 本指南第一节 |
| 一、核心业务概念 | 需求vs供应、编号共用、主数据与生产数据定义、主数据依赖链、多账套、通用约定 | PDF + 业务知识 |
| 二、场景速查表 | 用户场景→接口映射表（按主数据/供应/需求/报工/报表/内部分组） | routers.py 路由清单 |
| 三、接口详解 | 每个接口的标签/入参/语义/注意事项 | routers.py 路由签名 + summary |
| 四、DTO 字段定义 | 每个写入 DTO 的字段表（必填/约束/说明/示例） | schemas.py 的 Accept* 类 |
| 五、Agent 决策指引 | 关键词映射、歧义澄清、回答规范 | 综合提炼 |
| 六、附录 | 主数据关联关系 + 前端 BOM/工序查不到的排障（**本章允许使用表名/字段名**） | protomodels.py 主键 + v_mat_wc_bom/v_mat_wc 关联逻辑 |

**新增章节时顺延编号，勿破坏既有顺序。**

---

## 三、数据来源文件

| 文件 | 用途 | 关键内容 |
|---|---|---|
| `apps/io_api/routers.py` | 路由签名、summary、入参 | `@rt.get/post/put/delete` 装饰器 + 函数签名（Query/Path/Body） |
| `apps/io_api/schemas.py` | DTO 字段定义、校验、example | `class Accept*(BaseModel)` 的 `Field(...)` 定义 |
| `apps/io_api/protomodels.py` | 表唯一键、字段映射 | `class Proto*` 的 `Meta.unique_together` / 业务键 |
| `apps/io_api/gc.py`（如需） | 枚举取值 | `*Enum` 类成员 |

**提取参数签名的方法**：
```bash
# 列出所有路由装饰器与路径
grep -nE '@rt\.(get|post|put|delete|patch)\(' apps/io_api/routers.py
# 查看某路由函数入参（定位 async def 后的参数行）
sed -n '<行号>,+8p' apps/io_api/routers.py | grep -E 'Query|Path|Body|Literal'
```

**提取 DTO 字段的方法**：
```bash
grep -nE '^class Accept' apps/io_api/schemas.py  # 定位类
# 读取该类到下一个 class 之间的 Field(...) 行
```

### 主数据对象 → APS 表 / ProtoModel / Accept 映射

7 项主数据对象与 APS 数据库表、ORM 模型、DTO、路由的对应关系（维护时定位字段定义/唯一键的入口）：

| 主数据对象 | APS 表名 | ProtoModel（protomodels.py） | Accept DTO（schemas.py） | 写入路由 |
|---|---|---|---|---|
| 物料 | `t_material` | `ProtoMaterial` | `AcceptMaterial` | `POST /api/t_material` |
| 工作中心 | `t_workcenter` | `ProtoWorkcenter` | `AcceptWorkcenter` | `POST /api/t_workcenter` |
| 产线版本 | `t_mat_ver` | `ProtoMatVer` | `AcceptMatVer` | `POST /api/t_mat_ver` |
| 工序 | `t_mat_wc` | `ProtoMatWc` | `AcceptMatWc` | `POST /api/t_mat_wc` |
| BOM | `t_mat_wc_bom` | `ProtoMatWcBom` | `AcceptMatWcBom` | `POST /api/t_mat_wc_bom` |
| 模具 | `t_mold` | `ProtoMold` | `AcceptMold` | `POST /api/t_mold` |
| 机台模具 | `t_mat_wc_mold` | `ProtoMatWcMold` | `AcceptMatWcMold` | `POST /api/t_mat_wc_mold` |

- 表名与 API 路径一致（`POST /api/t_material` → 表 `t_material`），但**表名仅在本维护指南出现，接口知识库不得暴露**。
- `ProtoModel.Meta.unique_together` 给出唯一键；`Accept*` 的 `Field(...)` 给出字段定义/必填/约束。
- 生产/需求/报工等业务表同理：`t_supply`/`t_demand`/`t_confirm`/`t_checkqty_report`，对应 `AcceptSupply`/`AcceptDemand`/`AcceptConfirm`/`AcceptCheckQtyReport`。

---

## 四、维护约定（必须遵守）

### 1. 端点前缀
- **所有端点必须带 `/api` 前缀**，如 `POST /api/t_supply`，防止调用时遗漏。
- 速查表、接口详解标题、关键词映射、歧义澄清中**全部**端点都要带前缀，包括"或"分支的简写。

### 2. 不暴露源码细节
- DTO 类型统一写 `List[DTO]`，**禁止**出现 `List[AcceptMaterial]`、`List[AcceptSupply]` 等源码类名。
- **禁止**出现实现细节描述，如"由路由器 prefix 拼接"、"include_in_schema=False"（内部接口可注明"仅本地访问"）、分布式锁键名格式（如 `t_supply:{db_name}:post`，改用"分布式锁保护"）、存储过程名（如 `SupplyDeleteAll`，改用"先删除该供应及关联记录"）等。
- 枚举类型写取值，如 `枚举 Y/N`、`枚举 PL/MO/ST/PO/PR`，不写 `gc.YesNoEnum`。

### 3. 必填标记
- ✅ 必填（`Field(...)` 无默认值）
- ⚪ 可选（有默认值或 `Optional`）
- ⚠️ 条件必填（如 `Field(... if MYAPS_VERSION == 'P' else None)`）

### 4. 业务键白名单校验
- 路径参数含业务键（supplyno/demandno/materialno/itemno 等）的路由，文档应注明"经白名单校验"。
- 合法字符集：`^[A-Za-z0-9_.\-]+$`。
- 占位符约定：`itemno="..."` 或 `materialno="..."` 表示**不限制该字段**，文档需说明。

### 5. 多账套规则
- 写入可 `db_name=aps1,aps2`；**GET 查询只支持单账套**。
- 预测订单只传预测账套；其余主数据/生产数据同时传两个账套。

### 6. 接口职责划分（已确立，勿混淆）
| 接口 | 查询源 | 适用 |
|---|---|---|
| `GET /api/v_demand/{demandno}` | `v_demand` 视图（**不限类型**） | 按需求号查任意类型需求（SO/FC/DM/RS/SS）+ 合并 MO 信息到 `meta.mo` |
| `GET /api/v_mo_demand/{supplyno}` | `v_mo_demand` 视图（**仅 MO**） | 仅查 MO 工单领料（视图已过滤非 MO 数据） |

### 7. 覆盖语义说明
- `POST /api/t_supply`：按 supplyno **整条覆盖**（先删后插 + 分布式锁），非局部更新。
- `PUT /api/t_supply/type/{type_}`：按类型**整批替换**（清空该类型所有记录再插入），风险大。
- 当前**无局部 patch 接口**（`PATCH /t_supply/{supplyno}` 已注释）。

---

## 五、维护工作流

### 场景 A：新增路由

1. **改源码**：在 `routers.py` 添加路由，对齐现有风格（`log_api_request` + 白名单校验 + `build_safe_condition`/`build_safe_filter` + `standard_response` + `try/except`）。
2. **速查表**：在「二、场景速查表」对应分组加一行 `| 用户场景 | \`METHOD /api/path\` |`。
3. **接口详解**：在「三、接口详解」对应分组加 `#### \`METHOD /api/path\` — summary`，列出标签/入参/语义/注意事项。
4. **DTO 字段**：若为写入接口且对应新 DTO，在「四、DTO 字段定义」加字段表。
5. **关键词映射**：在「五、Agent 决策指引」关键词表加映射行。
6. **校验**：跑「六、检查清单」。

### 场景 B：修改路由

- 同步更新**速查表、接口详解、DTO 字段**三处（若有 DTO）。
- 入参变化时务必同步接口详解的 `- **入参**：` 行。

### 场景 C：启用被注释的路由

- 取消注释后，**必须对齐现有路由风格**（旧注释代码常缺 `log_api_request`/白名单校验/`standard_response`/异常处理/安全过滤，需补齐）。
- 用 `build_safe_condition` / `build_safe_filter` 替代裸字符串拼接（防 SQL 注入）。
- 启用后在 md 文档按「场景 A」流程补充。

### 场景 D：新增/修改 DTO 字段

- 在 `schemas.py` 改 `Field(...)` 定义后，同步「四、DTO 字段定义」对应表格。
- 必填/约束/示例三列必须与源码一致。

---

## 六、检查清单（每次维护后必跑）

```bash
# 1. routers.py 语法校验
python3 -c "import ast; ast.parse(open('apps/io_api/routers.py').read()); print('语法OK')"

# 2. 所有端点带 /api 前缀（不应有 /t_ /v_ 开头的不带前缀端点）
grep -nE '`(GET|POST|PUT|DELETE) /(t_|v_)' docs/guide/api-interface-guide.md  # 应无输出

# 3. 无源码细节泄漏（以下均应无输出）
grep -nE 'List\[Accept' docs/guide/api-interface-guide.md                  # DTO 源码类名
grep -nE 'include_in_schema' docs/guide/api-interface-guide.md             # FastAPI 装饰器参数
grep -nE ':\{db_name\}' docs/guide/api-interface-guide.md                  # 分布式锁键名格式
grep -nE 'SupplyDeleteAll|SupplyConvert' docs/guide/api-interface-guide.md # 存储过程名
grep -nE '视图' docs/guide/api-interface-guide.md                          # "视图"字样（全文禁用，附录以"数据源/严格关联"替代）
# PascalCase 数据库列名：仅限正文（〇~五章），附录「六、主数据关联与常见问题排障」合法使用表名/字段名
sed -n '1,/^## 六、附录/p' docs/guide/api-interface-guide.md | grep -nE '\b(DemandNo|SupplyNo|MaterialNo|ItemNo|ProductNo|WorkCenter|MatVer)\b'

# 4. 接口详解中每个 #### 标题都有对应的 - **入参** 行
# （接口数 == 入参行数）
grep -cE '^#### ' docs/guide/api-interface-guide.md
grep -cE '^- \*\*入参\*\*' docs/guide/api-interface-guide.md
# 两者应相等

# 5. 章节结构完整
grep -nE '^## ' docs/guide/api-interface-guide.md
# 应有：〇项目定位 / 一核心概念 / 二速查表 / 三接口详解 / 四DTO字段 / 五Agent决策指引 / 六附录(主数据关联与常见问题排障)
```

---

## 七、已确立的关键决策（勿推翻）

1. **`GET /api/t_demand` 不实现**：用 `GET /api/v_demand/{demandno}` 替代（查视图，不限需求类型，合并 MO 信息）。
2. **`GET /api/v_mo_demand/{supplyno}` 仅 MO**：视图已过滤非 MO 数据，查 SO/FC 等需用 `v_demand`。
3. **`DELETE /api/t_demand/{demandno}/{materialno}/{itemno}`**：按三段路径删除，`materialno`/`itemno` 传 `...` 表示不限制。
4. **`type` 字段条件必填**：AcceptMaterial 的 `type` 仅 `MYAPS_VERSION=P` 时必填。
5. **AcceptSupply 内部转换**：外部传 `type=MO` 会强制转 `PL` 适配工单推送逻辑。
6. **AcceptDemand 数量符号**：`req_qty` 须为负数，正数自动转负。
7. **PDF 弃用**：md 为权威，PDF 仅作历史参考。

---

## 八、回答规范（Agent 使用本文档时）

回答用户"该调哪个接口"时，应给出：
1. **接口**：方法 + 完整路径（带 `/api`）
2. **为什么**：一句话说明匹配理由
3. **关键参数**：必传的 path/body/query 参数
4. **注意事项**：覆盖语义、数量符号、多账套、占位符等易错点（若有）

---

**最后更新**：2026-10-29
**维护对象**：`docs/guide/api-interface-guide.md`
**本指南位置**：`docs/guide/api-interface-guide-maintenance.md`