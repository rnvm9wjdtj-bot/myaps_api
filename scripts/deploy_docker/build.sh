#!/bin/bash
# 构建Docker镜像

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 镜像构建"
echo "=========================================="

VERSION="${1:-latest}"
IMAGE_NAME="myaps_api:$VERSION"

echo ""
echo "构建镜像: $IMAGE_NAME"
echo ""

docker build -t "$IMAGE_NAME" .

echo ""
echo "✅ 镜像构建完成: $IMAGE_NAME"
echo ""
docker images myaps_api
