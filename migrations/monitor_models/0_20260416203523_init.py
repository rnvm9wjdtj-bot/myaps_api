from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "api_requests" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 请求时间 */,
    "method" VARCHAR(10) NOT NULL /* HTTP 方法 */,
    "path" VARCHAR(512) NOT NULL /* 请求路径 */,
    "query_params" TEXT /* 查询参数 */,
    "status_code" INT NOT NULL /* 响应状态码 */,
    "response_time" REAL NOT NULL /* 响应时间（毫秒） */,
    "client_ip" VARCHAR(64) /* 客户端 IP */,
    "user_agent" TEXT /* 用户代理 */,
    "payload_size" INT /* 请求体大小 */,
    "response_size" INT /* 响应体大小 */,
    "request_body" TEXT /* 请求体 */,
    "response_body" TEXT /* 响应体 */,
    "is_slow" INT NOT NULL DEFAULT 0 /* 是否慢请求 */,
    "slow_threshold" REAL /* 慢请求阈值（毫秒） */,
    "is_error" INT NOT NULL DEFAULT 0 /* 是否错误请求 */,
    "error_message" TEXT /* 错误信息 */
) /* API 请求记录模型 */;
CREATE INDEX IF NOT EXISTS "idx_api_request_timesta_26587d" ON "api_requests" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_api_request_path_6217b7" ON "api_requests" ("path");
CREATE INDEX IF NOT EXISTS "idx_api_request_status__d9e8c8" ON "api_requests" ("status_code");
CREATE INDEX IF NOT EXISTS "idx_api_request_respons_c31164" ON "api_requests" ("response_time");
CREATE INDEX IF NOT EXISTS "idx_api_request_is_slow_f53a5b" ON "api_requests" ("is_slow");
CREATE INDEX IF NOT EXISTS "idx_api_request_is_erro_ad6213" ON "api_requests" ("is_error");
CREATE TABLE IF NOT EXISTS "outbound_api_requests" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 请求时间 */,
    "method" VARCHAR(10) NOT NULL /* HTTP 方法 */,
    "url" TEXT NOT NULL /* 请求 URL */,
    "status_code" INT NOT NULL /* 响应状态码 */,
    "duration" REAL NOT NULL /* 响应时间（秒） */,
    "request_headers" TEXT /* 请求头 */,
    "request_body" TEXT /* 请求体 */,
    "response_headers" TEXT /* 响应头 */,
    "response_body" TEXT /* 响应体 */,
    "error_message" TEXT /* 错误信息 */,
    "module" VARCHAR(255) /* 发起请求的模块 */,
    "is_error" INT NOT NULL DEFAULT 0 /* 是否错误请求 */,
    "is_slow" INT NOT NULL DEFAULT 0 /* 是否慢请求 */
) /* 对外 HTTP 请求记录模型 */;
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_timesta_61cbc2" ON "outbound_api_requests" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_module_99fdb1" ON "outbound_api_requests" ("module");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_status__edc615" ON "outbound_api_requests" ("status_code");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_is_erro_503daa" ON "outbound_api_requests" ("is_error");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_is_slow_6abd9c" ON "outbound_api_requests" ("is_slow");
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
    "c0X/4Dnu2PMA=="
)
