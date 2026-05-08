#!/bin/bash
# ==============================================================================
# MyAPS FastAPI Ubuntu 部署脚本
# 自动从 .env 读取配置参数
# ==============================================================================

set -e

# 读取 .env 配置
read_env() {
    # 优先读取 APP_ROOT 目录下的 .env（服务器上的配置）
    local env_path="${APP_ROOT:-/opt/myaps_api}/.env"
    
    # 如果 APP_ROOT 目录下没有，检查当前目录
    if [ ! -f "$env_path" ] && [ -f ".env" ]; then
        env_path=".env"
    fi
    
    if [ -f "$env_path" ]; then
        echo "    读取环境变量: $env_path"
        while IFS= read -r line; do
            # 跳过注释和空行
            if [[ ! "$line" =~ ^# && "$line" =~ ^[A-Z_]+= ]]; then
                export "$line"
            fi
        done < "$env_path"
        
        # 验证读取结果
        echo "    读取到 PROJECT_DIR: ${PROJECT_DIR:-未设置}"
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

    # 保存命令行传入的租户参数（如果有）
    local cmdline_project_dir="$PROJECT_DIR"

    # 1. 读取环境变量
    echo "[1/6] 读取环境配置..."
    read_env

    # 如果命令行指定了租户，覆盖 .env 中的配置
    if [ -n "$cmdline_project_dir" ]; then
        echo "    使用命令行指定的租户: $cmdline_project_dir"
        PROJECT_DIR="$cmdline_project_dir"
    fi

    # 2. 验证必要参数
    echo "[2/6] 验证配置参数..."
    if [ -z "$PROJECT_DIR" ]; then
        echo "❌ 错误: PROJECT_DIR 未设置"
        exit 1
    fi

    # 3. 创建目录结构
    echo "[3/6] 创建目录结构..."
    mkdir -p "${APP_ROOT:-/opt/myaps_api}"
    mkdir -p "${APP_ROOT:-/opt/myaps_api}/logs"
    mkdir -p "${APP_ROOT:-/opt/myaps_api}/venv"
    
    # 设置运行服务的用户
    if id "www-data" &>/dev/null; then
        APP_USER="www-data"
        echo "    使用 www-data 用户"
    else
        APP_USER="root"
        echo "    www-data 用户不存在，使用 root 用户"
    fi
    
    # 设置目录权限
    chown -R ${APP_USER}:${APP_USER} "${APP_ROOT:-/opt/myaps_api}"

    # 4. 安装依赖
    echo "[4/6] 安装 Python 依赖..."
    python3 -m venv "${APP_ROOT:-/opt/myaps_api}/venv"
    source "${APP_ROOT:-/opt/myaps_api}/venv/bin/activate"
    
    if [ -d "offline_packages/ubuntu/python_pkg" ]; then
        echo "    使用 Ubuntu 离线依赖包..."
        # 先尝试完全离线安装
        if pip install --no-index --find-links=offline_packages/ubuntu/python_pkg -r requirements.txt 2>/dev/null; then
            echo "    ✅ 完全离线安装成功"
        else
            echo "    ⚠️ 部分包需要在线下载..."
            pip install --find-links=offline_packages/ubuntu/python_pkg -r requirements.txt
        fi
    elif [ -d "offline_packages" ]; then
        echo "    使用通用离线依赖包..."
        pip install --find-links=offline_packages -r requirements.txt
    else
        echo "    使用在线安装..."
        pip install -r requirements.txt
    fi

    # 数据库迁移
    echo "[5/7] 执行数据库迁移..."
    if [ "$SKIP_MIGRATE" = true ]; then
        echo "    ⏭️ 跳过数据库迁移（使用 -s 参数）"
    elif [ -f "scripts/migrate/auto_migrate.py" ]; then
        echo "    使用自动迁移脚本..."
        python scripts/migrate/auto_migrate.py
    elif command -v aerich &> /dev/null; then
        echo "    使用 Aerich 迁移..."
        aerich upgrade
    else
        echo "    ⚠️ 未找到迁移脚本，请手动执行数据库迁移"
    fi

    deactivate

    # 6. 创建 Systemd 服务
    echo "[6/7] 创建 Systemd 服务..."
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME:-MyAPS_API}.service"
    
    # 生成环境变量配置文件
    ENV_FILE="${APP_ROOT:-/opt/myaps_api}/.env_app"
    cat > "$ENV_FILE" << EOF
# 应用运行时环境变量
PROJECT_DIR=$PROJECT_DIR
PROJECT_JSON=${PROJECT_JSON:-dev}
EOF
    
    # 生成 Systemd 服务文件
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MyAPS_API FastAPI Application
After=network.target mysql.service redis.service

[Service]
Type=notify
User=${APP_USER}
WorkingDirectory=${APP_ROOT:-/opt/myaps_api}
# 使用 bash -c 方式启动，先加载 .env 文件再启动 Gunicorn
ExecStart=/bin/bash -c "source ${APP_ROOT:-/opt/myaps_api}/.env && ${APP_ROOT:-/opt/myaps_api}/venv/bin/gunicorn --workers=4 --bind=127.0.0.1:8000 --timeout=30 --worker-class=uvicorn.workers.UvicornWorker --access-logfile=${APP_ROOT:-/opt/myaps_api}/logs/access.log --error-logfile=${APP_ROOT:-/opt/myaps_api}/logs/error.log main:app"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # 7. 检查并启动 Redis 服务
    echo "[7/8] 检查 Redis 服务..."
    if systemctl is-active --quiet redis-server; then
        echo "    ✅ Redis 已运行"
    else
        echo "    启动 Redis 服务..."
        systemctl daemon-reload
        systemctl enable redis-server
        systemctl start redis-server
        # 等待 Redis 启动
        sleep 2
        if redis-cli ping > /dev/null 2>&1; then
            echo "    ✅ Redis 启动成功"
        else
            echo "    ⚠️ Redis 启动失败，请手动检查"
        fi
    fi

    # 8. 启动应用服务
    echo "[8/8] 启动应用服务..."
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
    echo "  -h, --help         显示帮助信息"
    echo "  -d, --deploy       执行部署"
    echo "  -t, --tenant       指定租户（可选，默认从 .env 读取）"
    echo "  -s, --skip-migrate 跳过数据库迁移（适用于增量更新）"
    echo ""
    echo "示例:"
    echo "  $0 -d                    # 使用 .env 中的配置部署（含迁移）"
    echo "  $0 -d -t CHANGDE         # 指定租户部署"
    echo "  $0 -d -s                 # 部署但跳过数据库迁移"
    echo "  $0 -d -t CHANGDE -s      # 指定租户部署，跳过迁移"
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
        -s|--skip-migrate)
            SKIP_MIGRATE=true
            shift
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