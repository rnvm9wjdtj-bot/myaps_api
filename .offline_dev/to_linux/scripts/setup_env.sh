#!/bin/bash
# ============================================================
# MyAPS API - 环境配置向导 (内网 Linux 机器执行)
# ============================================================
# 用途: 交互式生成 .env 配置文件
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
cd "${PROJECT_ROOT}"

ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

echo ""
echo "========================================"
echo "  MyAPS API 环境配置向导 (Linux)"
echo "========================================"
echo ""

# [1/4] 检查环境模板
echo -e "${BLUE}[1/4] 检查环境模板...${NC}"
if [[ ! -f "${ENV_EXAMPLE}" ]]; then
    echo -e "${RED}错误: 未找到 .env.example${NC}"
    exit 1
fi
echo -e "  模板文件: ${GREEN}${ENV_EXAMPLE}${NC}"

# [2/4] 备份现有 .env
echo -e "${BLUE}[2/4] 备份现有配置...${NC}"
if [[ -f "${ENV_FILE}" ]]; then
    backup_file="${ENV_FILE}.backup.$(date +%Y%m%d)"
    cp "${ENV_FILE}" "${backup_file}"
    echo -e "  已备份到: ${GREEN}${backup_file}${NC}"
fi

# 复制模板
cp "${ENV_EXAMPLE}" "${ENV_FILE}"
echo -e "  已创建: ${GREEN}${ENV_FILE}${NC}"

# [3/4] 配置环境变量
echo -e "${BLUE}[3/4] 配置环境变量...${NC}"
echo ""
echo "请根据内网环境填写以下配置（直接回车使用默认值）:"
echo ""

# 应用端口
read -p "应用端口 [8000]: " PORT
PORT=${PORT:-8000}

# MySQL 数据库
echo ""
echo "--- MySQL 数据库配置 ---"
read -p "MySQL 主机地址 [localhost]: " MYSQL_HOST
MYSQL_HOST=${MYSQL_HOST:-localhost}

read -p "MySQL 端口 [3306]: " MYSQL_PORT
MYSQL_PORT=${MYSQL_PORT:-3306}

read -p "MySQL 用户名 [root]: " MYSQL_USER
MYSQL_USER=${MYSQL_USER:-root}

read -p "MySQL 密码: " MYSQL_PASSWORD
while [[ -z "${MYSQL_PASSWORD}" ]]; do
    echo -e "${RED}密码不能为空${NC}"
    read -p "MySQL 密码: " MYSQL_PASSWORD
done

read -p "账套数据库列表 (逗号分隔) [db1,db2]: " MYSQL_DB_SET
MYSQL_DB_SET=${MYSQL_DB_SET:-db1,db2}

read -p "主账套数据库名 [db1]: " MYSQL_MAIN_DB
MYSQL_MAIN_DB=${MYSQL_MAIN_DB:-db1}

# PostgreSQL 数据库（可选）
echo ""
echo "--- PostgreSQL 数据库配置 (可选，直接回车跳过) ---"
read -p "PostgreSQL 主机地址 [localhost]: " PG_HOST
PG_HOST=${PG_HOST:-localhost}

read -p "PostgreSQL 端口 [5432]: " PG_PORT
PG_PORT=${PG_PORT:-5432}

read -p "PostgreSQL 用户名 [postgres]: " PG_USER
PG_USER=${PG_USER:-postgres}

read -p "PostgreSQL 密码: " PG_PASSWORD

read -p "PostgreSQL 数据库名 [appsmith]: " PG_DB_NAME
PG_DB_NAME=${PG_DB_NAME:-appsmith}

# Redis 配置
echo ""
echo "--- Redis 配置 ---"
read -p "Redis 主机地址 [localhost]: " REDIS_HOST
REDIS_HOST=${REDIS_HOST:-localhost}

read -p "Redis 端口 [6379]: " REDIS_PORT
REDIS_PORT=${REDIS_PORT:-6379}

read -p "Redis 密码 (可选，直接回车跳过): " REDIS_PASSWORD

# 项目配置
echo ""
echo "--- 项目配置 ---"
read -p "租户项目目录名 [HACYXS]: " PROJECT_DIR
PROJECT_DIR=${PROJECT_DIR:-HACYXS}

read -p "配置文件名 (不含.json) [dev]: " PROJECT_JSON
PROJECT_JSON=${PROJECT_JSON:-dev}

# [4/4] 写入配置文件
echo ""
echo -e "${BLUE}[4/4] 写入配置文件...${NC}"

# 更新 .env 文件
sed -i.bak "s|^PORT=.*|PORT=${PORT}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_DB_HOST=.*|MYAPS_DB_HOST=${MYSQL_HOST}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_DB_PORT=.*|MYAPS_DB_PORT=${MYSQL_PORT}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_DB_USER=.*|MYAPS_DB_USER=${MYSQL_USER}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_DB_PASSWORD=.*|MYAPS_DB_PASSWORD=${MYSQL_PASSWORD}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_DB_SET=.*|MYAPS_DB_SET=${MYSQL_DB_SET}|" "${ENV_FILE}"
sed -i.bak "s|^MYAPS_MAIN_DB=.*|MYAPS_MAIN_DB=${MYSQL_MAIN_DB}|" "${ENV_FILE}"

if [[ -n "${PG_HOST}" ]]; then
    sed -i.bak "s|^THIS_DB_HOST=.*|THIS_DB_HOST=${PG_HOST}|" "${ENV_FILE}"
    sed -i.bak "s|^THIS_DB_PORT=.*|THIS_DB_PORT=${PG_PORT}|" "${ENV_FILE}"
    sed -i.bak "s|^THIS_DB_USER=.*|THIS_DB_USER=${PG_USER}|" "${ENV_FILE}"
    if [[ -n "${PG_PASSWORD}" ]]; then
        sed -i.bak "s|^THIS_DB_PASSWORD=.*|THIS_DB_PASSWORD=${PG_PASSWORD}|" "${ENV_FILE}"
    fi
    sed -i.bak "s|^THIS_DB_NAME=.*|THIS_DB_NAME=${PG_DB_NAME}|" "${ENV_FILE}"
fi

sed -i.bak "s|^REDIS_HOST=.*|REDIS_HOST=${REDIS_HOST}|" "${ENV_FILE}"
sed -i.bak "s|^REDIS_PORT=.*|REDIS_PORT=${REDIS_PORT}|" "${ENV_FILE}"
if [[ -n "${REDIS_PASSWORD}" ]]; then
    sed -i.bak "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "${ENV_FILE}"
fi

sed -i.bak "s|^PROJECT_DIR=.*|PROJECT_DIR=${PROJECT_DIR}|" "${ENV_FILE}"
sed -i.bak "s|^PROJECT_JSON=.*|PROJECT_JSON=${PROJECT_JSON}|" "${ENV_FILE}"

# 清理备份文件
rm -f "${ENV_FILE}.bak"

echo -e "  ${GREEN}配置文件已更新: ${ENV_FILE}${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  配置完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步:"
echo "  1. 检查 ${ENV_FILE} 确认配置正确"
echo "  2. 运行 scripts/dev_server.sh start 启动服务"
echo ""