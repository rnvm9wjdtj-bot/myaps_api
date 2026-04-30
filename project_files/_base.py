"""
导入包和常量，供各项目文件使用
"""

# import threading
import os, asyncio, logging, json, requests, pandas as pd, threading, inspect
from functools import wraps
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional, Union
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pydantic import BaseModel as PydanticModel

# from tortoise import Tortoise
from core.settings import MAX_EVENTS_PER_SECOND, SCHEDULER_MINUTE, PLANNER_MAILS, ENGINEER_MAILS
from globalobjects.globalconst import OrderStatusEnum


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from core.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, PROJECT_JSON
from globalobjects import logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv, AlertType, QqEmailReminder, Reminder
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_supsert, db_update_by_index
from apps.io_api.models import TSupply
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests, get_session
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components import ApsPayloadSponsor, EventResultPoster, CacheItem
from apps.data_opt.components._base import async_rate_limit, sync_rate_limit, async_service_operation, batch_service_operation
from apps.data_opt.components.simple_hap import HapConnection




CLIENT_LOGGER = log_config.get_logger(__name__)

CLIENT_SESSION = get_session()

def get_scheduler_minute(offset: int = 0):
    result = set()
    for m in SCHEDULER_MINUTE.split(','):
        m = m.strip()
        if m == '*':
            for v in range(60):
                result.add((v + offset) % 60)
        elif m.startswith('*/'):
            step = int(m[2:])
            if step > 0:
                for v in range(0, 60, step):
                    result.add((v + offset) % 60)
        else:
            result.add((int(m) + offset) % 60)
    return ','.join(str(v) for v in sorted(result))



import time
import asyncio
from functools import wraps
from collections import namedtuple
from threading import Lock

# 定义任务执行结果的具名元组
# TaskResult = namedtuple('TaskResult', ['status', 'error'])


#################################################################################
# 公共装饰器 及 相关逻辑
#################################################################################


async def _execute_handler(handler: Union[callable, str], handler_name, event_data_list: List[Dict], _erp: EventResultPoster, *args, **kwargs):
    """执行回调处理器
    
    Args:
        handler: 回调处理器（可调用对象或字符串）
        handler_name: 处理器名称（用于日志）
        event_data_list: 事件数据列表
        _erp: EventResultPoster 实例
        *args, **kwargs: 额外参数
    """
    if isinstance(handler, str):
        # 从 _erp 中查找方法
        if hasattr(_erp, handler):
            method = getattr(_erp, handler, None)
            if not method:
                CLIENT_LOGGER.warning_msg(f"_erp 中 {handler} 方法不存在")
                return
            if not callable(method):
                CLIENT_LOGGER.warning_msg(f"{handler} 不是可调用对象")
                return
            try:
                if inspect.iscoroutinefunction(method):
                    await method(event_data_list, *args, **{k: v for k, v in kwargs.items() if k != '_erp'})
                else:
                    method(event_data_list, *args, **{k: v for k, v in kwargs.items() if k != '_erp'})
                CLIENT_LOGGER.info(f"已执行 _erp.{handler}")
            except Exception as e:
                CLIENT_LOGGER.fail(f"执行 _erp.{handler} 失败", str(e))
        else:
            CLIENT_LOGGER.warning_msg(f"_erp 中不存在 {handler} 方法")
    elif callable(handler):
        try:
            if inspect.iscoroutinefunction(handler):
                await handler(event_data_list, *args, **{k: v for k, v in kwargs.items() if k != '_erp'})
            else:
                handler(event_data_list, *args, **{k: v for k, v in kwargs.items() if k != '_erp'})
            CLIENT_LOGGER.info(f"已执行 {handler.__name__}")
        except Exception as e:
            CLIENT_LOGGER.fail(f"执行 {handler.__name__} 失败", str(e))
    else:
        CLIENT_LOGGER.warning_msg(f"{handler} 不是可调用对象")


def event_batch_handler(
    reminder: Reminder = None,
    start_handler: callable = None,
    final_handler: callable = None,
    error_handler: Union[callable, str] = None,
    description: str = None
):
    """
    事件批处理装饰器（整合开始通知、结果收集、结束通知）
    
    用法:
        @event_batch_handler(reminder=planner_email_reminder, final_handler=my_final_handler, start_handler=my_start_handler)
        async def batch_handle_pl_status_a2e(event_data: List[Dict], description="PL 单据下达", _erp=None):

            async def handle_pl_status_a2e(item):
                try:
                    # 业务逻辑
                    await _erp.pl_release_success(...)
                except Exception as e:
                    await _erp.pl_release_failed(...)
            
            tasks = [handle_pl_status_a2e(item) for item in event_data]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    参数说明:
        reminder: 通知发送器，用于发送开始/结束通知
        error_handler: 异常处理回调，签名: func(exception, *args, **kwargs)；若为字符串，则从 _erp 中查找同名方法
        final_handler: 最终回调，签名: func(event_data_list, *args, **kwargs)  # 第一个参数是事件数据列表；若为字符串，则从 _erp 中查找同名方法
        start_handler: 开始回调，签名: func(event_data_list, *args, **kwargs)  # 第一个参数是事件数据列表；若为字符串，则从 _erp 中查找同名方法
        description: 任务描述，用于通知内容
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            event_data_list = None
            pending_exception = None
            result = None
            
            # 1. 提取 description
            actual_description = description
            if not actual_description:
                actual_description = kwargs.get('description')
                if actual_description is None:
                    try:
                        sig = inspect.signature(func)
                        bound_args = sig.bind_partial(*args, **kwargs)
                        bound_args.apply_defaults()
                        actual_description = bound_args.arguments.get('description')
                    except:
                        pass
                if actual_description is None:
                    actual_description = func.__name__
            
            # 2. 提取 event_data_list
            if args and len(args) > 0:
                event_data_list = args[0]
            elif 'event_data' in kwargs:
                event_data_list = kwargs['event_data']
            
            # 3. 创建并注入 _erp
            _erp = EventResultPoster()
            kwargs['_erp'] = _erp
            
            # 4. 执行 start_handler
            if start_handler is not None:
                # 从 kwargs 中移除 _erp，避免参数重复
                execute_kwargs = {k: v for k, v in kwargs.items() if k != '_erp'}
                await _execute_handler(start_handler, "start_handler", event_data_list, _erp, *args, **execute_kwargs)
            
            # 5. 发送开始通知
            if reminder is not None and reminder.email_to:
                if event_data_list is not None:
                    if isinstance(event_data_list, list):
                        count = len(event_data_list)
                        require_time_sec = 30 + count * 2 / MAX_EVENTS_PER_SECOND
                        require_time_min = f"{int(require_time_sec / 60)} 分 {int(require_time_sec % 60)} 秒"
                        content = f"开始【{actual_description}】，将处理【{count}】条数据，预计耗时【{require_time_min}】"
                    else:
                        content = f"开始【{actual_description}】，处理数据：{str(event_data_list)[:1024]}"
                else:
                    content = f"开始【{actual_description}】"
                
                content += f"\n 🚩 在收到完成提示前请耐心等待，⚠️ 请勿进行其他操作"
                await reminder.remind(content)
            
            # 6. 执行被装饰函数
            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                CLIENT_LOGGER.error(f"{actual_description} 执行出错: {str(e)}")
                if error_handler is not None:
                    CLIENT_LOGGER.info(f"尝试使用 {error_handler} 进行错误捕获处理。。。")
                    if isinstance(error_handler, str):
                        if hasattr(func, '__self__'):
                            error_method = getattr(func.__self__, error_handler, None)
                        else:
                            error_method = None
                        if not error_method:
                            CLIENT_LOGGER.warning_msg(f"无法解析 {error_handler} 为有效的方法")
                            pending_exception = e
                        elif not callable(error_method):
                            CLIENT_LOGGER.warning_msg(f"{error_handler} 为不可调用对象")
                            pending_exception = e
                        else:
                            try:
                                if inspect.iscoroutinefunction(error_method):
                                    await error_method(msg=str(e))
                                else:
                                    error_method(msg=str(e))
                                CLIENT_LOGGER.info(f"已使用 {error_handler} 完成捕获处理")
                            except Exception as inner_e:
                                CLIENT_LOGGER.fail(f"使用 {error_handler} 处理异常", str(inner_e))
                                pending_exception = e
                    else:
                        if callable(error_handler):
                            try:
                                if inspect.iscoroutinefunction(error_handler):
                                    await error_handler(e, *args, **kwargs)
                                else:
                                    error_handler(e, *args, **kwargs)
                                CLIENT_LOGGER.info(f"已使用 {error_handler.__name__} 完成捕获处理")
                            except Exception as inner_e:
                                CLIENT_LOGGER.fail(f"使用 {error_handler.__name__} 处理异常", str(inner_e))
                                pending_exception = e
                        else:
                            CLIENT_LOGGER.warning_msg(f"{error_handler.__name__} 为不可调用对象")
                            pending_exception = e
                else:
                    pending_exception = e
            finally:
                # 6. 汇总结果
                summary = _erp.get_summary()
                execution_time = time.time() - start_time
                # 确保 summary 是可序列化的字典
                summary_dict = summary.to_dict() if hasattr(summary, 'to_dict') else summary
                CLIENT_LOGGER.info(f"{actual_description} 执行完成，耗时: {execution_time:.2f} 秒，汇总结果: {json.dumps(summary_dict, ensure_ascii=False)}")
                
                # 7. 发送结束通知
                if reminder is not None and reminder.email_to:
                    notification = _erp.format_notification(actual_description)
                    CLIENT_LOGGER.info(f"通知内容: {notification}")
                    await reminder.remind(notification)
                
                # 8. 执行 final_handler
                if final_handler is not None:
                    # 从 kwargs 中移除 _erp，避免参数重复
                    execute_kwargs = {k: v for k, v in kwargs.items() if k != '_erp'}
                    await _execute_handler(final_handler, "final_handler", event_data_list, _erp, *args, **execute_kwargs)
            
            # 9. 重新抛出未处理的异常
            if pending_exception is not None:
                raise pending_exception
            
            return summary
        
        return wrapper
    return decorator

