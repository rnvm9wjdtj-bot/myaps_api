#!/bin/bash
# ============================================================
# MyAPS API - 离线依赖包下载脚本 (Linux/macOS 外网机器执行)
# ============================================================
# 用途: 在外网机器上预先下载所有 Python 依赖包，供内网离线安装使用
# 执行环境: 有外网访问的 Linux/macOS 机器
# Python版本要求: 3.11 或 3.12 (必须与内网Windows目标机器一致)
#
# 使用方法:
#   # 默认使用 PyPI 官方源
#   bash download_packages.sh
#
#   # 使用阿里云镜像（推荐国内使用）
#   INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ bash download_packages.sh
#
#   # 使用清华镜像
#   INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash download_packages.sh
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
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
PACKAGES_DIR="${SCRIPT_DIR}/../packages"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
INDEX_URL="${INDEX_URL:-}"  # 支持通过环境变量指定镜像源

# 检查Python版本
check_python() {
    echo -e "${BLUE}[1/6] 检查 Python 环境...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: 未找到 python3 命令${NC}"
        exit 1
    fi

    local py_version
    py_version=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "  当前 Python 版本: ${GREEN}${py_version}${NC}"
    echo -e "  ${YELLOW}注意: 请确保此版本与内网目标机器一致${NC}"
}

# 创建输出目录
prepare_dirs() {
    echo -e "${BLUE}[2/6] 准备输出目录...${NC}"
    mkdir -p "${PACKAGES_DIR}"
    echo -e "  输出目录: ${GREEN}${PACKAGES_DIR}${NC}"
}

# 下载依赖包
download_packages() {
    echo -e "${BLUE}[3/6] 下载 Python 依赖包...${NC}"

    if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
        echo -e "${RED}错误: 未找到 requirements.txt${NC}"
        echo -e "  预期路径: ${REQUIREMENTS_FILE}"
        exit 1
    fi

    echo -e "  依赖文件: ${GREEN}${REQUIREMENTS_FILE}${NC}"
    
    # 配置镜像源
    PIP_ARGS=()
    if [[ -n "${INDEX_URL}" ]]; then
        echo -e "  使用镜像源: ${GREEN}${INDEX_URL}${NC}"
        PIP_ARGS+=("--index-url" "${INDEX_URL}")
        # 从 URL 提取 trusted-host
        HOST=$(echo "${INDEX_URL}" | sed -E 's|https?://([^/:]+).*|\1|')
        PIP_ARGS+=("--trusted-host" "${HOST}")
    fi
    
    echo -e "  ${YELLOW}开始下载，这可能需要较长时间...${NC}"
    echo ""

    # 使用 pip download 下载所有依赖（包括子依赖）
    pip download \
        --requirement "${REQUIREMENTS_FILE}" \
        --dest "${PACKAGES_DIR}" \
        --only-binary :all: \
        --python-version "${PYTHON_VERSION}" \
        --platform win_amd64 \
        --no-deps \
        "${PIP_ARGS[@]}" 2>&1 | tee "${PACKAGES_DIR}/download.log"

    # 下载源码包（部分包可能没有Windows wheel）
    echo -e "\n${YELLOW}补充下载源码包（无Windows wheel的包）...${NC}"
    pip download \
        --requirement "${REQUIREMENTS_FILE}" \
        --dest "${PACKAGES_DIR}" \
        --no-binary :all: \
        "${PIP_ARGS[@]}" 2>&1 | tee -a "${PACKAGES_DIR}/download.log"

    echo ""
}

# 验证下载结果
verify_packages() {
    echo -e "${BLUE}[4/6] 验证下载结果...${NC}"

    local total_count
    total_count=$(find "${PACKAGES_DIR}" -name "*.whl" -o -name "*.tar.gz" -o -name "*.zip" | wc -l)

    echo -e "  已下载包数量: ${GREEN}${total_count}${NC}"

    # 检查 requirements.txt 中列出的主要包是否都有对应文件
    local missing=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        # 跳过空行和注释
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

        # 提取包名（去除版本号）
        local pkg_name
        pkg_name=$(echo "$line" | sed -E 's/([a-zA-Z0-9_-]+).*/\1/' | tr '[:upper:]' '[:lower:]')

        # 检查是否有对应的包文件
        if ! find "${PACKAGES_DIR}" -iname "${pkg_name}*" | grep -q .; then
            missing+=("$pkg_name")
        fi
    done < "${REQUIREMENTS_FILE}"

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "  ${YELLOW}警告: 以下包可能未找到对应文件:${NC}"
        for pkg in "${missing[@]}"; do
            echo -e "    - ${pkg}"
        done
        echo -e "  ${YELLOW}这些包可能以不同名称存在，或需要手动处理${NC}"
    else
        echo -e "  ${GREEN}所有主要依赖包均已下载${NC}"
    fi
}

# 生成包清单
generate_manifest() {
    echo -e "${BLUE}[5/6] 生成包清单...${NC}"

    local manifest_file="${PACKAGES_DIR}/MANIFEST.txt"

    echo "# MyAPS API 离线依赖包清单" > "${manifest_file}"
    echo "# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "${manifest_file}"
    echo "# Python版本: $(python3 --version)" >> "${manifest_file}"
    echo "# 目标平台: Windows x64" >> "${manifest_file}"
    echo "" >> "${manifest_file}"

    find "${PACKAGES_DIR}" -name "*.whl" -o -name "*.tar.gz" -o -name "*.zip" | \
        sort | \
        while read -r f; do
            basename "$f" >> "${manifest_file}"
        done

    echo -e "  清单文件: ${GREEN}${manifest_file}${NC}"
}

# 打包输出
package_output() {
    echo -e "${BLUE}[6/6] 打包输出...${NC}"

    local output_file="${SCRIPT_DIR}/../offline_packages_$(date +%Y%m%d).tar.gz"

    tar -czf "${output_file}" -C "$(dirname "${PACKAGES_DIR}")" "$(basename "${PACKAGES_DIR}")"

    local file_size
    file_size=$(du -h "${output_file}" | cut -f1)

    echo -e "  输出文件: ${GREEN}${output_file}${NC}"
    echo -e "  文件大小: ${GREEN}${file_size}${NC}"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  离线包下载完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "请将以下文件复制到内网 Windows 机器:"
    echo "  1. ${output_file}"
    echo "  2. ${PROJECT_ROOT}/requirements.txt"
    echo "  3. ${PROJECT_ROOT}/.offline_dev/scripts/install_packages.bat"
    echo ""
    echo "在内网机器上解压后运行 install_packages.bat 即可安装"
}

# 主流程
main() {
    echo "========================================"
    echo "  MyAPS API 离线依赖包下载工具"
    echo "========================================"
    echo ""

    check_python
    prepare_dirs
    download_packages
    verify_packages
    generate_manifest
    package_output
}

main "$@"
