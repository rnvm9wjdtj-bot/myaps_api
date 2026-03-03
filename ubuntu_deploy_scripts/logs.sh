#!/bin/bash

# MyAPS FastAPI 日志查看脚本

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE_NAME="myaps-fastapi"

# 查看实时日志
sudo journalctl -u $SERVICE_NAME -f
