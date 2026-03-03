#!/bin/bash

# MyAPS FastAPI 一键部署脚本
# 适用于 Ubuntu Server

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
check_root() {
    if [ "$EUID" -eq 0 ]; then 
        log_warn "建议不要使用root用户运行此脚本"
        read -p "是否继续? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# 检查系统环境
check_system() {
    log_info "检查系统环境..."
    
    # 检查操作系统
    if [ ! -f /etc/os-release ]; then
        log_error "无法检测操作系统类型"
        exit 1
    fi
    
    source /etc/os-release
    log_info "操作系统: $PRETTY_NAME"
    
    # 检查Python版本
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    log_info "Python版本: $PYTHON_VERSION"
    
    # 检查pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 未安装"
        exit 1
    fi
    
    # 检查git
    if ! command -v git &> /dev/null; then
        log_warn "git 未安装，将自动安装"
        sudo apt-get update && sudo apt-get install -y git
    fi
}

# 安装系统依赖
install_system_dependencies() {
    log_info "安装系统依赖..."
    
    sudo apt-get update
    
    # 安装Python开发包和编译工具
    sudo apt-get install -y \
        python3-dev \
        python3-venv \
        python3-pip \
        build-essential \
        libpq-dev \
        libmysqlclient-dev \
        pkg-config \
        curl \
        nginx \
        supervisor
    
    log_info "系统依赖安装完成"
}

# 创建项目目录
setup_project_dir() {
    log_info "设置项目目录..."
    
    # 获取脚本所在目录
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    
    # 如果脚本在项目根目录，使用当前目录
    if [ -f "$SCRIPT_DIR/main.py" ] && [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        PROJECT_DIR="$SCRIPT_DIR"
        log_info "检测到项目目录: $PROJECT_DIR"
    else
        # 否则询问项目目录
        read -p "请输入项目目录路径 (默认: $HOME/myaps_fastapi): " INPUT_DIR
        PROJECT_DIR=${INPUT_DIR:-$HOME/myaps_fastapi}
        
        if [ ! -d "$PROJECT_DIR" ]; then
            log_info "创建项目目录: $PROJECT_DIR"
            mkdir -p "$PROJECT_DIR"
        fi
    fi
    
    cd "$PROJECT_DIR"
}

# 创建虚拟环境
create_venv() {
    log_info "创建Python虚拟环境..."
    
    if [ -d "venv" ]; then
        log_warn "虚拟环境已存在，是否删除并重新创建? (y/n)"
        read -p "" -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf venv
            python3 -m venv venv
        else
            log_info "使用现有虚拟环境"
        fi
    else
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip setuptools wheel
    
    log_info "虚拟环境创建完成"
}

# 安装Python依赖
install_python_dependencies() {
    log_info "安装Python依赖..."
    
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        log_error "requirements.txt 文件不存在"
        exit 1
    fi
    
    log_info "Python依赖安装完成"
}

# 配置环境变量
setup_env_file() {
    log_info "配置环境变量..."
    
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在，创建示例配置文件"
        cat > .env << 'EOF'
# 项目配置
PROJECT_DIR=ZONE
PORT=8000
HOST=0.0.0.0

# 数据库监控开关
TURNON_DBMONITOR=False

# 定时任务开关
TRUNON_SCHEDULER=False
SCHEDULER_HOUR=6,8,10,12,14,16
SCHEDULER_MINUTE=55

# MyAPS数据库配置
MYAPS_VERSION=L
MYAPS_BASE_URL=http://your-myaps-url
MYAPS_DB_HOST=localhost
MYAPS_DB_PORT=3333
MYAPS_DB_USER=your_db_user
MYAPS_DB_PASSWORD=your_db_password
MYAPS_DB_SET=your_db_name
MYAPS_MAIN_DB=your_main_db

# 本API数据库配置 (PostgreSQL)
THIS_DB_HOST=localhost
THIS_DB_PORT=5432
THIS_DB_USER=your_pg_user
THIS_DB_PASSWORD=your_pg_password
THIS_DB_NAME=your_pg_db

# 安全配置
IP_WHITELIST=
API_KEY=your_api_key_here
EOF
        log_warn "请编辑 .env 文件并配置正确的环境变量"
        read -p "是否现在编辑 .env 文件? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} .env
        fi
    else
        log_info ".env 文件已存在"
    fi
}

# 数据库迁移
run_migrations() {
    log_info "检查数据库迁移..."
    
    if command -v aerich &> /dev/null; then
        read -p "是否执行数据库迁移? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "执行数据库迁移..."
            aerich upgrade
            log_info "数据库迁移完成"
        fi
    else
        log_warn "aerich 未安装，跳过数据库迁移"
    fi
}

# 创建systemd服务文件
create_systemd_service() {
    log_info "创建systemd服务..."
    
    SERVICE_NAME="myaps-fastapi"
    PROJECT_DIR=$(pwd)
    USER=$(whoami)
    
    sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=MyAPS FastAPI Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    
    log_info "systemd服务创建完成: $SERVICE_NAME"
}

# 配置Nginx
setup_nginx() {
    log_info "配置Nginx..."
    
    read -p "是否配置Nginx反向代理? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        return
    fi
    
    SERVER_NAME=$(hostname -f)
    read -p "服务器域名 (默认: $SERVER_NAME): " INPUT_NAME
    SERVER_NAME=${INPUT_NAME:-$SERVER_NAME}
    
    sudo tee /etc/nginx/sites-available/myaps-fastapi > /dev/null << EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # 超时设置
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
        send_timeout 600;
    }

    location /static {
        alias $(pwd)/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    # 启用站点
    sudo ln -sf /etc/nginx/sites-available/myaps-fastapi /etc/nginx/sites-enabled/
    
    # 测试Nginx配置
    sudo nginx -t
    
    # 重启Nginx
    sudo systemctl restart nginx
    
    log_info "Nginx配置完成"
}

# 配置防火墙
setup_firewall() {
    log_info "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        sudo ufw allow 22/tcp
        sudo ufw allow 80/tcp
        sudo ufw allow 443/tcp
        sudo ufw --force enable
        log_info "防火墙配置完成"
    else
        log_warn "ufw 未安装，跳过防火墙配置"
    fi
}

# 启动服务
start_service() {
    log_info "启动服务..."
    
    SERVICE_NAME="myaps-fastapi"
    
    read -p "是否启动服务? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl start $SERVICE_NAME
        sudo systemctl status $SERVICE_NAME --no-pager
        
        log_info "服务已启动"
        log_info "查看服务状态: sudo systemctl status $SERVICE_NAME"
        log_info "查看服务日志: sudo journalctl -u $SERVICE_NAME -f"
    fi
}

# 显示部署信息
show_deployment_info() {
    log_info "======================================"
    log_info "部署完成！"
    log_info "======================================"
    log_info "项目目录: $(pwd)"
    log_info "服务名称: myaps-fastapi"
    log_info ""
    log_info "常用命令:"
    log_info "  启动服务: sudo systemctl start myaps-fastapi"
    log_info "  停止服务: sudo systemctl stop myaps-fastapi"
    log_info "  重启服务: sudo systemctl restart myaps-fastapi"
    log_info "  查看状态: sudo systemctl status myaps-fastapi"
    log_info "  查看日志: sudo journalctl -u myaps-fastapi -f"
    log_info ""
    log_info "访问地址:"
    log_info "  本地访问: http://localhost:8000"
    log_info "  API文档: http://localhost:8000/docs"
    log_info "======================================"
}

# 主函数
main() {
    log_info "开始部署 MyAPS FastAPI..."
    
    check_root
    check_system
    install_system_dependencies
    setup_project_dir
    create_venv
    install_python_dependencies
    setup_env_file
    run_migrations
    create_systemd_service
    setup_nginx
    setup_firewall
    start_service
    show_deployment_info
    
    log_info "部署脚本执行完成！"
}

# 执行主函数
main "$@"
