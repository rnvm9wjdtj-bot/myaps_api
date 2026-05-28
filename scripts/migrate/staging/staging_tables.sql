-- =====================================================
-- APS数据清洗缓冲表建表脚本 (PostgreSQL版本)
-- 版本: V001
-- 生成时间: 自动生成
-- 说明: 可重入脚本，支持重复执行和增量更新
-- =====================================================

-- =====================================================
-- 0. 初始化版本管理表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(16) UNIQUE NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    sql_scripts TEXT,
    status VARCHAR(16) DEFAULT 'applied'
);

-- =====================================================
-- 1. 物料缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_material_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMaterial 字段
    "MaterialNo" VARCHAR(64) NOT NULL,
    "Description" VARCHAR(128) NOT NULL,
    "Size" VARCHAR(128) NULL,
    "Plant" VARCHAR(32) NOT NULL,
    "Planner" VARCHAR(64) NULL,
    "FIFO" INT NOT NULL DEFAULT 0,
    "LeadDay" INT NOT NULL DEFAULT 0,
    "ExpDay" INT NULL,
    "GRDay" INT NOT NULL DEFAULT 0,
    "ABC" VARCHAR(8) NULL,
    "Unit" VARCHAR(8) NULL,
    "Price" DECIMAL(10,2) NULL,
    "GroupNo" VARCHAR(32) NULL,
    "Type" VARCHAR(1) NULL,
    "Phantom" VARCHAR(1) NULL,
    "PhantomMin" INT DEFAULT 0,
    "FirmDay" INT NULL,
    "DayGap" INT NULL,
    "CanDelay" VARCHAR(1) NULL,
    "LotSize" VARCHAR(2) NULL,
    "LotFix" DOUBLE PRECISION NULL,
    "LotMin" DOUBLE PRECISION NULL,
    "LotMax" DOUBLE PRECISION NULL,
    "LotRound" DOUBLE PRECISION NULL,
    "LotSS" DOUBLE PRECISION NULL,
    "LotPoint" DOUBLE PRECISION NULL,
    "LotTop" DOUBLE PRECISION NULL,
    "PlanItem" VARCHAR(32) NULL,
    "PreDay" INT NULL,
    "SubDay" INT NULL,
    "Free1" VARCHAR(255) NULL,
    "Free2" VARCHAR(255) NULL,
    "Free3" VARCHAR(255) NULL,
    "Memo" VARCHAR(255) NULL,
    "Sys_User" VARCHAR(32) NULL,
    "Sys_Date" TIMESTAMPTZ NULL,
    "Sys_Stamp" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 增量添加字段（可重入）
DO $$
BEGIN
    -- V001 新增字段示例（演示增量模式）
    -- 使用 pg_attribute 检查，支持大小写敏感的标识符
    IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND LOWER(attname) = LOWER('Free4') AND NOT attisdropped) THEN
        ALTER TABLE t_material_staging ADD COLUMN "Free4" VARCHAR(255) NULL;
    END IF;
END $$;

-- 索引（幂等创建）
CREATE INDEX IF NOT EXISTS idx_mat_stg_status ON t_material_staging(_status);
CREATE INDEX IF NOT EXISTS idx_mat_stg_source ON t_material_staging(_source_system);
CREATE INDEX IF NOT EXISTS idx_mat_stg_materialno ON t_material_staging("MaterialNo");

-- 注释（幂等创建）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_material_staging IS '物料数据缓冲表';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '_staging_id')) THEN
        COMMENT ON COLUMN t_material_staging._staging_id IS '缓冲表主键';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '_source_system')) THEN
        COMMENT ON COLUMN t_material_staging._source_system IS '来源系统';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '_status')) THEN
        COMMENT ON COLUMN t_material_staging._status IS '处理状态: pending/validated/approved/rejected/synced';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '"MaterialNo"')) THEN
        COMMENT ON COLUMN t_material_staging."MaterialNo" IS '物料号';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '"Description"')) THEN
        COMMENT ON COLUMN t_material_staging."Description" IS '物料描述';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_material_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_material_staging'::regclass AND attname = '"Type"')) THEN
        COMMENT ON COLUMN t_material_staging."Type" IS '物料类型: E-自制, P-采购, F-委外, M-模具, B-虚拟';
    END IF;
END $$;

-- =====================================================
-- 2. 工作中心缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_workcenter_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoWorkcenter 字段
    "WorkCenter" VARCHAR(32) NOT NULL,
    "WorkCenterName" VARCHAR(255) NULL,
    "Pri_WC" INT NULL,
    "Bottleneck" VARCHAR(1) NULL,
    "SortNo" VARCHAR(4) NULL,
    "Plant" VARCHAR(32) NULL,
    "Location" VARCHAR(32) NULL,
    "Finite" VARCHAR(1) NULL,
    "Type" VARCHAR(32) NULL,
    "CapNum" INT NULL,
    "CapMax" INT NULL,
    "Worker" DOUBLE PRECISION NULL,
    "SetupNo" VARCHAR(6) NULL,
    "GrpNo" VARCHAR(6) NULL,
    "Memo" VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_wc_stg_status ON t_workcenter_staging(_status);
CREATE INDEX IF NOT EXISTS idx_wc_stg_workcenter ON t_workcenter_staging("WorkCenter");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_workcenter_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_workcenter_staging IS '工作中心数据缓冲表';
    END IF;
END $$;

-- =====================================================
-- 3. 产线版本缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_mat_ver_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMatVer 字段
    "MaterialNo" VARCHAR(64) NOT NULL,
    "MatVer" VARCHAR(4) NOT NULL,
    "LotFrom" INT NULL,
    "LotTo" INT NULL,
    "Priority" INT NULL,
    "RefNo" VARCHAR(64) NULL,
    "Active" VARCHAR(1) NULL,
    "Memo" VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_mvr_stg_status ON t_mat_ver_staging(_status);
CREATE INDEX IF NOT EXISTS idx_mvr_stg_mat_ver ON t_mat_ver_staging("MaterialNo", "MatVer");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mat_ver_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_mat_ver_staging IS '产线版本数据缓冲表';
    END IF;
END $$;

-- =====================================================
-- 4. 工艺路线缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_mat_wc_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMatWc 字段
    "MaterialNo" VARCHAR(64) NOT NULL,
    "MatVer" VARCHAR(4) NOT NULL,
    "ItemNo" VARCHAR(6) NOT NULL,
    "WorkCenter" VARCHAR(32) NOT NULL,
    "SortNo" INT NOT NULL,
    "BaseSec" INT NOT NULL,
    "FixQty" INT NOT NULL,
    "FixSec" INT NOT NULL,
    "SF" VARCHAR(1) NULL,
    "OffSetSec" INT NULL,
    "Rate" DOUBLE PRECISION NULL,
    "Memo" VARCHAR(255) NULL,
    "Sys_Stamp" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mwc_stg_status ON t_mat_wc_staging(_status);
CREATE INDEX IF NOT EXISTS idx_mwc_stg_mat_ver_item ON t_mat_wc_staging("MaterialNo", "MatVer", "ItemNo");
CREATE INDEX IF NOT EXISTS idx_mwc_stg_workcenter ON t_mat_wc_staging("WorkCenter");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mat_wc_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_mat_wc_staging IS '工艺路线数据缓冲表';
    END IF;
END $$;

-- =====================================================
-- 5. 物料清单缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_mat_wc_bom_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMatWcBom 字段
    "ProductNo" VARCHAR(64) NOT NULL,
    "ProductUnit" VARCHAR(16) NULL,
    "MatVer" VARCHAR(4) NOT NULL,
    "ItemNo" VARCHAR(6) NOT NULL,
    "MaterialNo" VARCHAR(64) NOT NULL,
    "MaterialUnit" VARCHAR(16) NULL,
    "Qty" DOUBLE PRECISION NOT NULL,
    "OffsetHour" INT NOT NULL,
    "TreeNo" INT NULL,
    "MTO" VARCHAR(1) NULL,
    "Scrap" DOUBLE PRECISION NULL,
    "Alt" VARCHAR(1) NULL,
    "Memo" VARCHAR(255) NULL,
    "Sys_Stamp" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bom_stg_status ON t_mat_wc_bom_staging(_status);
CREATE INDEX IF NOT EXISTS idx_bom_stg_product ON t_mat_wc_bom_staging("ProductNo", "MatVer", "ItemNo", "MaterialNo");
CREATE INDEX IF NOT EXISTS idx_bom_stg_materialno ON t_mat_wc_bom_staging("MaterialNo");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mat_wc_bom_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_mat_wc_bom_staging IS '物料清单数据缓冲表';
    END IF;
END $$;

-- =====================================================
-- 6. 模具缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_mold_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMold 字段
    "MoldNo" VARCHAR(32) NOT NULL,
    "MoldName" VARCHAR(255) NULL,
    "Type" VARCHAR(8) NULL,
    "Status" VARCHAR(8) NULL,
    "MoldNum" INT NULL,
    "Qty" INT NULL,
    "Memo" VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_mold_stg_status ON t_mold_staging(_status);
CREATE INDEX IF NOT EXISTS idx_mold_stg_moldno ON t_mold_staging("MoldNo");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mold_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_mold_staging IS '模具数据缓冲表';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mold_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_mold_staging'::regclass AND attname = '"Type"')) THEN
        COMMENT ON COLUMN t_mold_staging."Type" IS '模具类型: 注塑/冲压/压铸/夹具';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mold_staging'::regclass AND objsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 't_mold_staging'::regclass AND attname = '"Status"')) THEN
        COMMENT ON COLUMN t_mold_staging."Status" IS '模具状态: 空闲/生产中/维修中/报废';
    END IF;
END $$;

-- =====================================================
-- 7. 机台模具关联缓冲表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_mat_wc_mold_staging (
    _staging_id SERIAL PRIMARY KEY,
    _source_system VARCHAR(32) DEFAULT 'unknown',
    _source_id VARCHAR(128) NULL,
    _status VARCHAR(20) DEFAULT 'pending',
    _error_msg TEXT NULL,
    _transform_rules TEXT NULL,
    _retry_count INT DEFAULT 0,
    _createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    _synced_id VARCHAR(128) NULL,
    _synced_time TIMESTAMPTZ NULL,
    
    -- ProtoMatWcMold 字段
    "MaterialNo" VARCHAR(64) NOT NULL,
    "WorkCenter" VARCHAR(32) NOT NULL,
    "ItemNo" VARCHAR(6) NOT NULL,
    "MoldNo" VARCHAR(32) NOT NULL,
    "BaseSec" INT NULL,
    "FixSec" INT NULL,
    "Priority" INT NULL,
    "Worker" FLOAT NULL,
    "Memo" VARCHAR(255) NULL
);

CREATE INDEX IF NOT EXISTS idx_mwm_stg_status ON t_mat_wc_mold_staging(_status);
CREATE INDEX IF NOT EXISTS idx_mwm_stg_mat_wc ON t_mat_wc_mold_staging("MaterialNo", "WorkCenter", "ItemNo", "MoldNo");
CREATE INDEX IF NOT EXISTS idx_mwm_stg_moldno ON t_mat_wc_mold_staging("MoldNo");

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_mat_wc_mold_staging'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_mat_wc_mold_staging IS '机台模具关联数据缓冲表';
    END IF;
END $$;

-- =====================================================
-- 8. 校验错误记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_validation_error (
    id SERIAL PRIMARY KEY,
    staging_table VARCHAR(64) NOT NULL,
    staging_id INT NOT NULL,
    error_type VARCHAR(32) NOT NULL,
    error_field VARCHAR(64) NOT NULL,
    error_value TEXT NULL,
    error_message TEXT NOT NULL,
    suggestion TEXT NULL,
    createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_err_staging ON t_validation_error(staging_table, staging_id);
CREATE INDEX IF NOT EXISTS idx_err_type ON t_validation_error(error_type);
CREATE INDEX IF NOT EXISTS idx_err_time ON t_validation_error(createtime);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_validation_error'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_validation_error IS '校验错误记录表';
    END IF;
END $$;

-- =====================================================
-- 9. 数据转换规则配置表
-- =====================================================
CREATE TABLE IF NOT EXISTS t_transform_rule (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(64) NOT NULL UNIQUE,
    source_system VARCHAR(32) NOT NULL,
    target_table VARCHAR(64) NOT NULL,
    field_mappings TEXT NOT NULL,
    default_values TEXT NULL,
    value_mappings TEXT NULL,
    validation_rules TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 0,
    description TEXT NULL,
    createtime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updatetime TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rule_source ON t_transform_rule(source_system);
CREATE INDEX IF NOT EXISTS idx_rule_target ON t_transform_rule(target_table);
CREATE INDEX IF NOT EXISTS idx_rule_active ON t_transform_rule(is_active);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_description WHERE objoid = 't_transform_rule'::regclass AND objsubid = 0) THEN
        COMMENT ON TABLE t_transform_rule IS '数据转换规则配置表';
    END IF;
END $$;

-- =====================================================
-- 10. 创建更新时间触发器函数（幂等）
-- =====================================================
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW._updatetime = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为每个缓冲表创建触发器（幂等）
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        't_material_staging',
        't_workcenter_staging',
        't_mat_ver_staging',
        't_mat_wc_staging',
        't_mat_wc_bom_staging',
        't_mold_staging',
        't_mat_wc_mold_staging'
    ]) LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trigger_update_%s ON %s;
             CREATE TRIGGER trigger_update_%s
             BEFORE UPDATE ON %s
             FOR EACH ROW EXECUTE FUNCTION update_timestamp()',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END $$;

-- =====================================================
-- 11. 记录版本（幂等）
-- =====================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM t_schema_version WHERE version = 'V001') THEN
        INSERT INTO t_schema_version (version, description, sql_scripts)
        VALUES (
            'V001',
            '初始化缓冲表结构：物料、工作中心、产线版本、工艺路线、物料清单、模具、机台模具关联、校验错误、转换规则',
            'staging_tables.sql V001'
        );
    END IF;
END $$;

-- =====================================================
-- 完成提示
-- =====================================================
-- 执行完成后，可通过以下命令验证:
-- SELECT tablename FROM pg_tables WHERE tablename LIKE '%staging' OR tablename IN ('t_validation_error', 't_transform_rule');
-- SELECT * FROM t_schema_version ORDER BY applied_at DESC;
