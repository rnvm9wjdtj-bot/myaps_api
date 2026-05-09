#!/bin/bash
# ==============================================================================
# MyAPS FastAPI Ubuntu 部署脚本
# 自动从 .env 读取配置参数
# ==============================================================================

set -e

# 读取 .env 配置
read_env() {
    # 获取脚本所在目录，用于定位项目根目录
    local SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
    local PROJECT_DIR_CANDIDATE=$(dirname "$SCRIPT_DIR")  # scripts 目录的父目录
    
    # 优先级：1. 当前目录 2. 脚本所在项目目录 3. APP_ROOT 环境变量
    local env_path=""
    
    # 1. 检查当前目录
    if [ -f ".env" ]; then
        env_path=".env"
    # 2. 检查脚本所在项目目录
    elif [ -f "$PROJECT_DIR_CANDIDATE/.env" ]; then
        env_path="$PROJECT_DIR_CANDIDATE/.env"
    # 3. 使用 APP_ROOT 环境变量
    elif [ -n "$APP_ROOT" ] && [ -f "$APP_ROOT/.env" ]; then
        env_path="$APP_ROOT/.env"
    # 4. 默认路径
    elif [ -f "/opt/myaps_api/myaps_api/.env" ]; then
        env_path="/opt/myaps_api/myaps_api/.env"
    elif [ -f "/opt/myaps_api/.env" ]; then
        env_path="/opt/myaps_api/.env"
    fi
    
    if [ -n "$env_path" ]; then
        echo "    读取环境变量: $env_path"
        
        # 使用 source 命令读取环境变量（更可靠）
        # 创建临时文件，确保文件以换行符结尾
        local temp_file=$(mktemp)
        cat "$env_path" > "$temp_file"
        echo "" >> "$temp_file"  # 添加换行符
        
        # 使用 source 读取，但只导入大写字母开头的环境变量
        while IFS= read -r line; do
            if [[ ! "$line" =~ ^# && "$line" =~ ^[A-Z_]+= ]]; then
                export "$line"
            fi
        done < "$temp_file"
        
        rm -f "$temp_file"
        
        # 验证读取结果
        echo "    读取到 PROJECT_DIR: ${PROJECT_DIR:-未设置}"
        echo "    读取到 APP_ROOT: ${APP_ROOT:-未设置}"
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
    # 仅在目录不存在时创建（处理只读文件系统情况）
    if [ ! -d "${APP_ROOT:-/opt/myaps_api}/logs" ]; then
        mkdir -p "${APP_ROOT:-/opt/myaps_api}/logs" || echo "    ⚠️ 无法创建 logs 目录（只读文件系统）"
    else
        echo "    logs 目录已存在"
    fi
    
    # 设置运行服务的用户
    if id "www-data" &>/dev/null; then
        APP_USER="www-data"
        echo "    使用 www-data 用户"
    else
        APP_USER="root"
        echo "    www-data 用户不存在，使用 root 用户"
    fi
    
    # 设置目录权限（跳过，只读文件系统）
    # chown -R ${APP_USER}:${APP_USER} "${APP_ROOT:-/opt/myaps_api}"
    echo "    ⚠️ 跳过权限设置（只读文件系统）"

    # 4. 安装依赖
    echo "[4/6] 安装 Python 依赖..."
    # 检查虚拟环境是否已存在
    if [ -d "${APP_ROOT:-/opt/myaps_api}/venv" ]; then
        echo "    虚拟环境已存在，跳过创建"
    else
        python3 -m venv "${APP_ROOT:-/opt/myaps_api}/venv"
    fi
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
    
    # 检测系统目录是否可写，否则使用用户级别服务
    if touch /etc/systemd/system/test_$$.service 2>/dev/null; then
        rm -f /etc/systemd/system/test_$$.service
        SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME:-MyAPS_API}.service"
        SYSTEMCTL_CMD="systemctl"
        echo "    使用系统级别 Systemd 服务"
    else
        # 使用用户级别 Systemd 服务
        mkdir -p ~/.config/systemd/user/
        SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME:-MyAPS_API}.service"
        SYSTEMCTL_CMD="systemctl --user"
        echo "    使用用户级别 Systemd 服务（系统只读）"
    fi
    
    # 生成 Systemd 服务文件
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MyAPS_API FastAPI Application
After=network.target mysql.service redis.service

[Service]
Type=notify
WorkingDirectory=${APP_ROOT:-/opt/myaps_api}
# 使用 bash -c 方式启动，先加载 .env 文件再启动 Gunicorn
ExecStart=/bin/bash -c "source ${APP_ROOT:-/opt/myaps_api}/.env && ${APP_ROOT:-/opt/myaps_api}/venv/bin/gunicorn --workers=4 --bind=127.0.0.1:8000 --timeout=30 --worker-class=uvicorn.workers.UvicornWorker --access-logfile=${APP_ROOT:-/opt/myaps_api}/logs/access.log --error-logfile=${APP_ROOT:-/opt/myaps_api}/logs/error.log main:app"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
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
    $SYSTEMCTL_CMD daemon-reload
    $SYSTEMCTL_CMD enable "${SERVICE_NAME:-MyAPS_API}"
    $SYSTEMCTL_CMD start "${SERVICE_NAME:-MyAPS_API}"

    echo ""
    echo "✅ 部署完成！"
    echo "   租户: $PROJECT_DIR"
    echo "   服务名称: ${SERVICE_NAME:-MyAPS_API}"
    echo "   绑定地址: ${GUNICORN_BIND:-127.0.0.1:8000}"
    echo ""
    echo "查看状态: systemctl status ${SERVICE_NAME:-MyAPS_API}"
    echo "查看日志: journalctl -u ${SERVICE_NAME:-MyAPS_API} -f"
    echo ""
    echo "注意: 如果系统目录只读，将使用用户级别 Systemd 服务"
    echo "      使用 'systemctl --user status ${SERVICE_NAME:-MyAPS_API}' 查看状态"
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