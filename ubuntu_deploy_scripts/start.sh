#!/bin/bash

# MyAPS FastAPI 快速启动脚本（开发环境）

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

cd "$PROJECT_DIR"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    log_warn "虚拟环境不存在，请先运行 deploy.sh"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查.env文件
if [ ! -f ".env" ]; then
    log_warn ".env 文件不存在，请先配置"
    exit 1
fi

# 启动服务
log_info "启动 MyAPS FastAPI 服务..."
log_info "访问地址: http://localhost:8000"
log_info "API文档: http://localhost:8000/docs"
log_info "按 Ctrl+C 停止服务"
echo ""

python main.py
