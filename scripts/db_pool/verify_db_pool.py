#!/usr/bin/env python3
"""
数据库连接池管理验证脚本

验证所有组件是否正确安装和配置。
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def check_imports():
    """检查导入是否正常"""
    print("检查导入...")
    
    try:
        # 检查数据模型
        from globalobjects.db_pool.db_pool_models import (
            ConnectionPoolState,
            LeakSeverity,
            TrendType,
            AlertLevel,
            AlertType,
            PoolManagerConfig
        )
        print("✅ 数据模型导入成功")
    except Exception as e:
        print(f"❌ 数据模型导入失败: {e}")
        return False
    
    try:
        # 检查异常类
        from globalobjects.db_pool.db_pool_exceptions import (
            DbPoolError,
            ConnectionPoolUnavailableError,
            HealthCheckError
        )
        print("✅ 异常类导入成功")
    except Exception as e:
        print(f"❌ 异常类导入失败: {e}")
        return False
    
    try:
        # 检查核心组件
        from globalobjects.db_pool import (
            ConnectionPoolStateManager,
            HealthChecker,
            SafeConnectionRefresher,
            EnhancedConnectionLeakDetector,
            BackgroundCleanupTask,
            EnhancedDbManager
        )
        print("✅ 核心组件导入成功")
    except Exception as e:
        print(f"❌ 核心组件导入失败: {e}")
        return False
    
    try:
        # 检查监控任务
        from globalobjects.db_pool import (
            PoolMonitorTask,
            start_pool_monitoring,
            stop_pool_monitoring,
            get_pool_monitor_status
        )
        print("✅ 监控任务导入成功")
    except Exception as e:
        print(f"❌ 监控任务导入失败: {e}")
        return False
    
    return True


def check_config():
    """检查配置是否正常"""
    print("\n检查配置...")
    
    try:
        from globalobjects.db_pool import PoolManagerConfig
        
        config = PoolManagerConfig()
        
        print(f"✅ 配置加载成功")
        print(f"  - 健康检查超时: {config.health_check_timeout}秒")
        print(f"  - 清理间隔: {config.cleanup_interval}秒")
        print(f"  - 警告阈值: {config.leak_warning_threshold}%")
        print(f"  - 严重阈值: {config.leak_critical_threshold}%")
        print(f"  - 紧急阈值: {config.leak_emergency_threshold}%")
        
        return True
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return False


def check_integration():
    """检查集成是否正常"""
    print("\n检查集成...")
    
    try:
        # 检查DbManager是否已集成
        from globalobjects.db_manager import DbManager
        
        # 创建一个临时实例
        manager = DbManager("test_connection")
        
        if hasattr(manager, '_use_enhanced_pool'):
            print(f"✅ DbManager已集成增强管理器")
            print(f"  - 增强池管理: {'启用' if manager._use_enhanced_pool else '禁用'}")
        else:
            print("⚠️  DbManager未集成增强管理器")
        
        return True
    except Exception as e:
        print(f"❌ 集成检查失败: {e}")
        return False


def check_files():
    """检查文件是否存在"""
    print("\n检查文件...")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_pool_dir = os.path.join(base_dir, "globalobjects", "db_pool")
    
    required_files = [
        "__init__.py",
        "README.md",
        "examples.py",
        "db_pool_models.py",
        "db_pool_exceptions.py",
        "db_pool_state_manager.py",
        "db_health_checker.py",
        "db_connection_refresher.py",
        "db_leak_detector.py",
        "db_cleanup_task.py",
        "db_enhanced_manager.py",
        "db_pool_monitor.py"
    ]
    
    all_exist = True
    for file in required_files:
        file_path = os.path.join(db_pool_dir, file)
        if os.path.exists(file_path):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} 不存在")
            all_exist = False
    
    return all_exist


def check_env_config():
    """检查环境变量配置"""
    print("\n检查环境变量配置...")
    
    env_vars = [
        "USE_ENHANCED_POOL",
        "POOL_STATE_LOCK_TIMEOUT",
        "HEALTH_CHECK_TIMEOUT",
        "CLEANUP_INTERVAL",
        "LEAK_WARNING_THRESHOLD",
        "LEAK_CRITICAL_THRESHOLD",
        "LEAK_EMERGENCY_THRESHOLD"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} = {value}")
        else:
            print(f"⚠️  {var} 未设置（将使用默认值）")
    
    return True


def main():
    """主函数"""
    print("="*60)
    print("数据库连接池管理验证")
    print("="*60)
    
    results = []
    
    # 检查文件
    results.append(("文件检查", check_files()))
    
    # 检查导入
    results.append(("导入检查", check_imports()))
    
    # 检查配置
    results.append(("配置检查", check_config()))
    
    # 检查集成
    results.append(("集成检查", check_integration()))
    
    # 检查环境变量
    results.append(("环境变量检查", check_env_config()))
    
    # 总结
    print("\n" + "="*60)
    print("验证结果总结")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n🎉 所有检查通过！连接池管理功能已正确安装。")
        print("\n下一步:")
        print("1. 启动应用: ./scripts/dev_server.sh start")
        print("2. 查看监控: python scripts/db_pool_manager.py status")
        print("3. 检查连接: python scripts/db_pool_manager.py check <connection_name>")
        return 0
    else:
        print("\n⚠️  部分检查未通过，请检查上述错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())