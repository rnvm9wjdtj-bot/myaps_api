@echo off
title MyAPS API SERVER
:: 配置变量
set "VENV_PYTHON=%~dp0..\venv\Scripts\python.exe"
set "PROJECT_ROOT=%~dp0.."
set "ENV_FILE=%PROJECT_ROOT%\.env"
set "RESTART_DELAY=5"
set "MAX_RESTARTS=5"
set "RESTART_COUNT=0"
set "HOST=0.0.0.0"
set "PORT=8000"
set "PROJECT_DIR="

:: 从 .env 文件读取 HOST 和 PORT 配置
echo Before reading .env: HOST=%HOST%, PORT=%PORT%
if exist "%ENV_FILE%" (
    echo Reading from .env file: %ENV_FILE%
    for /f "usebackq tokens=1,2 delims==" %%a in ("%ENV_FILE%") do (
        if /i "%%a"=="HOST" set "HOST=%%b"
        if /i "%%a"=="PORT" set "PORT=%%b"
        if /i "%%a"=="PROJECT_DIR" set "PROJECT_DIR=%%b"
        if /i "%%a"=="PROJECT_JSON" set "PROJECT_JSON=%%b"
    )
)
echo After reading .env: HOST=%HOST%, PORT=%PORT%

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

:: 执行 Python 命令
%VENV_PYTHON% -m uvicorn main:app --host %HOST% --port %PORT% --log-level info --access-log

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