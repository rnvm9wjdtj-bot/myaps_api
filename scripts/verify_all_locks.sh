#!/bin/bash
# 验证所有文件锁机制是否正常工作

echo "======================================================================"
echo "多 Worker 环境文件锁机制全面验证"
echo "======================================================================"
echo ""

# 定义所有锁文件
LOCK_FILES=(
    "binlog:/tmp/.myaps_binlog.lock"
    "scheduler:/tmp/.myaps_scheduler.lock"
    "redis_consumer:/tmp/.myaps_redis_consumer.lock"
    "db_health_check:/tmp/.myaps_db_health_check.lock"
    "failed_op_recovery:/tmp/.myaps_failed_op_recovery.lock"
    "log_stream:/tmp/.myaps_log_stream.lock"
)

echo "1. 检查所有锁文件状态"
echo "   ----------------------------------------"
total_locks=0
active_locks=0

for lock_entry in "${LOCK_FILES[@]}"; do
    IFS=':' read -r lock_name lock_file <<< "$lock_entry"
    total_locks=$((total_locks + 1))
    
    if [ -f "$lock_file" ]; then
        PID=$(cat "$lock_file" 2>/dev/null)
        echo "   ✅ $lock_name"
        echo "      锁文件: $lock_file"
        echo "      持有进程 PID: $PID"
        
        # 检查进程是否存活
        if [ -d "/proc/$PID" ]; then
            echo "      进程状态: ✅ 正在运行"
            active_locks=$((active_locks + 1))
        else
            echo "      进程状态: ⚠️  已死亡（废弃锁）"
        fi
    else
        echo "   ℹ️  $lock_name"
        echo "      锁文件: $lock_file"
        echo "      状态: 未启动"
    fi
    echo ""
done

echo "   统计: $active_locks/$total_locks 个服务已启动"
echo ""

# 检查运行中的进程
echo "2. 检查运行中的相关进程"
echo "   ----------------------------------------"
PROCESS_PIDS=$(ps aux | grep -E "python.*main|uvicorn|gunicorn" | grep -v grep | awk '{print $2}')
if [ -n "$PROCESS_PIDS" ]; then
    echo "   找到以下进程:"
    ps aux | grep -E "python.*main|uvicorn|gunicorn" | grep -v grep | while read line; do
        echo "   - $line"
    done
else
    echo "   ℹ️  未找到运行中的进程"
fi
echo ""

# 检查环境变量
echo "3. 检查环境变量配置"
echo "   ----------------------------------------"
if [ -f ".env" ]; then
    echo "   TRUNON_SCHEDULER: $(grep '^TRUNON_SCHEDULER=' .env 2>/dev/null | cut -d'=' -f2 || echo '未设置')"
    echo "   TURNON_BINLOG_LISTENER: $(grep '^TURNON_BINLOG_LISTENER=' .env 2>/dev/null | cut -d'=' -f2 || echo '未设置')"
    echo "   WORKERS: $(grep '^WORKERS=' .env 2>/dev/null | cut -d'=' -f2 || echo '未设置')"
else
    echo "   ⚠️  .env 文件不存在"
fi
echo ""

# 检查最近的日志
echo "4. 检查最近的启动日志（最近 30 行）"
echo "   ----------------------------------------"
if [ -d "logs" ]; then
    LATEST_LOG=$(ls -t logs/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "   日志文件: $LATEST_LOG"
        echo ""
        grep -E "Worker|已启动|已在其他|通过文件锁" "$LATEST_LOG" 2>/dev/null | tail -30 | while read line; do
            echo "   $line"
        done
        echo ""
    else
        echo "   ℹ️  未找到日志文件"
    fi
else
    echo "   ℹ️  logs 目录不存在"
fi
echo ""

# 验证结果
echo "======================================================================"
echo "验证结果"
echo "======================================================================"
echo ""

if [ $active_locks -eq $total_locks ]; then
    echo "✅ 所有服务已正确启动（$active_locks/$total_locks）"
elif [ $active_locks -gt 0 ]; then
    echo "⚠️  部分服务已启动（$active_locks/$total_locks）"
else
    echo "ℹ️  服务未启动或已停止"
fi

echo ""
echo "预期结果（Gunicorn 多 Worker 环境）："
echo "  • 每个服务只有 1 个 Worker 启动"
echo "  • 其他 Worker 显示'已在其他 Worker 中运行，跳过'"
echo "  • 锁文件数量 = 已启动服务数量"
echo "  • 所有锁文件持有者 PID 相同（同一个 Worker）"
echo ""

echo "======================================================================"
echo "验证完成"
echo "======================================================================"