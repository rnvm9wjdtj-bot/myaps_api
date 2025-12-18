"""
初始化模块，负责加载当前激活的连接器，并调用其中注册的的数据库事件及定时任务

连接器需要实现以下方法：
- refresh_stock(db_name: str | None = None) -> None: 刷新库存
- confirm_pl(pl_data: dict) -> None: 确认生产计划单PL
"""

import os, importlib

from ..utils.scheduler import cron_task
from apps.io_api.common import dict_to_lower_keys
from apps.data_opt.components.hap_v3 import HapApiV3


app_key = os.getenv("HAP_APP_KEY", None )
sign = os.getenv("HAP_SIGN", None)
base_url = os.getenv("HAP_BASE_URL", None)
if all([app_key, sign, base_url]):
    mingdao_api = HapApiV3(app_key=app_key, sign=sign, base_url=base_url)
else:
    mingdao_api = None


active_connector = importlib.import_module(os.getenv("ACTIVE_CONNECTOR"))
project_default_value = active_connector.DefaultValue
#################################################################################
# ⬇️定时任务HOOK
#################################################################################
schedule_task_hour = active_connector.SCHEDULE_TASK_HOUR
schedule_task_minute = active_connector.SCHEDULE_TASK_MINUTE
turn_on_schedule_task = os.getenv('TURN_ON_SCHEDULE_TASK', 'True').lower() == 'true'


if turn_on_schedule_task:
    @cron_task(hour=schedule_task_hour, minute=schedule_task_minute)
    async def refresh_stock(db_name: str | None = None): 
        return await active_connector.ScheduleTasks.refresh_stock(db_name)



#################################################################################
# ⬇️MYAPS数据库事件HOOK
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor

main_db = os.getenv('MYAPS_MAIN_DB')


@mysql_monitor.on_update_for_table("t_supply", database=main_db)
async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    supply_type = data['new']['Type']

    # 确认/下达生产计划单PL
    if supply_type == 'PL':
        supply_old_status = data['old']['Status']
        supply_new_status = data['new']['Status']
        if supply_old_status in ["NEW", "CRE"] and supply_new_status == 'A2E':
            pl_data = dict_to_lower_keys(data['new'])
            await active_connector.MyapsDbActions.confirm_pl(pl_data)
    print(f"更新到 {database}.{table}: {data}")
    print(f"数据变更: {data_diff}")



"""

CREATE DEFINER=`root`@`localhost` PROCEDURE `SupplyConvertMOByE2A`(
    IN i_SupplyNo varchar(255),
    IN i_MONO varchar(255),
    IN i_Status varchar(255),
    IN i_Memo varchar(255),
    IN i_ExecuteUpdates boolean
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    -- 只有当 i_ExecuteUpdates 为 TRUE 时才执行完整的更新逻辑
    IF i_ExecuteUpdates THEN
        START TRANSACTION;
        
            UPDATE t_supply SET Type ='MO', SupplyNo = i_MONO, Memo = i_Memo, `Status` = IFNULL(i_Status, `Status`) 
            WHERE SupplyNo = i_SupplyNo AND Type ='PL';
            
            UPDATE t_OrderWC SET SupplyNo = i_MONO, OrderNo = CONCAT(i_MONO,ItemNo) 
            WHERE SupplyNo = i_SupplyNo;
            
            UPDATE t_demand SET Type ='RS', DemandNo = i_MONO 
            WHERE DemandNo = i_SupplyNo;
            
            UPDATE t_peg SET Type ='RS', DemandNo = i_MONO 
            WHERE DemandNo = i_SupplyNo AND Type ='DM';
        
        COMMIT;
        
        SELECT 
            (SELECT COUNT(*) FROM t_supply WHERE SupplyNo = i_SupplyNo) AS t_supply_updated,

            '已下达' AS Result;
    ELSE
        -- 只更新相关表的Memo字段为i_Memo
        START TRANSACTION;
        
            UPDATE t_supply SET Memo = i_Memo, `Status` = IFNULL(i_Status, `Status`)  
            WHERE SupplyNo = i_SupplyNo;
        
        COMMIT;
        
        -- 返回更新结果统计
        SELECT 
            0 AS t_supply_updated,
            '未更新' AS Result;
    END IF;
END

"""
