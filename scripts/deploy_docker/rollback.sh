#!/bin/bash
set -e

# 回滚脚本 - 蓝绿部署回滚
# 使用方法：
#   ./rollback.sh

PROJECT_DIR=$(grep PROJECT_DIR .env | cut -d'=' -f2)
PORT=$(grep PORT .env | cut -d'=' -f2)
PORT=${PORT:-8000}

BLUE_CONTAINER="myaps_api_blue"
GREEN_CONTAINER="myaps_api_green"

echo "🔄 开始回滚..."

# 获取当前运行的容器
RUNNING_CONTAINER=""
if docker ps --filter "name=myaps_api" --filter "status=running" | grep -q "myaps_api"; then
    RUNNING_CONTAINER=$(docker ps --filter "name=myaps_api" --filter "status=running" --format "{{.Names}}")
fi

echo "当前运行容器: $RUNNING_CONTAINER"

# 确定要回滚到的环境
if [ "$RUNNING_CONTAINER" = "$BLUE_CONTAINER" ]; then
    ROLLBACK_TO="$GREEN_CONTAINER"
else
    ROLLBACK_TO="$BLUE_CONTAINER"
fi

# 检查是否有已停止的容器可以恢复
if docker inspect "$ROLLBACK_TO" &>/dev/null; then
    echo "🔧 恢复已停止的容器: $ROLLBACK_TO"
    docker start "$ROLLBACK_TO"
    
    # 等待健康检查
    echo "⏳ 等待容器启动..."
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -f "http://localhost:$PORT/docs" &>/dev/null; then
            echo "✅ 容器恢复成功"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        sleep 2
    done
    
    # 停止当前运行的容器
    if [ -n "$RUNNING_CONTAINER" ]; then
        echo "🛑 停止当前容器: $RUNNING_CONTAINER"
        docker stop "$RUNNING_CONTAINER"
    fi
else
    echo "⚠️  没有找到可恢复的容器，尝试重新启动最近的容器..."
    
    # 获取最近创建的 myaps_api 镜像
    LATEST_IMAGE=$(docker images --filter=reference="*myaps*" --format "{{.Repository}}:{{.Tag}}" | head -1)
    
    if [ -z "$LATEST_IMAGE" ]; then
        echo "❌ 没有找到可用的镜像，请手动部署"
        exit 1
    fi
    
    echo "使用镜像: $LATEST_IMAGE"
    docker run -d \
        --name "$ROLLBACK_TO" \
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
        "$LATEST_IMAGE" \
        gunicorn -w 4 -k uvicorn.workers.UvicornWorker -b "0.0.0.0:$PORT" main:app
fi

echo ""
echo "🎉 回滚完成！"
echo "当前运行容器: $ROLLBACK_TO"