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
    "error_message" TEXT /* 错误信息 */,
    "is_internal" INT NOT NULL DEFAULT 0 /* 是否内部请求 */
) /* API 请求记录模型 */;
CREATE INDEX IF NOT EXISTS "idx_api_request_timesta_26587d" ON "api_requests" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_api_request_path_6217b7" ON "api_requests" ("path");
CREATE INDEX IF NOT EXISTS "idx_api_request_status__d9e8c8" ON "api_requests" ("status_code");
CREATE INDEX IF NOT EXISTS "idx_api_request_respons_c31164" ON "api_requests" ("response_time");
CREATE INDEX IF NOT EXISTS "idx_api_request_is_slow_f53a5b" ON "api_requests" ("is_slow");
CREATE INDEX IF NOT EXISTS "idx_api_request_is_erro_ad6213" ON "api_requests" ("is_error");
CREATE INDEX IF NOT EXISTS "idx_api_request_is_inte_adec5b" ON "api_requests" ("is_internal");
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
    "is_slow" INT NOT NULL DEFAULT 0 /* 是否慢请求 */,
    "is_internal" INT NOT NULL DEFAULT 0 /* 是否内部请求 */
) /* 对外 HTTP 请求记录模型 */;
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_timesta_61cbc2" ON "outbound_api_requests" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_module_99fdb1" ON "outbound_api_requests" ("module");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_status__edc615" ON "outbound_api_requests" ("status_code");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_is_erro_503daa" ON "outbound_api_requests" ("is_error");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_is_slow_6abd9c" ON "outbound_api_requests" ("is_slow");
CREATE INDEX IF NOT EXISTS "idx_outbound_ap_is_inte_20bddc" ON "outbound_api_requests" ("is_internal");
        CREATE TABLE IF NOT EXISTS "system_logs" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 日志时间 */,
    "level" VARCHAR(10) NOT NULL /* 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL */,
    "module" VARCHAR(255) NOT NULL /* 模块名称 */,
    "function" VARCHAR(255) NOT NULL /* 函数名称 */,
    "line_number" INT NOT NULL /* 行号 */,
    "message" TEXT NOT NULL /* 日志消息 */,
    "details" TEXT /* 详细信息 */,
    "stack_trace" TEXT /* 堆栈跟踪 */,
    "process_id" INT /* 进程ID */,
    "thread_id" INT /* 线程ID */,
    "thread_name" VARCHAR(255) /* 线程名称 */
) /* 系统日志模型 */;
CREATE INDEX IF NOT EXISTS "idx_system_logs_timesta_525890" ON "system_logs" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_system_logs_level_607a60" ON "system_logs" ("level");
CREATE INDEX IF NOT EXISTS "idx_system_logs_module_943f90" ON "system_logs" ("module");
CREATE INDEX IF NOT EXISTS "idx_system_logs_functio_02afce" ON "system_logs" ("function");
        CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "api_requests";
        DROP TABLE IF EXISTS "outbound_api_requests";
        DROP TABLE IF EXISTS "system_logs";
        DROP TABLE IF EXISTS "aerich";
        """


MODELS_STATE = (
    "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"
)