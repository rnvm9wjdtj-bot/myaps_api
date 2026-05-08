#!/bin/bash
# ==============================================================================
# 停止 MyAPS 服务
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

echo "⏹️ 停止 ${SERVICE_NAME:-MyAPS_API} 服务..."
systemctl stop "${SERVICE_NAME:-MyAPS_API}"
echo "✅ 服务已停止"