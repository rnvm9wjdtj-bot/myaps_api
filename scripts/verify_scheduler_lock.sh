#!/bin/bash
# 验证调度器文件锁机制是否正常工作

echo "======================================================================"
echo "调度器文件锁机制验证脚本"
echo "======================================================================"
echo ""

# 检查锁文件
LOCK_FILE="/tmp/.myaps_scheduler.lock"
echo "1. 检查锁文件状态"
echo "   锁文件路径: $LOCK_FILE"
if [ -f "$LOCK_FILE" ]; then
    echo "   ✅ 锁文件存在"
    PID=$(cat "$LOCK_FILE")
    echo "   持有锁的进程 PID: $PID"
    
    # 检查进程是否存活
    if [ -d "/proc/$PID" ]; then
        echo "   ✅ 进程 $PID 正在运行"
        ps -p "$PID" -o pid,cmd --no-headers 2>/dev/null || echo "   进程信息: 无法获取"
    else
        echo "   ⚠️  进程 $PID 已死亡（废弃锁）"
    fi
else
    echo "   ℹ️  锁文件不存在（调度器未启动或已停止）"
fi
echo ""

# 检查运行中的调度器进程
echo "2. 检查运行中的调度器进程"
SCHEDULER_PIDS=$(ps aux | grep -E "python.*main|uvicorn|gunicorn" | grep -v grep | awk '{print $2}')
if [ -n "$SCHEDULER_PIDS" ]; then
    echo "   找到以下进程:"
    ps aux | grep -E "python.*main|uvicorn|gunicorn" | grep -v grep | while read line; do
        echo "   - $line"
    done
else
    echo "   ℹ️  未找到运行中的调度器进程"
fi
echo ""

# 检查环境变量
echo "3. 检查环境变量配置"
if [ -f ".env" ]; then
    echo "   TRUNON_SCHEDULER: $(grep '^TRUNON_SCHEDULER=' .env | cut -d'=' -f2)"
    echo "   WORKERS: $(grep '^WORKERS=' .env | cut -d'=' -f2)"
    echo "   SCHEDULER_HOUR: $(grep '^SCHEDULER_HOUR=' .env | cut -d'=' -f2)"
    echo "   SCHEDULER_MINUTE: $(grep '^SCHEDULER_MINUTE=' .env | cut -d'=' -f2)"
else
    echo "   ⚠️  .env 文件不存在"
fi
echo ""

# 检查最近的日志
echo "4. 检查最近的调度器日志（最近 20 行）"
if [ -d "logs" ]; then
    LATEST_LOG=$(ls -t logs/*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "   日志文件: $LATEST_LOG"
        echo "   ----------------------------------------"
        grep -E "定时任务|scheduler|task_confirm_workreport" "$LATEST_LOG" | tail -20 | while read line; do
            echo "   $line"
        done
        echo "   ----------------------------------------"
    else
        echo "   ℹ️  未找到日志文件"
    fi
else
    echo "   ℹ️  logs 目录不存在"
fi
echo ""

echo "======================================================================"
echo "验证完成"
echo "======================================================================"
echo ""
echo "预期结果："
echo "  ✅ 锁文件存在且持有锁的进程正在运行"
echo "  ✅ 日志中只有一个 Worker 启动了调度器"
echo "  ✅ 定时任务执行次数为 1 次（无重复）"
echo ""