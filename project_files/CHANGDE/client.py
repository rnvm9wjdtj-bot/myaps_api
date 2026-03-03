from datetime import datetime, timedelta
import json

from .._base import cron_task, get_scheduler_minute

from apps.data_opt.components.hap import HapConfig, HapConnection
from apps.data_opt.components.ecerp_jky import (
    JkyConnection,
    Group, Currency, Company, BankAccounts, Department, Staff,
    GoodsCate, Spu, Sku, Warehouse, Logistic,
    Channel, CustomerType, CustomerSource, Customer,
    BusinessOrderGoodsDetail, BusinessOrder, TradeGoodsDetail, TradePay, Trade, Order
    )


class ChangdeHapConfig(HapConfig):
    pass


hap_conn = HapConnection(config=ChangdeHapConfig)
hap_conn.register_models([
    Currency, Group, Company, BankAccounts, Department, Staff, Channel, GoodsCate, Warehouse, Logistic,
    CustomerSource, CustomerType, Customer, Sku, Spu, BusinessOrder, BusinessOrderGoodsDetail, TradeGoodsDetail, Trade, Order
])

jky_conn = JkyConnection()


def pull_full_data(source_name, model):
    data_gen = jky_conn.pull_from_source(source_name=source_name)
    for data in data_gen:
        hap_conn.rows(model).upsert(data)

def pull_incremental_data(source_name, model, biz_content_format, add_origin_json=False):
    data_gen = jky_conn.pull_from_source(source_name=source_name, biz_content_format=biz_content_format)
    for data in data_gen:
        if add_origin_json:
            for row in data:
                row["jkyOriginJson___"] = json.dumps(row, ensure_ascii=False)
        hap_conn.rows(model).upsert(data)

def get_full_data_configs():
# 全量数据配置
    return [
    {"source_name": "全量公司信息", "model": Company},
    {"source_name": "全部部门", "model": Department},
    {"source_name": "全部员工", "model": Staff},
    {"source_name": "全部销售渠道", "model": Channel},
    {"source_name": "货品全量分类", "model": GoodsCate},
    {"source_name": "全量物流公司", "model": Logistic},
    {"source_name": "全量结算账户", "model": BankAccounts},
    {"source_name": "全部仓库", "model": Warehouse},
]

# 增量数据配置模板
def get_incremental_configs(last_pull_time: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return [
        {
            "source_name": "更新客户信息", 
            "model": Customer, 
            "biz_content_format": {"gmtModifiedBegin": last_pull_time, "gmtModifiedEnd": now}, 
            "add_origin_json": False
        },
        {
            "source_name": "更新SKU", 
            "model": Sku, 
            "biz_content_format": {"startDateModifiedSku": last_pull_time, "endDateModifiedSku": now}, 
            "add_origin_json": True
        },
        {
            "source_name": "更新JY单", 
            "model": Trade, 
            "biz_content_format": {"startModified": last_pull_time, "endModified": now}, 
            "add_origin_json": True
        },
        {
            "source_name": "更新网店订单", 
            "model": BusinessOrder, 
            "biz_content_format": {"startModified": last_pull_time, "endModified": now}, 
            "add_origin_json": True
        },
        {
            "source_name": "发货单", 
            "model": Order, 
            "biz_content_format": {"startModifyTime": last_pull_time, "endModifyTime": now}, 
            "add_origin_json": True
        },
    ]

@cron_task(hour=2, minute=0)
def sync_full_data():
    full_data_configs = get_full_data_configs()
    for config in full_data_configs:
        pull_full_data(config["source_name"], config["model"])

@cron_task(hour='0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23', minute=5)
def sync_incremental_data():
    incremental_data_configs = get_incremental_configs()
    for config in incremental_data_configs:
        pull_incremental_data(
            config["source_name"], 
            config["model"], 
            config["biz_content_format"], 
            config.get("add_origin_json", False)
        )