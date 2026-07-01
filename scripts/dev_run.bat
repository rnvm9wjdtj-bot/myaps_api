@echo off
title MyAPS API SERVER
:: 启用延迟扩展以支持循环内变量
setlocal enabledelayedexpansion
:: 配置变量
set "VENV_PYTHON=%~dp0..\venv\Scripts\python.exe"
set "PROJECT_ROOT=%~dp0.."
set "ENV_FILE=%PROJECT_ROOT%\.env"
set "RESTART_DELAY=5"
set "MAX_RESTARTS=5"
set "RESTART_COUNT=0"
set "HOST=0.0.0.0"
set "PORT=8000"
set "WORKERS=4"
set "PROJECT_DIR="
set "PROJECT_JSON="

:: 从 .env 文件读取 HOST 和 PORT 配置
echo Before reading .env: HOST=%HOST%, PORT=%PORT%, PROJECT_JSON=%PROJECT_JSON%
if exist "%ENV_FILE%" (
    echo Reading from .env file: %ENV_FILE%
    
    :: 读取 HOST
    for /f "tokens=2 delims==" %%a in ('findstr /i "^HOST=" "%ENV_FILE%"') do set "HOST=%%a"
    
    :: 读取 PORT
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PORT=" "%ENV_FILE%"') do set "PORT=%%a"
    
    :: 读取 PROJECT_DIR
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PROJECT_DIR=" "%ENV_FILE%"') do set "PROJECT_DIR=%%a"
    
    :: 读取 PROJECT_JSON
    for /f "tokens=2 delims==" %%a in ('findstr /i "^PROJECT_JSON=" "%ENV_FILE%"') do set "PROJECT_JSON=%%a"
    
    :: 去除所有变量的前后空格
    for /f "tokens=* delims= " %%a in ("%HOST%") do set "HOST=%%a"
    for /f "tokens=* delims= " %%a in ("%PORT%") do set "PORT=%%a"
    for /f "tokens=* delims= " %%a in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%a"
    for /f "tokens=* delims= " %%a in ("%PROJECT_JSON%") do set "PROJECT_JSON=%%a"
)
echo After reading .env: HOST=%HOST%, PORT=%PORT%, PROJECT_JSON=%PROJECT_JSON%

:: 显示启动信息
echo =========================================
echo FastAPI Server Monitor
echo Project Root: %PROJECT_ROOT%
echo Python: %VENV_PYTHON%
echo Environment: %ENV_FILE%
echo Host: %HOST%
echo Port: %PORT%
:: 使用颜色和特殊字符增强显示
echo.
echo [92m=========================================[0m
echo [93mProject File: [0m[91m[%PROJECT_DIR%][0m
echo [93mProject JSON: [0m[91m[%PROJECT_JSON%][0m
echo [92m=========================================[0m
echo.
echo Press Ctrl+C to stop
echo =========================================
echo.

:: 进入项目根目录
cd /d "%PROJECT_ROOT%"

:: 无限循环监测
:LOOP
echo [%date% %time%] Starting FastAPI server...

:: 执行 Python 命令（对标Docker部署的Gunicorn多Worker模式）
%VENV_PYTHON% -m uvicorn main:app --host %HOST% --port %PORT% --workers %WORKERS% --log-level info --access-log

:: 检查退出码（0=正常退出，非0=异常退出）
if %errorlevel% equ 0 (
    echo [%date% %time%] Server exited normally.
    goto END
) else (
    set /a "RESTART_COUNT=%RESTART_COUNT%+1"
    echo [%date% %time%] Server exited with error code %errorlevel%.
    echo [%date% %time%] Restart count: %RESTART_COUNT%/%MAX_RESTARTS%
    
    :: 检查是否达到最大重启次数
    if %RESTART_COUNT% gtr %MAX_RESTARTS% (
        echo [%date% %time%] Max restart limit reached. Stopping...
        goto END
    )
    
    :: 延迟后重启
    echo [%date% %time%] Restarting in %RESTART_DELAY% seconds...
    timeout /t %RESTART_DELAY% /nobreak >nul
    goto LOOP
)

:END
echo [%date% %time%] Monitoring stopped.