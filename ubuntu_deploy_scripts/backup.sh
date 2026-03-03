#!/bin/bash

# MyAPS FastAPI 备份脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="myaps_backup_$TIMESTAMP"

cd "$PROJECT_DIR"

log_info "开始备份 MyAPS FastAPI..."

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份配置文件
log_info "备份配置文件..."
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
cp .env "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || log_warn ".env 文件不存在"

# 备份项目文件（可选）
read -p "是否备份项目文件? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "备份项目文件..."
    tar -czf "$BACKUP_DIR/$BACKUP_NAME/project.tar.gz" \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git' \
        --exclude='backups' \
        .
fi

# 备份数据库（如果配置了）
if [ -f ".env" ]; then
    source .env
    if [ -n "$THIS_DB_NAME" ] && [ -n "$THIS_DB_HOST" ]; then
        read -p "是否备份数据库? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "备份数据库: $THIS_DB_NAME"
            PGPASSWORD="$THIS_DB_PASSWORD" pg_dump -h "$THIS_DB_HOST" -U "$THIS_DB_USER" -d "$THIS_DB_NAME" > "$BACKUP_DIR/$BACKUP_NAME/database.sql" || log_warn "数据库备份失败"
        fi
    fi
fi

# 压缩备份
log_info "压缩备份文件..."
cd "$BACKUP_DIR"
tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

# 清理旧备份（保留最近7天）
log_info "清理旧备份..."
find "$BACKUP_DIR" -name "myaps_backup_*.tar.gz" -mtime +7 -delete

log_info "备份完成: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
