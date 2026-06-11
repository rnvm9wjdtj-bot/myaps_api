#!/bin/bash
# ============================================================
# MyAPS API - 离线依赖安装脚本 (内网 Linux 机器执行)
# ============================================================
# 用途: 在内网Linux机器上离线安装所有Python依赖
# 前置条件:
#   1. Python 3.11+ 已安装
#   2. 已将 offline_packages 目录复制到本机
#   3. 已将 requirements.txt 复制到项目根目录
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
cd "${PROJECT_ROOT}"

VENV_DIR="${PROJECT_ROOT}/venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
VENV_PIP="${VENV_DIR}/bin/pip"
PACKAGES_DIR="${SCRIPT_DIR}/../packages"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  MyAPS API 离线依赖安装工具 (Linux)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# [1/7] 检查Python环境
echo -e "${BLUE}[1/7] 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3 命令${NC}"
    echo -e "${YELLOW}请确保 Python 3.11+ 已安装${NC}"
    exit 1
fi

PYTHON_EXE="python3"
py_version=$(${PYTHON_EXE} --version 2>&1 | awk '{print $2}')
echo -e "  当前 Python 版本: ${GREEN}${py_version}${NC}"

# [2/7] 检查离线包目录
echo -e "${BLUE}[2/7] 检查离线包目录...${NC}"
if [[ ! -d "${PACKAGES_DIR}" ]]; then
    echo -e "${RED}错误: 未找到离线包目录${NC}"
    echo -e "  预期路径: ${PACKAGES_DIR}"
    echo -e "${YELLOW}请将 packages 目录复制到 scripts 同级目录${NC}"
    exit 1
fi
echo -e "  离线包目录: ${GREEN}${PACKAGES_DIR}${NC}"

# [3/7] 检查 requirements.txt
echo -e "${BLUE}[3/7] 检查依赖清单...${NC}"
if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    echo -e "${RED}错误: 未找到 requirements.txt${NC}"
    echo -e "  预期路径: ${REQUIREMENTS_FILE}"
    exit 1
fi
echo -e "  依赖文件: ${GREEN}${REQUIREMENTS_FILE}${NC}"

# [4/7] 创建虚拟环境
echo -e "${BLUE}[4/7] 创建虚拟环境...${NC}"
if [[ -d "${VENV_DIR}" ]]; then
    echo -e "  ${YELLOW}发现已有虚拟环境，是否删除重建? [y/N]:${NC}"
    read -r REBUILD
    if [[ "${REBUILD}" =~ ^[Yy]$ ]]; then
        echo "  删除旧虚拟环境..."
        rm -rf "${VENV_DIR}"
    else
        echo "  使用现有虚拟环境"
    fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "  创建虚拟环境..."
    ${PYTHON_EXE} -m venv "${VENV_DIR}"
    if [[ $? -ne 0 ]]; then
        echo -e "${RED}错误: 创建虚拟环境失败${NC}"
        exit 1
    fi
    echo -e "  虚拟环境创建成功: ${GREEN}${VENV_DIR}${NC}"
fi

# [5/7] 升级pip
echo -e "${BLUE}[5/7] 升级 pip...${NC}"
"${VENV_PIP}" install --upgrade pip --no-index --find-links="${PACKAGES_DIR}" || {
    echo -e "${YELLOW}警告: pip 升级失败，尝试使用默认 pip...${NC}"
}

# [6/7] 安装依赖
echo -e "${BLUE}[6/7] 安装依赖包...${NC}"
echo -e "  ${YELLOW}这可能需要几分钟，请耐心等待...${NC}"
echo ""

"${VENV_PIP}" install --no-index --find-links="${PACKAGES_DIR}" -r "${REQUIREMENTS_FILE}"
if [[ $? -ne 0 ]]; then
    echo ""
    echo -e "${RED}错误: 依赖安装失败${NC}"
    echo -e "${YELLOW}可能原因:${NC}"
    echo "  1. 离线包不完整，缺少某些依赖"
    echo "  2. Python 版本与打包时不一致"
    echo "  3. 某些包需要编译环境（如 gcc, make）"
    echo ""
    echo -e "${YELLOW}建议:${NC}"
    echo "  - 检查 packages 目录是否完整"
    echo "  - 确认 Python 版本与打包机器一致"
    echo "  - 如需编译，请先安装编译工具: yum install gcc make 或 apt-get install build-essential"
    exit 1
fi

echo ""
echo -e "  ${GREEN}依赖安装成功!${NC}"

# [7/7] 验证安装
echo -e "${BLUE}[7/7] 验证安装...${NC}"
echo "  检查关键包:"

KEY_PACKAGES="fastapi uvicorn tortoise-orm pydantic pandas redis"
for pkg in ${KEY_PACKAGES}; do
    "${VENV_PYTHON}" -c "import ${pkg}" 2>/dev/null && \
        echo -e "    [OK] ${pkg}" || \
        echo -e "    [FAIL] ${pkg}"
done

echo ""
# 创建必要目录
mkdir -p "${PROJECT_ROOT}/logs"
mkdir -p "${PROJECT_ROOT}/storage"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  安装完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步:"
echo "  1. 复制 .env.example 为 .env 并配置数据库连接"
echo "  2. 运行 scripts/dev_server.sh start 启动服务"
echo "  3. 访问 http://localhost:8000/docs 查看API文档"
echo ""