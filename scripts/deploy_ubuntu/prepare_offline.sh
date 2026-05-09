#!/bin/bash
# ==============================================================================
# 打包离线依赖包（在有外网的开发机执行）
# ==============================================================================

set -e

echo "========================================"
echo "  准备离线依赖包"
echo "========================================"

# 检查 requirements.txt 是否存在
if [ ! -f "requirements.txt" ]; then
    echo "❌ 错误: requirements.txt 不存在"
    exit 1
fi

# 创建离线包目录
echo "[1/2] 创建离线包目录..."
mkdir -p offline_packages

# 下载依赖
echo "[2/2] 下载 Python 依赖..."
pip download -r requirements.txt -d offline_packages/

echo ""
echo "✅ 离线依赖包准备完成！"
echo "   目录: $(pwd)/offline_packages/"
echo "   文件数: $(ls offline_packages/ | wc -l)"
echo ""
echo "使用方式:"
echo "  1. 将整个项目目录拷贝到离线服务器"
echo "  2. 运行 deploy.sh -d 进行部署"