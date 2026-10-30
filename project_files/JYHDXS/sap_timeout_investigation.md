# SAP 投料数据超时问题排查文档

> **来源**: 生产环境日志 ID 888472，2026-10-27T22:56:22 UTC
> **客户**: JYHDXS（江阴海达橡塑）
> **触发函数**: `project_files/JYHDXS/client.py:351` `get_sap_input_stock`
> **错误消息**: 生产投料同步失败：获取SAP投料数据超时 - 超过75秒
> **文档用途**: 供开发/测试环境 AI AGENT 按本流程复现与定位根因

---

## 一、原始错误堆栈

```
File "/root/.local/bin/gunicorn", line 8, in <module>
    sys.exit(run())
File "/root/.local/lib/python3.12/site-packages/gunicorn/app/wsgiapp.py", line 66, in run
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]", prog=prog).run()
File "/root/.local/lib/python3.12/site-packages/gunicorn/app/base.py", line 235, in run
    super().run()
File "/root/.local/lib/python3.12/site-packages/gunicorn/app/base.py", line 71, in run
    Arbiter(self).run()
File "/root/.local/lib/python3.12/site-packages/gunicorn/arbiter.py", line 248, in run
    self.manage_workers()
File "/root/.local/lib/python3.12/site-packages/gunicorn/arbiter.py", line 701, in manage_workers
    self.spawn_workers()
File "/root/.local/lib/python3.12/site-packages/gunicorn/arbiter.py", line 788, in spawn_workers
    self.spawn_worker()
File "/root/.local/lib/python3.12/site-packages/gunicorn/arbiter.py", line 753, in spawn_worker
    worker.init_process()
File "/root/.local/lib/python3.12/site-packages/gunicorn/workers/base.py", line 145, in init_process
    self.run()
File "/root/.local/lib/python3.12/site-packages/uvicorn/workers.py", line 104, in run
    return asyncio_run(self._serve(), loop_factory=self.config.get_loop_factory())
File "/usr/local/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
File "/usr/local/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
File "/root/.local/lib/python3.12/site-packages/apscheduler/executors/base.py", line 181, in run_coroutine_job
    retval = await job.func(*job.args, **job.kwargs)
File "/app/apps/data_opt/utils/scheduler.py", line 295, in async_wrapper
    result = await asyncio.wait_for(func(), timeout=max_execution_time)
File "/usr/local/lib/python3.12/asyncio/tasks.py", line 520, in wait_for
    return await fut
File "/app/project_files/JYHDXS/client.py", line 603, in task_refresh_stock
    await StockManager.refresh()
File "/app/project_files/JYHDXS/client.py", line 416, in refresh
    df_input_vir = await StockManager.get_sap_input_stock()
File "/app/project_files/JYHDXS/client.py", line 351, in get_sap_input_stock
    CLIENT_LOGGER.fail("生产投料同步", "获取SAP投料数据超时", "超过75秒")
File "/app/globalobjects/logger/core.py", line 303, in fail
    self.error(msg)
File "/app/globalobjects/logger/core.py", line 281, in error
    self._log(logging.ERROR, msg, *args, **kwargs)
File "/app/globalobjects/logger/core.py", line 193, in _log
    stack_trace = ''.join(traceback.format_stack())
```

---

## 二、调用链解读

| 层级 | 位置 | 作用 |
|---|---|---|
| 1 | `gunicorn` → `uvicorn worker` | WSGI 容器启动 worker 进程 |
| 2 | `apscheduler executors` | APScheduler 调度执行定时任务 |
| 3 | `scheduler.py:295 async_wrapper` | 定时任务包装器，外层 `asyncio.wait_for` 限制总执行时长 |
| 4 | `client.py:603 task_refresh_stock` | 入口：刷新库存定时任务 |
| 5 | `client.py:416 refresh` | 调用 `get_sap_input_stock()` |
| 6 | `client.py:351 get_sap_input_stock` | **触发点**：内层 `wait_for(timeout=75)` 超时 |
| 7 | `logger/core.py:193 _log` | 记录日志时 `traceback.format_stack()` 生成当前调用栈（非异常堆栈） |

### 关键澄清

1. **此堆栈不是异常抛出堆栈**：`core.py:193` 调用的是 `traceback.format_stack()`（打印当前调用栈），而非 `format_exc()`（打印异常栈）。说明是**主动记录**，不是程序崩溃。
2. **业务影响有限**：`get_sap_input_stock` 超时后 `return None`（`client.py:352`），`refresh()` 在 `client.py:421` 判断 `if df_input_vir is not None` 跳过投料数据，最终库存刷新会用 SAP 库存 + MTO 数据继续执行，**仅缺失 MI 投料虚拟库存部分**，任务不会中断。

---

## 三、相关代码定位

### 3.1 SAP 投料取数（`client.py:295-363`）

```python
# client.py:295-305  同步函数，通过 run_in_executor 调用
def fetch_input_data():
    response = sap_session.get(
        url=sap_url1,
        headers={
            'interface': 'order_material_input',
            'werks': werks,
            'i_datum_f': i_datum_f,
            'i_datum_t': i_datum_t,
        },
        timeout=(15, 60),   # 连接15s + 读取60s
    ).json()
    ...

# client.py:344-355  双层超时保护
loop = asyncio.get_event_loop()
try:
    df_input = await asyncio.wait_for(
        loop.run_in_executor(None, fetch_input_data),
        timeout=75,          # ← 整体协程超时 75s
    )
except asyncio.TimeoutError:
    CLIENT_LOGGER.fail("生产投料同步", "获取SAP投料数据超时", "超过75秒")
    return None
except Exception as e:
    CLIENT_LOGGER.fail("生产投料同步", "获取SAP投料数据失败", str(e))
    return None
```

### 3.2 `sap_session` 初始化（`client.py:28-37`）

```python
erp = PROJECT_JSON_FILE.get("erp", {})
sap_url1 = erp.get("base_url", "") + '/zrestful_test2?sap-client=800'   # 硬编码 800
sap_url2 = erp.get("base_url", "") + '/zrestful_plan?sap-client=' + erp.get("sap-client")
werks = erp.get("werks", "")
sap_username = erp.get("username", "")
sap_password = erp.get("password", "")

sap_session = get_session(allowed_methods=["GET", "POST"])               # 模块级全局单例
add_basic_auth_requests(sap_session, sap_username, sap_password)
```

### 3.3 `get_session` 实现（`apps/data_opt/utils/common.py:20-78`）

```python
def get_session(
    retries: int = 3,
    allowed_methods: list = ["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
    pool_connections: int = 50,
    pool_maxsize: int = 50,
    connect_timeout: float = 15.0,
    read_timeout: float = 60.0,
    backoff_factor: float = 1.0,
    enable_monitor: bool = True,
):
    retry_strategy = Retry(
        total=retries,
        connect=retries,
        read=retries,
        redirect=retries,
        status=retries,
        backoff_factor=backoff_factor,            # 1s → 2s → 4s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=allowed_methods,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        pool_block=False
    )
    request_session = requests.Session()
    request_session.timeout = (connect_timeout, read_timeout)
    request_session.keep_alive = True
    request_session.headers.update({
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, deflate',
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0 ...'
    })
    request_session.mount("http://", adapter)
    request_session.mount("https://", adapter)
    if enable_monitor:
        return HTTPMonitorWrapper(request_session)
    return request_session
```

### 3.4 异步客户端（已存在但未被投料取数使用，`client.py:42-57`）

```python
API_TIMEOUT = 1800.0
_sap_async_client = httpx.AsyncClient(
    auth=httpx.BasicAuth(sap_username, sap_password),
    timeout=httpx.Timeout(connect=15, read=API_TIMEOUT, write=API_TIMEOUT, pool=15),
    transport=httpx.AsyncHTTPTransport(
        retries=3,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
    ),
)
```

---

## 四、根因分析

### 4.1 核心隐患：超时预算与重试叠加错配

`fetch_input_data` 显式传 `timeout=(15, 60)`，但 `urllib3.Retry` 仍然生效：

```
单次请求最长耗时 = connect(15s) + read(60s) = 75s
重试 3 次 + 退避 1s + 2s = 75×3 + 3 = 228s（最坏情况）
```

而外层 `asyncio.wait_for(timeout=75)` 只给 **75 秒**。

> **只要 SAP 第一次请求 read 超时（60s）触发 urllib3 重试，整个 `wait_for` 必然在 75s 处先超时，重试根本来不及完成。**

### 4.2 与日志现象的吻合

日志触发的是 `client.py:351` 的 `asyncio.TimeoutError` 分支，而非 `client.py:354` 的 `Exception` 分支，印证：

- **不是 SAP 返回错误状态码**（否则会重试后抛 `RetryError`，走 354 分支）
- **是 SAP 接受了连接但响应体迟迟不返回**，`wait_for` 在 75s 处先于 `read_timeout=60s` 触发

**反直觉点**：理论上 `read_timeout=60s` 应先于 `wait_for=75s` 触发，实际却触发了 75s，可能原因：
1. SAP 在 60s 内持续缓慢吐数据（chunked transfer），每次 chunk 重置 read 计时，但总时长 > 75s
2. `run_in_executor` 把 requests 调用扔进线程池，`asyncio.wait_for` 取消协程时**无法中断线程内阻塞的 socket read**，线程仍在跑，只是协程侧已超时返回

### 4.3 其他结构性问题

| # | 问题 | 位置 | 风险 |
|---|---|---|---|
| A | `sap_session` 为模块级全局单例 | `client.py:35` | 多 worker 共享同一连接池，长连接可能被 SAP 网关单侧回收后变成"半死连接" |
| B | `pool_block=False` | `common.py:62` | 连接池满时创建新连接，可能突破 SAP 网关并发上限被拒 |
| C | 重试退避叠加超时未纳入 `wait_for` 预算 | `client.py:348` vs `common.py:30` | 设计层面超时预算错配（见 4.1） |
| D | `sap_url1` 硬编码 `sap-client=800` | `client.py:29` | dev 环境 sap-client=500 时会 401 |
| E | 同步 `sap_session` 与异步 `_sap_async_client` 并存 | `client.py:35` vs `client.py:43` | `fetch_input_data` 仍走同步路径 + `run_in_executor`，超时取消时线程泄漏 |

---

## 五、可能的根因（按概率排序）

| # | 原因 | 验证方式 |
|---|---|---|
| 1 | SAP 接口 `order_material_input` 本身慢（数据量大/ABAP 查询低效） | 查看 SAP 端 RFC 日志、接口平均响应时间 |
| 2 | 网络问题（到 SAP 网关延迟高/丢包） | 在服务器上 `curl -w "%{time_total}"` 直接请求 SAP 接口计时 |
| 3 | `i_datum_f ~ i_datum_t` 查询区间过大导致 SAP 返回数据量爆炸 | 检查 `get_sap_input_stock` 入参的日期范围 |
| 4 | SAP 网关连接池耗尽/会话过期，`sap_session` 复用了失效连接 | 检查 `sap_session` 的创建与复用逻辑、SAP 网关连接数 |
| 5 | `mo_whitelist` 过大导致 SAP 端按工单过滤耗时 | 检查白名单规模 |

---

## 六、排查步骤（开发/测试环境执行）

### 步骤 1：确认 SAP 接口真实响应时长

在测试服务器上直接复现，绕开应用层超时，看 SAP 真实响应时长：

```bash
docker exec myaps_api python -c "
import requests, time
from project_files.JYHDXS.client import sap_url1, sap_session, werks
t=time.time()
r=sap_session.get(sap_url1, headers={'interface':'order_material_input','werks':werks,'i_datum_f':'2026-10-01','i_datum_t':'2026-10-27'}, timeout=(15,180))
print('elapsed=%.1fs status=%s len=%s' % (time.time()-t, r.status_code, len(r.text)))
"
```

**判定**：
- `elapsed > 75s` → SAP 端慢，转步骤 2
- `elapsed < 60s` 但应用层仍超时 → 连接池/重试叠加问题，转步骤 3
- `status != 200` → SAP 返回错误，转步骤 4

### 步骤 2：检查 SAP 端

1. 查看 SAP 网关日志（`/usr/sap/<SID>/GWD/work/`）确认该接口在 2026-10-27 22:56 UTC 的处理时长与是否有报错
2. 检查 ABAP 端 `ZRESTFUL_TEST2` 对 `interface=order_material_input` 的查询逻辑：
   - 是否对 `i_datum_f ~ i_datum_t` 全表扫描
   - 是否有 `AUFNR` 过滤条件导致慢查询
3. 评估 `i_datum_f ~ i_datum_t` 的实际区间（在 `get_sap_input_stock` 入口打印）

### 步骤 3：检查连接池与重试

```bash
# 查看当前连接池状态
docker exec myaps_api python -c "
from project_files.JYHDXS.client import sap_session
s = sap_session.client if hasattr(sap_session, 'client') else sap_session
for prefix, adapter in s.adapters.items():
    pool = adapter.get_manager().pool
    print(prefix, 'pool_connections=', adapter.pool_connections, 'pool_maxsize=', adapter.pool_maxsize)
"
```

```bash
# 多次连续请求，观察是否首次慢、后续快（连接复用问题）
docker exec myaps_api python -c "
import time
from project_files.JYHDXS.client import sap_url1, sap_session, werks
for i in range(5):
    t=time.time()
    try:
        r=sap_session.get(sap_url1, headers={'interface':'order_material_input','werks':werks,'i_datum_f':'2026-10-01','i_datum_t':'2026-10-27'}, timeout=(15,180))
        print(f'#{i} elapsed=%.1fs status=%s' % (time.time()-t, r.status_code))
    except Exception as e:
        print(f'#{i} elapsed=%.1fs err=%s' % (time.time()-t, e))
    time.sleep(2)
"
```

### 步骤 4：检查日期区间与白名单

在 `get_sap_input_stock` 入口添加临时日志，打印 `i_datum_f`、`i_datum_t`、`len(mo_whitelist)`：

```python
# client.py get_sap_input_stock 入口处临时添加
CLIENT_LOGGER.info("生产投料同步-DEBUG", f"i_datum_f={i_datum_f}, i_datum_t={i_datum_t}, mo_whitelist={len(mo_whitelist)}个")
```

### 步骤 5：检查 sap-client 硬编码

```bash
# 确认当前环境 prod.json 与 dev.json 的 sap-client
cat project_files/JYHDXS/prod.json | python -c "import json,sys; print('prod sap-client=', json.load(sys.stdin).get('erp',{}).get('sap-client'))"
cat project_files/JYHDXS/dev.json   | python -c "import json,sys; print('dev  sap-client=', json.load(sys.stdin).get('erp',{}).get('sap-client'))"
```

> 已知问题：`sap_url1` 硬编码 `sap-client=800`（`client.py:29`），dev 环境 sap-client=500 时会 401。

---

## 七、修复建议（按优先级）

| 优先级 | 建议 | 理由 | 影响范围 |
|---|---|---|---|
| **P0** | 将 `fetch_input_data` 改用 `sap_async_client`（httpx.AsyncClient），去掉 `run_in_executor` | 协程取消可真正中断请求；复用已配好的 `read=1800s` 超时与重试 | `client.py:295-355` |
| **P0** | 重新对齐超时预算：要么放宽 `wait_for` 到 ≥ 228s，要么关闭 SAP 调用的重试（`retries=0`） | 消除"重试未完成就被外层超时砍掉"的设计矛盾 | `client.py:348` 或 `get_session` 调用 |
| **P1** | 给 `sap_session` 加连接健康检查：定期发 HEAD 探活，或设置 `Connection: close` 失效复用 | 规避半死连接 | `client.py:35` |
| **P2** | `sap_url1` 的 `sap-client` 改为从 `erp.get("sap-client")` 读取，与 `sap_url2` 对齐 | 修掉 dev 环境 401 隐患 | `client.py:29` |

### 7.1 P0 修复示例（改用异步客户端）

```python
# client.py get_sap_input_stock 内，替换 fetch_input_data + run_in_executor
async def fetch_input_data_async():
    resp = await sap_async_client.get(
        sap_url1,
        headers={
            'interface': 'order_material_input',
            'werks': werks,
            'i_datum_f': i_datum_f,
            'i_datum_t': i_datum_t,
        },
    )
    resp.raise_for_status()
    response = resp.json()
    data = response.get('data', [])
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df = df.astype({
        'werks': 'str', 'matnr': 'str', 'aufnr': 'str',
        'menge': 'float64', 'bwart': 'str',
    })
    # ... 后续处理逻辑不变
    return df

try:
    df_input = await asyncio.wait_for(fetch_input_data_async(), timeout=180)
except asyncio.TimeoutError:
    CLIENT_LOGGER.fail("生产投料同步", "获取SAP投料数据超时", "超过180秒")
    return None
```

### 7.2 P0 修复示例（对齐超时预算，保留同步路径）

```python
# 方案A：放宽 wait_for
timeout=228   # 75×3 + 退避3s

# 方案B：关闭重试（推荐，SAP 慢重试无意义）
sap_session = get_session(retries=0, allowed_methods=["GET", "POST"])
```

---

## 八、验证清单

修复后需确认：

- [ ] 测试环境复现原超时场景，确认修复后不再触发 75s 超时
- [ ] `task_refresh_stock` 定时任务正常完成，日志出现 `获取N条投料虚拟库存`
- [ ] 协程取消时无线程泄漏（`ps -eL | grep python` 线程数稳定）
- [ ] SAP 端无 401/连接拒绝错误
- [ ] dev 环境 `sap-client` 与 prod 一致生效

---

## 九、参考信息

| 项 | 值 |
|---|---|
| 生产镜像 | `gitea.chaoge.xyz/chaoge/myaps-api:e16@e16a7ad` |
| Python | 3.12 |
| WSGI | Gunicorn + Uvicorn worker |
| 调度 | APScheduler |
| SAP 接口 | `zrestful_test2` (`interface=order_material_input`) |
| 超时配置 | 连接 15s / 读取 60s / wait_for 75s / 重试 3 次 |
| 日志时间 | 2026-10-27T22:56:22 UTC |
| 日志 ID | 888472 |

---

**文档生成时间**: 2026-10-29
**生成环境**: 生产服务器 `/opt/myapi_projects`
**目标用途**: 开发/测试环境 AI AGENT 排查依据