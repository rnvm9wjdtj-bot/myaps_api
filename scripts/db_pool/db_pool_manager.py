#!/usr/bin/env python3
"""
数据库连接池管理快速启动脚本

用于快速启动连接池监控和查看状态。
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from globalobjects.db_pool import (
    start_pool_monitoring,
    stop_pool_monitoring,
    get_pool_monitor_status,
    get_enhanced_db_manager,
    PoolManagerConfig
)
from globalobjects import logger


async def start_monitoring():
    """启动连接池监控"""
    from core.settings import MYAPS_DBSET_LIST
    
    connection_names = MYAPS_DBSET_LIST if MYAPS_DBSET_LIST else []
    
    if not connection_names:
        logger.error("未找到要监控的数据库连接，请检查 MYAPS_DBSET_LIST 配置")
        return
    
    logger.info(f"准备启动连接池监控，监控连接: {connection_names}")
    
    try:
        await start_pool_monitoring(connection_names)
        logger.info("连接池监控已启动")
    except Exception as e:
        logger.error(f"启动连接池监控失败: {e}")


async def stop_monitoring():
    """停止连接池监控"""
    try:
        await stop_pool_monitoring()
        logger.info("连接池监控已停止")
    except Exception as e:
        logger.error(f"停止连接池监控失败: {e}")


def show_status():
    """显示监控状态"""
    try:
        status = get_pool_monitor_status()
        
        print("\n" + "="*50)
        print("数据库连接池监控状态")
        print("="*50)
        print(f"运行状态: {'运行中' if status['is_running'] else '已停止'}")
        print(f"监控间隔: {status['monitor_interval']}秒")
        print(f"监控连接: {', '.join(status['connection_names'])}")
        
        cleanup_status = status['cleanup_status']
        print(f"\n后台清理任务:")
        print(f"  运行状态: {'运行中' if cleanup_status['is_running'] else '已停止'}")
        print(f"  队列大小: {cleanup_status['queue_size']}/{cleanup_status['max_queue_size']}")
        print(f"  已清理数: {cleanup_status['cleanup_count']}")
        
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"获取监控状态失败: {e}")


async def check_connection(connection_name: str):
    """检查指定连接的健康状态"""
    try:
        manager = get_enhanced_db_manager(connection_name)
        
        print(f"\n检查连接: {connection_name}")
        print("-" * 50)
        
        # 检查健康状态
        health_result = await manager.check_health()
        print(f"健康状态: {'健康' if health_result.is_healthy else '不健康'}")
        if not health_result.is_healthy:
            print(f"错误信息: {health_result.error_message}")
        if health_result.response_time:
            print(f"响应时间: {health_result.response_time:.3f}秒")
        
        # 获取连接池状态
        pool_status = await manager.get_connection_pool_status()
        print(f"\n连接池状态:")
        print(f"  总连接数: {pool_status.total_connections}")
        print(f"  已用连接: {pool_status.used_connections}")
        print(f"  空闲连接: {pool_status.idle_connections}")
        print(f"  使用率: {pool_status.usage_rate:.1f}%")
        print(f"  可用状态: {'可用' if pool_status.pool_available else '不可用'}")
        
        # 获取状态信息
        state_info = manager.get_state_info()
        print(f"\n状态管理:")
        print(f"  当前状态: {state_info.state.value}")
        print(f"  是否可用: {'是' if state_info.is_available else '否'}")
        if state_info.update_reason:
            print(f"  更新原因: {state_info.update_reason}")
        
        print("-" * 50 + "\n")
        
    except Exception as e:
        logger.error(f"检查连接失败: {e}")


async def detect_leak(connection_name: str):
    """检测指定连接的泄漏情况"""
    try:
        manager = get_enhanced_db_manager(connection_name)
        
        # 记录使用情况
        await manager.record_usage()
        
        # 检测泄漏
        result = await manager.detect_leak()
        
        print(f"\n泄漏检测: {connection_name}")
        print("-" * 50)
        print(f"是否泄漏: {'是' if result.leak_detected else '否'}")
        print(f"严重程度: {result.severity.value}")
        print(f"当前使用率: {result.usage_rate:.1f}%")
        print(f"平均使用率: {result.avg_usage_rate:.1f}%")
        print(f"最高使用率: {result.max_usage_rate:.1f}%")
        print(f"健康检查失败率: {result.health_check_failure_rate:.1%}")
        
        if result.trend:
            print(f"\n趋势分析:")
            print(f"  趋势类型: {result.trend.trend_type.value}")
            print(f"  斜率: {result.trend.slope:.4f}")
            print(f"  置信度: {result.trend.confidence:.2f}")
            print(f"  数据点: {result.trend.data_points}")
        
        print("-" * 50 + "\n")
        
    except Exception as e:
        logger.error(f"泄漏检测失败: {e}")


def print_usage():
    """打印使用说明"""
    print("""
数据库连接池管理工具

用法:
  python scripts/db_pool_manager.py <命令> [参数]

命令:
  start       启动连接池监控
  stop        停止连接池监控
  status      显示监控状态
  check       检查连接健康状态
  leak        检测连接泄漏

示例:
  python scripts/db_pool_manager.py start
  python scripts/db_pool_manager.py stop
  python scripts/db_pool_manager.py status
  python scripts/db_pool_manager.py check db1
  python scripts/db_pool_manager.py leak db1
""")


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1]
    
    if command == "start":
        await start_monitoring()
    elif command == "stop":
        await stop_monitoring()
    elif command == "status":
        show_status()
    elif command == "check":
        if len(sys.argv) < 3:
            print("错误: 请指定连接名称")
            print("用法: python scripts/db_pool_manager.py check <connection_name>")
            return
        await check_connection(sys.argv[2])
    elif command == "leak":
        if len(sys.argv) < 3:
            print("错误: 请指定连接名称")
            print("用法: python scripts/db_pool_manager.py leak <connection_name>")
            return
        await detect_leak(sys.argv[2])
    else:
        print(f"错误: 未知命令 '{command}'")
        print_usage()


if __name__ == "__main__":
    asyncio.run(main())