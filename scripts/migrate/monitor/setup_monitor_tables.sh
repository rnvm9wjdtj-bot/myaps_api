#!/bin/bash
# ==============================================
# 监控模块数据库一键建表脚本
# 使用方法: ./setup_monitor_tables.sh [选项]
# 功能: 向MyAPS API容器的SQLite数据库执行建表脚本
# ==============================================

set -e

# 配置
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SQL_FILE="${SCRIPT_DIR}/monitor_tables.sql"
ENV_FILE="${SCRIPT_DIR}/../../../.env"
CONTAINER_NAME="myaps_api"
STORAGE_DIR="/app/storage"

# 默认数据库名
SQLITE_FILE="local_data"

# 从.env文件读取配置
read_env_config() {
    if [ -f "$ENV_FILE" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                SQLITE_FILE)
                    if [ -n "$value" ]; then
                        SQLITE_FILE="$value"
                    fi
                    ;;
            esac
        done < "$ENV_FILE"
    fi
    
    # 移除.sqlite3后缀
    SQLITE_FILE="${SQLITE_FILE%.sqlite3}"
}

# 显示帮助
show_help() {
    echo "监控模块数据库一键建表脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --help, -h      显示此帮助信息"
    echo "  --db, -d        指定SQLite数据库文件名（不含.sqlite3后缀）"
    echo "  --container, -c 指定MyAPS API容器名称 (默认: $CONTAINER_NAME)"
    echo "  --dry-run, -n   仅显示将要执行的操作，不实际执行"
    echo "  --local, -l     在本地直接执行（不通过容器）"
    echo ""
    echo "示例:"
    echo "  # 使用默认配置"
    echo "  ./setup_monitor_tables.sh"
    echo ""
    echo "  # 指定数据库文件名"
    echo "  ./setup_monitor_tables.sh -d my_data"
    echo ""
    echo "  # 指定容器名称"
    echo "  ./setup_monitor_tables.sh -c my_api_container"
    echo ""
    echo "  # 本地执行（开发环境）"
    echo "  ./setup_monitor_tables.sh -l"
}

# 解析参数
DRY_RUN=false
LOCAL_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --db|-d)
            SQLITE_FILE="$2"
            shift
            ;;
        --container|-c)
            CONTAINER_NAME="$2"
            shift
            ;;
        --dry-run|-n)
            DRY_RUN=true
            ;;
        --local|-l)
            LOCAL_MODE=true
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
    shift
done

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 读取环境变量
read_env_config

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}  监控模块数据库一键建表脚本${NC}"
echo -e "${BLUE}==============================================${NC}"

# 1. 检查SQL文件是否存在
echo -e "\n${YELLOW}🔍 检查SQL文件...${NC}"
if [ ! -f "$SQL_FILE" ]; then
    echo -e "${RED}❌ 错误: SQL文件不存在 - $SQL_FILE${NC}"
    exit 1
fi
echo -e "${GREEN}✅ SQL文件存在: $SQL_FILE${NC}"

if [ "$LOCAL_MODE" = true ]; then
    # 本地模式执行
    echo -e "\n${YELLOW}⚙️  本地模式执行...${NC}"
    
    DB_PATH="${SCRIPT_DIR}/../../../storage/${SQLITE_FILE}.sqlite3"
    echo -e "${BLUE}   数据库文件: ${DB_PATH}${NC}"
    
    if $DRY_RUN; then
        echo -e "${YELLOW}   [模拟] sqlite3 ${DB_PATH} < ${SQL_FILE}${NC}"
    else
        # 确保storage目录存在
        mkdir -p "$(dirname "$DB_PATH")"
        
        # 执行SQL脚本
        echo -e "${YELLOW}   执行SQL脚本...${NC}"
        sqlite3 "$DB_PATH" < "$SQL_FILE"
        
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}✅ 建表成功${NC}"
        else
            echo -e "${RED}❌ 建表失败 (退出码: $EXIT_CODE)${NC}"
            exit 1
        fi
    fi
else
    # 容器模式执行
    # 2. 检查容器是否存在
    echo -e "\n${YELLOW}🔍 检查MyAPS API容器状态...${NC}"
    if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
        echo -e "${RED}❌ 错误: 容器 $CONTAINER_NAME 不存在${NC}"
        echo -e "${RED}   请先启动MyAPS API容器${NC}"
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

    # 3. 执行建表
    echo -e "\n${YELLOW}⚙️  执行建表脚本...${NC}"
    echo -e "${BLUE}   数据库文件: ${STORAGE_DIR}/${SQLITE_FILE}.sqlite3${NC}"

    if $DRY_RUN; then
        echo -e "${YELLOW}   [模拟] docker cp ${SQL_FILE} ${CONTAINER_NAME}:/tmp/monitor_tables.sql${NC}"
        echo -e "${YELLOW}   [模拟] docker exec ${CONTAINER_NAME} sqlite3 ${STORAGE_DIR}/${SQLITE_FILE}.sqlite3 < /tmp/monitor_tables.sql${NC}"
    else
        # 复制SQL文件到容器
        echo -e "${YELLOW}   复制SQL文件到容器...${NC}"
        docker cp "$SQL_FILE" "$CONTAINER_NAME":/tmp/monitor_tables.sql
        
        # 执行建表脚本
        echo -e "${YELLOW}   执行SQL脚本...${NC}"
        docker exec "$CONTAINER_NAME" sqlite3 "${STORAGE_DIR}/${SQLITE_FILE}.sqlite3" < /tmp/monitor_tables.sql
        
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}✅ 建表成功${NC}"
        else
            echo -e "${RED}❌ 建表失败 (退出码: $EXIT_CODE)${NC}"
            exit 1
        fi
        
        # 清理容器内的临时文件
        docker exec "$CONTAINER_NAME" rm -f /tmp/monitor_tables.sql
    fi
fi

# 4. 验证结果
echo -e "\n${YELLOW}📊 验证建表结果...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] 验证表是否创建成功${NC}"
else
    if [ "$LOCAL_MODE" = true ]; then
        TABLES=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    else
        TABLES=$(docker exec "$CONTAINER_NAME" sqlite3 "${STORAGE_DIR}/${SQLITE_FILE}.sqlite3" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    fi
    
    echo -e "${GREEN}✅ 创建的表:${NC}"
    echo "$TABLES" | while read -r table; do
        if [ -n "$table" ]; then
            echo -e "   - $table"
        fi
    done
    
    # 检查版本记录
    if [ "$LOCAL_MODE" = true ]; then
        VERSION=$(sqlite3 "$DB_PATH" "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;")
    else
        VERSION=$(docker exec "$CONTAINER_NAME" sqlite3 "${STORAGE_DIR}/${SQLITE_FILE}.sqlite3" "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;")
    fi
    if [ -n "$VERSION" ]; then
        echo -e "\n${GREEN}✅ 版本记录: $VERSION${NC}"
    fi
fi

echo -e "\n${BLUE}==============================================${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}⚠️  模拟完成，未执行实际操作${NC}"
else
    echo -e "${GREEN}🎉 建表完成！${NC}"
fi
echo -e "${BLUE}==============================================${NC}"
echo -e "\n${YELLOW}💡 验证命令:${NC}"
if [ "$LOCAL_MODE" = true ]; then
    echo -e "${YELLOW}   sqlite3 ${DB_PATH}${NC}"
else
    echo -e "${YELLOW}   docker exec -it ${CONTAINER_NAME} sqlite3 ${STORAGE_DIR}/${SQLITE_FILE}.sqlite3${NC}"
fi
echo -e "${YELLOW}   SELECT * FROM schema_version;${NC}"