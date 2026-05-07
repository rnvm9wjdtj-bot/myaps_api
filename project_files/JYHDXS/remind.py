#!/usr/bin/env python3
"""
租户独立告警发送脚本
可被 service_daemon.ps1 或其他外部程序调用

用法:
    python remind.py --message "服务异常" --level error --subject "告警测试"
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

# 将项目根目录添加到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from globalobjects.reminder import QqEmailReminder


def load_project_config():
    """从环境变量和JSON配置文件加载项目配置"""
    # 读取 .env 文件获取 PROJECT_JSON 配置
    env_path = os.path.join(project_root, '.env')
    project_json = 'dev'
    
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('PROJECT_JSON='):
                    project_json = line.split('=', 1)[1].strip()
                    break
    
    # 构建配置文件路径
    project_dir = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, 'project_files', project_dir, f'{project_json}.json')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 全局配置缓存
project_config = load_project_config()

ops_config = project_config.get('ops_reminder', {})
bus_config = project_config.get('bus_reminder', {})


ops_reminder = QqEmailReminder(
    smtp_user=ops_config.get('smtp_user', ''),
    smtp_password=ops_config.get('smtp_password', ''),
    email_from=ops_config.get('email_from', ''),
    email_to=ops_config.get('email_to', ''),
)

bus_reminder = QqEmailReminder(
    smtp_user=bus_config.get('smtp_user', ''),
    smtp_password=bus_config.get('smtp_password', ''),
    email_from=bus_config.get('email_from', ''),
    email_to=bus_config.get('email_to', ''),
)


async def send_alert(message: str, level: str = "warning", subject: str = None):
    """发送告警"""

    if subject is None:
        level_prefix = {
            "info": "ℹ️ 信息",
            "warning": "⚠️ 警告",
            "error": "❌ 错误"
        }.get(level, "🔔")
        subject = f"{level_prefix} 系统告警"

    alert_content = {
        "level": level,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "source": "service_daemon"
    }

    await ops_reminder.remind(alert_content)
    return True


def main():
    parser = argparse.ArgumentParser(description="项目告警发送工具")
    parser.add_argument("--message", required=True, help="告警消息内容")
    parser.add_argument("--level", default="warning",
                        choices=["info", "warning", "error"], help="告警级别")
    parser.add_argument("--subject", help="邮件主题（可选）")

    args = parser.parse_args()

    try:
        asyncio.run(send_alert(args.message, args.level, args.subject))
        print(f"[SUCCESS] Alert sent: {args.subject or args.message}")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to send alert: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())