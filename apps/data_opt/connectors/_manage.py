"""
管理模块，负责加载当前激活的连接器，并调用其中的定时任务及数据库事件

连接器需要实现以下方法：
- refresh_stock(db_name: str | None = None) -> None: 刷新库存
- insert_pl_to_external(pl_data: dict) -> None: 将主账套中的工单类数据推送到外部系统（如ERP）
"""

import os, importlib


active_connector = importlib.import_module(os.getenv("ACTIVE_CONNECTOR"))

#################################################################################
# ⬇️定时任务
#################################################################################
schedule_task_hour = os.getenv('SCHEDULE_TASK_HOUR', '9,12,15')
schedule_task_minute = os.getenv('SCHEDULE_TASK_MINUTE', 0)
turn_on_schedule_task = os.getenv('TURN_ON_SCHEDULE_TASK', 'True').lower() == 'true'


if turn_on_schedule_task:
    @cron_task(hour=schedule_task_hour, minute=schedule_task_minute)
    async def refresh_stock(db_name: str | None = None): 
        return await active_connector.refresh_stock(db_name)



#################################################################################
# ⬇️MYAPS数据库事件
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor

main_db = os.getenv('MYAPS_MAIN_DB')


@mysql_monitor.on_update_for_table("t_supply", database=main_db)
async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    supply_type = data['new']['Type']

    # 下达生产计划单
    if supply_type == 'PL':
        supply_old_status = data['old']['Status']
        supply_new_status = data['new']['Status']
        if supply_old_status in ["NEW", "CRE"] and supply_new_status == 'A2E':
            await active_connector.insert_pl_to_external(data['new'])
    print(f"更新到 {database}.{table}: {data}")
    print(f"数据变更: {data_diff}")