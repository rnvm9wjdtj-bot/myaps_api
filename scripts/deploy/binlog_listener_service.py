# binlog_listener_service.py
import os
import sys
import time
import psutil

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from apps.data_opt.utils.binlog_listener import binlog_listener

def is_process_running(process_name):
    """检查进程是否在运行"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if process_name in ' '.join(proc.info['cmdline']):
                return True
        except:
            pass
    return False

def main():
    # 检查是否已有监听器进程在运行
    if is_process_running("binlog_listener_service.py"):
        print("Binlog listener is already running.")
        return
    
    try:
        # 启动监听器
        print("Starting Binlog listener...")
        binlog_listener.start()
    except KeyboardInterrupt:
        print("Stopping Binlog listener...")
    except Exception as e:
        print(f"Error starting Binlog listener: {e}")

if __name__ == "__main__":
    main()