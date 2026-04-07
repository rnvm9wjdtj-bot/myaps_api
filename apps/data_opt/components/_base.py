import json
from pathlib import Path
from typing import List, Dict, Optional, Literal, Callable, Union, Any, Type
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
import pandas as pd
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel
import requests
import time


from config.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET
from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.schemas import (
    model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm
)
from apps.io_api.models import TSupply, TDemand
from apps.io_api.utils.db_operation import db_query
from apps.io_api.utils.common import standard_response
from globalobjects import globalconst, logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv
from globalobjects.json_manager import JSONManager



logger = log_config.get_logger(__name__)


SESSION = get_session()


class BaseConnection(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    
    def __init__(self):
        self._session = get_session()


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
    def _call_api(method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        通用 API 调用方法，包含错误处理、超时设置和重试机制
        
        Args:
            method: HTTP 方法，如 'GET', 'POST', 'PATCH', 'PUT'
            url: API 地址
            **kwargs: 其他参数，如 json, timeout 等
        
        Returns:
            API 返回的 JSON 数据
        
        Raises:
            Exception: API 调用失败
        """
        max_retries = 3
        retry_count = 0
        timeout = kwargs.pop('timeout', (30, 60))
        
        while retry_count < max_retries:
            try:
                if method.upper() == 'GET':
                    response = SESSION.get(url, timeout=timeout, **kwargs)
                elif method.upper() == 'POST':
                    response = SESSION.post(url, timeout=timeout, **kwargs)
                elif method.upper() == 'PATCH':
                    response = SESSION.patch(url, timeout=timeout, **kwargs)
                elif method.upper() == 'PUT':
                    response = SESSION.put(url, timeout=timeout, **kwargs)
                elif method.upper() == 'DELETE':
                    response = SESSION.delete(url, timeout=timeout, **kwargs)
                else:
                    raise ValueError(f"不支持的 HTTP 方法: {method}")
                
                response.raise_for_status()  # 检查 HTTP 状态码
                return response.json()
                
            except (requests.RequestException, ValueError, KeyError) as e:
                retry_count += 1
                logger.warning(f"API 调用失败，第{retry_count}次重试: {str(e)}")
                if retry_count >= max_retries:
                    logger.fail("API 调用", url, str(e))
                    raise
                time.sleep(1 * retry_count)  # 指数退避策略
        
        # 理论上不会走到这里
        raise Exception("API 调用失败：达到最大重试次数")

    @staticmethod
    def mto_workreport_to_virtual_stock(db:str=MYAPS_MAIN_DB):
        """
        将报工数据 转化为 虚拟库存 数据，只处理MTO报工
        🅰 db: 账套名称，默认MYAPS_MAIN_DB
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        url = f"{THIS_BASE_URL}/api/v_supply_complete?db_name={db}"
        response_json = ApsHelpers._call_api('GET', url)
        mo_complete_data = response_json.get('data')
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
    def refresh_supply(supply_data:Union[List[Dict[str, Any]], pd.DataFrame], type_:Literal['ST', 'SO']='ST', dbs:str=MYAPS_DB_SET):
        from apps.io_api.schemas import AcceptSupply

        if isinstance(supply_data, pd.DataFrame):
            supply_data = supply_data.to_dict('records')
        supply_data = [AcceptSupply(**item).model_dump(exclude_none=True) for item in supply_data]
        url = f"{THIS_BASE_URL}/api/t_supply/type/{type_}?db_name={dbs}"
        refresh_result_json = ApsHelpers._call_api('PUT', url, json=supply_data)
        if refresh_result_json.get('success'):
            logger.success("刷新供应数据", f"type_{type_}", f"账套{dbs}")
        else:
            logger.fail("刷新供应数据", f"type_{type_}", refresh_result_json.get('message'))


    @staticmethod
    def confirm_workreport(db_name:str=MYAPS_MAIN_DB):
        """
        确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        """
        logger.start("确认报工记录任务")
        url = f"{THIS_BASE_URL}/api/t_confirm?db_name={db_name}"
        response_json = ApsHelpers._call_api('PATCH', url)
        logger.success("确认报工记录任务")
        return response_json


    @staticmethod
    def pl_release_success(native_plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _id: str=None, _entryid: str=None):
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
            logger.query("PL信息", native_plno, "")
            query_url = f"{THIS_BASE_URL}/api/v_supply_mo/{native_plno}?db_name={MYAPS_MAIN_DB}"
            query_result_json = ApsHelpers._call_api('GET', query_url)
            logger.info(f"查询PL信息响应：成功")

            if query_result_json.get('success') == 0:
                logger.fail("PL查询", native_plno, query_result_json.get('message'))
                return standard_response(status_code=query_result_json.get('status_code', 500), success=0, message=query_result_json.get('message'))

            query_data = query_result_json.get('data', [])
            if not query_data or len(query_data) > 1:
                logger.fail("PL查询", native_plno, "未找到或多条匹配", to_file=True)
                return standard_response(success=0, message=f"PL {native_plno} not found or multiple records matched.")

            if query_data[0].get("type") != "PL":
                logger.fail("PL查询", native_plno, "非PL类型", to_file=True)
                return standard_response(status_code=400, success=0, message=f"Supply {native_plno} is not a PL.")

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.success("推送 MO", f"原供应号{native_plno}", f"MO单号{mono}", to_file=True)

            memo = json.dumps({
                "msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now,
                "native_no": native_plno, "_code": mono, "_id": _id, "_entryid": _entryid}, ensure_ascii=False
            )

            logger.update("PL状态", native_plno, f"目标状态{to_status}，MO单号{mono}")
            patch_url = f'{THIS_BASE_URL}/api/t_supply/{native_plno}?db_name={MYAPS_MAIN_DB}'
            patch_data = {
                'status': to_status,
                'apiex_sn': str(mono),
                'apiex_id': str(_id or ""),
                'apiex_entryid': str(_entryid or ""),
                'supplyno': str(mono),
                'memo': memo,
            }
            response_json = ApsHelpers._call_api('PATCH', patch_url, json=patch_data)
            logger.info(f"更新PL状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PL状态为MO时发生网络错误：{str(e)}"
            logger.fail("PL状态更新", native_plno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def pl_release_failed(native_plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, push_data: dict=None, msg_from: str=None):
        logger.fail("推送 MO", json.dumps(push_data, ensure_ascii=False), msg)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
        
        try:
            url = f'{THIS_BASE_URL}/api/t_supply/{native_plno}/...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'status': to_status,
                'memo': memo,
            })
            logger.info(f"更新PL状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PL状态时发生网络错误：{str(e)}"
            logger.fail("PL状态更新", native_plno, error_msg)
            return None


    @staticmethod
    def rs_push_success(rsno: str, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now, "native_no": rsno, "_code": _code, "_id": _id, "_entryid": _entryid}, ensure_ascii=False)
            
            logger.update("RS状态", rsno, f"目标状态{to_status}")
            url = f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'status': to_status,
                'memo': memo,
            })
            logger.info(f"更新RS状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新RS状态时发生网络错误：{str(e)}"
            logger.fail("RS状态更新", rsno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def rs_push_failed(rsno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
        logger.fail("推送 RS", json.dumps(push_data, ensure_ascii=False), msg)

        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
            url = f'{THIS_BASE_URL}/api/t_demand/{rsno}/.../...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'memo': memo,
            })
            return response_json
        except Exception as e:
            error_msg = f"更新RS失败状态时发生网络错误：{str(e)}"
            logger.fail("RS状态更新", rsno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def query_material(materialnos: str | list[str]) -> dict:
        """
        查询物料信息
        Args:
            materialnos: 物料编号（多个用半角逗号分隔）或物料编号列表
        Returns:
            物料信息字典或列表
        """
        if isinstance(materialnos, list):
            materialnos = ','.join(materialnos)
        url = f"{THIS_BASE_URL}/api/t_material/{materialnos}?db_name={MYAPS_MAIN_DB}"
        try:
            response_json = ApsHelpers._call_api('GET', url)
            return response_json.get('data', [])
        except Exception as e:
            error_msg = f"查询物料信息时发生网络错误：{str(e)}"
            logger.fail("查询物料信息", materialnos, error_msg)
            return []


    @staticmethod
    def get_new_pr_data():
        from apps.io_api.utils.db_operation import db_query

        pr_data_list = db_query(MYAPS_MAIN_DB, "v_supply", "`Type`='PR' AND `Status`='NEW'").get('data')
        return pr_data_list


    @staticmethod
    def aggregate_pr_data(pr_data_list: list[dict]=None, group_by: list=['materialno', 'avail_date', 'vendorno']) -> list[dict]:
        """
        聚合 PR avail_qty 字段
        Args:
            pr_data_list: PR 数据列表，若为None则查询主账套中状态为 NEW 的 PR 数据
            group_by: 分组字段，默认['materialno', 'avail_date', 'vendorno']
        Returns:
            聚合后的 PR 数据列表
        """
        import pandas as pd

        if not pr_data_list:
            pr_data_list = ApsHelpers.get_new_pr_data()
            if not pr_data_list:
                return []

        pr_datetime_fields = ('avail_date', 'create_date', 'avail_end_date', 'sys_date', 'sys_stamp')

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


    @staticmethod
    def _pr_push_success(prno: str, msg: str=None, msg_from: str=None, _code: str=None, _id: str=None, _entryid: str=None):
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"✅ {msg}", "from": msg_from, "success": True, "datetime": now, "native_no": prno, "_code": _code, "_id": _id, "_entryid": _entryid}, ensure_ascii=False)
            logger.update("PR状态", prno, "")
            url = f'{THIS_BASE_URL}/api/t_supply/{prno}/...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'memo': memo,
                'status': 'CRE',
                'apiex_sn': _code,
                'apiex_id': _id,
                'apiex_entryid': _entryid,
            })
            logger.info(f"更新PR状态响应：成功")
            return response_json
        except Exception as e:
            error_msg = f"更新PR状态时发生网络错误：{str(e)}"
            logger.fail("PR状态更新", prno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def _pr_push_failed(prno: str, msg: str=None, msg_from: str=None, push_data: dict | list=None):
        logger.fail("推送 PR", json.dumps(push_data, ensure_ascii=False), msg)
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memo = json.dumps({"msg": f"🚫 {msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False)
            url = f'{THIS_BASE_URL}/api/t_supply/{prno}/...?db_name={MYAPS_MAIN_DB}'
            response_json = ApsHelpers._call_api('PATCH', url, json={
                'memo': memo,
                'status': 'NEW',
            })
            return response_json
        except Exception as e:
            error_msg = f"更新PR失败状态时发生网络错误：{str(e)}"
            logger.fail("PR状态更新", prno, error_msg)
            return standard_response(status_code=500, success=0, message=error_msg)


    @staticmethod
    def get_supplymo_detaildata(supplyno: str, get_prev_mo:bool=False, get_next_mo:bool=False, get_origin_so:bool=False):
        """
        获取工单的工序详情、及MTO销售订单信息
        Args:
            supplyno: 工单号
            get_prev_mo: 是否查询前 前置 工单
            get_next_mo: 是否查询后 后置 工单
        Returns:
            工单计划单详情
        """
        url = f"{THIS_BASE_URL}/api/v_supply_mo/{supplyno}?db_name={MYAPS_MAIN_DB}&prev_mo={get_prev_mo}&next_mo={get_next_mo}&origin_so={get_origin_so}"
        supply_response_json = ApsHelpers._call_api('GET', url)
        
        if supply_response_json.get('success') != 0 and supply_response_json.get('data'):
            return supply_response_json['data'][0]
        else:
            raise Exception(f"API返回错误: {supply_response_json.get('message', '未知错误')}")


    @staticmethod
    def get_demand_datalist(demandno: str) -> List[Dict]:
        """
        获取工单原料需求
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        url = f"{THIS_BASE_URL}/api/v_demand/{demandno}?db_name={MYAPS_MAIN_DB}"
        demand_response_json = ApsHelpers._call_api('GET', url)
        return demand_response_json.get('data', [])


    @staticmethod
    def get_dategrouped_pr(db_name: str=None, period: int|str=30, groupdates: Optional[str]=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        db_name = db_name or MYAPS_MAIN_DB
        url = f"{THIS_BASE_URL}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}"
        response_json = ApsHelpers._call_api('GET', url)
        data = response_json.get('data', [])
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
