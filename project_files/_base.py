"""
引用包和常量，供各项目文件使用
"""

# import threading
import os, asyncio
import logging, json, requests, pandas as pd
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, SCHEDULER_MINUTE
from globalobjects.globalconst import OrderStatusEnum
from apps.data_opt.utils.common import get_session


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from globalobjects import logger as log_config, CACHE_JSON, ProjectDefaultValues as pdv
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_bupsert, db_supsert, db_update_by_index
from apps.data_opt.components.hap import HapConnection
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.utils.db_operation import db_delete, db_bupsert


# 配置日志
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')


# 获取统一日志器
console_log = log_config.get_logger(__name__)


def get_scheduler_minute(offset: int=0):

    minutes = []
    for m in SCHEDULER_MINUTE.split(','):
        minute = int(m) + offset
        minutes.append(str(minute % 60))
    return ','.join(minutes)


class ApsBaseAction(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()
    

    @classmethod
    @abstractmethod
    def click_release_button(cls, supplyno: str, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        - 各项目文件须声明子类并覆写该方法，注意要包含实现推送 PL 至 ERP 的逻辑：
            - 若 ERP 同步返回创建结果，则覆写方法需还需将 ERP 返回信息更新至原PL
            - 若异步，则由 ERP 调用 api patch("/t_supply/{path_targetsupply}") 更新 PL
        - 若无需对接ERP，则无需覆写此方法
        """
        cls._pl_release_success(plno=supplyno, to_status='REL')


    @classmethod
    @abstractmethod
    def push_rs(cls, supplymo_detaildata: Dict, *args, **kwargs):
        """
        调用存储过程将demand type由DM变更为RS时自动调用
        """
        pass


    @classmethod
    def _get_supplymo_detaildata(cls, supplyno: str):
        """
        获取工单计划单详情
        Args:
            supplyno: 工单号
        Returns:
            工单计划单详情
        """
        supply_response = cls._session.get(f"{cls.this_base_url}/api/v_supply_mo/{supplyno}?db_name={cls.main_db}")
        supply_response_json = supply_response.json()
        supplymo_detaildata = supply_response_json['data'][0]
        return supplymo_detaildata

    
    @classmethod
    def _get_demand_datalist(cls, demandno: str) -> List[Dict]:
        """
        获取工单原料需求
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        demand_response = cls._session.get(f"{cls.this_base_url}/api/v_demand/{demandno}?db_name={cls.main_db}")
        demand_response_json = demand_response.json()
        demand_detaildata = demand_response_json['data']
        return demand_detaildata


    @classmethod
    def _pl_release_success(cls, plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', change_supplyno: bool=True, msg: str=None, msg_from: str=None, _id: str=None, _entryid: str=None):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段，作为私有方法在 def click_release_button() 中被直接调用
        🅰 plno: PL计划单编号
        🅰 mono: MO号，可选，若非None则更改PL的SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 change_supplyno: 是否更改PL的SupplyNo，默认True
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        🅰 _id: 外部系统返回的 MO ID
        🅰 _entryid: 外部系统返回的 MO 详情 ID（对于某些有表头的ERP，具体的 MO 是存在于子表中的，有单独的行记录id
        """
        try:
            console_log.info(f"开始查询PL信息: {plno}")
            query_result = cls._session.get(f"{cls.this_base_url}/api/v_supply_mo/{plno}?db_name={cls.main_db}")
            console_log.info(f"查询PL信息响应: {query_result.status_code}")
            query_result_json = query_result.json()

            if query_result_json['success'] == 0:
                console_log.error(f"Error querying supply {plno}: {query_result_json['message']}")
                return standard_response(status_code=query_result_json['status_code'], success=0, message=query_result_json['message'])

            query_data = query_result_json['data']
            if not query_data or len(query_data) > 1:
                filelog_error.error(f"Error querying supply {plno}: multiple records matched.")
                return standard_response(success=0, message=f"PL {plno} not found or multiple records matched.")

            if query_data[0]["type"] != "PL":
                filelog_error.error(f"Error querying supply {plno}: not a PL.")
                return standard_response(status_code=400, success=0, message=f"Supply {plno} is not a PL.")

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_msg = f"✅ 推送计划任务执行成功，账套：{cls.main_db}，PL单号：{plno}，MO单号：{mono or plno}"
            console_log.info(log_msg)
            filelog_normal.info(log_msg)
            memo = json.dumps({
                "msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now,
                "native_no": plno, "_code": mono, "_id": _id, "_entryid": _entryid}, ensure_ascii=False
            )

            console_log.info(f"开始更新PL状态为MO: {plno}, 目标状态: {to_status}, MO单号: {mono}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{plno}?db_name={cls.main_db}', json={
                'status': to_status,
                'apiex_code': str(mono),
                'apiex_id': str(_id or ""),
                'apiex_entryid': str(_entryid or ""),
                'supplyno': str(mono),
                'change_supplyno': change_supplyno,
                'memo': memo,
            })
            console_log.info(f"更新PL状态为MO响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PL状态为MO时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @classmethod
    def _pl_release_failed(cls, plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, msg_from: str=None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"🚫 推送计划任务执行失败，账套：{cls.main_db}，PL单号：{plno}"
        console_log.error(log_msg)
        filelog_error.error(log_msg)
        memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
        
        try:
            console_log.info(f"开始更新PL状态: {plno}, 目标状态: {to_status}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{plno}/...?db_name={cls.main_db}', json={
                'status': to_status,    # ❗❗失败情况下，状态务必回撤为 CRE 或 NEW ，否则后续无法再次下达
                'memo': memo,
            })
            console_log.info(f"更新PL状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PL状态时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            # 可以考虑添加重试逻辑
            return None


    @classmethod
    def _rs_push_success(cls, rsno: str, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        """
        当推送 领料申请 RS 至 ERP 成功时，调用该方法更新 RS
        Args:
            rsno: RS 号
            msg: 外部系统返回信息
            msg_from: 外部系统名称
            _code: 外部系统返回的 领料单 编号
            _id: 外部系统返回的 领料单 ID
            _entryid: 外部系统返回的 领料单 详情 ID（对于某些有表头的ERP，具体的 领料申请 是存在于子表中的，有单独的行记录id
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now, "native_no": rsno, "_code": _code, "_id": _id, "_entryid": _entryid}, ensure_ascii=False)
            
            console_log.info(f"开始更新RS状态: {rsno}, 目标状态: {to_status}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_demand/{rsno}/.../...?db_name={cls.main_db}', json={
                'status': to_status,
                'memo': memo,
            })
            console_log.info(f"更新RS状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新RS状态时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @classmethod
    def _rs_push_failed(cls, rsno: str, msg: str=None, msg_from: str=None):
        """
        当推送 RS 至 ERP 失败时，调用该方法更新 RS 状态
        Args:
            rsno: RS 号
            msg: 外部系统返回信息
            msg_from: 外部系统名称
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
            console_log.info(f"开始更新RS失败状态: {rsno}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_demand/{rsno}/.../...?db_name={cls.main_db}', json={
                'memo': memo,
            })
            console_log.info(f"更新RS失败状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新RS失败状态时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @classmethod
    def _pr_push_success(cls, prno: str, msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        """ TODO
        当推送 PR 至 ERP 成功时，调用该方法更新 PR
        Args:
            prno: PR 号
            msg: 外部系统返回信息
            msg_from: 外部系统名称
            _code: 外部系统返回的 请购单 编号
            _id: 外部系统返回的 请购单 ID
            _entryid: 外部系统返回的 请购单 详情 ID（对于某些有表头的ERP，具体的 请购申请 是存在于子表中的，有单独的行记录id
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now, "native_no": prno, "_code": _code, "_id": _id, "_entryid": _entryid}, ensure_ascii=False)
            console_log.info(f"开始更新PR状态: {prno}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{prno}/...?db_name={cls.main_db}', json={
                'memo': memo,
            })
            console_log.info(f"更新PR状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PR状态时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @classmethod
    def _pr_push_failed(cls, prno: str, msg: str=None, msg_from: str=None):
        """ TODO
        当推送 PR 至 ERP 失败时，调用该方法更新 PR 状态
        Args:
            prno: PR 号
            msg: 外部系统返回信息
            msg_from: 外部系统名称
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
            console_log.info(f"开始更新PR失败状态: {prno}")
            response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{prno}/...?db_name={cls.main_db}', json={
                'memo': memo,
            })
            console_log.info(f"更新PR失败状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PR失败状态时发生网络错误: {str(e)}"
            filelog_error.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @classmethod
    def _fetch_data(cls, url: str) -> List[Dict]:
        # 调用自身 API GET 数据
        response = cls._session.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('data', [])


    @classmethod
    def get_dategrouped_pr(cls, db_name: str=None, period: int|str=30, groupdates: str=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认cls.main_db
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        from apps.io_api.routers import get_matdailyqtyreport
        from datetime import date, datetime
        db_name = db_name or cls.main_db
        # response = asyncio.run(get_matdailyqtyreport(db_name=db_name, period=period, groupdates=groupdates, materialno=None))
        # data = response.get('data', [])
        response = cls._session.get(f"{cls.this_base_url}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}")
        response.raise_for_status()
        data = response.json().get('data', [])
        field_map = field_map or {
            'materialno': '料号',
            'datestr': '交期',
            'groupdate': '日期',
            'qty': '数量',
        }
        if not field_map:
            return data
        # 转换数据，确保所有日期对象都被转换为字符串
        result = []
        for item in data:
            mapped_item = {}
            for k, v in item.items():
                # 转换日期对象为字符串
                if isinstance(v, (date, datetime)):
                    v = str(v)
                mapped_item[field_map.get(k, k)] = v
            result.append(mapped_item)
        return result


    @classmethod
    def confirm_workreport(cls):
        """
        确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认cls.main_db
        """
        db_name = cls.main_db
        response = cls._session.patch(f"{cls.this_base_url}/api/t_confirm?db_name={db_name}")
        response.raise_for_status()
        return response.json()


    @classmethod
    @abstractmethod
    def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当MO关闭时该方法将被自动调用
        🅰 mo_data: MO数据
        """
        pass