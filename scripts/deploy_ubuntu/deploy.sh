#!/bin/bash
# ==============================================================================
# MyAPS FastAPI Ubuntu 部署脚本
# 自动从 .env 读取配置参数
# ==============================================================================

set -e

# 读取 .env 配置
read_env() {
    if [ -f ".env" ]; then
        while IFS= read -r line; do
            # 跳过注释和空行
            if [[ ! "$line" =~ ^# && "$line" =~ ^[A-Z_]+= ]]; then
                export "$line"
            fi
        done < ".env"
    else
        echo "❌ 错误: .env 文件不存在"
        exit 1
    fi
}

# 主部署函数
deploy() {
    echo "========================================"
    echo "  MyAPS Ubuntu 部署脚本"
    echo "========================================"

    # 1. 读取环境变量
    echo "[1/6] 读取环境配置..."
    read_env

    # 2. 验证必要参数
    echo "[2/6] 验证配置参数..."
    if [ -z "$PROJECT_DIR" ]; then
        echo "❌ 错误: PROJECT_DIR 未设置"
        exit 1
    fi

    # 3. 创建目录结构
    echo "[3/6] 创建目录结构..."
    mkdir -p "${APP_ROOT:-/opt/myaps}"
    mkdir -p "${APP_ROOT:-/opt/myaps}/logs"
    mkdir -p "${APP_ROOT:-/opt/myaps}/venv"

    # 4. 安装依赖
    echo "[4/6] 安装 Python 依赖..."
    python3 -m venv "${APP_ROOT:-/opt/myaps}/venv"
    source "${APP_ROOT:-/opt/myaps}/venv/bin/activate"
    
    if [ -d "offline_packages/ubuntu" ]; then
        echo "    使用 Ubuntu 离线依赖包..."
        # 先尝试完全离线安装
        if pip install --no-index --find-links=offline_packages/ubuntu -r requirements.txt 2>/dev/null; then
            echo "    ✅ 完全离线安装成功"
        else
            echo "    ⚠️ 部分包需要在线下载..."
            pip install --find-links=offline_packages/ubuntu -r requirements.txt
        fi
    elif [ -d "offline_packages" ]; then
        echo "    使用通用离线依赖包..."
        pip install --find-links=offline_packages -r requirements.txt
    else
        echo "    使用在线安装..."
        pip install -r requirements.txt
    fi
    deactivate

    # 5. 创建 Systemd 服务
    echo "[5/6] 创建 Systemd 服务..."
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME:-MyAPS_API}.service"
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=${SERVICE_NAME:-MyAPS_API} FastAPI Application
After=network.target mysql.service redis.service

[Service]
Type=notify
User=${APP_USER:-www-data}
WorkingDirectory=${APP_ROOT:-/opt/myaps}
Environment="PROJECT_DIR=${PROJECT_DIR}"
Environment="PROJECT_JSON=${PROJECT_JSON:-dev}"
ExecStart=${APP_ROOT:-/opt/myaps}/venv/bin/gunicorn \
    --workers=${WORKERS:-4} \
    --bind=${GUNICORN_BIND:-127.0.0.1:8000} \
    --timeout=${GUNICORN_TIMEOUT:-30} \
    --worker-class=uvicorn.workers.UvicornWorker \
    --access-logfile=${APP_ROOT:-/opt/myaps}/logs/access.log \
    --error-logfile=${APP_ROOT:-/opt/myaps}/logs/error.log \
    main:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # 6. 启动服务
    echo "[6/6] 启动服务..."
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME:-MyAPS_API}"
    systemctl start "${SERVICE_NAME:-MyAPS_API}"

    echo ""
    echo "✅ 部署完成！"
    echo "   租户: $PROJECT_DIR"
    echo "   服务名称: ${SERVICE_NAME:-MyAPS_API}"
    echo "   绑定地址: ${GUNICORN_BIND:-127.0.0.1:8000}"
    echo ""
    echo "查看状态: systemctl status ${SERVICE_NAME:-MyAPS_API}"
    echo "查看日志: journalctl -u ${SERVICE_NAME:-MyAPS_API} -f"
}

# 显示帮助
usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示帮助信息"
    echo "  -d, --deploy   执行部署"
    echo "  -t, --tenant   指定租户（可选，默认从 .env 读取）"
    echo ""
    echo "示例:"
    echo "  $0 -d                    # 使用 .env 中的配置部署"
    echo "  $0 -d -t CHANGDE         # 指定租户部署"
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--deploy)
            DEPLOY=true
            shift
            ;;
        -t|--tenant)
            PROJECT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            usage
            exit 1
            ;;
    esac
done

# 执行部署
if [ "$DEPLOY" = true ]; then
    deploy
else
    usage
fi