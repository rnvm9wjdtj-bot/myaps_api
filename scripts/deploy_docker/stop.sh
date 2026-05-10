#!/bin/bash
# 停止Docker服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 服务停止"
echo "=========================================="

echo ""
echo "停止服务..."
echo ""

docker-compose down

echo ""
echo "✅ 服务已停止"
