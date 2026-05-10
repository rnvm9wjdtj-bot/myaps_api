#!/bin/bash
# ==============================================================================
# 打包离线依赖包（在有外网的开发机执行）
# ==============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 显示帮助
usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help          显示帮助信息"
    echo ""
    echo "说明:"
    echo "  此脚本使用当前 Python 环境下载依赖包。"
    echo "  请确保在与目标服务器相同 Python 版本的环境中运行此脚本。"
    echo ""
    echo "示例:"
    echo "  $0                    # 使用当前 Python 版本下载"
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

echo "========================================"
echo "  准备离线依赖包"
echo "========================================"

# 检查 requirements.txt 是否存在
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ 错误: requirements.txt 不存在${NC}"
    exit 1
fi

# 检测当前 Python 版本
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PYTHON_VERSION="${PYTHON_MAJOR}${PYTHON_MINOR}"
echo -e "${GREEN}✅ 当前 Python 版本: ${PYTHON_MAJOR}.${PYTHON_MINOR} (cp${PYTHON_VERSION})${NC}"

# 检查 Python 版本警告
if [ "$PYTHON_VERSION" != "310" ] && [ "$PYTHON_VERSION" != "312" ]; then
    echo -e "${YELLOW}⚠️  警告: 目标服务器使用 Python 3.10 或 3.12，当前版本可能不兼容${NC}"
fi

# 创建离线包目录
echo ""
echo "[1/2] 创建离线包目录..."
OFFLINE_DIR="offline_packages/ubuntu/python_pkg"
mkdir -p "$OFFLINE_DIR"

# 下载依赖
echo "[2/2] 下载 Python 依赖..."
echo "    离线包目录: $OFFLINE_DIR"
echo ""

# 直接下载，使用当前 Python 环境的配置
echo "    正在下载依赖包..."
pip download -r requirements.txt -d "$OFFLINE_DIR"

# 统计下载结果
FILE_COUNT=$(ls -1 "$OFFLINE_DIR" 2>/dev/null | wc -l)

echo ""
echo "========================================"
echo "✅ 离线依赖包准备完成！"
echo "========================================"
echo "   目录: $(pwd)/$OFFLINE_DIR/"
echo "   文件数: $FILE_COUNT"
echo ""
echo "使用方式:"
echo "  1. 将整个项目目录拷贝到离线服务器"
echo "  2. 运行 deploy.sh -d 进行部署"
echo ""
echo "验证命令（在离线服务器上）:"
echo "  cd /opt/myaps_api/myaps_api"
echo "  python3 -m venv venv"
echo "  source venv/bin/activate"
echo "  pip install --no-index --find-links=$OFFLINE_DIR -r requirements.txt"
echo ""