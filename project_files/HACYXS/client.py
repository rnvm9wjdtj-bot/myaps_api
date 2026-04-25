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
import asyncio
from apps.io_api.models import TSupply
from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, CLIENT_LOGGER, CLIENT_SESSION, PROJECT_JSON_FILE,
    ApsPayloadSponsor, EventResultPoster, get_session, CacheItem,
    QqEmailReminder, AlertType, async_rate_limit, start_event_batch_reminder, finish_event_batch_reminder,
    TSupply, PLANNER_MAILS, ENGINEER_MAILS
)


from apps.data_opt.components.yonyou_tplus import TplusConnection, RsPushModel, MoPushModel, model_validator
from typing import Dict, Any, Union

#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
REMAIN_NATIVE_SUPPLYNO = True   # 本项目需要推送 MO 前后关系，所以必须保留原生供应号，否则会导致关系断开

# 延迟初始化TplusConnection，避免在模块导入时立即连接
_tplus_conn = None

def get_tplus_conn():
    """获取TplusConnection实例（延迟初始化）"""
    global _tplus_conn
    if _tplus_conn is None:
        _tplus_conn = TplusConnection()
    return _tplus_conn

#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################

async def refresh_stock(dbs: str=MYAPS_DB_SET):
    """刷新库存数据"""
    try:
        tplus_conn = get_tplus_conn()
        stock_data = await tplus_conn.pull_stock()
        if stock_data:
            await ApsPayloadSponsor.refresh_supply(stock_data, dbs=dbs)
    except Exception as e:
        CLIENT_LOGGER.fail("刷新库存数据", "", str(e))
        raise


#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(), description="刷新库存数据")
async def task_refresh_stock():
    """定时任务：刷新库存数据"""
    try:
        await refresh_stock()
        CLIENT_LOGGER.success("定时任务执行", "刷新库存数据", "任务完成")
    except Exception as e:
        CLIENT_LOGGER.fail("定时任务执行", "刷新库存数据", f"任务失败: {str(e)}")
        # 不抛出异常，避免影响其他任务


# @cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(1), description="确认报工")
async def task_confirm_workreport():
    """定时任务：确认报工"""
    try:
        await ApsPayloadSponsor.confirm_workreport()
        CLIENT_LOGGER.success("定时任务执行", "确认报工", "任务完成")
    except Exception as e:
        CLIENT_LOGGER.fail("定时任务执行", "确认报工", f"任务失败: {str(e)}")
        # 不抛出异常，避免影响其他任务

#################################################################################
# ⬇️ 数据库事件
#################################################################################

back_flush_warehouse = 'ck06'

def create_custom_mo_push_model(_aps: ApsPayloadSponsor):
    """创建带有 ApsHelper 实例的 CustomMoPushModel 类"""
    
    class CustomMoPushModel(MoPushModel):
        class Config:
            extra = 'allow'

        @model_validator(mode="before")
        @classmethod
        def model_valid(cls, values: Dict[str, Any]):
            cleaned_values = MoPushModel.model_valid(values)

            workcenter = None
            try:
                first_orderwc = values["orderwc"][0]
                workcenter = first_orderwc.get("workcenter", "")
            except:
                workcenter = ""
            cleaned_values['Department'] = {'Code': workcenter}

            mo_details = cleaned_values['ManufactureOrderDetails'][0]
            mo_material_details: list[dict] = mo_details['ManufactureOrderMaterialDetails']

            # 批量查询所有物料的 free1 字段
            materialnos = [md['Inventory']['Code'] for md in mo_material_details]
            # 使用闭包中的 _aps 实例，调用同步方法
            materials = _aps.query_material_sync(materialnos)
            materials = {item['materialno']: item for item in materials}
            
            for md in mo_material_details:
                materialno = md['Inventory']['Code']
                free1 = materials.get(materialno, {}).get('free1',"")
                if free1.upper().strip() == 'Y':    # 该物料为倒冲料
                    md['Warehouse'] = {'Code': back_flush_warehouse} # 倒冲料仓库
                    md.pop('IsMaterialRequest')

            mo_details['DynamicPropertyKeys'] = []
            mo_details['DynamicPropertyValues'] = []
            # 构建后续工单关系
            next_mos: list[dict] = values.get('next_mo')
            if next_mos:
                next_mo_sn = ','.join([_['supplyno'] for _ in next_mos])
                if next_mo_sn:
                    mo_details['DynamicPropertyKeys'].append('priuserdefnvc1')  # 存入自定义字段
                    mo_details['DynamicPropertyValues'].append(next_mo_sn)
            
            # 源销售订单号
            so = values.get('so')
            if so:
                mo_details['DynamicPropertyKeys'].append('priuserdefnvc4')  # 存入自定义字段
                mo_details['DynamicPropertyValues'].append(so.get('demandno', ""))
            return cleaned_values

    return CustomMoPushModel


def create_custom_rs_push_model(_aps: ApsPayloadSponsor):
    class CustomRsPushModel(RsPushModel):

        class Config:
            extra = 'allow'

        @model_validator(mode="before")
        @classmethod
        def model_valid(cls, values: Dict[str, Any]):
            cleaned_values = RsPushModel.model_valid(values)

            mr_details:list[dict] = cleaned_values['MaterialRequestDetails']
            materialnos = [md['Inventory']['Code'] for md in mr_details]
            materials = _aps.query_material_sync(materialnos)
            # materialnos = ','.join([md['Inventory']['Code'] for md in mr_details])
            # materials = CLIENT_SESSION.get(f"{THIS_BASE_URL}/api/t_material/{materialnos}")
            # materials = materials.json()['data']
            materials = {item['materialno']: item for item in materials}
            
            mr_details2 = []
            for md in mr_details:
                materialno = md['Inventory']['Code']
                free1 = materials.get(materialno, {}).get('free1',"")
                if free1.upper().strip() != 'Y':    # 该物料 不为 倒冲料
                    mr_details2.append(md)
            
            cleaned_values['MaterialRequestDetails'] = mr_details2
            return cleaned_values
            
    return CustomRsPushModel


planner_email_reminder = QqEmailReminder(
    smtp_user="2982212683@qq.com",
    smtp_password="jyboujldhplddhdf",
    email_from="2982212683@qq.com",
    email_to=PLANNER_MAILS,
)


@start_event_batch_reminder(reminder=planner_email_reminder)
@finish_event_batch_reminder(reminder=planner_email_reminder)
async def batch_handle_pl_status_a2e(supplyno_or_data_list: list[str | dict], _erp: EventResultPoster, description="下达生产加工单至 T+"):
    @async_rate_limit()
    async def handle_pl_status_a2e(supplyno_or_data: Union[str, dict], _aps: ApsPayloadSponsor):
        """处理PL状态变更为A2E"""
        try:
            if isinstance(supplyno_or_data, str):
                supplyno = supplyno_or_data
            elif isinstance(supplyno_or_data, dict):
                supplyno = supplyno_or_data['supplyno']
            tplus_conn = get_tplus_conn()
            await tplus_conn.create_mo(
                supplyno=supplyno,
                remain_native_supplyno=REMAIN_NATIVE_SUPPLYNO,
                pydantic_model=_CustomMoPushModel,
                _erp=_erp, _aps=_aps
            )
        except Exception as e:
            CLIENT_LOGGER.fail("处理PL状态变更", str(supplyno_or_data), str(e))
            await _erp.mo_release_failed(supplyno, msg=str(e))

    _aps = ApsPayloadSponsor(production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL])
    _CustomMoPushModel = create_custom_mo_push_model(_aps)

    supply_nos = [s['supplyno'] for s in supplyno_or_data_list]
    TSupply.objects.filter(supplyno__in=supply_nos).update(memo=" 📤 正在推送至 T+ ...")
    cache = await _aps.establish_production_cache(supplynos=supply_nos)
    tasks = [handle_pl_status_a2e(item, _aps) for item in supplyno_or_data_list]
    await asyncio.gather(*tasks, return_exceptions=True)


@start_event_batch_reminder(reminder=planner_email_reminder)
@finish_event_batch_reminder(reminder=planner_email_reminder)
async def batch_handle_pl_to_mo(supplyno_or_data_list: list[str | dict], _erp: EventResultPoster, description="推送领料申请至 T+)"):
    
    @async_rate_limit()
    async def handle_pl_to_mo(supplyno_or_data: Union[str, dict], _aps: ApsPayloadSponsor):
        """处理PL类型变更：转为MO"""
        try:
            if isinstance(supplyno_or_data, str):
                supplyno = supplyno_or_data
            elif isinstance(supplyno_or_data, dict):
                supplyno = supplyno_or_data['supplyno']
            tplus_conn = get_tplus_conn()
            mo_data = await tplus_conn.query_mo(index_value=supplyno, filter_field='voucherCode')
            if mo_data:
                await tplus_conn.push_rs(mdlist_or_supplyno=supplyno, tplus_mo_data_or_id=mo_data, pydantic_model=_CustomRsPushModel, _erp=_erp, _aps=_aps)
        except Exception as e:
            CLIENT_LOGGER.fail("处理PL类型变更", str(supplyno_or_data), str(e))
            await _erp.rs_release_failed(rsno=supplyno, msg=str(e))

    _aps = ApsPayloadSponsor(production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL])
    _CustomRsPushModel = create_custom_rs_push_model(_aps)
    supply_nos = [s['supplyno'] for s in supplyno_or_data_list]
    cache = await _aps.establish_production_cache(supplynos=supply_nos)
    tasks = [handle_pl_to_mo(item, _aps) for item in supplyno_or_data_list]
    await asyncio.gather(*tasks, return_exceptions=True)


@start_event_batch_reminder(reminder=planner_email_reminder)
@finish_event_batch_reminder(reminder=planner_email_reminder)
async def batch_handle_pr_status_a2e(pr_data_list: list[dict], _erp: EventResultPoster, description="推送请购单至 T+"):
    """批量处理PR状态变更为A2E"""
    try:
        tplus_conn = get_tplus_conn()
        await tplus_conn.push_pr(pr_data_list, _erp=_erp)
    except Exception as e:
        pr_nos = [p.get('supplyno') for p in pr_data_list if p.get('supplyno')]
        await _erp.pr_release_failed(prno=pr_nos[0], msg=str(e))
        
        


if __name__ == '__main__':
    from .._base import HapConnection
    
    hap_conn = HapConnection()
