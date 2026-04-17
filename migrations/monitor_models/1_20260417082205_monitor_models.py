from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "api_requests" ADD "is_internal" INT NOT NULL DEFAULT 0 /* 是否内部请求 */;
        ALTER TABLE "outbound_api_requests" ADD "is_internal" INT NOT NULL DEFAULT 0 /* 是否内部请求 */;
        CREATE INDEX "idx_api_request_is_inte_adec5b" ON "api_requests" ("is_internal");
        CREATE INDEX "idx_outbound_ap_is_inte_20bddc" ON "outbound_api_requests" ("is_internal");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_outbound_ap_is_inte_20bddc";
        DROP INDEX IF EXISTS "idx_api_request_is_inte_adec5b";
        ALTER TABLE "api_requests" DROP COLUMN "is_internal";
        ALTER TABLE "outbound_api_requests" DROP COLUMN "is_internal";"""


MODELS_STATE = (
    "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"
)
