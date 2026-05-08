#!/usr/bin/env python3
"""
租户独立告警发送脚本
可被 service_daemon.ps1 或其他外部程序调用

用法:
    python remind.py --message "服务异常" --level error --subject "告警测试"
"""

from globalobjects.reminder import QqEmailReminder



ops_reminder = QqEmailReminder(
    smtp_user="2982212683@qq.com",
    smtp_password="jyboujldhplddhdf",
    email_from="2982212683@qq.com",
    email_to="2982212683@qq.com",
)

bus_reminder = QqEmailReminder(
    smtp_user="2982212683@qq.com",
    smtp_password="jyboujldhplddhdf",
    email_from="2982212683@qq.com",
    email_to="2982212683@qq.com",
)



if __name__ == "__main__":
    import sys
    sys.exit(ops_reminder.remind_by_shell())