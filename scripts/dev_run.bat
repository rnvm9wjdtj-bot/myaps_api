@echo off
chcp 65001 >nul
title MyAPS API SERVER
setlocal EnableDelayedExpansion

if /i "%~1"=="/?" goto :help
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help

:: 配置变量
set "VENV_PYTHON=%~dp0..\venv\Scripts\python.exe"
set "PROJECT_ROOT=%~dp0.."
set "ENV_FILE=%PROJECT_ROOT%\.env"
set "RESTART_DELAY=5"
set "MAX_RESTARTS=5"
set "RESTART_COUNT=0"
set "HOST=0.0.0.0"
set "PORT=8000"
set "WORKERS=1"
set "PROJECT_DIR="
set "PROJECT_JSON="

:: 从 .env 文件读取 HOST/PORT/PROJECT_DIR/PROJECT_JSON 配置
if exist "%ENV_FILE%" (
    for /f "tokens=2 delims==" %%a in ('findstr /i "^HOST=" "%ENV_FILE%"') do set "HOST=%%a"
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PORT=" "%ENV_FILE%"') do set "PORT=%%a"
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PROJECT_DIR=" "%ENV_FILE%"') do set "PROJECT_DIR=%%a"
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PROJECT_JSON=" "%ENV_FILE%"') do set "PROJECT_JSON=%%a"
    :: 去除变量前后空格
    for /f "tokens=* delims= " %%a in ("%HOST%") do set "HOST=%%a"
    for /f "tokens=* delims= " %%a in ("%PORT%") do set "PORT=%%a"
    for /f "tokens=* delims= " %%a in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%a"
    for /f "tokens=* delims= " %%a in ("%PROJECT_JSON%") do set "PROJECT_JSON=%%a"
)

:: 显示启动信息
echo =========================================
echo FastAPI Server Monitor
echo Project Root: %PROJECT_ROOT%
echo Python:       %VENV_PYTHON%
echo Environment:  %ENV_FILE%
echo Host:         %HOST%
echo Port:         %PORT%
echo Workers:      %WORKERS%

echo.
echo [92m=========================================[0m
echo [93mProject File: [0m[91m[%PROJECT_DIR%][0m
echo [93mProject JSON: [0m[91m[%PROJECT_JSON%][0m
echo [92m=========================================[0m
echo.
echo 按 Ctrl+C 停止; 崩溃将自动重启 (最多 %MAX_RESTARTS% 次, 间隔 %RESTART_DELAY% 秒)
echo =========================================
echo.

:: 进入项目根目录
cd /d "%PROJECT_ROOT%"

:: 无限循环监控
:LOOP
echo [%date% %time%] Starting FastAPI server...

:: 执行 uvicorn 多 worker 启动 (对标 Docker 部署的 Gunicorn 多 Worker 模式)
:: --no-use-colors: 禁用 ANSI 颜色码, 避免 Windows CMD 乱码
%VENV_PYTHON% -m uvicorn main:app --host %HOST% --port %PORT% --workers %WORKERS% --log-level info --access-log --no-use-colors

:: 检查退出码 (0=正常退出, 非0=异常退出)
if %errorlevel% equ 0 (
    echo [%date% %time%] Server exited normally.
    goto END
) else (
    set /a "RESTART_COUNT=!RESTART_COUNT!+1"
    echo [%date% %time%] Server exited with error code %errorlevel%.
    echo [%date% %time%] Restart count: !RESTART_COUNT!/%MAX_RESTARTS%

    if !RESTART_COUNT! gtr %MAX_RESTARTS% (
        echo [%date% %time%] Max restart limit reached. Stopping...
        goto END
    )

    echo [%date% %time%] Restarting in %RESTART_DELAY% seconds...
    timeout /t %RESTART_DELAY% /nobreak >nul
    goto LOOP
)

:help
echo 用法: dev_run.bat
echo.
echo 前台启动 MyAPS API 服务, 崩溃自动重启 (最多 %MAX_RESTARTS% 次).
echo 配置自动从 .env 读取 HOST/PORT/PROJECT_DIR/PROJECT_JSON.
echo 启动使用 uvicorn 多 worker 模式, 对标生产 Docker 部署.
echo.
echo 启动后可访问:
echo   http://localhost:PORT          应用主页
echo   http://localhost:PORT/docs     API 文档
echo   http://localhost:PORT/monitor  监控面板
echo.
echo 按 Ctrl+C 停止服务.
exit /b 0

:END
echo [%date% %time%] Monitoring stopped.
