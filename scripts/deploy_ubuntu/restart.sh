#!/bin/bash
# ==============================================================================
# 重启 MyAPS 服务
# ==============================================================================

set -e

# 读取 .env 配置
read_env() {
    if [ -f ".env" ]; then
        while IFS= read -r line; do
            if [[ ! "$line" =~ ^# && "$line" =~ ^[A-Z_]+= ]]; then
                export "$line"
            fi
        done < ".env"
    fi
}

read_env

echo "🔄 重启 ${SERVICE_NAME:-MyAPS_API} 服务..."
systemctl restart "${SERVICE_NAME:-MyAPS_API}"
echo "✅ 服务已重启"
echo "查看状态: systemctl status ${SERVICE_NAME:-MyAPS_API}"