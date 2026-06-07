"""
数据库连接池管理使用示例

演示如何使用增强的连接池管理功能。
"""
import asyncio
from globalobjects.db_pool import (
    get_enhanced_db_manager,
    EnhancedConnectionLeakDetector,
    BackgroundCleanupTask,
    ConnectionPoolStatus,
    PoolManagerConfig
)


async def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 获取增强管理器
    manager = get_enhanced_db_manager("my_connection")
    
    # 检查健康状态
    health_result = await manager.check_health()
    print(f"健康状态: {health_result.is_healthy}")
    if not health_result.is_healthy:
        print(f"错误信息: {health_result.error_message}")
    
    # 获取连接池状态
    pool_status = await manager.get_connection_pool_status()
    print(f"总连接数: {pool_status.total_connections}")
    print(f"已用连接: {pool_status.used_connections}")
    print(f"使用率: {pool_status.usage_rate:.1f}%")
    
    # 获取状态信息
    state_info = manager.get_state_info()
    print(f"连接池状态: {state_info.state.value}")
    print(f"是否可用: {state_info.is_available}")


async def example_leak_detection():
    """泄漏检测示例"""
    print("\n=== 泄漏检测示例 ===")
    
    # 创建检测器
    detector = EnhancedConnectionLeakDetector()
    
    # 模拟记录使用情况
    for i in range(10):
        pool_status = ConnectionPoolStatus(
            connection_name="my_connection",
            total_connections=10,
            used_connections=8 + i % 3,
            idle_connections=2 - i % 3,
            usage_rate=80.0 + i % 3 * 5
        )
        detector.record_usage("my_connection", pool_status, is_healthy=True)
    
    # 检测泄漏
    result = detector.detect_leak("my_connection")
    print(f"是否检测到泄漏: {result.leak_detected}")
    print(f"严重程度: {result.severity.value}")
    print(f"平均使用率: {result.avg_usage_rate:.1f}%")
    print(f"最高使用率: {result.max_usage_rate:.1f}%")
    
    # 生成告警
    if result.leak_detected:
        alert = detector.generate_alert("my_connection", result)
        print(f"\n告警消息: {alert.message}")
        print(f"处理建议: {alert.suggestion}")


async def example_cleanup_task():
    """后台清理任务示例"""
    print("\n=== 后台清理任务示例 ===")
    
    # 获取清理任务实例
    cleanup_task = BackgroundCleanupTask.get_instance()
    
    # 启动清理任务
    await cleanup_task.start()
    print("清理任务已启动")
    
    # 查看状态
    status = cleanup_task.get_status()
    print(f"是否运行: {status['is_running']}")
    print(f"队列大小: {status['queue_size']}")
    print(f"最大队列: {status['max_queue_size']}")
    
    # 模拟添加待清理连接
    # await cleanup_task.add_to_cleanup_queue(
    #     connection=old_conn,
    #     connection_name="my_connection",
    #     reason="event_loop_conflict"
    # )
    
    # 停止清理任务
    await cleanup_task.stop()
    print("清理任务已停止")


async def example_connection_refresh():
    """连接刷新示例"""
    print("\n=== 连接刷新示例 ===")
    
    manager = get_enhanced_db_manager("my_connection")
    
    # 检查当前状态
    state_info = manager.get_state_info()
    print(f"刷新前状态: {state_info.state.value}")
    
    # 刷新连接（快速模式）
    success = await manager.refresh_connection(fast_mode=True)
    print(f"刷新结果: {'成功' if success else '失败'}")
    
    # 检查刷新后状态
    state_info = manager.get_state_info()
    print(f"刷新后状态: {state_info.state.value}")
    
    # 验证健康状态
    health_result = await manager.check_health()
    print(f"健康状态: {health_result.is_healthy}")


async def example_custom_config():
    """自定义配置示例"""
    print("\n=== 自定义配置示例 ===")
    
    # 创建自定义配置
    config = PoolManagerConfig(
        health_check_timeout=3.0,
        cleanup_interval=180,
        leak_warning_threshold=75,
        leak_critical_threshold=85,
        leak_emergency_threshold=92
    )
    
    # 使用自定义配置创建管理器
    manager = get_enhanced_db_manager("my_connection", config)
    
    print(f"健康检查超时: {config.health_check_timeout}秒")
    print(f"清理间隔: {config.cleanup_interval}秒")
    print(f"警告阈值: {config.leak_warning_threshold}%")
    print(f"严重阈值: {config.leak_critical_threshold}%")
    print(f"紧急阈值: {config.leak_emergency_threshold}%")


async def example_with_context_manager():
    """使用上下文管理器示例"""
    print("\n=== 上下文管理器示例 ===")
    
    manager = get_enhanced_db_manager("my_connection")
    
    try:
        # 使用上下文管理器获取连接
        async with manager.get_connection() as conn:
            # 执行查询
            # result = await conn.execute_query("SELECT * FROM users")
            print("成功获取连接")
            print("连接池状态检查通过")
    except Exception as e:
        print(f"获取连接失败: {str(e)}")


async def main():
    """主函数"""
    print("数据库连接池管理功能演示\n")
    
    try:
        await example_basic_usage()
        await example_leak_detection()
        await example_cleanup_task()
        await example_connection_refresh()
        await example_custom_config()
        await example_with_context_manager()
    except Exception as e:
        print(f"\n示例执行出错: {str(e)}")
        print("注意: 部分示例需要实际的数据库连接才能运行")
    
    print("\n演示完成")


if __name__ == "__main__":
    asyncio.run(main())