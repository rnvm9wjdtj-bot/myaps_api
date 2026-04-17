from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "api_logs" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 日志时间 */,
    "level" VARCHAR(10) NOT NULL /* 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL */,
    "message" TEXT NOT NULL /* 日志消息 */,
    "details" TEXT /* 详细信息 */,
    "stack_trace" TEXT /* 堆栈跟踪 */,
    "api_request_id" INT REFERENCES "api_requests" ("id") ON DELETE CASCADE /* 关联的内部API请求 */,
    "outbound_api_request_id" INT REFERENCES "outbound_api_requests" ("id") ON DELETE CASCADE /* 关联的对外API请求 */
) /* API 相关日志模型 */;
CREATE INDEX IF NOT EXISTS "idx_api_logs_timesta_e2ee1b" ON "api_logs" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_api_logs_level_a7ff7f" ON "api_logs" ("level");
CREATE INDEX IF NOT EXISTS "idx_api_logs_api_req_5085a4" ON "api_logs" ("api_request_id");
CREATE INDEX IF NOT EXISTS "idx_api_logs_outboun_eadd97" ON "api_logs" ("outbound_api_request_id");
        CREATE TABLE IF NOT EXISTS "performance_logs" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 日志时间 */,
    "operation" VARCHAR(255) NOT NULL /* 操作名称 */,
    "duration" REAL NOT NULL /* 执行时间（毫秒） */,
    "module" VARCHAR(255) NOT NULL /* 模块名称 */,
    "function" VARCHAR(255) NOT NULL /* 函数名称 */,
    "details" TEXT /* 详细信息 */,
    "is_slow" INT NOT NULL DEFAULT 0 /* 是否慢操作 */,
    "slow_threshold" REAL /* 慢操作阈值（毫秒） */
) /* 性能日志模型 */;
CREATE INDEX IF NOT EXISTS "idx_performance_timesta_373d28" ON "performance_logs" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_performance_operati_093db6" ON "performance_logs" ("operation");
CREATE INDEX IF NOT EXISTS "idx_performance_duratio_f0ea5d" ON "performance_logs" ("duration");
CREATE INDEX IF NOT EXISTS "idx_performance_module_732787" ON "performance_logs" ("module");
CREATE INDEX IF NOT EXISTS "idx_performance_is_slow_529dc0" ON "performance_logs" ("is_slow");
        CREATE TABLE IF NOT EXISTS "security_logs" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL /* 日志时间 */,
    "event_type" VARCHAR(50) NOT NULL /* 事件类型：登录、登出、权限变更等 */,
    "user" VARCHAR(255) /* 用户标识 */,
    "ip_address" VARCHAR(64) /* IP地址 */,
    "action" TEXT NOT NULL /* 操作描述 */,
    "status" VARCHAR(20) NOT NULL /* 状态：成功、失败 */,
    "details" TEXT /* 详细信息 */
) /* 安全日志模型 */;
CREATE INDEX IF NOT EXISTS "idx_security_lo_timesta_be950c" ON "security_logs" ("timestamp");
CREATE INDEX IF NOT EXISTS "idx_security_lo_event_t_94b202" ON "security_logs" ("event_type");
CREATE INDEX IF NOT EXISTS "idx_security_lo_user_fcfcc1" ON "security_logs" ("user");
CREATE INDEX IF NOT EXISTS "idx_security_lo_ip_addr_14fd5d" ON "security_logs" ("ip_address");
CREATE INDEX IF NOT EXISTS "idx_security_lo_status_701fa9" ON "security_logs" ("status");
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
CREATE INDEX IF NOT EXISTS "idx_system_logs_functio_02afce" ON "system_logs" ("function");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "api_logs";
        DROP TABLE IF EXISTS "system_logs";
        DROP TABLE IF EXISTS "performance_logs";
        DROP TABLE IF EXISTS "security_logs";"""


MODELS_STATE = (
    "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"
)
