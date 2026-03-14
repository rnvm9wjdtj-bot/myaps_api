from apps.data_opt.components.ecerp_jky import HapConnection, JkyConnection, JkyPullTask



_MINUTE = 0

_TASKS = [
    # JkyPullTask(task_hours=(19, ), source_codes=['$Company', '$Department']),
    JkyPullTask(task_hours=(0, ), source_codes=['$Company', '$Department', '$Staff', '$BankAccounts', '$Channel', '$GoodsCate', '$Warehouse', '$Logistic']),
    JkyPullTask(task_hours=(0,2,4,6,8,9,10,11,12,13,14,15,16,17,18,19,20,21,23), source_codes=['~Customer', '~Sku', '~BusinessOrder', '~Trade', '~Order']),
    JkyPullTask(task_hours=(6,12,15), source_codes=['^Customer', '^Sku', '^BusinessOrder', '^Trade']),
]


_HAP = HapConnection()
_JKY = JkyConnection(hap_conn=_HAP)
_JKY.create_pull_task(exec_minute=_MINUTE, tasks=_TASKS)
