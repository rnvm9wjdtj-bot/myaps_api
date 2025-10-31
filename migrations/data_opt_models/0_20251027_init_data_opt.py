from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
    CREATE TABLE IF NOT EXISTS `opt_material` (
        `_id` SERIAL NOT NULL,
        `_oid` VARCHAR(32) NOT NULL,
        `_createtime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        `_updatetime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        `_deletetime` TIMESTAMP NULL,
        `_createby` VARCHAR(32) NULL,
        `_updateby` VARCHAR(32) NULL,
        `materialno` VARCHAR(32) NOT NULL,
        `description` VARCHAR(200) NULL,
        `rev` VARCHAR(32) NULL,
        `dwgno` VARCHAR(32) NULL,
        `dwgrev` VARCHAR(32) NULL,
        `mattype` VARCHAR(32) NULL,
        `model` VARCHAR(32) NULL,
        `std` VARCHAR(32) NULL,
        `unit` VARCHAR(16) NULL,
        `weight` DECIMAL(10,4) NULL,
        `length` DECIMAL(10,4) NULL,
        `width` DECIMAL(10,4) NULL,
        `height` DECIMAL(10,4) NULL,
        `volumn` DECIMAL(10,4) NULL,
        `color` VARCHAR(32) NULL,
        `surface` VARCHAR(32) NULL,
        `material` VARCHAR(32) NULL,
        `supplier` VARCHAR(32) NULL,
        `supplier_part_no` VARCHAR(32) NULL,
        `manufacturer` VARCHAR(32) NULL,
        `manufacturer_part_no` VARCHAR(32) NULL,
        `cost_price` DECIMAL(10,4) NULL,
        `sales_price` DECIMAL(10,4) NULL,
        `currency` VARCHAR(16) NULL,
        `remark` TEXT NULL,
        `spec` TEXT NULL,
        `attr1` VARCHAR(32) NULL,
        `attr2` VARCHAR(32) NULL,
        `attr3` VARCHAR(32) NULL,
        `attr4` VARCHAR(32) NULL,
        `attr5` VARCHAR(32) NULL,
        PRIMARY KEY (`_id`),
        UNIQUE KEY `idx_opt_material__oid` (`_oid`),
        UNIQUE KEY `idx_opt_material_materialno` (`materialno`)
    );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
    DROP TABLE IF EXISTS `opt_material`;
    """