#!/bin/bash
set -e

echo "========================================"
echo "   MyAPS Docker Service Start Script"
echo "========================================"
echo ""

PROJECT_DIR="/opt/myaps_api"
SCRIPT_DIR="$PROJECT_DIR/scripts/deploy_docker"

echo "1. Preparing directories..."

# 确保所有必要目录存在
mkdir -p "$PROJECT_DIR/static"
mkdir -p "$PROJECT_DIR/storage"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/project_files"

# 设置权限
chown -R root:root "$PROJECT_DIR/static"
chmod -R 755 "$PROJECT_DIR/static"

echo "[OK] Directories prepared"

echo ""
echo "2. Checking Redis port..."

# 检查 Redis 端口
if lsof -Pi :6379 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[WARN] Port 6379 is in use"
    OLD_CONTAINER=$(docker ps -q --filter "name=myaps_redis")
    if [ -n "$OLD_CONTAINER" ]; then
        echo "[INFO] Stopping old Redis container..."
        docker stop myaps_redis >/dev/null 2>&1 || true
        docker rm myaps_redis >/dev/null 2>&1 || true
    fi
fi

echo "[OK] Port check completed"

echo ""
echo "3. Starting services..."

cd "$PROJECT_DIR"
docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo ""
echo "4. Checking status..."
sleep 10
docker-compose -f "$SCRIPT_DIR/docker-compose.yml" ps

echo ""
echo "========================================"
echo "   Service start completed!"
echo "========================================"