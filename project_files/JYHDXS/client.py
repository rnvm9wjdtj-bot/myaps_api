"""江阴海达橡塑"""

from re import A
import requests, uuid, asyncio, json, httpx
import pandas as pd
from datetime import datetime
from typing import List, Dict, Union

from contextlib import asynccontextmanager
from fastapi import status
from dateutil.relativedelta import relativedelta

from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR
from .._base import (
    get_scheduler_minute, async_rate_limit, CacheItem,
    ApsPayloadSponsor, EventResultPoster, CLIENT_LOGGER, standard_response, get_session, get_async_session, event_batch_handler,
    cron_task, add_basic_auth_requests, db_delete, db_bupsert, db_query, PROJECT_JSON_FILE, pdv,
)


#################################################################################
# ⬇️对象及项目参数
#################################################################################

erp = PROJECT_JSON_FILE.get("erp", {})
sap_url1 = erp.get("base_url", "") + '/zrestful_test2?sap-client=800'  # 库存
sap_url2 = erp.get("base_url", "") + '/zrestful_plan?sap-client=' + erp.get("sap-client")  # 计划
werks = erp.get("werks", "")
sap_username = erp.get("username", "")
sap_password = erp.get("password", "")
# 创建requests会话
sap_session = get_session(allowed_methods=["GET", "POST"])
# 添加Basic认证
add_basic_auth_requests(sap_session, sap_username, sap_password)

# API 超时配置
API_TIMEOUT = 1800.0  # API 调用超时（秒）

mes = PROJECT_JSON_FILE.get("mes", {})
mes_url = mes.get("base_url", "")


srm = PROJECT_JSON_FILE.get("srm", {})
srm_url = srm.get("base_url", "")
srm_headers = {
    "Authorization": srm.get("Authorization", ""),
    "Content-Type": "application/json",
}
# 同步HTTP会话（已废弃，仅保留用于向后兼容）
# 注意：push_pr 函数已改造为异步实现，不再使用此同步会话
srm_session = get_session()
srm_session.headers.update(srm_headers)
srm_field_map = {
    "materialno": "material_no", "description": "description", "size": "size",
    "type": "type", "abc": "abc", "planner": "planner", "datestr": "datestr",
    "物料来源": "name", "首期库存": "stock_qty", "累计盈余": "cumulative_balance",
    "期间合计需求": "total_demand", "期间合计供应": "total_supply", "期间盈余": "daily_balance",
    "期间": "original_datestr", "期间要货数": "current_order_quantity",
    "期初盈余": "initial_surplus", "期末盈余": "last_surplus", "要求交期": "datestr",
}


def get_srm_config() -> Dict:
    """
    获取SRM配置
    
    从project.json读取SRM配置，返回配置字典
    
    Returns:
        Dict: SRM配置字典，包含：
            - timeout: HTTP请求总超时时间（秒）
            - connect_timeout: 连接超时时间（秒）
            - read_timeout: 读取超时时间（秒）
            - pool_size: 连接池大小
            - url: SRM基础URL
            - headers: 请求头（包含认证信息）
    
    Raises:
        ValueError: 如果SRM配置缺失或非法
    """
    srm_config = PROJECT_JSON_FILE.get("srm", {})
    
    timeout = srm_config.get("timeout", 360)
    connect_timeout = srm_config.get("connect_timeout", 10)
    read_timeout = srm_config.get("read_timeout", 360)
    pool_size = srm_config.get("pool_size", 10)
    
    if not (30 <= timeout <= 600):
        CLIENT_LOGGER.warning("SRM配置", f"timeout={timeout} 超出范围[30, 600]，使用默认值 360")
        timeout = 360
    
    if not (1 <= connect_timeout <= 60):
        CLIENT_LOGGER.warning("SRM配置", f"connect_timeout={connect_timeout} 超出范围[1, 60]，使用默认值 10")
        connect_timeout = 10
    
    if not (30 <= read_timeout <= 600):
        CLIENT_LOGGER.warning("SRM配置", f"read_timeout={read_timeout} 超出范围[30, 600]，使用默认值 360")
        read_timeout = 360
    
    if not (1 <= pool_size <= 100):
        CLIENT_LOGGER.warning("SRM配置", f"pool_size={pool_size} 超出范围[1, 100]，使用默认值 10")
        pool_size = 10
    
    config = {
        "timeout": timeout,
        "connect_timeout": connect_timeout,
        "read_timeout": read_timeout,
        "pool_size": pool_size,
        "url": srm_config.get("base_url", ""),
        "headers": {
            "Authorization": srm_config.get("Authorization", ""),
            "Content-Type": "application/json",
        },
    }
    
    if not config["url"]:
        raise ValueError("SRM配置缺失：srm.base_url 未配置")
    
    if not config["headers"].get("Authorization"):
        CLIENT_LOGGER.warning("SRM配置", "Authorization 未配置，可能导致认证失败")
    
    CLIENT_LOGGER.debug(f"SRM配置加载完成: timeout={config['timeout']}s, pool_size={config['pool_size']}")
    return config


async def get_srm_async_session():
    """SRM异步会话单例，首次调用时初始化"""
    session = getattr(get_srm_async_session, '_session', None)
    if session is not None:
        return session
    
    lock = getattr(get_srm_async_session, '_lock', None)
    if lock is None:
        lock = asyncio.Lock()
        get_srm_async_session._lock = lock
    
    async with lock:
        session = getattr(get_srm_async_session, '_session', None)
        if session is not None:
            return session
        
        c = get_srm_config()
        get_srm_async_session._session = await get_async_session(
            pool_connections=c["pool_size"], pool_maxsize=c["pool_size"],
            connect_timeout=c["connect_timeout"], read_timeout=c["read_timeout"],
        )
        CLIENT_LOGGER.debug(f"创建SRM异步会话: pool_size={c['pool_size']}, timeout={c['timeout']}s")
        return get_srm_async_session._session


async def async_post_to_srm(url: str, json_data: dict) -> dict:
    """
    向SRM发送异步POST请求（复用单例会话，支持监控记录）
    
    Args:
        url: 请求URL（完整URL）
        json_data: JSON请求数据
    
    Returns:
        dict: 响应JSON数据
    
    Raises:
        asyncio.TimeoutError: 请求超时
        httpx.HTTPError: 连接异常
        json.JSONDecodeError: 响应解析异常
    """
    session = await get_srm_async_session()
    config = get_srm_config()
    try:
        response = await session.post(
            url, 
            json=json_data, 
            headers=config["headers"],
            timeout=httpx.Timeout(config["timeout"], connect=config["connect_timeout"])
        )
        return response.json()
    except json.JSONDecodeError as e:
        CLIENT_LOGGER.fail("SRM请求", f"响应解析失败: {str(e)}", f"原始响应: {response.text[:500]}")
        raise

#################################################################################
# ⬇️项目可复用逻辑
#################################################################################

def sap_post(url: str, session: requests.Session, interface_id: str, data: dict, timeout: float = 60.0):
    """
    向SAP系统发送POST请求
    url: 请求URL
    session: requests会话
    data: 请求数据
    timeout: 读取超时时间（秒）
    """
    headers = {
            "INTF_ID": interface_id,
            "SRC_SYSTEM": "APS", 
            "DEST_SYSTEM": "SAP",
            "SRC_MSGID": str(uuid.uuid4()).replace("-", ""),
            "BACKUP1": "",
            "BACKUP2": ""
    }
    response: requests.Response = session.post(url, headers=headers, json={
        "HEAD": headers,
        "BODY": [data]
    }, timeout=(15, timeout))

    response_json = {}
    if response.status_code == status.HTTP_200_OK:
        try:
            response_json = response.json()
            # CLIENT_LOGGER.success("POST请求", f"状态码{response.status_code}", f"响应{response_json}")
        except Exception as e:
            CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"解析JSON失败: {str(e)}")
            CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"响应文本: {response.text}")
            pass
    else:
        CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"响应{response.text}")
    return {
        'status_code': response.status_code,
        'response_text': response.text,
        'response_json': response_json
    }


async def refresh_stock(dbs: str=MYAPS_DB_SET):
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    
    Args:
        dbs: 对哪些账套生效，多个账套用逗号分隔
    
    Note:
        已改造为无阻塞异步执行，同步HTTP请求和pandas处理在线程池中运行。
        超时保护设置为75秒（连接15秒 + 读取60秒）。
    """
    def get_sap_stock_data():
        """
        从SAP系统获取1600厂全部库存数据
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            sap_stock_response = sap_session.get(url=f"{sap_url1}", headers={'interface': 'stock', 'werks': werks}, timeout=(15, 60)).json()
            sap_st_data = sap_stock_response.get('data', [])
            df_sap_st = pd.DataFrame(sap_st_data)
            df_sap_st = df_sap_st.astype({
                'werks': 'str',
                'matnr': 'str',
                'lgort': 'str',
                'labst': 'int32',
                'labst2': 'int32',
                'charg': 'str'
            })
            df_sap_st['avail_qty'] = df_sap_st['labst'] + df_sap_st['labst2']
            df_sap_st['supplyno'] = df_sap_st['matnr'] + '-' + df_sap_st['werks'] # 注意不要用f string，否则supplyno会变成所有料号的超长字符串
            df_sap_st['type'] = 'ST'
            df_sap_st['priority'] = 0
            df_sap_st['avail_date'] = now
            df_sap_st['dt_req'] = now
            df_sap_st['status'] = 'NEW'
            df_sap_st['category'] = ''
            df_sap_st['create_date'] = now
            df_sap_st = (df_sap_st
                            .groupby(['supplyno'], as_index=False)
                            .agg({
                                'matnr': 'first',
                                'avail_qty': 'sum',
                                'type': 'first',
                                'avail_date': 'first',
                                'dt_req': 'first',
                                'priority': 'first',
                                'status': 'first',
                                'category': 'first',
                                'create_date': 'first',
                            })) 
            df_sap_st = df_sap_st.rename(columns={
                'matnr': 'materialno',
            })
            df_sap_st['itemno'] = pdv.ITEMNO
        except Exception as e:

            raise
        return df_sap_st

    CLIENT_LOGGER.start("刷新库存任务")
    mto_vir_st = await ApsPayloadSponsor.mto_workreport_to_virtual_stock()
    
    loop = asyncio.get_event_loop()
    try:
        df_sap_st = await asyncio.wait_for(
            loop.run_in_executor(None, get_sap_stock_data),
            timeout=75
        )
    except asyncio.TimeoutError:
        CLIENT_LOGGER.fail("刷新库存任务", "获取SAP库存数据超时", "超过75秒")
        return
    except Exception as e:
        CLIENT_LOGGER.fail("刷新库存任务", "获取SAP库存数据失败", str(e))
        return

    if mto_vir_st is not None:
        stock_data_total = pd.concat([df_sap_st, mto_vir_st], axis=0, ignore_index=True)
    else:
        stock_data_total = df_sap_st
    
    # if stock_data_total is not None:
    stock_data_total.fillna('', inplace=True)
    await ApsPayloadSponsor.refresh_supply(stock_data_total.to_dict(orient='records'), dbs=dbs)


async def push_pr(period: int = 30, groupdates: List[str] | str = None):
    """
    推送要货计划到SRM（分批发送）
    
    Args:
        period: 期间（天数），默认30天
        groupdates: 指定日期列表，可选
    
    Note:
        已改造为异步HTTP请求，不阻塞事件循环。
        采用分批发送策略，每批100条数据，避免超时。
    """
    try:
        if groupdates:
            if isinstance(groupdates, list):
                groupdates = ','.join(groupdates)
        
        # 查询数据
        pr_data = await ApsPayloadSponsor.get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=period, field_map=srm_field_map, groupdates=groupdates)
        
        # 数据验证
        if not pr_data or len(pr_data) == 0:
            CLIENT_LOGGER.warning("推送要货计划到SRM", "查询数据为空", f"period={period}天, groupdates={groupdates}")
            return False
        
        # 补充字段
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for item in pr_data:
            item["plant"] = "1000"
            item["bu_code"] = werks
            item["version"] = timestamp
        
        total_count = len(pr_data)
        CLIENT_LOGGER.start(f"推送要货计划到SRM", f"共{total_count}条数据，开始分批发送")
        
        config = get_srm_config()
        url = f"{config['url']}/jbl/service/execute/SRM_RECEIVE_PUSHED_DEMAND_PLAN_SERVICE"
        
        # 并发配置
        batch_size = 100
        max_concurrent = 5  # 最大并发数
        max_retries = 2  # 每批最大重试次数
        
        # 准备所有批次
        batches = []
        for i in range(0, total_count, batch_size):
            batch_num = i // batch_size + 1
            batch_data = pr_data[i:i + batch_size]
            batches.append((batch_num, batch_data))
        
        # 信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def send_batch(batch_num: int, batch_data: list) -> tuple[int, int]:
            """发送单个批次，返回 (成功数, 失败数)"""
            batch_count = len(batch_data)
            
            async with semaphore:  # 控制并发
                for attempt in range(1 + max_retries):
                    try:
                        CLIENT_LOGGER.info(f"推送批次 {batch_num}", f"发送{batch_count}条数据" + (f"（第{attempt + 1}次尝试）" if attempt > 0 else ""))
                        
                        result = await async_post_to_srm(url, {"demand_plan": batch_data})
                        
                        if result.get("body", {}).get("status", "").lower() == "success":
                            CLIENT_LOGGER.success(f"批次 {batch_num} 推送成功", f"成功{batch_count}条")
                            return (batch_count, 0)
                        else:
                            CLIENT_LOGGER.fail(f"批次 {batch_num} 推送失败", f"响应状态异常: {result}")
                            return (0, batch_count)
                        
                    except httpx.TimeoutException:
                        if attempt < max_retries:
                            CLIENT_LOGGER.warning(f"批次 {batch_num} 超时重试", f"第{attempt + 1}次超时，准备重试")
                            await asyncio.sleep(1.0)
                        else:
                            CLIENT_LOGGER.fail(f"批次 {batch_num} 推送失败", f"重试{max_retries}次后仍超时", f"超时时间: {config['timeout']}秒")
                            return (0, batch_count)
                    
                    except Exception as e:
                        if attempt < max_retries:
                            CLIENT_LOGGER.warning(f"批次 {batch_num} 连接异常重试", f"第{attempt + 1}次异常: {str(e)[:100]}，准备重试")
                            await asyncio.sleep(1.0)
                        else:
                            CLIENT_LOGGER.fail(f"批次 {batch_num} 推送失败", f"重试{max_retries}次后仍连接异常: {str(e)}")
                            return (0, batch_count)
            
            return (0, batch_count)  # 兜底返回
        
        # 并发执行所有批次（总超时保护）
        tasks = [send_batch(batch_num, batch_data) for batch_num, batch_data in batches]
        total_timeout = config["timeout"] * len(batches) / max_concurrent + 60  # 总超时 = 单批超时 × 批次数 / 并发数 + 缓冲时间
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=total_timeout
            )
        except asyncio.TimeoutError:
            CLIENT_LOGGER.fail("推送要货计划到SRM", f"总执行超时（{total_timeout}秒）", f"已发送批次可能部分成功")
            return False
        
        # 统计结果
        success_count = 0
        fail_count = 0
        for result in results:
            if isinstance(result, tuple):
                success, fail = result
                success_count += success
                fail_count += fail
            else:
                # 异常情况
                fail_count += batch_size
        
        # 汇总结果
        if fail_count == 0:
            CLIENT_LOGGER.success(f"推送要货计划到SRM完成", f"全部成功：{success_count}条")
            return True
        else:
            CLIENT_LOGGER.warning(f"推送要货计划到SRM完成", f"部分失败：成功{success_count}条，失败{fail_count}条")
            return False
        
    except Exception as e:
        CLIENT_LOGGER.exception("推送要货计划到SRM", f"未知异常: {str(e)}")
        return False


async def push_weekpr_to_srm():
    CLIENT_LOGGER.start("推送周要货计划到SRM任务")
    success = await push_pr(period=30)
    if success:
        CLIENT_LOGGER.success("推送周要货计划到SRM任务", "", "执行完成")
    else:
        CLIENT_LOGGER.fail("推送周要货计划到SRM任务", "", "执行失败")


async def push_monthpr_to_srm():
    CLIENT_LOGGER.start("推送月度要货计划到SRM任务")
    date_list = [
        (datetime.now().replace(day=1) + relativedelta(months=i + 1) - relativedelta(days=1)).strftime('%Y-%m-%d')
        for i in range(3)
    ]
    success = await push_pr(period=90, groupdates=date_list)
    if success:
        CLIENT_LOGGER.success("推送月度要货计划到SRM任务", "", "执行完成")
    else:
        CLIENT_LOGGER.fail("推送月度要货计划到SRM任务", "", "执行失败")
#################################################################################
# ⬇️定时任务设置
#################################################################################

@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(), description="刷新库存数据")
async def task_refresh_stock():
    try:
        await refresh_stock()
    except Exception as e:
        pass


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(2), description="确认报工")
async def task_confirm_workreport():
    await ApsPayloadSponsor.confirm_workreport()


@cron_task(hour=23, minute=59, description="推送周要货计划到SRM")  # 每天23:59执行一次，需须在23:55拉取库存和确认报工之后
async def task_push_weekpr_to_srm():
    await push_weekpr_to_srm()


@cron_task(day=1, hour=0, minute=5, description="推送月度要货计划到SRM")
async def task_push_seasonpr_to_srm():
    await push_monthpr_to_srm()


#################################################################################
# ⬇️APS事件
#################################################################################
from .remind import ops_reminder, bus_reminder


@event_batch_handler(reminder=bus_reminder)
async def batch_handle_pl_status_a2e(event_data_list: List[Dict], _erp: EventResultPoster, description="PL 单据下达"):
    """
    Args:
        event_data_list: 事件数据，由数据库事件触发时注入
        _erp: EventResultPoster 实例，用于变更APS数据，由装饰器注入
        description: 事件描述，会被装饰器捕获，邮件头文字
    """

    @async_rate_limit()
    async def handle_pl_status_a2e(event_data: Dict, _aps: ApsPayloadSponsor):
        """
        处理单个PL状态变为A2E事件
        Args:
            event_data: 事件数据，由主函数注入
            _aps: ApsPayloadStorage 实例，用于获取APS数据或缓存，由主函数注入
        """

        if isinstance(event_data, str):
            supplyno = event_data
        else:
            supplyno = event_data['supplyno']

        data = None
        try:
            supplymo_detaildata = await _aps.get_supplymo_detaildata(supplyno=supplyno)
            if not supplymo_detaildata:
                CLIENT_LOGGER.fail("获取工单详情", supplyno, "get_supplymo_detaildata 返回 None，可能是缓存未命中或数据尚未提交")
                await _erp.mo_release_failed(native_plno=supplyno, msg=f"获取工单详情失败: 数据不存在或尚未提交", push_data=data, msg_from='ERP')
                return

            dt_start = supplymo_detaildata.get('dt_ordstart')
            dt_end = supplymo_detaildata.get('dt_ordend')
            
            if not dt_start or not dt_end:
                CLIENT_LOGGER.fail("日期字段为空", supplyno, f"dt_ordstart={dt_start}, dt_ordend={dt_end}")
                await _erp.mo_release_failed(native_plno=supplyno, msg=f"日期字段为空: dt_ordstart={dt_start}, dt_ordend={dt_end}", push_data=data, msg_from='ERP')
                return
            
            start_datetime: str = dt_start.split(" ")[0]
            end_datetime: str = dt_end.split(" ")[0]
            orderwc: list = supplymo_detaildata.get('orderwc', [])

            data = {
                "WERKS": werks,  # 工厂
                "MATNR": supplymo_detaildata['materialno'],
                "AUART": "ZP01",  # 订单类型
                "VERID": "SAP",    # 生产版本
                "GSTRP": start_datetime,  # 基本开始日期
                "GLTRP": end_datetime,  # 基本完成日期
                "GAMNG": supplymo_detaildata['avail_qty'],  # 总订单数量
                "WEMPF": "SAP",  # 产线代码
                "BACKUP1": ','.join([i['workcenter'] for i in orderwc]),
                "BACKUP2": supplyno,

            }

            loop = asyncio.get_event_loop()
            sap_post_future = loop.run_in_executor(
                None,
                sap_post,
                sap_url2,
                sap_session,
                "ZPP_PLAN_ORD_CREATE",
                data,
                API_TIMEOUT
            )
            try:
                sap_response = await asyncio.wait_for(sap_post_future, timeout=API_TIMEOUT)
            except asyncio.TimeoutError:
                await _erp.mo_release_failed(native_plno=supplyno, msg=f"SAP API 调用超时（{API_TIMEOUT}秒）", push_data=data, msg_from='ERP')
                return
            sap_response_json = sap_response['response_json']
            
            try:
                if 'BODY' in sap_response_json and len(sap_response_json['BODY']) > 0:
                    sap_mo_data = sap_response_json['BODY'][0]
                    
                    if sap_mo_data.get('STATUS') == 'S':
                        await _erp.mo_release_success(native_plno=supplyno, mono=sap_mo_data.get('AUFNR'), msg=sap_mo_data.get('MESSAGE'), msg_from='ERP')
                    else:
                        await _erp.mo_release_failed(native_plno=supplyno, msg=sap_mo_data.get('MESSAGE', '未知错误'), push_data=data, msg_from='ERP')
                else:
                    await _erp.mo_release_failed(native_plno=supplyno, msg=f"响应格式不正确: {sap_response['response_text']}", push_data=data, msg_from='ERP')
            except Exception as e:
                await _erp.mo_release_failed(native_plno=supplyno, msg=f"处理响应时出错: {str(e)}", push_data=data, msg_from='ERP')           
        except Exception as e:
            await _erp.mo_release_failed(native_plno=supplyno, msg=f"处理请求时出错: {str(e)}", push_data=data, msg_from='ERP')


    from apps.io_api.models import TSupply
    
    if not event_data_list:
        return
        
    supply_nos = [_['supplyno'] for _ in event_data_list]
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    supply_list = await TSupply.filter(supplyno__in=supply_nos).update(memo=f" {now} 📤 正在推送...")
    _aps = ApsPayloadSponsor(production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.ORDER_WC])
    cache = await _aps.establish_production_cache(supplynos=supply_nos)
    tasks = [handle_pl_status_a2e(event_data=item, _aps=_aps) for item in event_data_list]
    await asyncio.gather(*tasks, return_exceptions=True)


#################################################################################
# ⬇️一键通排批次日志
#################################################################################

# strategy -> handler function 映射表
_STRATEGY_HANDLERS: Dict[str, callable] = {
    '库存': refresh_stock,
    # 添加更多策略处理器...
    # '采购': refresh_purchase,
    # '生产': refresh_production,
}

async def batch_handle_new_batchlog(event_data_list: List[Dict]):

    await ApsPayloadSponsor.execute_batchlog(event_data_list[0], _STRATEGY_HANDLERS)