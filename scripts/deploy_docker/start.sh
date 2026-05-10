#!/bin/bash
# 启动Docker服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 服务启动"
echo "=========================================="

if [ ! -f ".env" ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "请先创建 .env 配置文件"
    exit 1
fi

echo ""
echo "启动服务..."
echo ""

docker-compose up -d

echo ""
echo "等待服务启动..."
sleep 5

echo ""
echo "服务状态:"
docker-compose ps

echo ""
echo "✅ 服务已启动"
echo ""
echo "访问地址: http://localhost:${PORT:-8000}"
echo "查看日志: docker-compose logs -f"
