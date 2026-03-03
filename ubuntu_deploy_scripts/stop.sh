#!/bin/bash

# MyAPS FastAPI 停止脚本

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

log_info "停止 MyAPS FastAPI 服务..."

if systemctl is-active --quiet $SERVICE_NAME; then
    sudo systemctl stop $SERVICE_NAME
    log_info "服务已停止"
else
    log_warn "服务未运行"
fi
