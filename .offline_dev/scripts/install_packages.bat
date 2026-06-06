@echo off
chcp 65001 >nul
REM ============================================================
REM MyAPS API - 离线依赖安装脚本 (内网 Windows 机器执行)
REM ============================================================
REM 用途: 在内网Windows机器上离线安装所有Python依赖
REM 前置条件:
REM   1. Python 3.11+ 已安装并配置环境变量
REM   2. 已将 offline_packages 目录复制到本机
REM   3. 已将 requirements.txt 复制到项目根目录
REM ============================================================

setlocal EnableDelayedExpansion

REM 配置
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
cd /d "%PROJECT_ROOT%"

set "VENV_DIR=%PROJECT_ROOT%\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "PACKAGES_DIR=%SCRIPT_DIR%..\packages"
set "REQUIREMENTS_FILE=%PROJECT_ROOT%\requirements.txt"

REM 颜色定义 (使用 ANSI 转义码)
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

echo.
echo %GREEN%========================================%NC%
echo %GREEN%  MyAPS API 离线依赖安装工具%NC%
echo %GREEN%========================================%NC%
echo.

REM [1/7] 检查Python环境
set "PYTHON_EXE=python"
echo %BLUE%[1/7] 检查 Python 环境...%NC%
%PYTHON_EXE% --version >nul 2>&1
if %errorLevel% neq 0 (
    set "PYTHON_EXE=python3"
    %PYTHON_EXE% --version >nul 2>&1
    if %errorLevel% neq 0 (
        echo %RED%错误: 未找到 python 或 python3 命令%NC%
        echo %YELLOW%请确保 Python 3.11+ 已安装并添加到系统 PATH%NC%
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%a in ('%PYTHON_EXE% --version 2^>^&1') do set "PY_VERSION=%%a"
echo   当前 Python 版本: %GREEN%%PY_VERSION%%NC%

REM [2/7] 检查离线包目录
echo %BLUE%[2/7] 检查离线包目录...%NC%
if not exist "%PACKAGES_DIR%" (
    echo %RED%错误: 未找到离线包目录%NC%
    echo   预期路径: %PACKAGES_DIR%
    echo %YELLOW%请将 offline_packages 目录复制到 scripts 同级目录%NC%
    pause
    exit /b 1
)
echo   离线包目录: %GREEN%%PACKAGES_DIR%%NC%

REM [3/7] 检查 requirements.txt
echo %BLUE%[3/7] 检查依赖清单...%NC%
if not exist "%REQUIREMENTS_FILE%" (
    echo %RED%错误: 未找到 requirements.txt%NC%
    echo   预期路径: %REQUIREMENTS_FILE%
    pause
    exit /b 1
)
echo   依赖文件: %GREEN%%REQUIREMENTS_FILE%%NC%

REM [4/7] 创建虚拟环境
echo %BLUE%[4/7] 创建虚拟环境...%NC%
if exist "%VENV_DIR%" (
    echo   发现已有虚拟环境，是否删除重建?
    set /p "REBUILD=[Y/N]: "
    if /i "!REBUILD!"=="Y" (
        echo   删除旧虚拟环境...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo   使用现有虚拟环境
        goto :SKIP_VENV_CREATE
    )
)

echo   创建虚拟环境...
%PYTHON_EXE% -m venv "%VENV_DIR%"
if %errorLevel% neq 0 (
    echo %RED%错误: 创建虚拟环境失败%NC%
    pause
    exit /b 1
)
echo   虚拟环境创建成功

:SKIP_VENV_CREATE

REM [5/7] 升级pip
echo %BLUE%[5/7] 升级 pip...%NC%
"%VENV_PIP%" install --upgrade pip --no-index --find-links="%PACKAGES_DIR%"
if %errorLevel% neq 0 (
    echo %YELLOW%警告: pip 升级失败，尝试使用默认 pip...%NC%
)

REM [6/7] 安装依赖
echo %BLUE%[6/7] 安装依赖包...%NC%
echo   %YELLOW%这可能需要几分钟，请耐心等待...%NC%
echo.

"%VENV_PIP%" install --no-index --find-links="%PACKAGES_DIR%" -r "%REQUIREMENTS_FILE%"
if %errorLevel% neq 0 (
    echo.
    echo %RED%错误: 依赖安装失败%NC%
    echo %YELLOW%可能原因:%NC%
    echo   1. 离线包不完整，缺少某些依赖
    echo   2. Python 版本与打包时不一致
    echo   3. 某些包需要编译环境（如 Visual C++ Build Tools）
    echo.
    echo %YELLOW%建议:%NC%
    echo   - 检查 offline_packages 目录是否完整
    echo   - 确认 Python 版本与打包机器一致
    echo   - 如需编译，请先安装 Visual Studio Build Tools
    pause
    exit /b 1
)

echo.
echo   %GREEN%依赖安装成功!%NC%

REM [7/7] 验证安装
echo %BLUE%[7/7] 验证安装...%NC%
echo   检查关键包:

set "KEY_PACKAGES=fastapi uvicorn tortoise-orm pydantic pandas redis"
for %%p in (%KEY_PACKAGES%) do (
    "%VENV_PYTHON%" -c "import %%p" >nul 2>&1
    if !errorLevel! equ 0 (
        echo     [OK] %%p
    ) else (
        echo     [FAIL] %%p
    )
)

echo.
REM 创建必要目录
if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"
if not exist "%PROJECT_ROOT%\storage" mkdir "%PROJECT_ROOT%\storage"

echo %GREEN%========================================%NC%
echo %GREEN%  安装完成!%NC%
echo %GREEN%========================================%NC%
echo.
echo 下一步:
echo   1. 复制 .env.example 为 .env 并配置数据库连接
@echo   2. 运行 scripts\dev_server.bat start 启动服务
@echo   3. 访问 http://localhost:8000/docs 查看API文档
echo.
pause
