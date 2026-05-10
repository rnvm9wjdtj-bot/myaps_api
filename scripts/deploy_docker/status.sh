#!/bin/bash
# 查看Docker服务状态

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "  MyAPS API Docker 服务状态"
echo "=========================================="

echo ""
docker-compose ps

echo ""
echo "容器健康状态:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|myaps"

echo ""
echo "日志查看命令:"
echo "  全部日志: docker-compose logs -f"
echo "  应用日志: docker-compose logs -f app"
echo "  Redis日志: docker-compose logs -f redis"
