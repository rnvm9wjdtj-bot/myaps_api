
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    # 只创建非抽象模型的表
    # Storage是具体模型，需要创建表
    # OptMaterial如果设置了managed=False，则不应创建表
    sql = """
        CREATE TABLE IF NOT EXISTS `a_storage` (
            `id` SERIAL PRIMARY KEY,
            `namespace` VARCHAR(64) NOT NULL,
            `item` VARCHAR(256) NOT NULL,
            `content` TEXT NOT NULL,
            `remark` TEXT
        );
        
        -- OptMaterial表的创建根据模型设置决定
        -- 如果models.py中设置了managed=False，这里应该注释掉表创建语句
        CREATE TABLE IF NOT EXISTS `opt_material` (
            `_id` SERIAL PRIMARY KEY,
            `_oid` VARCHAR(64) NOT NULL,
            `_createtime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `_updatetime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `_syncstatus` INTEGER NOT NULL DEFAULT 0,
            `_synctime` TIMESTAMP,
            `_sysprompt` TEXT
        );
    """
    return sql


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `opt_material`;
        DROP TABLE IF EXISTS `a_storage`;
    """
