#!/bin/bash

# MyAPS FastAPI 更新脚本

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

SERVICE_NAME="myaps-fastapi"
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

cd "$PROJECT_DIR"

log_info "开始更新 MyAPS FastAPI..."

# 拉取最新代码
if [ -d ".git" ]; then
    log_info "拉取最新代码..."
    git pull origin main
else
    log_warn "不是Git仓库，跳过代码更新"
fi

# 激活虚拟环境
source venv/bin/activate

# 更新依赖
log_info "更新Python依赖..."
pip install --upgrade pip
pip install -r requirements.txt

# 数据库迁移
if command -v aerich &> /dev/null; then
    read -p "是否执行数据库迁移? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "执行数据库迁移..."
        aerich upgrade
    fi
fi

# 重启服务
log_info "重启服务..."
sudo systemctl restart $SERVICE_NAME

# 检查服务状态
sleep 2
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    log_info "服务重启成功"
    sudo systemctl status $SERVICE_NAME --no-pager
else
    log_warn "服务重启失败，请检查日志"
    sudo journalctl -u $SERVICE_NAME -n 50 --no-pager
    exit 1
fi

log_info "更新完成！"
