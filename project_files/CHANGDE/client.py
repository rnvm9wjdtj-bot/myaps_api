from apps.data_opt.components.ecerp_jky import HapConnection, JkyConnection, JkyPullTask
    


_MINUTE = 0

_TASKS = [
    JkyPullTask(task_hour=(0, ), source_codes=['$Company', '$Department', '$Staff', '$BankAccounts', '$Channel', '$GoodsCate', '$Warehouse', '$Logistic']),
    JkyPullTask(task_hour=(0, ), source_codes=['~BusinessOrder', '~Trade', '~Order']),
    JkyPullTask(task_hour=(0, ), source_codes=['^Customer', '^Sku', '^BusinessOrder', '^Trade']),
]


_HAP = HapConnection()
_JKY = JkyConnection(hap_conn=_HAP)
_JKY.create_pull_task(exec_minute=_MINUTE, task_name=f"sync_changde_jky_data")

# @cron_task(minute=_MINUTE)
# async def exec_schedule():
#     now = datetime.now()
#     hour = int(now.hour)
#     this_slice_end = f"{now.strftime('%Y-%m-%d')} {hour:02d}:{_MINUTE:02d}:00"
#     for task in _TASKS:
#         if not hour in task.task_hour:
#             continue
#         sorted_src_codes = _JKY.sort_tasks(task.source_codes)
#         for src_code in sorted_src_codes:
#             if src_code.startswith('$'):
#                 # 如果是全量数据
#                 await _JKY.data_to_hap(src_code)
#             else:
#                 # 如果是增量数据
#                 last_slice_end = CACHE_JSON.get(f"last_slice_end / {src_code}", None)
#                 if last_slice_end:
#                     slice_timerange = (last_slice_end, this_slice_end)
#                     await _JKY.data_to_hap(src_code, slice_timerange)
#                 CACHE_JSON.set(f"last_slice_end / {src_code}", this_slice_end)

# for task_time, src_codes in schedule_tasks.items():
#     hour, minute = task_time
#     _JKY.create_cron_task(
#         hour=hour,
#         minute=minute,
#         task_name=f"sync_changde_jky_data",
#         source_codes=src_codes,
#     )

# @cron_task(hour='0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23', minute=46)
# @cron_task(hour=22, minute=42)
# async def sync_incremental_data():
#     slice_timerange = ("2026-03-11 00:00:00", "2026-03-12 00:00:00")
#     for source_code in _JKY.sorted_models.keys():
#         await _JKY.data_to_hap(source_code, slice_timerange)
