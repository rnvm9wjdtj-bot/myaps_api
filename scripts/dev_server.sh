#!/bin/bash
# =====================================================
# 开发环境服务启停脚本
# 用法:
#   ./dev_server.sh start   - 启动服务
#   ./dev_server.sh stop    - 停止服务
#   ./dev_server.sh restart - 重启服务
#   ./dev_server.sh status  - 查看状态
#   ./dev_server.sh logs    - 查看日志
# =====================================================

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# 查找Python解释器
find_python() {
    # 优先使用虚拟环境
    if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
        echo "$PROJECT_DIR/venv/bin/python"
        return
    fi
    # 尝试python3
    if command -v python3 &> /dev/null; then
        echo "python3"
        return
    fi
    # 尝试python
    if command -v python &> /dev/null; then
        echo "python"
        return
    fi
    echo "python3"
}

PYTHON_CMD=$(find_python)

# 配置
APP_NAME="myaps_api"
PID_FILE="$PROJECT_DIR/.dev_server.pid"
LOG_FILE="$PROJECT_DIR/logs/dev_server.log"
HOST="0.0.0.0"
PORT="8001"

# 创建日志目录
mkdir -p "$PROJECT_DIR/logs"

# 获取进程ID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        pgrep -f "python.*main\.py" | head -1 || pgrep -f "python3.*main\.py" | head -1
    fi
}

# 检查服务是否运行
is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

# 启动服务
start() {
    if is_running; then
        echo "服务已在运行中 (PID: $(get_pid))"
        return 1
    fi
    
    echo "正在启动服务..."
    echo "项目目录: $PROJECT_DIR"
    echo "Python解释器: $PYTHON_CMD"
    echo "访问地址: http://localhost:$PORT"
    echo "API文档: http://localhost:$PORT/docs"
    
    # 启动服务
    nohup env PORT=$PORT $PYTHON_CMD main.py > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"
    
    sleep 2
    
    if is_running; then
        echo "✓ 服务启动成功 (PID: $pid)"
        echo "日志文件: $LOG_FILE"
    else
        echo "✗ 服务启动失败，请查看日志:"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 停止服务
stop() {
    if ! is_running; then
        echo "服务未运行"
        rm -f "$PID_FILE"
        return 0
    fi
    
    local pid=$(get_pid)
    echo "正在停止服务 (PID: $pid)..."
    
    # 发送SIGTERM信号
    kill "$pid" 2>/dev/null
    
    # 等待进程结束
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    # 如果进程还在运行，强制结束
    if kill -0 "$pid" 2>/dev/null; then
        echo "强制结束进程..."
        kill -9 "$pid" 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    echo "✓ 服务已停止"
}

# 清除Python缓存
clear_cache() {
    echo "清除Python缓存..."
    find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null
    echo "✓ 缓存已清除"
}

# 重启服务
restart() {
    stop
    clear_cache
    sleep 1
    start
}

# 查看状态
status() {
    if is_running; then
        local pid=$(get_pid)
        echo "✓ 服务运行中"
        echo "  PID: $pid"
        echo "  访问地址: http://localhost:$PORT"
        echo "  API文档: http://localhost:$PORT/docs"
        
        # 显示进程信息
        if command -v ps &> /dev/null; then
            ps -p "$pid" -o pid,ppid,%cpu,%mem,etime,cmd 2>/dev/null || true
        fi
    else
        echo "✗ 服务未运行"
    fi
}

# 查看日志
logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "日志文件不存在: $LOG_FILE"
        return 1
    fi
    
    if [ "$1" = "-f" ] || [ "$1" = "--follow" ]; then
        echo "实时查看日志 (Ctrl+C 退出)..."
        tail -f "$LOG_FILE"
    else
        echo "最近50行日志:"
        tail -50 "$LOG_FILE"
    fi
}

# 帮助信息
help() {
    echo "用法: $0 {start|stop|restart|status|logs|clear_cache}"
    echo ""
    echo "命令:"
    echo "  start       - 启动服务"
    echo "  stop        - 停止服务"
    echo "  restart     - 重启服务（自动清除缓存）"
    echo "  status      - 查看服务状态"
    echo "  logs        - 查看日志 (添加 -f 参数实时查看)"
    echo "  clear_cache - 清除Python缓存"
    echo ""
    echo "示例:"
    echo "  $0 start"
    echo "  $0 restart"
    echo "  $0 logs -f"
}

# 主入口
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    clear_cache)
        clear_cache
        ;;
    -h|--help|help)
        help
        ;;
    *)
        echo "错误: 未知命令 '$1'"
        help
        exit 1
        ;;
esac
