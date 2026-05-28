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
ENV_FILE="${SCRIPT_DIR}/../../.env"
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
    echo ""
    echo "示例:"
    echo "  # 使用默认配置"
    echo "  ./setup_staging_tables.sh -d myaps_db"
    echo ""
    echo "  # 指定容器名称"
    echo "  ./setup_staging_tables.sh -d myaps_db -c my_postgres"
    echo ""
    echo "  # 模拟执行"
    echo "  ./setup_staging_tables.sh -d myaps_db -n"
}

# 解析参数
DRY_RUN=false

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

# 检查数据库名称是否指定
if [ -z "$DB_NAME" ]; then
    echo -e "${RED}❌ 错误: 必须使用 -d 指定数据库名称${NC}"
    show_help
    exit 1
fi

# 读取环境变量
read_env_config

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

# 2. 检查容器是否存在
echo -e "\n${YELLOW}🔍 检查PostgreSQL容器状态...${NC}"
if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
    echo -e "${RED}❌ 错误: 容器 $CONTAINER_NAME 不存在${NC}"
    echo -e "${RED}   请先启动PostgreSQL容器${NC}"
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
echo -e "${BLUE}   数据库: ${DB_NAME}${NC}"
echo -e "${BLUE}   用户: ${DB_USER}${NC}"
echo -e "${BLUE}   端口: ${DB_PORT}${NC}"

if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] docker exec -i $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME -f - < $SQL_FILE${NC}"
else
    # 检查数据库是否存在，不存在则创建
    echo -e "${YELLOW}   检查数据库是否存在...${NC}"
    if ! docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
        echo -e "${YELLOW}   数据库不存在，创建数据库...${NC}"
        docker exec "$CONTAINER_NAME" createdb -U "$DB_USER" "$DB_NAME"
    fi
    
    # 执行建表脚本
    echo -e "${YELLOW}   执行SQL脚本...${NC}"
    cat "$SQL_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME"
    
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✅ 建表成功${NC}"
    else
        echo -e "${RED}❌ 建表失败 (退出码: $EXIT_CODE)${NC}"
        exit 1
    fi
fi

# 4. 验证结果
echo -e "\n${YELLOW}📊 验证建表结果...${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}   [模拟] 验证缓冲表是否创建成功${NC}"
else
    TABLES=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT tablename FROM pg_tables WHERE tablename LIKE '%staging' OR tablename IN ('t_validation_error', 't_transform_rule', 't_schema_version') ORDER BY tablename;")
    echo -e "${GREEN}✅ 创建的表:${NC}"
    echo "$TABLES" | while read -r table; do
        if [ -n "$table" ]; then
            echo -e "   - $table"
        fi
    done
    
    # 检查版本记录
    VERSION=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT version FROM t_schema_version ORDER BY applied_at DESC LIMIT 1;")
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
echo -e "${YELLOW}   docker exec -it $CONTAINER_NAME psql -U $DB_USER -d $DB_NAME${NC}"
echo -e "${YELLOW}   SELECT * FROM t_schema_version;${NC}"