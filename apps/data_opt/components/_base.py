import json
from pathlib import Path
from typing import List, Dict, Optional, Literal, Callable, Union, Any
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
import pandas as pd
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel

from config.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET
from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.schemas import (
    BaseModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm
)
from apps.io_api.models import TSupply, TDemand
from apps.io_api.utils.db_operation import db_query
from globalobjects import globalconst, logger as log_config, CACHE_JSON, ProjectDefaultValues as pdv
from globalobjects.json_manager import JSONManager


# 获取统一日志器
console_log = log_config.get_logger(__name__)
file_log = log_config.get_file_logger(__name__)

SESSION = get_session()


class BaseConnection(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        pass


    # @abstractmethod
    def pull_from_source(self, *args, **kwargs):
        """
        从目标系统获取数据
        """
        pass


    # @abstractmethod
    def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass


class ApsHelpers:

    @staticmethod
    def mto_workreport_to_virtual_stock(db:str=MYAPS_MAIN_DB):
        """
        将报工数据 转化为 虚拟库存 数据，只处理MTO报工
        🅰 db: 账套名称，默认MYAPS_MAIN_DB
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mo_complete_data = SESSION.get(url=f"{THIS_BASE_URL}/api/v_supply_complete?db_name={db}").json().get('data')
        df_mto_vir_st = None
        if mo_complete_data:
            df_mo_complete = pd.DataFrame(mo_complete_data)
            df_mto_vir_st = (df_mo_complete[df_mo_complete['category'] == 'MTO']
                    [['materialno', 'vendorno', 'finalopqty', 'category', 'avail_date']]
                    .groupby('vendorno', as_index=False)
                    .agg({
                        'finalopqty': 'sum',
                        'materialno': 'first',
                        'category': 'first',
                        'avail_date': 'first',
                    }))
            df_mto_vir_st['supplyno'] = df_mto_vir_st['materialno'] + '-' + df_mto_vir_st['vendorno']
            df_mto_vir_st['type'] = 'ST'
            df_mto_vir_st['priority'] = 0
            df_mto_vir_st['status'] = 'NEW'
            df_mto_vir_st['dt_req'] = df_mto_vir_st['avail_date']
            df_mto_vir_st['create_date'] = now
            df_mto_vir_st['itemno'] = pdv.ITEMNO
            df_mto_vir_st.rename(columns={'finalopqty': 'avail_qty'}, inplace=True)
        return df_mto_vir_st


    @staticmethod
    def refresh_stock(stock_data:Union[List[Dict[str, Any]], pd.DataFrame], dbs:str=MYAPS_DB_SET):
        if isinstance(stock_data, pd.DataFrame):
            stock_data = stock_data.to_dict('records')
        refresh_result = SESSION.put(url=f"{THIS_BASE_URL}/api/t_supply/type/ST?db_name={dbs}", json=stock_data)
        if refresh_result.json()['success']:
            file_log.info(f"✅ 刷新库存任务执行完成，账套：{dbs}")
        else:
            file_log.error(f"🚫 刷新库存任务执行失败: {refresh_result.json()['message']}")


    @staticmethod
    def confirm_workreport(db_name:str=MYAPS_MAIN_DB):
        """
        确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        """
        file_log.info("⏰ 开始执行确认报工记录任务")
        response = SESSION.patch(f"{THIS_BASE_URL}/api/t_confirm?db_name={db_name}")
        response.raise_for_status()
        console_log.info(f"✅ 确认报工记录任务执行完成")
        return response.json()


    @staticmethod
    def _pl_release_success(native_plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _id: str=None, _entryid: str=None):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段，作为私有方法在 def click_release_button() 中被直接调用
        🅰 native_plno: 原生PL计划单编号
        🅰 mono: MO号，可选，若传值则更改PL的原生SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        🅰 _id: 外部系统返回的 MO ID
        🅰 _entryid: 外部系统返回的 MO 详情 ID（对于某些有表头的ERP，具体的 MO 是存在于子表中的，有单独的行记录id
        """
        mono = mono or native_plno
        try:
            console_log.info(f"开始查询PL信息: {native_plno}")
            query_result = SESSION.get(f"{THIS_BASE_URL}/api/v_supply_mo/{native_plno}?db_name={MYAPS_MAIN_DB}")
            console_log.info(f"查询PL信息响应: {query_result.status_code}")
            query_result_json = query_result.json()

            if query_result_json['success'] == 0:
                console_log.error(f"Error querying supply {native_plno}: {query_result_json['message']}")
                return standard_response(status_code=query_result_json['status_code'], success=0, message=query_result_json['message'])

            query_data = query_result_json['data']
            if not query_data or len(query_data) > 1:
                file_log.error(f"Error querying supply {native_plno}: multiple records matched.")
                return standard_response(success=0, message=f"PL {native_plno} not found or multiple records matched.")

            if query_data[0]["type"] != "PL":
                file_log.error(f"Error querying supply {native_plno}: not a PL.")
                return standard_response(status_code=400, success=0, message=f"Supply {native_plno} is not a PL.")

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_msg = f"✅ 推送计划任务执行成功，账套：{MYAPS_MAIN_DB}，PL单号：{native_plno}，MO单号：{mono}"
            console_log.info(log_msg)
            file_log.info(log_msg)
            memo = json.dumps({
                "msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now,
                "native_no": native_plno, "_code": mono, "_id": _id, "_entryid": _entryid}, ensure_ascii=False
            )

            console_log.info(f"开始更新PL状态为MO: {native_plno}, 目标状态: {to_status}, MO单号: {mono}")
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_supply/{native_plno}?db_name={MYAPS_MAIN_DB}', json={
                'status': to_status,
                'apiex_sn': str(mono),
                'apiex_id': str(_id or ""),
                'apiex_entryid': str(_entryid or ""),
                'supplyno': str(mono),
                'memo': memo,
            })
            console_log.info(f"更新PL状态为MO响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PL状态为MO时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _pl_release_failed(native_plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, data: dict=None, msg_from: str=None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"🚫 推送计划任务执行失败，账套：{MYAPS_MAIN_DB}，PL单号：{native_plno}，错误信息：{msg}，数据：{data}"
        console_log.error(log_msg)
        file_log.error(log_msg)
        memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
        
        try:
            console_log.info(f"开始更新PL状态: {native_plno}, 目标状态: {to_status}")
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_supply/{native_plno}/...?db_name={MYAPS_MAIN_DB}', json={
                'status': to_status,    # ❗❗失败情况下，状态务必回撤为 CRE 或 NEW ，否则后续无法再次下达
                'memo': memo,
            })
            console_log.info(f"更新PL状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PL状态时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            # 可以考虑添加重试逻辑
            return None


    @staticmethod
    def _rs_push_success(rsno: str, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
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
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}', json={
                'status': to_status,
                'memo': memo,
            })
            console_log.info(f"更新RS状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新RS状态时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _rs_push_failed(rsno: str, msg: str=None, data: dict=None, msg_from: str=None):
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
            file_log.error(f"❌ 领料申请推送失败，对应工单：{rsno}，错误信息：{msg}，数据：{data}")
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}', json={
                'memo': memo,
            })
            console_log.info(f"更新RS失败状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新RS失败状态时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _pr_push_success(prno: str, msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
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
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_supply/{prno}/...?db_name={MYAPS_MAIN_DB}', json={
                'memo': memo,
            })
            console_log.info(f"更新PR状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PR状态时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _pr_push_failed(prno: str, msg: str=None, msg_from: str=None):
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
            response = SESSION.patch(f'{THIS_BASE_URL}/api/t_supply/{prno}/...?db_name={MYAPS_MAIN_DB}', json={
                'memo': memo,
            })
            console_log.info(f"更新PR失败状态响应: {response.status_code}, {response.text}")
            return response
        except Exception as e:
            error_msg = f"更新PR失败状态时发生网络错误: {str(e)}"
            file_log.error(error_msg)
            console_log.error(error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _get_supplymo_detaildata(supplyno: str, get_prev_mo:bool=False, get_next_mo:bool=False):
        """
        获取工单的工序详情、及MTO销售订单信息
        Args:
            supplyno: 工单号
            get_prev_mo: 是否查询前 前置 工单
            get_next_mo: 是否查询后 后置 工单
        Returns:
            工单计划单详情
        """
        supply_response = SESSION.get(f"{THIS_BASE_URL}/api/v_supply_mo/{supplyno}?db_name={MYAPS_MAIN_DB}&prev_mo={get_prev_mo}&next_mo={get_next_mo}")
        supply_response_json = supply_response.json()
        supplymo_detaildata = supply_response_json['data'][0]
        return supplymo_detaildata


    @staticmethod
    def _get_demand_datalist(demandno: str) -> List[Dict]:
        """
        获取工单原料需求
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        demand_response = SESSION.get(f"{THIS_BASE_URL}/api/v_demand/{demandno}?db_name={MYAPS_MAIN_DB}")
        demand_response_json = demand_response.json()
        demand_detaildata = demand_response_json['data']
        return demand_detaildata


    @staticmethod
    def _get_dategrouped_pr(db_name: str=None, period: int|str=30, groupdates: Optional[str]=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        db_name = db_name or MYAPS_MAIN_DB
        response = SESSION.get(f"{THIS_BASE_URL}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}")
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


    @staticmethod
    def aggregate_pr_data(pr_data_list: list[dict], group_by: list=['materialno', 'avail_date', 'vendorno']) -> list[dict]:
        """
        聚合 PR avail_qty 字段
        Args:
            pr_data_list: PR 数据列表
        Returns:
            聚合后的 PR 数据列表
        """
        import pandas as pd
        
        pr_datetime_fields = ('avail_date', 'create_date', 'avail_end_date', 'sys_date', 'sys_stamp')

        if not pr_data_list:
            return []
        
        df = pd.DataFrame(pr_data_list)
        
        keep_cols = ['materialno', 'category', 'avail_qty', 'create_date', 'avail_date', 'vendorno']
        df = df[[col for col in keep_cols if col in df.columns]]
        
        for field in group_by:
            if field in pr_datetime_fields and field in df.columns:
                df[field] = pd.to_datetime(df[field], errors='coerce').dt.date
        
        agg_dict = {'avail_qty': 'sum'}
        other_cols = [col for col in df.columns if col not in group_by and col != 'avail_qty']
        for col in other_cols:
            agg_dict[col] = 'last'
        
        result_df = df.groupby(group_by, dropna=False).agg(agg_dict).reset_index()
        
        result_df = result_df.replace({pd.NA: None, pd.NaT: None, float('nan'): None})
        
        return result_df.to_dict('records')
