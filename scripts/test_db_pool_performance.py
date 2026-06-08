#!/usr/bin/env python3
"""
数据库连接池性能测试脚本

测试连接池优化后的性能指标。
"""
import asyncio
import time
from globalobjects.db_pool import (
    get_enhanced_db_manager,
    EnhancedConnectionLeakDetector,
    ConnectionPoolStatus
)


async def test_health_check_performance():
    """测试健康检查性能"""
    print("=== 健康检查性能测试 ===")
    
    manager = get_enhanced_db_manager("test_conn")
    
    iterations = 100
    start_time = time.time()
    
    for _ in range(iterations):
        try:
            await manager.check_health()
        except Exception as e:
            print(f"健康检查失败: {e}")
    
    elapsed = time.time() - start_time
    avg_time = elapsed / iterations
    
    print(f"总耗时: {elapsed:.3f}秒")
    print(f"平均耗时: {avg_time*1000:.2f}毫秒")
    print(f"吞吐量: {iterations/elapsed:.2f}次/秒")
    
    return avg_time < 0.1


async def test_leak_detection_performance():
    """测试泄漏检测性能"""
    print("\n=== 泄漏检测性能测试 ===")
    
    detector = EnhancedConnectionLeakDetector()
    
    for i in range(100):
        pool_status = ConnectionPoolStatus(
            connection_name="test_conn",
            total_connections=10,
            used_connections=5,
            idle_connections=5,
            usage_rate=50.0
        )
        detector.record_usage("test_conn", pool_status, is_healthy=True)
    
    iterations = 100
    start_time = time.time()
    
    for _ in range(iterations):
        detector.detect_leak("test_conn")
    
    elapsed = time.time() - start_time
    avg_time = elapsed / iterations
    
    print(f"总耗时: {elapsed:.3f}秒")
    print(f"平均耗时: {avg_time*1000:.2f}毫秒")
    print(f"吞吐量: {iterations/elapsed:.2f}次/秒")
    
    return avg_time < 0.05


async def test_state_management_performance():
    """测试状态管理性能"""
    print("\n=== 状态管理性能测试 ===")
    
    manager = get_enhanced_db_manager("test_conn")
    
    iterations = 1000
    start_time = time.time()
    
    for _ in range(iterations):
        state_info = manager.get_state_info()
    
    elapsed = time.time() - start_time
    avg_time = elapsed / iterations
    
    print(f"总耗时: {elapsed:.3f}秒")
    print(f"平均耗时: {avg_time*1000000:.2f}微秒")
    print(f"吞吐量: {iterations/elapsed:.2f}次/秒")
    
    return avg_time < 0.001


async def test_concurrent_access_performance():
    """测试并发访问性能"""
    print("\n=== 并发访问性能测试 ===")
    
    manager = get_enhanced_db_manager("test_conn")
    
    concurrent_tasks = 100
    start_time = time.time()
    
    async def single_operation():
        try:
            await manager.check_health()
        except Exception:
            pass
    
    await asyncio.gather(*[single_operation() for _ in range(concurrent_tasks)])
    
    elapsed = time.time() - start_time
    
    print(f"并发任务数: {concurrent_tasks}")
    print(f"总耗时: {elapsed:.3f}秒")
    print(f"吞吐量: {concurrent_tasks/elapsed:.2f}次/秒")
    
    return elapsed < 5.0


async def main():
    """主函数"""
    print("数据库连接池性能测试\n")
    
    results = []
    
    try:
        results.append(("健康检查", await test_health_check_performance()))
    except Exception as e:
        print(f"健康检查测试失败: {e}")
        results.append(("健康检查", False))
    
    try:
        results.append(("泄漏检测", await test_leak_detection_performance()))
    except Exception as e:
        print(f"泄漏检测测试失败: {e}")
        results.append(("泄漏检测", False))
    
    try:
        results.append(("状态管理", await test_state_management_performance()))
    except Exception as e:
        print(f"状态管理测试失败: {e}")
        results.append(("状态管理", False))
    
    try:
        results.append(("并发访问", await test_concurrent_access_performance()))
    except Exception as e:
        print(f"并发访问测试失败: {e}")
        results.append(("并发访问", False))
    
    print("\n=== 性能测试总结 ===")
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print(f"\n总体结果: {'✓ 全部通过' if all_passed else '✗ 部分失败'}")


if __name__ == "__main__":
    asyncio.run(main())