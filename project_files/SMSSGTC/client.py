"""
无锡西门子燃气轮机
"""

import asyncio
import pandas as pd
from datetime import datetime

from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR

from apps.data_opt.components.qingflow import (
    QingflowConnection, QingflowMaterial, model_validator
)

from .._base import (
    get_scheduler_minute, async_rate_limit, CacheItem,
    ApsPayloadSponsor, EventResultPoster, CLIENT_LOGGER, standard_response, get_session, get_async_session, event_batch_handler,
    cron_task, add_basic_auth_requests, db_delete, db_bupsert, db_query, PROJECT_JSON_FILE, pdv,
    TSupply, batch_service_operation,
)


#################################################################################
# ⬇️轻流
#################################################################################

smssgtc_qingflow_conn = QingflowConnection()
smssgtc_qingflow_conn.register_source(QingflowMaterial)


async def pull_all_material():
    """拉取所有物料数据"""
    materials = await smssgtc_qingflow_conn.query_batch()
    return await materials.dumps(to_dbtable='t_material')



@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(-1))
async def task_pull_all_material():
    materials = await pull_all_material()
    return materials


#################################################################################
# ⬇️wms
#################################################################################
wms_config = PROJECT_JSON_FILE.get("wms", {})
wms_base_url = wms_config.get("base_url", "")
wms_stock_url = wms_base_url + "/api/erp/queryProductInventory"
wms_outplan_url = wms_base_url + "/api/erp/outPlan"

WMS_OUT_DOC_TYPE_OTHER = 1
WMS_OUT_DOC_TYPE_PPE = 2
WMS_OUT_DOC_TYPE_PUBLIC = 3
WMS_OUT_DOC_TYPE_PURCHASE_RETURN = 4
WMS_OUT_DOC_TYPE_WORK_ORDER_RETURN = 5

WMS_CONNECT_TIMEOUT = 15.0
WMS_READ_TIMEOUT = 60.0
WMS_TOTAL_TIMEOUT = WMS_CONNECT_TIMEOUT + WMS_READ_TIMEOUT

_wms_async_session = None
_wms_async_lock = asyncio.Lock()


async def _get_wms_async_session():
    """获取WMS异步会话单例（基于httpx.AsyncClient，原生异步）"""
    global _wms_async_session
    if _wms_async_session is not None:
        return _wms_async_session
    async with _wms_async_lock:
        if _wms_async_session is not None:
            return _wms_async_session
        _wms_async_session = await get_async_session(
            pool_connections=10, pool_maxsize=20,
            connect_timeout=WMS_CONNECT_TIMEOUT, read_timeout=WMS_READ_TIMEOUT,
        )
        return _wms_async_session


async def refresh_stock(dbs: str=MYAPS_DB_SET):

    """
    刷新库存，先清空supply中类型为ST的数据，再从WMS同步全部产品库存数据

    Args:
        dbs: 对哪些账套生效，多个账套用逗号分隔

    Note:
        原生异步实现，使用httpx.AsyncClient直接发起HTTP请求，无需线程池中转。
        超时保护设置为 WMS_TOTAL_TIMEOUT 秒。
    """
    CLIENT_LOGGER.start("刷新库存任务")

    try:
        session = await _get_wms_async_session()
        wms_response = await asyncio.wait_for(
            session.post(url=wms_stock_url, json={}, headers={"Content-Type": "application/json"}),
            timeout=WMS_TOTAL_TIMEOUT,
        )
        wms_data = wms_response.json()
    except asyncio.TimeoutError:
        CLIENT_LOGGER.fail("刷新库存任务", "获取WMS库存数据超时", f"超过{WMS_TOTAL_TIMEOUT}秒")
        return
    except Exception as e:
        CLIENT_LOGGER.fail("刷新库存任务", "获取WMS库存数据失败", str(e))
        return

    code = wms_data.get('CODE', 0)
    if code != 1:
        msg = wms_data.get('MSG', '未知错误')
        CLIENT_LOGGER.fail("刷新库存任务", "WMS接口返回失败", f"CODE={code}, MSG={msg}")
        return

    rows = wms_data.get('DATA', {}).get('ROWS', [])
    if not rows:
        CLIENT_LOGGER.warning_msg("刷新库存任务", "WMS返回库存数据为空")
        await ApsPayloadSponsor.refresh_supply([], dbs=dbs)
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_wms_st = pd.DataFrame(rows)
    df_wms_st = df_wms_st.astype({
        'PRODUCT_CODE': 'str',
        'PRODUCT_NAME': 'str',
        'PRODUCT_TYPE_CODE': 'str',
        'PRODUCT_TYPE_NAME': 'str',
        'TOTAL_QUANTITY': 'float',
        'PICK_QUANTITY': 'float',
        'AVAILABLE_QUANTITY': 'float',
    })

    df_wms_st['supplyno'] = df_wms_st['PRODUCT_CODE']
    df_wms_st['materialno'] = df_wms_st['PRODUCT_CODE']
    df_wms_st['avail_qty'] = df_wms_st['AVAILABLE_QUANTITY']
    df_wms_st['type'] = 'ST'
    df_wms_st['priority'] = 0
    df_wms_st['avail_date'] = now
    df_wms_st['dt_req'] = now
    df_wms_st['status'] = 'CRE'
    df_wms_st['category'] = 'MTS'
    df_wms_st['create_date'] = now
    df_wms_st['itemno'] = pdv.ITEMNO
    df_wms_st['batchno'] = ''
    df_wms_st['free1'] = df_wms_st['PRODUCT_TYPE_CODE']
    df_wms_st['free2'] = df_wms_st['PRODUCT_TYPE_NAME']
    df_wms_st['memo'] = df_wms_st['PRODUCT_NAME']

    df_wms_st = df_wms_st.groupby(['supplyno'], as_index=False).agg({
        'materialno': 'first',
        'avail_qty': 'sum',
        'type': 'first',
        'avail_date': 'first',
        'dt_req': 'first',
        'priority': 'first',
        'status': 'first',
        'category': 'first',
        'create_date': 'first',
        'itemno': 'first',
        'batchno': 'first',
        'free1': 'first',
        'free2': 'first',
        'memo': 'first',
    })

    df_wms_st.fillna('', inplace=True)
    await ApsPayloadSponsor.refresh_supply(df_wms_st.to_dict(orient='records'), dbs=dbs)



@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
@async_service_operation(module="定时任务")
async def task_refresh_stock(description="刷新库存数据"):
    await refresh_stock()



def _build_outplan_payload(event_data: dict, _aps: ApsPayloadSponsor) -> dict:
    """
    将APS事件数据构建为WMS出库通知单接口格式

    单据头: t_supply中的MO记录（supplyno, materialno, avail_qty等）
    单据明细: 该MO的用料需求列表（t_demand中demandno=supplyno的记录）

    Args:
        event_data: 事件数据，t_supply行数据（小写键名）
        _aps: ApsPayloadSponsor 实例

    Returns:
        WMS出库通知单请求体字典
    """
    supplyno = event_data.get('supplyno', '')
    now = datetime.now()

    demand_list = _aps._production_cache.get_demand(supplyno) or []
    mo_data = _aps._production_cache.get_supply_mo(supplyno) or {}

    # bill_code = f"OUT{now.strftime('%Y%m%d%H%M%S')}{supplyno[-4:]}"
    bill_code = supplyno

    detail_list = []
    for idx, demand in enumerate(demand_list):
        line_code = f"{bill_code}{str(idx + 1).zfill(4)}"
        detail_list.append({
            "LINE_CODE": line_code,
            "SEQ_NO": str(idx + 1),
            "PRODUCT_CODE": demand.get('materialno', ''),
            "LOT": now.strftime('%Y%m%d'),
            "PLAN_QUANTITY": abs(demand.get('req_qty', 0)),
            "QUALITY_STATUS": 1,
        })

    if not detail_list:
        raise ValueError(f"工单 {supplyno} 无用料需求，无法生成出库通知单")

    return {
        "BILL_CODE": bill_code,
        "PLATFORM_CODE": "101",
        "OUT_DOC_TYPE": WMS_OUT_DOC_TYPE_OTHER,
        "DETAIL": detail_list,
    }


@async_rate_limit()
async def _push_outplan_single(event_data: dict, _aps: ApsPayloadSponsor, _erp: EventResultPoster):
    """
    推送单条出库通知单到WMS

    Args:
        event_data: 事件数据
        _aps: ApsPayloadSponsor 实例
        _erp: EventResultPoster 实例
    """
    supplyno = event_data.get('supplyno', '')

    try:
        payload = _build_outplan_payload(event_data, _aps)

        session = await _get_wms_async_session()
        wms_response = await asyncio.wait_for(
            session.post(
                url=wms_outplan_url,
                json=[payload],
                headers={"Content-Type": "application/json"},
            ),
            timeout=WMS_TOTAL_TIMEOUT,
        )
        wms_data = wms_response.json()

        outer_code = wms_data.get('CODE', 0)
        if outer_code != 1:
            msg = wms_data.get('MSG', '未知错误')
            await _erp.rs_release_failed(rsno=supplyno, msg=msg, push_data=payload, msg_from='WMS')
            CLIENT_LOGGER.fail("推送出库通知单", supplyno, f"外层CODE={outer_code}, MSG={msg}")
            return

        data_list = wms_data.get('DATA', [])
        bill_result = data_list[0] if data_list else {}
        inner_code = bill_result.get('CODE', -1)

        if inner_code == 1:
            await _erp.rs_release_success(
                rsno=supplyno,
                msg=bill_result.get('MSG', ''),
                msg_from='WMS',
                _code=payload['BILL_CODE'],
            )
            CLIENT_LOGGER.success("推送出库通知单", supplyno, f"单据编号{payload['BILL_CODE']}")
        else:
            msg = bill_result.get('MSG', '未知错误')
            await _erp.rs_release_failed(rsno=supplyno, msg=msg, push_data=payload, msg_from='WMS')
            CLIENT_LOGGER.fail("推送出库通知单", supplyno, f"内层CODE={inner_code}, MSG={msg}")

    except asyncio.TimeoutError:
        await _erp.rs_release_failed(rsno=supplyno, msg=f"WMS请求超时，超过{timeout}秒", msg_from='WMS')
        CLIENT_LOGGER.fail("推送出库通知单", supplyno, f"WMS请求超时，超过{timeout}秒")

    except Exception as e:
        await _erp.rs_release_failed(rsno=supplyno, msg=str(e)[:64], push_data=payload, msg_from='WMS')
        CLIENT_LOGGER.fail("推送出库通知单", supplyno, str(e))



@event_batch_handler(reminder=None, remind_start=False)
@batch_service_operation(module="事件处理")
async def batch_handle_pl_to_mo(event_data_list: list[dict], _erp: EventResultPoster, description="推送出库通知单至WMS"):
    """
    数据库事件，批量推送出库通知单至WMS

    当PL变为MO时触发，将出库需求推送到WMS系统。

    Args:
        event_data_list: 事件数据列表，每条包含 supplyno
        _erp: EventResultPoster 实例
    """
    supply_nos = [s['supplyno'] for s in event_data_list]
    await TSupply.filter(supplyno__in=supply_nos).update(memo="📤 正在推送出库通知单...")

    _aps = ApsPayloadSponsor(production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.DEMAND])
    await _aps.establish_production_cache(supplynos=supply_nos)

    tasks = [
        _push_outplan_single(event_data=_, _aps=_aps, _erp=_erp)
        for _ in event_data_list
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    unknown_failed = await TSupply.filter(status='A2E', supplyno__in=supply_nos).values('supplyno')
    if unknown_failed:
        fallback_tasks = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in unknown_failed:
            fallback_tasks.append(
                db_update_by_index(
                    db_names=MYAPS_MAIN_DB,
                    model_or_tablename="t_supply",
                    index_dict={"SupplyNo": item["supplyno"]},
                    new_values_dict={"Status": "CRE", "Memo": f"{now} 推送失败，请重试"},
                    not_found_behavior="skip",
                )
            )
        await asyncio.gather(*fallback_tasks, return_exceptions=True)
