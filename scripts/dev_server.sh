#!/bin/bash
# =====================================================
# 开发环境服务启停脚本（智能版）
# 用法:
#   ./dev_server.sh start   - 智能启动（自动检测并启动所需服务）
#   ./dev_server.sh stop    - 停止服务
#   ./dev_server.sh restart - 重启服务
#   ./dev_server.sh status  - 查看状态
#   ./dev_server.sh logs    - 查看日志
# =====================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# 查找Python解释器
find_python() {
    if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
        echo "$PROJECT_DIR/venv/bin/python"
        return
    fi
    if command -v python3 &> /dev/null; then
        echo "python3"
        return
    fi
    if command -v python &> /dev/null; then
        echo "python"
        return
    fi
    echo "python3"
}

PYTHON_CMD=$(find_python)

# 配置
APP_NAME="myaps_api"
PID_FILE="$PROJECT_DIR/storage/.dev_server.pid"
LOG_FILE="$PROJECT_DIR/logs/dev_server.log"
HOST="0.0.0.0"
PORT="8001"

# 创建必要目录
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/storage"

# =====================================================
# 智能服务检测与管理
# =====================================================

check_redis() {
    # 方式1: 检查Docker容器
    if command -v docker &> /dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'redis'; then
            return 0
        fi
    fi
    
    # 方式2: 检查进程
    if pgrep -x "redis-server" > /dev/null 2>&1; then
        if redis-cli ping > /dev/null 2>&1; then
            return 0
        fi
    fi
    
    # 方式3: 检查端口
    if command -v nc &> /dev/null; then
        if nc -z localhost 6379 2>/dev/null; then
            return 0
        fi
    fi
    
    return 1
}

check_postgresql() {
    # 方式1: 检查Docker容器
    if command -v docker &> /dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'postgres'; then
            return 0
        fi
    fi
    
    # 方式2: 检查进程
    if pgrep -x "postgres" > /dev/null 2>&1; then
        if pg_isready > /dev/null 2>&1; then
            return 0
        fi
    fi
    
    # 方式3: 检查端口
    if command -v nc &> /dev/null; then
        if nc -z localhost 5432 2>/dev/null; then
            return 0
        fi
    fi
    
    return 1
}

check_app() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

start_redis() {
    echo -e "${BLUE}[Redis]${NC} 检查服务状态..."
    
    if check_redis; then
        echo -e "${GREEN}[Redis]${NC} ✓ 已在运行"
        # 显示运行方式
        if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'redis'; then
            local container=$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'redis' | head -1)
            echo -e "${GREEN}[Redis]${NC}   容器: $container"
        fi
        return 0
    fi
    
    echo -e "${YELLOW}[Redis]${NC} 服务未运行，正在启动..."
    
    # 优先尝试Docker方式
    if command -v docker &> /dev/null; then
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q 'redis'; then
            local container=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep 'redis' | head -1)
            echo -e "${BLUE}[Redis]${NC} 启动Docker容器: $container"
            docker start "$container" 2>/dev/null && sleep 2
            if check_redis; then
                echo -e "${GREEN}[Redis]${NC} ✓ 启动成功 (Docker)"
                return 0
            fi
        fi
    fi
    
    # 尝试直接启动
    if ! command -v redis-server &> /dev/null; then
        echo -e "${RED}[Redis]${NC} ✗ 未安装 redis-server"
        echo -e "${YELLOW}[Redis]${NC}   请执行: sudo apt install redis-server"
        echo -e "${YELLOW}[Redis]${NC}   或使用Docker: docker run -d --name redis -p 6379:6379 redis"
        return 1
    fi
    
    redis-server --daemonize yes 2>/dev/null
    
    local count=0
    while ! check_redis && [ $count -lt 10 ]; do
        sleep 0.5
        count=$((count + 1))
    done
    
    if check_redis; then
        echo -e "${GREEN}[Redis]${NC} ✓ 启动成功"
        return 0
    else
        echo -e "${RED}[Redis]${NC} ✗ 启动失败"
        return 1
    fi
}

start_postgresql() {
    echo -e "${BLUE}[PostgreSQL]${NC} 检查服务状态..."
    
    if check_postgresql; then
        echo -e "${GREEN}[PostgreSQL]${NC} ✓ 已在运行"
        # 显示运行方式
        if command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'postgres'; then
            local container=$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'postgres' | head -1)
            echo -e "${GREEN}[PostgreSQL]${NC}   容器: $container"
        fi
        return 0
    fi
    
    echo -e "${YELLOW}[PostgreSQL]${NC} 服务未运行，正在启动..."
    
    # 优先尝试Docker方式
    if command -v docker &> /dev/null; then
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q 'postgres'; then
            local container=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep 'postgres' | head -1)
            echo -e "${BLUE}[PostgreSQL]${NC} 启动Docker容器: $container"
            docker start "$container" 2>/dev/null && sleep 2
            if check_postgresql; then
                echo -e "${GREEN}[PostgreSQL]${NC} ✓ 启动成功 (Docker)"
                return 0
            fi
        fi
    fi
    
    # 尝试直接启动
    if ! command -v pg_isready &> /dev/null; then
        echo -e "${RED}[PostgreSQL]${NC} ✗ 未安装 PostgreSQL"
        echo -e "${YELLOW}[PostgreSQL]${NC}   请执行: sudo apt install postgresql postgresql-contrib"
        echo -e "${YELLOW}[PostgreSQL]${NC}   或使用Docker: docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres"
        return 1
    fi
    
    sudo service postgresql start 2>/dev/null || true
    
    local count=0
    while ! check_postgresql && [ $count -lt 15 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    if check_postgresql; then
        echo -e "${GREEN}[PostgreSQL]${NC} ✓ 启动成功"
        return 0
    else
        echo -e "${RED}[PostgreSQL]${NC} ✗ 启动失败"
        return 1
    fi
}

ensure_services() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}检查基础服务...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    local redis_ok=true
    local pg_ok=true
    
    start_redis || redis_ok=false
    start_postgresql || pg_ok=false
    
    echo ""
    
    if [ "$redis_ok" = false ] || [ "$pg_ok" = false ]; then
        echo -e "${RED}部分基础服务启动失败，应用可能无法正常工作${NC}"
        echo -e "${YELLOW}是否继续启动应用？[y/N]${NC}"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "已取消启动"
            exit 1
        fi
    fi
}

# =====================================================
# 应用服务管理
# =====================================================

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return
        fi
    fi
    pgrep -f "python.*main\.py" | head -1 || true
}

start_app() {
    if check_app; then
        echo -e "${GREEN}[应用]${NC} ✓ 已在运行 (PID: $(get_pid))"
        echo -e "${GREEN}[应用]${NC}   访问地址: http://localhost:$PORT"
        echo -e "${GREEN}[应用]${NC}   API文档: http://localhost:$PORT/docs"
        return 0
    fi
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}启动应用服务...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  项目目录: $PROJECT_DIR"
    echo -e "  Python: $PYTHON_CMD"
    echo -e "  端口: $PORT"
    echo ""
    
    nohup env PORT=$PORT $PYTHON_CMD main.py > "$LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$PID_FILE"
    
    sleep 2
    
    if check_app; then
        echo -e "${GREEN}[应用]${NC} ✓ 启动成功 (PID: $pid)"
        echo -e "${GREEN}[应用]${NC}   访问地址: http://localhost:$PORT"
        echo -e "${GREEN}[应用]${NC}   API文档: http://localhost:$PORT/docs"
        echo -e "${GREEN}[应用]${NC}   日志文件: $LOG_FILE"
        return 0
    else
        echo -e "${RED}[应用]${NC} ✗ 启动失败"
        echo -e "${YELLOW}[应用]${NC} 最近日志:"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_app() {
    if ! check_app; then
        echo -e "${YELLOW}[应用]${NC} 服务未运行"
        rm -f "$PID_FILE"
        return 0
    fi
    
    local pid=$(get_pid)
    echo -e "${YELLOW}[应用]${NC} 正在停止 (PID: $pid)..."
    
    kill "$pid" 2>/dev/null
    
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done
    
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}[应用]${NC} 强制结束..."
        kill -9 "$pid" 2>/dev/null
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}[应用]${NC} ✓ 已停止"
}

clear_cache() {
    echo -e "${YELLOW}清除Python缓存...${NC}"
    find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}✓ 缓存已清除${NC}"
}

# =====================================================
# 主命令
# =====================================================

cmd_start() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}MyAPS API 开发服务器${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    ensure_services
    echo ""
    start_app
}

cmd_stop() {
    echo -e "${BLUE}停止服务...${NC}"
    stop_app
}

cmd_restart() {
    cmd_stop
    clear_cache
    sleep 1
    cmd_start
}

cmd_status() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}服务状态${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    echo ""
    echo -e "${BLUE}[Redis]${NC}"
    if check_redis; then
        echo -e "  状态: ${GREEN}运行中${NC}"
        # 显示运行方式
        if command -v docker &> /dev/null; then
            local redis_container=$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'redis' | head -1)
            if [ -n "$redis_container" ]; then
                echo -e "  方式: ${GREEN}Docker容器${NC} ($redis_container)"
                docker ps --filter "name=$redis_container" --format "  镜像: {{.Image}}\n  端口: {{.Ports}}" 2>/dev/null || true
            else
                echo -e "  方式: ${GREEN}宿主机服务${NC}"
                # 显示主进程信息
                local redis_main_pid=$(pgrep -x redis-server | head -1)
                if [ -n "$redis_main_pid" ]; then
                    local redis_cmd=$(cat /proc/$redis_main_pid/cmdline 2>/dev/null | tr '\0' ' ')
                    echo -e "  PID: $redis_main_pid"
                    # 显示监听地址
                    local redis_bind=$(echo "$redis_cmd" | grep -oP '\-\-bind\s+\K[^\s]+' | head -1)
                    local redis_port=$(echo "$redis_cmd" | grep -oP '\-\-port\s+\K[^\s]+' | head -1)
                    [ -z "$redis_bind" ] && redis_bind="*"
                    [ -z "$redis_port" ] && redis_port="6379"
                    echo -e "  监听: $redis_bind:$redis_port"
                fi
            fi
        fi
        if command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null; then
            local redis_version=$(redis-cli INFO server 2>/dev/null | grep "redis_version" | cut -d: -f2 | tr -d '\r')
            local redis_used_memory=$(redis-cli INFO memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
            local redis_connected=$(redis-cli INFO clients 2>/dev/null | grep "connected_clients" | cut -d: -f2 | tr -d '\r')
            [ -n "$redis_version" ] && echo -e "  版本: $redis_version"
            [ -n "$redis_used_memory" ] && echo -e "  内存: $redis_used_memory"
            [ -n "$redis_connected" ] && echo -e "  连接: $redis_connected clients"
        fi
    else
        echo -e "  状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    echo -e "${BLUE}[PostgreSQL]${NC}"
    if check_postgresql; then
        echo -e "  状态: ${GREEN}运行中${NC}"
        # 显示运行方式
        if command -v docker &> /dev/null; then
            local pg_container=$(docker ps --format '{{.Names}}' 2>/dev/null | grep 'postgres' | head -1)
            if [ -n "$pg_container" ]; then
                echo -e "  方式: ${GREEN}Docker容器${NC} ($pg_container)"
                docker ps --filter "name=$pg_container" --format "  镜像: {{.Image}}\n  端口: {{.Ports}}" 2>/dev/null || true
            else
                echo -e "  方式: ${GREEN}宿主机服务${NC}"
                # 显示版本和数据目录
                if command -v psql &> /dev/null; then
                    local pg_version=$(psql --version 2>/dev/null | grep -oE '[0-9]+' | head -1)
                    [ -n "$pg_version" ] && echo -e "  版本: PostgreSQL $pg_version"
                fi
                # 显示主进程信息
                local pg_main_pid=$(pgrep -x postgres | head -1)
                if [ -n "$pg_main_pid" ]; then
                    local pg_cmd=$(cat /proc/$pg_main_pid/cmdline 2>/dev/null | tr '\0' ' ')
                    # 提取数据目录
                    local pg_data=$(echo "$pg_cmd" | grep -oP '\-D\s+\K[^\s]+' | head -1)
                    local pg_config=$(echo "$pg_cmd" | grep -oP 'config_file=\K[^\s]+' | head -1)
                    [ -n "$pg_data" ] && echo -e "  数据: $pg_data"
                    [ -n "$pg_config" ] && echo -e "  配置: $pg_config"
                fi
                # 显示连接数
                if command -v psql &> /dev/null; then
                    local pg_connections=$(psql -U postgres -t -c "SELECT count(*) FROM pg_stat_activity WHERE state='active';" 2>/dev/null | xargs)
                    [ -n "$pg_connections" ] && echo -e "  连接: $pg_connections active"
                fi
            fi
        fi
        if command -v pg_isready &> /dev/null; then
            local pg_ready=$(pg_isready 2>/dev/null)
            echo -e "  ${GREEN}$pg_ready${NC}"
        fi
    else
        echo -e "  状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    echo -e "${BLUE}[应用服务]${NC}"
    if check_app; then
        local pid=$(get_pid)
        echo -e "  状态: ${GREEN}运行中${NC}"
        echo -e "  PID: $pid"
        echo -e "  访问地址: http://localhost:$PORT"
        echo -e "  API文档: http://localhost:$PORT/docs"
        if command -v ps &> /dev/null; then
            ps -p "$pid" -o pid,ppid,%cpu,%mem,etime 2>/dev/null || true
        fi
    else
        echo -e "  状态: ${RED}未运行${NC}"
    fi
    
    echo ""
}

cmd_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}日志文件不存在: $LOG_FILE${NC}"
        return 1
    fi
    
    if [ "$1" = "-f" ] || [ "$1" = "--follow" ]; then
        echo -e "${BLUE}实时查看日志 (Ctrl+C 退出)...${NC}"
        tail -f "$LOG_FILE"
    else
        echo -e "${BLUE}最近50行日志:${NC}"
        tail -50 "$LOG_FILE"
    fi
}

help() {
    echo -e "${BLUE}用法:${NC} $0 {start|stop|restart|status|logs|clear_cache}"
    echo ""
    echo -e "${BLUE}命令:${NC}"
    echo "  start       - 智能启动（自动检测并启动 Redis/PostgreSQL/应用）"
    echo "  stop        - 停止应用服务"
    echo "  restart     - 重启应用服务（自动清除缓存）"
    echo "  status      - 查看所有服务状态"
    echo "  logs        - 查看日志 (添加 -f 参数实时查看)"
    echo "  clear_cache - 清除Python缓存"
    echo ""
    echo -e "${BLUE}示例:${NC}"
    echo "  $0 start          # 一键启动所有服务"
    echo "  $0 restart        # 重启应用"
    echo "  $0 logs -f        # 实时查看日志"
    echo "  $0 status         # 查看所有服务状态"
}

case "$1" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs "$2"
        ;;
    clear_cache)
        clear_cache
        ;;
    -h|--help|help)
        help
        ;;
    *)
        echo -e "${RED}错误: 未知命令 '$1'${NC}"
        help
        exit 1
        ;;
esac
