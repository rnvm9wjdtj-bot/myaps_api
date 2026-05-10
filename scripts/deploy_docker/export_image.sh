#!/bin/bash
# 导出Docker镜像（用于离线部署）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 镜像导出"
echo "=========================================="

VERSION="${1:-latest}"
OUTPUT_DIR="${2:-$SCRIPT_DIR}"
IMAGE_NAME="myaps_api:$VERSION"
OUTPUT_FILE="$OUTPUT_DIR/myaps_api_$VERSION.tar"

echo ""
echo "导出镜像: $IMAGE_NAME"
echo "输出文件: $OUTPUT_FILE"
echo ""

if ! docker images "$IMAGE_NAME" | grep -q "myaps_api"; then
    echo "❌ 镜像不存在，请先构建镜像"
    echo "运行: ./build.sh $VERSION"
    exit 1
fi

docker save -o "$OUTPUT_FILE" "$IMAGE_NAME"

echo ""
echo "✅ 镜像已导出: $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"
