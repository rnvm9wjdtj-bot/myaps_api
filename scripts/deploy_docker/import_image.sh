#!/bin/bash
# 导入Docker镜像（用于离线部署）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 镜像导入"
echo "=========================================="

IMAGE_FILE="${1:-$SCRIPT_DIR/myaps_api_latest.tar}"

if [ ! -f "$IMAGE_FILE" ]; then
    echo "❌ 镜像文件不存在: $IMAGE_FILE"
    exit 1
fi

echo ""
echo "导入镜像: $IMAGE_FILE"
echo ""

docker load -i "$IMAGE_FILE"

echo ""
echo "✅ 镜像已导入"
docker images myaps_api
