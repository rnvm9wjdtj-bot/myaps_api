# Loguru 日志系统使用指南

## 概述

本项目默认使用 **Loguru** 作为日志引擎，相比原生 logging 具有以下优势：

- ✅ 自动捕获完整异常堆栈（`logger.exception()`）
- ✅ 装饰器静默捕获（`@logger.catch`）
- ✅ 上下文绑定（`logger.bind(user_id="xxx")`）
- ✅ 异步写入，零阻塞
- ✅ 自动轮转和清理

---

## 快速开始

### 基本使用

```python
from globalobjects import logger as log_config

# 获取日志器
logger = log_config.get_logger(__name__)

# 基本日志
logger.info("普通日志")
logger.warning("警告日志")
logger.error("错误日志")

# 异常捕获（自动附带完整 traceback）
try:
    1 / 0
except Exception:
    logger.exception("捕获异常")  # 自动记录完整堆栈

# 装饰器捕获（程序不中断）
@logger.catch
def risky_function():
    1 / 0

risky_function()  # 异常被记录，程序继续
```

### 业务日志

```python
logger.success("推送订单", "订单001", "共10条")
logger.fail("推送失败", "仓库A", "网络超时")
logger.query("订单表", count=100)
logger.insert("日志表", count=5)
```

---

## 日志引擎切换

### 默认行为

| 条件 | 使用的引擎 |
|------|-----------|
| loguru 已安装 | **V2 (Loguru)** ✅ |
| loguru 未安装 | V1 (原生 logging) |
| `USE_LOGURU=false` | V1 (原生 logging) |

### 切换到原生 logging

```bash
# 方式 1：环境变量
export USE_LOGURU=false
./scripts/dev_server.sh restart

# 方式 2：修改 .env
echo "USE_LOGURU=false" >> .env
./scripts/dev_server.sh restart
```

---

## Loguru 核心功能

### 1. 异常捕获

```python
# 方式 1：logger.exception()
try:
    risky_operation()
except Exception:
    logger.exception("操作失败")  # 自动捕获完整 traceback

# 方式 2：装饰器
@logger.catch
def risky_function():
    1 / 0  # 异常自动记录，程序不中断
```

### 2. 上下文绑定

```python
# 绑定上下文信息
user_logger = logger.bind(user_id="U001", request_id="REQ-123")
user_logger.info("用户操作")  # 日志自动包含 user_id、request_id
```

### 3. 文件轮转

```python
# 配置已内置：
# - rotation: 每天午夜轮转
# - retention: 保留 10 天
# - ERROR 级别单独写入 error.log
```

---

## 常见问题

### Q: 日志格式是什么？

**A:** `2026-05-17 10:30:45 - INFO - 消息内容`

### Q: 日志写入数据库吗？

**A:** 是的，所有 INFO 及以上级别的日志都会异步写入 `system_logs` 表。

### Q: 日志流怎么工作？

**A:** WebSocket 连接建立后，日志会实时推送到监控页面。

### Q: 性能有影响吗？

**A:** Loguru 使用异步写入（`enqueue=True`），对主线程无阻塞。

---

## 文件结构

| 文件 | 说明 |
|------|------|
| `globalobjects/logger_v2.py` | Loguru 适配器 |
| `globalobjects/logger.py` | 统一入口 + V1 实现 |
| `core/settings.py` | USE_LOGURU 配置 |

---

## 回滚

如遇问题，立即切回 V1：

```bash
export USE_LOGURU=false
./scripts/dev_server.sh restart
```
