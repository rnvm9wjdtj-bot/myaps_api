@echo off
:: 配置变量
set "PS_SCRIPT=%~dp0run.ps1"
set "ENV_FILE=%~dp0.env"
set "RESTART_DELAY=5"
set "MAX_RESTARTS=5"
set "RESTART_COUNT=0"

:: 从 .env 文件读取 HOST 和 PORT 配置
if exist "%ENV_FILE%" (
    for /f "tokens=1,2 delims==" %%a in ('findstr /i "^HOST=" "%ENV_FILE%"') do set "HOST=%%b"
    for /f "tokens=1,2 delims==" %%a in ('findstr /i "^PORT=" "%ENV_FILE%"') do set "PORT=%%b"
)

:: 显示启动信息
echo =========================================
echo FastAPI Server Monitor
echo Monitoring: %PS_SCRIPT%
echo Environment: %ENV_FILE%
echo Host: %HOST%
echo Port: %PORT%
echo Press Ctrl+C twice to stop monitoring
echo =========================================
echo.

:: 无限循环监测
:LOOP
echo [%date% %time%] Starting run.ps1...

:: 构建命令参数
set "PS_ARGS="
if defined HOST set "PS_ARGS=%PS_ARGS% -HostAddress %HOST%"
if defined PORT set "PS_ARGS=%PS_ARGS% -Port %PORT%"

:: 执行 PowerShell 脚本
powershell -ExecutionPolicy Bypass -NoProfile -Command "& '%PS_SCRIPT%' %PS_ARGS% %*"

:: 检查退出码（0=正常退出，非0=异常退出）
if %errorlevel% equ 0 (
    echo [%date% %time%] run.ps1 exited normally.
    goto END
) else (
    set /a "RESTART_COUNT=%RESTART_COUNT%+1"
    echo [%date% %time%] run.ps1 exited with error code %errorlevel%.
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