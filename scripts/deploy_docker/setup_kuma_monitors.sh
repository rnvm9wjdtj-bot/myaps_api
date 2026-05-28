#!/bin/bash
# ==============================================
# Uptime Kuma 监控配置一键安装脚本
# 使用方法: ./setup_kuma_monitors.sh
# 功能: 自动配置7个监控项到Uptime Kuma
# ==============================================

set -e

# 配置
CONTAINER_NAME="myaps_uptime_kuma"
KUMA_DB="/app/data/kuma.db"
TEMP_SQL="/tmp/kuma_monitors_$$.sql"
ENV_FILE="../.env"

# 从.env文件读取数据库和端口配置
read_env_config() {
    if [ -f "$ENV_FILE" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                MYAPS_DB_HOST) MYAPS_DB_HOST="$value" ;;
                MYAPS_DB_PORT) MYAPS_DB_PORT="$value" ;;
                REDIS_PORT) REDIS_PORT="$value" ;;
                THIS_DB_PORT) THIS_DB_PORT="$value" ;;
                PORTAINER_PORT) PORTAINER_PORT="$value" ;;
                UPTIME_KUMA_PORT) UPTIME_KUMA_PORT="$value" ;;
                PORT) APP_PORT="$value" ;;
            esac
        done < "$ENV_FILE"
    fi

    MYAPS_DB_HOST=${MYAPS_DB_HOST:-1.13.184.21}
    MYAPS_DB_PORT=${MYAPS_DB_PORT:-3333}
    REDIS_PORT=${REDIS_PORT:-6379}
    THIS_DB_PORT=${THIS_DB_PORT:-5432}
    PORTAINER_PORT=${PORTAINER_PORT:-9000}
    UPTIME_KUMA_PORT=${UPTIME_KUMA_PORT:-3001}
    APP_PORT=${APP_PORT:-8000}
}

# 读取环境变量
read_env_config

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 清理函数
cleanup() {
    rm -f "$TEMP_SQL" 2>/dev/null || true
    docker exec "$CONTAINER_NAME" rm -f "$TEMP_SQL" 2>/dev/null || true
}
trap cleanup EXIT

# 显示帮助
show_help() {
    echo "Uptime Kuma 监控配置一键安装脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --help, -h      显示此帮助信息"
    echo "  --list, -l      显示监控配置列表"
    echo "  --dry-run, -n   仅显示将要执行的操作，不实际执行"
    echo "  --container, -c 指定容器名称 (默认: $CONTAINER_NAME)"
    echo ""
    echo "监控配置列表:"
    echo "  1. MyAPI服务        - HTTP http://localhost:${APP_PORT}/docs"
    echo "  2. Redis            - Port localhost:${REDIS_PORT}"
    echo "  3. PostgreSQL       - Port localhost:${THIS_DB_PORT}"
    echo "  4. Portainer        - HTTP http://localhost:${PORTAINER_PORT}"
    echo "  5. Binlog监听器     - HTTP http://localhost:${APP_PORT}/monitor/api/binlog-listener"
    echo "  6. Uptime Kuma      - HTTP http://localhost:${UPTIME_KUMA_PORT}"
    echo "  7. MyAPS数据库      - Port ${MYAPS_DB_HOST}:${MYAPS_DB_PORT} (从.env读取)"
}

# 生成SQL内容（幂等性保证）
generate_sql() {
    cat > "$TEMP_SQL" << EOF
-- 先删除已存在的同名监控（幂等性保证）
DELETE FROM monitor WHERE name IN ('MyAPI服务', 'Redis', 'PostgreSQL', 'Portainer', 'Binlog监听器', 'Uptime Kuma', 'MyAPS数据库');

-- 插入监控配置
INSERT INTO monitor (name, type, url, interval, maxretries, active, user_id, created_date, keyword)
SELECT 'MyAPI服务', 'http', 'http://localhost:${APP_PORT}/docs', 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now'), NULL;

INSERT INTO monitor (name, type, hostname, port, interval, maxretries, active, user_id, created_date)
SELECT 'Redis', 'port', 'localhost', ${REDIS_PORT}, 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now');

INSERT INTO monitor (name, type, hostname, port, interval, maxretries, active, user_id, created_date)
SELECT 'PostgreSQL', 'port', 'localhost', ${THIS_DB_PORT}, 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now');

INSERT INTO monitor (name, type, url, interval, maxretries, active, user_id, created_date, keyword)
SELECT 'Portainer', 'http', 'http://localhost:${PORTAINER_PORT}', 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now'), NULL;

INSERT INTO monitor (name, type, url, interval, maxretries, active, user_id, created_date, keyword)
SELECT 'Binlog监听器', 'http', 'http://localhost:${APP_PORT}/monitor/api/binlog-listener', 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now'), '"healthy": true';

INSERT INTO monitor (name, type, url, interval, maxretries, active, user_id, created_date, keyword)
SELECT 'Uptime Kuma', 'http', 'http://localhost:${UPTIME_KUMA_PORT}', 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now'), NULL;

INSERT INTO monitor (name, type, hostname, port, interval, maxretries, active, user_id, created_date)
SELECT 'MyAPS数据库', 'port', '$MYAPS_DB_HOST', $MYAPS_DB_PORT, 60, 3, 1, (SELECT id FROM user LIMIT 1), datetime('now');

SELECT '本次执行添加 ' || changes() || ' 条监控记录' AS result;
EOF
}

# 解析参数
DRY_RUN=false
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --list|-l)
            LIST_ONLY=true
            ;;
        --dry-run|-n)
            DRY_RUN=true
            ;;
        --container|-c)
            CONTAINER_NAME="$2"
            shift
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

# 如果只显示列表
if $LIST_ONLY; then
    show_help
    exit 0
fi

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}  Uptime Kuma 监控配置一键安装脚本${NC}"
echo -e "${BLUE}==============================================${NC}"

# 1. 检查容器是否存在
echo -e "\n${YELLOW}🔍 检查Uptime Kuma容器状态...${NC}"
if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
    echo -e "${RED}❌ 错误: 容器 $CONTAINER_NAME 不存在${NC}"
    echo -e "${RED}   请先启动Uptime Kuma容器${NC}"
    exit 1
fi

# 检查容器是否运行
CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME")
if [ "$CONTAINER_STATUS" != "running" ]; then
    if $DRY_RUN; then
        echo -e "${YELLOW}⚠️  [模拟] 容器未运行，将启动...${NC}"
    else
        echo -e "${YELLOW}⚠️  容器未运行，正在启动...${NC}"
        docker start "$CONTAINER_NAME"
        sleep 5
    fi
fi

echo -e "${GREEN}✅ 容器 $CONTAINER_NAME 运行正常${NC}"

# 2. 生成SQL脚本
echo -e "\n${YELLOW}📝 生成SQL脚本...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] 将生成7条监控配置的SQL${NC}"
else
    generate_sql
    echo -e "${GREEN}✅ SQL脚本生成成功${NC}"
fi

# 3. 复制SQL脚本到容器
echo -e "\n${YELLOW}📤 复制SQL脚本到容器...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] docker cp $TEMP_SQL $CONTAINER_NAME:$TEMP_SQL${NC}"
else
    docker cp "$TEMP_SQL" "$CONTAINER_NAME":"$TEMP_SQL"
    echo -e "${GREEN}✅ SQL脚本已复制到容器${NC}"
fi

# 4. 在容器内执行SQL
echo -e "\n${YELLOW}⚙️  在容器内执行SQL导入...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] docker exec -i $CONTAINER_NAME sqlite3 $KUMA_DB < $TEMP_SQL${NC}"
else
    echo -e "${BLUE}   执行命令: docker exec -i $CONTAINER_NAME sqlite3 $KUMA_DB < $TEMP_SQL${NC}"
    cat "$TEMP_SQL" | docker exec -i "$CONTAINER_NAME" sqlite3 "$KUMA_DB"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✅ SQL导入成功${NC}"
    else
        echo -e "${RED}❌ SQL导入失败 (退出码: $EXIT_CODE)${NC}"
        exit 1
    fi
fi

# 5. 清理临时文件
echo -e "\n${YELLOW}🧹 清理临时文件...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] rm -f $TEMP_SQL${NC}"
else
    cleanup
    echo -e "${GREEN}✅ 清理完成${NC}"
fi

# 6. 检查导入结果
echo -e "\n${YELLOW}📊 检查监控配置...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] docker exec $CONTAINER_NAME sqlite3 $KUMA_DB 'SELECT COUNT(*) FROM monitor;'${NC}"
else
    RESULT=$(docker exec "$CONTAINER_NAME" sqlite3 "$KUMA_DB" "SELECT COUNT(*) FROM monitor;")
    echo -e "${GREEN}✅ 当前监控数量: $RESULT 个${NC}"
fi

echo -e "\n${BLUE}==============================================${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}⚠️  模拟完成，未执行实际操作${NC}"
else
    echo -e "${GREEN}🎉 监控配置导入完成！${NC}"
fi
echo -e "${BLUE}==============================================${NC}"
echo -e "\n${YELLOW}💡 访问地址: http://localhost:3001${NC}"
echo -e "${YELLOW}   查看已添加的7个监控项${NC}"
