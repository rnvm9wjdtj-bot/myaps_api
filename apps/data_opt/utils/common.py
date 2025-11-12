import os, base64, requests

from typing import Optional, Dict, Union

def add_basic_auth_requests(
    session: Optional[Union[requests.Session, Dict[str, str]]] = None,
    username: Optional[str] = None,
    password: Optional[str] = None
) -> Dict[str, str]:
    """
    为requests库添加Basic认证头部
    
    Args:
        session: requests.Session对象或headers字典
        username: 用户名
        password: 密码
    
    Returns:
        包含认证头的字典
    """
    if not username or not username.strip():
        return {}

    auth_string = f"{username}:{password or ''}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    auth_header = {'Authorization': f'Basic {encoded_auth}'}
    
    if isinstance(session, requests.Session):
        session.headers.update(auth_header)
    elif isinstance(session, dict):
        session.update(auth_header)
    
    return auth_header


#################################################################################
# MYAPS数据库通用事件
#################################################################################
# from apps.data_opt.utils.mysqlmonitor import mysql_monitor

# main_db = os.getenv('MAIN_DB')
# # 下达生产计划单
# @mysql_monitor.on_update_for_table("t_supply")
# async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
#     """处理t_supply表的更新事件"""
#     if database == main_db:
#         supply_old_type = data['old']['Type']
#         supply_new_type = data['new']['Type']
#         if supply_old_type == 'PL' and supply_new_type == 'MO':
#             await insert_pl_to_sap(data['new'])
#     print(f"更新到 {database}.{table}: {data}")
#     print(f"数据变更: {data_diff}")