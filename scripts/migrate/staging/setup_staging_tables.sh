#!/bin/bash
# ==============================================
# PostgreSQL 缓冲表一键建表脚本
# 使用方法: ./setup_staging_tables.sh [选项]
# 功能: 向PostgreSQL容器执行建表SQL脚本
# ==============================================

set -e

# 配置
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SQL_FILE="${SCRIPT_DIR}/staging_tables.sql"
ENV_FILE="${SCRIPT_DIR}/../../../.env"
CONTAINER_NAME="myaps_postgres"

# 默认数据库名
DB_NAME=""

# 从.env文件读取数据库配置
read_env_config() {
    if [ -f "$ENV_FILE" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                THIS_DB_HOST) DB_HOST="$value" ;;
                THIS_DB_PORT) DB_PORT="$value" ;;
                THIS_DB_USER) DB_USER="$value" ;;
                THIS_DB_PASSWORD) DB_PASSWORD="$value" ;;
                THIS_DB_NAME) DB_NAME="$value" ;;
            esac
        done < "$ENV_FILE"
    fi
    
    # 设置默认值
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_USER=${DB_USER:-postgres}
}

# 显示帮助
show_help() {
    echo "PostgreSQL 缓冲表一键建表脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --help, -h      显示此帮助信息"
    echo "  --db, -d        指定数据库名称（必填）"
    echo "  --container, -c 指定PostgreSQL容器名称 (默认: $CONTAINER_NAME)"
    echo "  --dry-run, -n   仅显示将要执行的操作，不实际执行"
    echo "  --local, -l     在本地直接执行（不通过容器）"
    echo ""
    echo "示例:"
    echo "  # 使用默认配置"
    echo "  ./setup_staging_tables.sh -d myaps_db"
    echo ""
    echo "  # 指定容器名称"
    echo "  ./setup_staging_tables.sh -d myaps_db -c my_postgres"
    echo ""
    echo "  # 本地执行（开发环境）"
    echo "  ./setup_staging_tables.sh -d myaps_db -l"
    echo ""
    echo "  # 模拟执行"
    echo "  ./setup_staging_tables.sh -d myaps_db -n"
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
            DB_NAME="$2"
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

# 读取环境变量（优先使用命令行参数，env文件作兜底）
read_env_config

# 检查数据库名称是否指定
if [ -z "$DB_NAME" ]; then
    echo -e "${RED}❌ 错误: 必须使用 -d 指定数据库名称${NC}"
    show_help
    exit 1
fi

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE}  PostgreSQL 缓冲表一键建表脚本${NC}"
echo -e "${BLUE}==============================================${NC}"

# 1. 检查SQL文件是否存在
echo -e "\n${YELLOW}🔍 检查SQL文件...${NC}"
if [ ! -f "$SQL_FILE" ]; then
    echo -e "${RED}❌ 错误: SQL文件不存在 - $SQL_FILE${NC}"
    exit 1
fi
echo -e "${GREEN}✅ SQL文件存在: $SQL_FILE${NC}"

exec_sql_container() {
    local db="$1"
    if ! docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1; then
        echo -e "${YELLOW}   数据库不存在，创建数据库...${NC}"
        docker exec "$CONTAINER_NAME" createdb -U "$DB_USER" "$db"
    fi
    echo -e "${YELLOW}   执行SQL脚本...${NC}"
    cat "$SQL_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$db"
    return $?
}

exec_sql_local() {
    local db="$1"
    export PGPASSWORD="$DB_PASSWORD"
    if ! command -v psql &>/dev/null; then
        echo -e "${RED}❌ 错误: 未找到psql客户端${NC}"
        echo -e "${YELLOW}   请安装postgresql-client或使用Docker模式${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}   尝试连接PostgreSQL...${NC}"
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc "SELECT 1" 2>/dev/null | grep -q 1; then
        echo -e "${RED}❌ 错误: 无法连接到PostgreSQL服务器${NC}"
        echo -e "${YELLOW}   服务器: ${DB_HOST}:${DB_PORT}, 用户: ${DB_USER}${NC}"
        return 1
    fi
    
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" 2>/dev/null | grep -q 1; then
        echo -e "${YELLOW}   数据库不存在，创建数据库...${NC}"
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -c "CREATE DATABASE $db" 2>/dev/null
    fi
    echo -e "${YELLOW}   执行SQL脚本...${NC}"
    cat "$SQL_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$db"
    return $?
}

verify_tables_container() {
    local db="$1"
    TABLES=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$db" -tAc "SELECT tablename FROM pg_tables WHERE tablename LIKE '%staging' OR tablename IN ('t_validation_error', 't_transform_rule', 't_schema_version') ORDER BY tablename;")
    VERSION=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$db" -tAc "SELECT version FROM t_schema_version ORDER BY applied_at DESC LIMIT 1;")
}

verify_tables_local() {
    local db="$1"
    export PGPASSWORD="$DB_PASSWORD"
    TABLES=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$db" -tAc "SELECT tablename FROM pg_tables WHERE tablename LIKE '%staging' OR tablename IN ('t_validation_error', 't_transform_rule', 't_schema_version') ORDER BY tablename;" 2>/dev/null)
    VERSION=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$db" -tAc "SELECT version FROM t_schema_version ORDER BY applied_at DESC LIMIT 1;" 2>/dev/null)
}

# 检查Docker权限
check_docker_access() {
    if docker info &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# 自动检测运行中的PostgreSQL容器
find_postgres_container() {
    # 首先检查Docker权限
    if ! check_docker_access; then
        return 1
    fi
    
    # 查找运行中的postgres容器
    local pg_container=$(docker ps --filter "ancestor=postgres" --format "{{.Names}}" 2>/dev/null | head -1)
    if [ -n "$pg_container" ]; then
        echo "$pg_container"
        return 0
    fi
    # 尝试其他方式查找
    pg_container=$(docker ps --filter "name=postgres" --format "{{.Names}}" 2>/dev/null | head -1)
    if [ -n "$pg_container" ]; then
        echo "$pg_container"
        return 0
    fi
    # 查找包含postgres的容器
    pg_container=$(docker ps --filter "name=*postgres*" --format "{{.Names}}" 2>/dev/null | head -1)
    if [ -n "$pg_container" ]; then
        echo "$pg_container"
        return 0
    fi
    return 1
}

# 2. 检查容器是否存在并决定执行模式
echo -e "\n${YELLOW}🔍 检查PostgreSQL容器状态...${NC}"
AUTO_LOCAL=false

# 先检查Docker权限
if ! check_docker_access; then
    echo -e "${YELLOW}⚠️  Docker权限不足${NC}"
    echo -e "${YELLOW}   请使用 sudo 运行脚本或检查Docker配置${NC}"
    echo -e "${YELLOW}   尝试本地模式...${NC}"
    AUTO_LOCAL=true
    LOCAL_MODE=true
else
    if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
        echo -e "${YELLOW}⚠️  配置的容器 $CONTAINER_NAME 不存在${NC}"
        # 尝试自动检测PostgreSQL容器
        DETECTED_CONTAINER=$(find_postgres_container)
        if [ -n "$DETECTED_CONTAINER" ]; then
            echo -e "${GREEN}✅ 自动检测到运行中的PostgreSQL容器: $DETECTED_CONTAINER${NC}"
            CONTAINER_NAME="$DETECTED_CONTAINER"
        else
            echo -e "${YELLOW}   未检测到运行中的PostgreSQL容器，尝试本地模式${NC}"
            AUTO_LOCAL=true
            LOCAL_MODE=true
        fi
    elif [ "$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME")" != "running" ]; then
        echo -e "${YELLOW}⚠️  容器 $CONTAINER_NAME 未运行${NC}"
        DETECTED_CONTAINER=$(find_postgres_container)
        if [ -n "$DETECTED_CONTAINER" ]; then
            echo -e "${GREEN}✅ 自动检测到运行中的PostgreSQL容器: $DETECTED_CONTAINER${NC}"
            CONTAINER_NAME="$DETECTED_CONTAINER"
        else
            echo -e "${YELLOW}   未检测到运行中的PostgreSQL容器，尝试本地模式${NC}"
            AUTO_LOCAL=true
            LOCAL_MODE=true
        fi
    fi
fi

if [ "$LOCAL_MODE" = true ]; then
    echo -e "${GREEN}✅ 使用本地PostgreSQL执行${NC}"
    echo -e "${BLUE}   主机: ${DB_HOST}:${DB_PORT}${NC}"
    echo -e "${BLUE}   用户: ${DB_USER}${NC}"
    echo -e "${BLUE}   数据库: ${DB_NAME}${NC}"

    if $DRY_RUN; then
        echo -e "${YELLOW}   [模拟] psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $SQL_FILE${NC}"
    else
        exec_sql_local "$DB_NAME"
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}✅ 建表成功${NC}"
        else
            echo -e "${RED}❌ 建表失败 (退出码: $EXIT_CODE)${NC}"
            exit 1
        fi
    fi
else
    echo -e "${GREEN}✅ 容器 $CONTAINER_NAME 运行正常${NC}"
    echo -e "${BLUE}   数据库: ${DB_NAME}${NC}"
    echo -e "${BLUE}   用户: ${DB_USER}${NC}"
    echo -e "${BLUE}   端口: ${DB_PORT}${NC}"

    if $DRY_RUN; then
        echo -e "${YELLOW}   [模拟] docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f - < $SQL_FILE${NC}"
    else
        exec_sql_container "$DB_NAME"
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}✅ 建表成功${NC}"
        else
            echo -e "${RED}❌ 建表失败 (退出码: $EXIT_CODE)${NC}"
            exit 1
        fi
    fi
fi

# 4. 验证结果
echo -e "\n${YELLOW}📊 验证建表结果...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] 验证缓冲表是否创建成功${NC}"
else
    if [ "$LOCAL_MODE" = true ]; then
        verify_tables_local "$DB_NAME"
        echo -e "${GREEN}✅ 创建的表:${NC}"
        echo "$TABLES" | while read -r table; do
            if [ -n "$table" ]; then
                echo -e "   - $table"
            fi
        done
        if [ -n "$VERSION" ]; then
            echo -e "\n${GREEN}✅ 版本记录: $VERSION${NC}"
        fi
    else
        verify_tables_container "$DB_NAME"
        echo -e "${GREEN}✅ 创建的表:${NC}"
        echo "$TABLES" | while read -r table; do
            if [ -n "$table" ]; then
                echo -e "   - $table"
            fi
        done
        if [ -n "$VERSION" ]; then
            echo -e "\n${GREEN}✅ 版本记录: $VERSION${NC}"
        fi
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
    echo -e "${YELLOW}   PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME${NC}"
else
    echo -e "${YELLOW}   docker exec -it $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME${NC}"
fi
echo -e "${YELLOW}   SELECT * FROM t_schema_version;${NC}"