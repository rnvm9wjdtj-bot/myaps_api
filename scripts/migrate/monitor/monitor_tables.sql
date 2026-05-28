-- =====================================================
-- 监控模块数据库表建表脚本 (SQLite版本)
-- 版本: V001
-- 生成时间: 自动生成
-- 说明: 可重入脚本，支持重复执行和增量更新
-- =====================================================

-- =====================================================
-- 1. API 请求记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS api_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(36),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    method VARCHAR(10) NOT NULL,
    path VARCHAR(512) NOT NULL,
    query_params TEXT,
    status_code INTEGER NOT NULL,
    response_time REAL NOT NULL,
    client_ip VARCHAR(64),
    user_agent TEXT,
    payload_size INTEGER,
    response_size INTEGER,
    request_body TEXT,
    response_body TEXT,
    is_slow INTEGER DEFAULT 0,
    slow_threshold REAL,
    is_error INTEGER DEFAULT 0,
    error_message TEXT,
    is_internal INTEGER DEFAULT 0
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp ON api_requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_requests_path ON api_requests(path);
CREATE INDEX IF NOT EXISTS idx_api_requests_status_code ON api_requests(status_code);
CREATE INDEX IF NOT EXISTS idx_api_requests_response_time ON api_requests(response_time);
CREATE INDEX IF NOT EXISTS idx_api_requests_is_slow ON api_requests(is_slow);
CREATE INDEX IF NOT EXISTS idx_api_requests_is_error ON api_requests(is_error);
CREATE INDEX IF NOT EXISTS idx_api_requests_is_internal ON api_requests(is_internal);
CREATE INDEX IF NOT EXISTS idx_api_requests_request_id ON api_requests(request_id);
CREATE INDEX IF NOT EXISTS idx_api_requests_client_ip ON api_requests(client_ip);
CREATE INDEX IF NOT EXISTS idx_api_requests_method ON api_requests(method);
CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp_status ON api_requests(timestamp, status_code);

-- =====================================================
-- 2. 对外 HTTP 请求记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS outbound_api_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    method VARCHAR(10) NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    duration REAL NOT NULL,
    request_headers TEXT,
    request_body TEXT,
    response_headers TEXT,
    response_body TEXT,
    error_message TEXT,
    module VARCHAR(255),
    is_error INTEGER DEFAULT 0,
    is_slow INTEGER DEFAULT 0,
    is_internal INTEGER DEFAULT 0
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_outbound_timestamp ON outbound_api_requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_outbound_module ON outbound_api_requests(module);
CREATE INDEX IF NOT EXISTS idx_outbound_status_code ON outbound_api_requests(status_code);
CREATE INDEX IF NOT EXISTS idx_outbound_is_error ON outbound_api_requests(is_error);
CREATE INDEX IF NOT EXISTS idx_outbound_is_slow ON outbound_api_requests(is_slow);
CREATE INDEX IF NOT EXISTS idx_outbound_is_internal ON outbound_api_requests(is_internal);
CREATE INDEX IF NOT EXISTS idx_outbound_method ON outbound_api_requests(method);
CREATE INDEX IF NOT EXISTS idx_outbound_timestamp_status ON outbound_api_requests(timestamp, status_code);

-- =====================================================
-- 3. 系统日志表
-- =====================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(10) NOT NULL,
    module VARCHAR(255) NOT NULL,
    function VARCHAR(255) NOT NULL,
    line_number INTEGER NOT NULL,
    message TEXT NOT NULL,
    details TEXT,
    stack_trace TEXT,
    process_id INTEGER,
    thread_id INTEGER,
    thread_name VARCHAR(255)
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_module ON system_logs(module);
CREATE INDEX IF NOT EXISTS idx_logs_function ON system_logs(function);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp_level ON system_logs(timestamp, level);

-- =====================================================
-- 4. Binlog 位置记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS binlog_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id VARCHAR(255) NOT NULL,
    log_file VARCHAR(255) NOT NULL,
    log_pos INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_binlog_server_id ON binlog_positions(server_id);

-- =====================================================
-- 5. 已处理事件记录表（用于去重）
-- =====================================================
CREATE TABLE IF NOT EXISTS processed_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(512) UNIQUE NOT NULL,
    log_file VARCHAR(255) NOT NULL,
    log_pos INTEGER NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    database_name VARCHAR(255) NOT NULL,
    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_events_event_id ON processed_events(event_id);
CREATE INDEX IF NOT EXISTS idx_events_log_file_pos ON processed_events(log_file, log_pos);
CREATE INDEX IF NOT EXISTS idx_events_processed_at ON processed_events(processed_at);

-- =====================================================
-- 6. 失败操作记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS failed_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id VARCHAR(64) UNIQUE NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    db_name VARCHAR(100) NOT NULL,
    function_name VARCHAR(255) NOT NULL,
    args_json TEXT NOT NULL,
    kwargs_json TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_type VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 10,
    last_retry_time DATETIME,
    next_retry_time DATETIME,
    event_type VARCHAR(100),
    event_data TEXT,
    metadata TEXT
);

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_failed_timestamp ON failed_operations(timestamp);
CREATE INDEX IF NOT EXISTS idx_failed_db_name_status ON failed_operations(db_name, status);
CREATE INDEX IF NOT EXISTS idx_failed_next_retry_status ON failed_operations(next_retry_time, status);
CREATE INDEX IF NOT EXISTS idx_failed_event_type ON failed_operations(event_type);

-- =====================================================
-- 7. 版本管理表
-- =====================================================
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version VARCHAR(16) UNIQUE NOT NULL,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    sql_scripts TEXT,
    status VARCHAR(16) DEFAULT 'applied'
);

-- =====================================================
-- 记录版本（幂等）
-- =====================================================
INSERT OR IGNORE INTO schema_version (version, description, sql_scripts)
VALUES (
    'V001',
    '初始化监控模块表结构：api_requests, outbound_api_requests, system_logs, binlog_positions, processed_events, failed_operations',
    'monitor_tables.sql V001'
);

-- =====================================================
-- 完成提示与验证
-- =====================================================
-- 验证建表结果（执行此查询以确认所有表已创建）
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
SELECT 'Schema version applied: ' || version AS result FROM schema_version ORDER BY applied_at DESC LIMIT 1;