#!/bin/bash
# ==============================================================================
# 查看 MyAPS 服务状态
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

echo "📊 ${SERVICE_NAME:-MyAPS_API} 服务状态:"
systemctl status "${SERVICE_NAME:-MyAPS_API}"