"""
加载当前项目文件（项目py），提取其中的对象，并通过预设的钩子方法执行它们

项目文件要实现以下方法（即使 pass 也需要实现）：

ScheduleTasks
    - refresh_stock(db_name: str | None = None) -> None: 刷新库存

MyapsDbActions
    - confirm_pl(pl_data: dict) -> None: 确认生产计划单PL
"""

import os, importlib

from config.settings import MYAPS_MAIN_DB, TURN_ON_SCHEDULE_TASK
from ..utils.scheduler import cron_task
from apps.io_api.common import dict_to_lower_keys


project_name = os.getenv("PROJECT_FILE").replace('.py', '')
current_project = importlib.import_module(f'apps.data_opt.project_files.{project_name}')
project_default_value = current_project.DefaultValue
try:
    hap_conn = current_project.hap_conn
except:
    hap_conn = None


#################################################################################
# ⬇️定时任务HOOK
#################################################################################
schedule_task_hour = "6,8,10,12,14,16"
schedule_task_minute = "55"


if TURN_ON_SCHEDULE_TASK:
    @cron_task(hour=schedule_task_hour, minute=schedule_task_minute)
    async def refresh_stock(db_name: str | None = None): 
        return await current_project.ScheduleTasks.refresh_stock(db_name)



#################################################################################
# ⬇️MYAPS数据库事件HOOK
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor


@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    supply_type = data['new']['Type']

    # 确认/下达生产计划单PL
    if supply_type == 'PL':
        supply_old_status = data['old']['Status']
        supply_new_status = data['new']['Status']
        if supply_old_status in ["NEW", "CRE"] and supply_new_status == 'A2E':
            pl_data = dict_to_lower_keys(data['new'])
            await current_project.MyapsDbActions.confirm_pl(pl_data)
    print(f"更新到 {database}.{table}: {data}")
    print(f"数据变更: {data_diff}")
