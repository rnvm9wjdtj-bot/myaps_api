# HMAC-SHA256 请求签名指南

## 概述

MyAPS API 使用 HMAC-SHA256 签名机制对非白名单请求进行鉴权，替代原有的静态 `X-API-Key` 方式。

**安全优势：**
- 防篡改：请求体任何字节变动都会导致签名失败
- 防重放：时间戳超时自动拒绝（默认 300 秒）
- 防时序攻击：使用常量时间比较（`hmac.compare_digest`）

## 鉴权流程

```
请求到达
  ├─ IP 在白名单中？ → 放行
  ├─ API_KEY 未配置？ → 放行（开发模式）
  └─ HMAC 签名验证
       ├─ 通过 → 放行
       └─ 失败 → 401 Unauthorized
```

## 签名算法

```
sign_string = METHOD + PATH + QUERY + TIMESTAMP + SHA256(BODY)
signature   = HMAC-SHA256(API_KEY, sign_string)
```

| 组成部分 | 说明 | 示例 |
|----------|------|------|
| METHOD | HTTP 方法大写 | `POST` |
| PATH | 请求路径（不含 host 和 query） | `/api/t_material` |
| QUERY | 原始查询字符串（不含 `?`，无参数时为空字符串），需与请求 URL 的 query 完全一致（含顺序与编码） | `db_name=hacy_p&return_data=true` |
| TIMESTAMP | 签名时的 Unix 时间戳（秒，浮点数） | `1722672000.123` |
| SHA256(BODY) | 请求体的 SHA-256 哈希值（十六进制小写） | `a3f2b8...` |

**GET 请求（无 body）：** `SHA256("")` = `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

## 请求头

| Header | 必填 | 说明 |
|--------|------|------|
| `X-Signature` | 是 | HMAC-SHA256 签名值（十六进制小写） |
| `X-Timestamp` | 是 | 签名生成时的 Unix 时间戳（秒，浮点数） |

## 防重放机制

服务端校验 `|当前时间 - X-Timestamp| <= SIGNATURE_MAX_AGE`（默认 300 秒），超时请求返回 401。

## 环境配置

```bash
# .env

# API密钥，同时作为HMAC签名密钥
# 配置后非白名单请求必须携带签名，留空则不开启鉴权
API_KEY=your_secret_key

# 签名有效期（秒），超时视为重放攻击
SIGNATURE_MAX_AGE=300
```

## 错误响应

签名验证失败时返回：

```json
{
    "status_code": 401,
    "success": 0,
    "meta": {},
    "message": "Unauthorized: Invalid or expired HMAC signature"
}
```

---

## Python 调用示例

### 基础工具函数

```python
import hmac
import hashlib
import time
import json
import urllib.parse
import httpx


API_KEY = "your_secret_key"
BASE_URL = "http://localhost:8000"


def generate_signature(method: str, path: str, query: str, timestamp: str,
                       body: bytes) -> str:
    """生成 HMAC-SHA256 签名

    query 为请求 URL 的原始查询字符串（不含 "?"，无参数时为空字符串），
    必须与实际发送的 URL 完全一致（含顺序与编码）。
    """
    body_hash = hashlib.sha256(body).hexdigest()
    sign_string = f"{method}{path}{query}{timestamp}{body_hash}"
    return hmac.new(
        API_KEY.encode(), sign_string.encode(), hashlib.sha256
    ).hexdigest()


def signed_request(method: str, path: str, body: bytes = b"",
                   params: dict = None) -> httpx.Response:
    """发送带签名的请求"""
    timestamp = str(time.time())
    query = urllib.parse.urlencode(params) if params else ""
    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    signature = generate_signature(method, path, query, timestamp, body)

    headers = {
        "X-Signature": signature,
        "X-Timestamp": timestamp,
    }
    if body:
        headers["Content-Type"] = "application/json"

    return httpx.request(
        method, url,
        content=body, headers=headers
    )
```

### POST 请求

```python
payload = [{"materialno": "M001", "materialname": "测试物料"}]
body = json.dumps(payload).encode()

resp = signed_request("POST", "/api/t_material", body, params={"db_name": "hacy_p"})
print(resp.json())
```

### GET 请求

```python
# GET 请求 body 为空
resp = signed_request("GET", "/api/t_material/M001", params={"db_name": "hacy_p"})
print(resp.json())
```

---

## Java 调用示例

### 基础工具类

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public class MyApsHmacClient {

    private static final String API_KEY = "your_secret_key";
    private static final String BASE_URL = "http://localhost:8000";
    private static final HttpClient HTTP_CLIENT = HttpClient.newHttpClient();

    /**
     * 生成 HMAC-SHA256 签名
     *
     * @param method    HTTP 方法（大写），如 "POST"
     * @param path      请求路径（不含 host），如 "/api/t_material"
     * @param query     请求 URL 的原始查询字符串（不含 "?"，无参数时为空字符串），
     *                  必须与实际请求完全一致（含顺序与编码）
     * @param timestamp Unix 时间戳（秒，浮点数字符串）
     * @param body      请求体字节数组，GET 请求传空数组
     * @return 签名值（十六进制小写）
     */
    public static String generateSignature(String method, String path, String query,
                                           String timestamp, byte[] body) throws Exception {
        // 计算 body SHA-256
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        String bodyHash = hexEncode(digest.digest(body));

        // 拼接签名字符串: METHOD + PATH + QUERY + TIMESTAMP + BODY_SHA256
        String signString = method + path + query + timestamp + bodyHash;

        // 计算 HMAC-SHA256
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                API_KEY.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return hexEncode(mac.doFinal(signString.getBytes(StandardCharsets.UTF_8)));
    }

    /**
     * 字节数组转十六进制小写字符串
     */
    private static String hexEncode(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    /**
     * 获取当前 Unix 时间戳（秒，浮点数），与 Python time.time() 一致
     */
    private static String currentTimestamp() {
        return String.valueOf(System.currentTimeMillis() / 1000.0);
    }

    /**
     * 发送带签名的 POST 请求（无 query 参数）
     *
     * @param path     请求路径，如 "/api/t_material"
     * @param jsonBody JSON 请求体字符串
     * @return 响应体
     */
    public static String post(String path, String jsonBody) throws Exception {
        return post(path, "", jsonBody);
    }

    /**
     * 发送带签名的 POST 请求
     *
     * @param path     请求路径，如 "/api/t_material"
     * @param query    查询字符串（不含 "?"，无参数时为空字符串），如 "db_name=hacy_p"
     * @param jsonBody JSON 请求体字符串
     * @return 响应体
     */
    public static String post(String path, String query, String jsonBody) throws Exception {
        byte[] bodyBytes = jsonBody.getBytes(StandardCharsets.UTF_8);
        String timestamp = currentTimestamp();
        String signature = generateSignature("POST", path, query, timestamp, bodyBytes);

        String url = BASE_URL + path + (query.isEmpty() ? "" : "?" + query);
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .header("X-Signature", signature)
                .header("X-Timestamp", timestamp)
                .POST(HttpRequest.BodyPublishers.ofByteArray(bodyBytes))
                .build();

        HttpResponse<String> response = HTTP_CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }

    /**
     * 发送带签名的 GET 请求（无 query 参数）
     *
     * @param path 请求路径，如 "/api/t_material/M001"
     * @return 响应体
     */
    public static String get(String path) throws Exception {
        return get(path, "");
    }

    /**
     * 发送带签名的 GET 请求
     *
     * @param path  请求路径，如 "/api/t_material/M001"
     * @param query 查询字符串（不含 "?"，无参数时为空字符串），如 "db_name=hacy_p"
     * @return 响应体
     */
    public static String get(String path, String query) throws Exception {
        String timestamp = currentTimestamp();
        String signature = generateSignature("GET", path, query, timestamp, new byte[0]);

        String url = BASE_URL + path + (query.isEmpty() ? "" : "?" + query);
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("X-Signature", signature)
                .header("X-Timestamp", timestamp)
                .GET()
                .build();

        HttpResponse<String> response = HTTP_CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
}
```

### 使用示例

```java
public class Main {
    public static void main(String[] args) throws Exception {
        // POST 示例
        String postResult = MyApsHmacClient.post(
                "/api/t_material",
                "[{\"materialno\":\"M001\",\"materialname\":\"测试物料\"}]"
        );
        System.out.println("POST 响应: " + postResult);

        // GET 示例
        String getResult = MyApsHmacClient.get("/api/t_material/M001");
        System.out.println("GET 响应: " + getResult);
    }
}
```

### JDK 版本说明

- 上述示例使用 JDK 11+ 的 `java.net.http.HttpClient`
- JDK 8 替换方案：使用 OkHttp 或 Apache HttpClient 发送请求，签名逻辑不变

---

## 签名验证调试

当签名验证失败时，可按以下步骤排查：

1. **确认时间戳**：客户端与服务器时钟偏差是否超过 `SIGNATURE_MAX_AGE`
2. **确认 PATH**：签名中的路径必须与实际请求路径完全一致（含 `/api` 前缀，不含 query 参数）
3. **确认 QUERY**：签名中的 query 字符串必须与实际请求 URL 的 query 完全一致（含顺序与编码），无 query 参数时为空字符串
4. **确认 BODY**：签名时的 body 字节必须与实际发送的字节完全一致（注意 JSON 序列化差异）
5. **确认 API_KEY**：客户端与服务器配置的密钥必须一致
6. **确认编码**：所有字符串统一使用 UTF-8 编码

### 在线验证脚本

```python
# 本地验证签名是否正确（无需启动服务器）
import hmac, hashlib

API_KEY = "your_secret_key"
method = "POST"
path = "/api/t_material"
query = "db_name=hacy_p"          # 与实际请求 URL 的 query 完全一致，无参数时为空字符串
timestamp = "1722672000.123"
body = b'[{"materialno":"M001"}]'

body_hash = hashlib.sha256(body).hexdigest()
sign_string = f"{method}{path}{query}{timestamp}{body_hash}"
signature = hmac.new(API_KEY.encode(), sign_string.encode(), hashlib.sha256).hexdigest()

print(f"sign_string: {sign_string}")
print(f"signature:   {signature}")
```