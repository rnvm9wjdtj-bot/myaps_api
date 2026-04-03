"""
淮安超越橡塑项目文件
需要 ERP 推送的数据：
- 各种主数据
- 销售订单SO 
- 审批好的新 PO 及后续执行情况
- 报工数据

其他：
- 物料主数据
    - free1 是否倒冲料，Y 表示倒冲料，N 表示普通物料

# - 销售订单SO
#     - free1 客户订单号
#     - free2 客户产品号
#     - free3 包装要求
"""
from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, CLIENT_LOGGER, CLIENT_SESSION, CACHE_JSON,
    ApsHelpers, get_session
)


from apps.data_opt.components.yonyou_tplus import TplusConnection, RsPushModel, MoPushModel, model_validator
from typing import Dict, Any

#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
REMAIN_NATIVE_SUPPLYNO = True   # 本项目需要推送 MO 前后关系，所以必须保留原生供应号，否则会导致关系断开

tplus_conn = TplusConnection()

#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################

def refresh_stock(dbs: str=MYAPS_DB_SET):
    stock_data = tplus_conn.pull_stock()
    if stock_data:
        ApsHelpers.refresh_supply(stock_data, dbs=dbs)


#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def task_refresh_stock():
    refresh_stock()


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(1))
def task_confirm_workreport():
    ApsHelpers.confirm_workreport()

#################################################################################
# ⬇️ 数据库事件
#################################################################################
class CustomMoPushModel(MoPushModel):

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = MoPushModel.model_valid(values)

        mo_details = cleaned_values['ManufactureOrderDetails'][0]
        mo_material_details: list[dict] = mo_details['ManufactureOrderMaterialDetails']

        # 批量查询所有物料的 free1 字段
        materialnos = [md['Inventory']['Code'] for md in mo_material_details]
        materials = ApsHelpers.query_material(materialnos)
        materials = {item['materialno']: item for item in materials}
        
        for md in mo_material_details:
            materialno = md['Inventory']['Code']
            free1 = materials.get(materialno, {}).get('free1')
            if free1 == 'Y':    # 该物料为倒冲料
                md['Warehouse'] = {'Code': '5'} # 倒冲料仓库
                md.pop('IsMaterialRequest')
        
        # 构建后续工单关系
        next_mos: list[dict] = values.get('next_mo')
        if next_mos:
            # next_mo_sn = {_['supplyno']: _['avail_qty'] for _ in next_mos}
            next_mo_sn = ','.join([_['supplyno'] for _ in next_mos])
            if next_mo_sn:
                # cleaned_values['ManufactureOrderDetails'][0]['DynamicPropertyKeys'] = ['priuserdefnvc1']
                # cleaned_values['ManufactureOrderDetails'][0]['DynamicPropertyValues'] = [next_mo_sn]
                mo_details['DynamicPropertyKeys'] = ['priuserdefnvc1']
                mo_details['DynamicPropertyValues'] = [next_mo_sn]
        return cleaned_values


class CustomRsPushModel(RsPushModel):

    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = RsPushModel.model_valid(values)

        mr_details:list[dict] = cleaned_values['MaterialRequestDetails']
        materialnos = [md['Inventory']['Code'] for md in mr_details]
        materials = ApsHelpers.query_material(materialnos)
        # materialnos = ','.join([md['Inventory']['Code'] for md in mr_details])
        # materials = CLIENT_SESSION.get(f"{THIS_BASE_URL}/api/t_material/{materialnos}")
        # materials = materials.json()['data']
        materials = {item['materialno']: item for item in materials}
        
        mr_details2 = []
        for md in mr_details:
            materialno = md['Inventory']['Code']
            free1 = materials.get(materialno, {}).get('free1')
            if free1 != 'Y':    # 该物料 不为 倒冲料
                mr_details2.append(md)
        
        cleaned_values['MaterialRequestDetails'] = mr_details2
        return cleaned_values



def handle_pl_status_a2e(supplyno_or_data: str | dict):
    if isinstance(supplyno_or_data, str):
        supplyno = supplyno_or_data
    elif isinstance(supplyno_or_data, dict):
        supplyno = supplyno_or_data['supplyno']
    tplus_conn.create_mo(supplyno=supplyno, remain_native_supplyno=REMAIN_NATIVE_SUPPLYNO, pydantic_model=CustomMoPushModel)


def handle_pl_typeto_mo(supplyno_or_data: str | dict):
    if isinstance(supplyno_or_data, str):
        supplyno = supplyno_or_data
    elif isinstance(supplyno_or_data, dict):
        supplyno = supplyno_or_data['supplyno']
        # tplus_mo_id = supplyno_or_data['apiex_id']
    mo_data = tplus_conn.query_mo(index_value=supplyno, filter_field='voucherCode')
    if mo_data:
        tplus_conn.push_rs(mdlist_or_supplyno=supplyno, tplus_mo_data_or_id=mo_data, pydantic_model=CustomRsPushModel)    


def batch_handle_pr_created(pr_data_list: list[dict]):
    tplus_conn.push_pr(pr_data_list)


if __name__ == '__main__':
    from .._base import HapConnection
    
    hap_conn = HapConnection()
