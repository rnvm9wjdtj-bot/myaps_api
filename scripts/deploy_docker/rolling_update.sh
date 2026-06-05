#!/bin/bash
set -e

# 滚动更新脚本 - 蓝绿部署策略
# 使用方法：
#   ./rolling_update.sh <镜像标签>
#   ./rolling_update.sh qsct/myaps-api:master

IMAGE_TAG="${1:-qsct/myaps-api:master}"
PROJECT_DIR=$(grep PROJECT_DIR .env | cut -d'=' -f2)
PORT=$(grep PORT .env | cut -d'=' -f2)
PORT=${PORT:-8000}

# 当前活跃容器（蓝环境）
BLUE_CONTAINER="myaps_api_blue"
GREEN_CONTAINER="myaps_api_green"

# 检查参数
if [ -z "$IMAGE_TAG" ]; then
    echo "❌ 请提供镜像标签参数"
    echo "用法: $0 <镜像标签>"
    exit 1
fi

# 拉取最新镜像
echo "📥 拉取镜像: $IMAGE_TAG"
docker pull "$IMAGE_TAG"

# 获取当前活跃环境
ACTIVE_ENV=""
if docker inspect "$BLUE_CONTAINER" &>/dev/null && docker ps --filter "name=$BLUE_CONTAINER" --filter "status=running" | grep -q "$BLUE_CONTAINER"; then
    ACTIVE_ENV="blue"
    NEW_CONTAINER="$GREEN_CONTAINER"
    OLD_CONTAINER="$BLUE_CONTAINER"
elif docker inspect "$GREEN_CONTAINER" &>/dev/null && docker ps --filter "name=$GREEN_CONTAINER" --filter "status=running" | grep -q "$GREEN_CONTAINER"; then
    ACTIVE_ENV="green"
    NEW_CONTAINER="$BLUE_CONTAINER"
    OLD_CONTAINER="$GREEN_CONTAINER"
else
    # 首次部署，使用蓝环境
    ACTIVE_ENV="none"
    NEW_CONTAINER="$BLUE_CONTAINER"
    OLD_CONTAINER=""
fi

echo "当前活跃环境: $ACTIVE_ENV"
echo "新容器: $NEW_CONTAINER"

# 启动新容器（绿环境）
echo "🚀 启动新版本容器: $NEW_CONTAINER"
docker run -d \
    --name "$NEW_CONTAINER" \
    --network host \
    --restart unless-stopped \
    --env-file .env \
    -e REDIS_HOST=localhost \
    -e THIS_DB_HOST=localhost \
    -e GUNICORN_BIND="0.0.0.0:$PORT" \
    -e APP_ROOT=/app \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/storage:/app/storage" \
    -v "$(pwd)/project_files/$PROJECT_DIR:/app/project_files/$PROJECT_DIR" \
    "$IMAGE_TAG" \
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b "0.0.0.0:$PORT" main:app

# 等待新容器健康检查通过
echo "⏳ 等待新容器健康检查..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f "http://localhost:$PORT/docs" &>/dev/null; then
        echo "✅ 新容器健康检查通过"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    sleep 2
    echo "   等待中... ($RETRY_COUNT/$MAX_RETRIES)"
done

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "❌ 新容器健康检查失败，回滚..."
    docker stop "$NEW_CONTAINER"
    docker rm "$NEW_CONTAINER"
    exit 1
fi

# 停止旧容器（蓝环境）
if [ -n "$OLD_CONTAINER" ]; then
    echo "🛑 停止旧容器: $OLD_CONTAINER"
    docker stop "$OLD_CONTAINER"
    docker rm "$OLD_CONTAINER"
fi

echo ""
echo "🎉 滚动更新完成！"
echo "当前运行容器: $NEW_CONTAINER"
echo "镜像版本: $IMAGE_TAG"
echo "访问地址: http://localhost:$PORT"