#!/bin/bash
# 重启Docker服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 服务重启"
echo "=========================================="

echo ""
echo "重启服务..."
echo ""

docker-compose restart

echo ""
echo "服务状态:"
docker-compose ps

echo ""
echo "✅ 服务已重启"
