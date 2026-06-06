# ============================================================
# MyAPS API - 离线依赖包下载脚本 (Windows PowerShell 外网机器执行)
# ============================================================
# 用途: 在外网Windows机器上预先下载所有Python依赖包
# 执行环境: 有外网访问的 Windows 机器
# Python版本要求: 3.11 或 3.12 (必须与内网目标机器一致)
#
# 使用方法:
#   # 默认使用 PyPI 官方源
#   .\download_packages.ps1
#
#   # 使用阿里云镜像（推荐国内使用）
#   .\download_packages.ps1 -IndexUrl "https://mirrors.aliyun.com/pypi/simple/"
#
#   # 使用清华镜像
#   .\download_packages.ps1 -IndexUrl "https://pypi.tuna.tsinghua.edu.cn/simple"
# ============================================================

#Requires -Version 5.1

param(
    [string]$PythonVersion = "3.12",
    [string]$Platform = "win_amd64",
    [string]$IndexUrl = ""  # 镜像源，默认为空使用 PyPI 官方源
)

# 颜色函数
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# 配置
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$PackagesDir = Join-Path $ScriptDir "..\packages"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

Write-Output "========================================"
Write-Output "  MyAPS API 离线依赖包下载工具"
Write-Output "========================================"
Write-Output ""

# [1/6] 检查Python环境
Write-ColorOutput Blue "[1/6] 检查 Python 环境..."
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-ColorOutput Red "错误: 未找到 python 或 python3 命令"
    exit 1
}

$PyVersion = & $PythonCmd.Source --version 2>&1
Write-Output "  当前 Python 版本: $PyVersion"
Write-ColorOutput Yellow "  注意: 请确保此版本与内网目标机器一致"

# [2/6] 准备输出目录
Write-ColorOutput Blue "[2/6] 准备输出目录..."
New-Item -ItemType Directory -Force -Path $PackagesDir | Out-Null
Write-Output "  输出目录: $PackagesDir"

# [3/6] 下载依赖包
Write-ColorOutput Blue "[3/6] 下载 Python 依赖包..."

if (-not (Test-Path $RequirementsFile)) {
    Write-ColorOutput Red "错误: 未找到 requirements.txt"
    Write-Output "  预期路径: $RequirementsFile"
    exit 1
}

Write-Output "  依赖文件: $RequirementsFile"

# 配置镜像源
$PipArgs = @()
if ($IndexUrl) {
    Write-Output "  使用镜像源: $IndexUrl"
    $PipArgs += @("--index-url", $IndexUrl)
    # 从 URL 提取 trusted-host
    if ($IndexUrl -match 'https?://([^/]+)') {
        $TrustedHost = $Matches[1]
        $PipArgs += @("--trusted-host", $TrustedHost)
    }
}

Write-ColorOutput Yellow "  开始下载，这可能需要较长时间..."
Write-Output ""

# 下载所有依赖（包括子依赖）
$DownloadArgs = @(
    "--requirement", "$RequirementsFile",
    "--dest", "$PackagesDir",
    "--only-binary", ":all:",
    "--python-version", $PythonVersion,
    "--platform", $Platform,
    "--no-deps"
) + $PipArgs

& $PythonCmd.Source -m pip download @DownloadArgs 2>&1 | Tee-Object -FilePath "$PackagesDir\download.log"

# 补充下载源码包
Write-Output ""
Write-ColorOutput Yellow "补充下载源码包（无Windows wheel的包）..."
$SourceArgs = @(
    "--requirement", "$RequirementsFile",
    "--dest", "$PackagesDir",
    "--no-binary", ":all:"
) + $PipArgs

& $PythonCmd.Source -m pip download @SourceArgs 2>&1 | Tee-Object -Append -FilePath "$PackagesDir\download.log"

Write-Output ""

# [4/6] 验证下载结果
Write-ColorOutput Blue "[4/6] 验证下载结果..."
$PackageFiles = Get-ChildItem -Path $PackagesDir -Include "*.whl","*.tar.gz","*.zip" -Recurse
Write-Output "  已下载包数量: $($PackageFiles.Count)"

# [5/6] 生成包清单
Write-ColorOutput Blue "[5/6] 生成包清单..."
$ManifestFile = Join-Path $PackagesDir "MANIFEST.txt"
$ManifestContent = @"
# MyAPS API 离线依赖包清单
# 生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# Python版本: $PyVersion
# 目标平台: Windows x64

"@

$PackageFiles | ForEach-Object { $ManifestContent += "$($_.Name)`n" }
$ManifestContent | Out-File -FilePath $ManifestFile -Encoding UTF8
Write-Output "  清单文件: $ManifestFile"

# [6/6] 打包输出
Write-ColorOutput Blue "[6/6] 打包输出..."
$OutputFile = Join-Path (Split-Path -Parent $PackagesDir) "offline_packages_$(Get-Date -Format 'yyyyMMdd').zip"
Compress-Archive -Path "$PackagesDir\*" -DestinationPath $OutputFile -Force

$FileSize = (Get-Item $OutputFile).Length
$FileSizeMB = [math]::Round($FileSize / 1MB, 2)

Write-Output "  输出文件: $OutputFile"
Write-Output "  文件大小: ${FileSizeMB} MB"
Write-Output ""
Write-ColorOutput Green "========================================"
Write-ColorOutput Green "  离线包下载完成！"
Write-ColorOutput Green "========================================"
Write-Output ""
Write-Output "请将以下文件复制到内网 Windows 机器:"
Write-Output "  1. $OutputFile"
Write-Output "  2. $RequirementsFile"
Write-Output "  3. $(Join-Path $ProjectRoot ".offline_dev\scripts\install_packages.bat")"
Write-Output ""
Write-Output "在内网机器上解压后运行 install_packages.bat 即可安装"
