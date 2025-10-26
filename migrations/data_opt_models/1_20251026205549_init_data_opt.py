
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- This migration is redundant as it creates the same tables as the first migration
        -- It's kept here for completeness
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- No changes needed for downgrade
    """
