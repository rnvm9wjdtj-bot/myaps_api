@echo off
chcp 65001 >nul
REM =====================================================
REM 开发环境服务启停脚本 (Windows)
REM 用法:
REM   dev_server.bat start   - 启动服务
REM   dev_server.bat stop    - 停止服务
REM   dev_server.bat restart - 重启服务
REM   dev_server.bat status  - 查看状态
REM =====================================================

setlocal EnableDelayedExpansion

REM 项目根目录
set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

REM 配置
set "APP_NAME=myaps_api"
set "PID_FILE=%PROJECT_DIR%\storage\.dev_server.pid"
set "LOG_FILE=%PROJECT_DIR%\logs\dev_server.log"
set "HOST=0.0.0.0"
set "PORT=8000"

REM 创建日志目录
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

REM 主命令
if "%1"=="" goto help
if "%1"=="start" goto start
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="status" goto status
if "%1"=="logs" goto logs
if "%1"=="-h" goto help
if "%1"=="--help" goto help
goto help

:start
REM 检查是否已运行
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *main.py*" 2>nul | find "python.exe" >nul
if %errorlevel%==0 (
    echo 服务已在运行中
    goto end
)

echo 正在启动服务...
echo 项目目录: %PROJECT_DIR%
echo 访问地址: http://localhost:%PORT%
echo API文档: http://localhost:%PORT%/docs
echo.

REM 启动服务
start "myaps_api_server" /min python main.py
timeout /t 3 /nobreak >nul

REM 检查是否启动成功
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find "python.exe" >nul
if %errorlevel%==0 (
    echo ✓ 服务启动成功
    echo 日志目录: %PROJECT_DIR%\logs
) else (
    echo ✗ 服务启动失败
)
goto end

:stop
echo 正在停止服务...

REM 方式1: 通过窗口标题关闭
taskkill /FI "WINDOWTITLE eq myaps_api_server*" /F >nul 2>&1

REM 方式2: 通过命令行参数匹配关闭
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr "PID:"') do (
    wmic process where "ProcessId=%%i and CommandLine like '%%main.py%%'" delete >nul 2>&1
)

timeout /t 2 /nobreak >nul
echo ✓ 服务已停止
goto end

:restart
call :stop
timeout /t 1 /nobreak >nul
call :start
goto end

:status
echo 检查服务状态...
echo.

REM 检查进程
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find "python.exe" >nul
if %errorlevel%==0 (
    echo ✓ 服务运行中
    echo   访问地址: http://localhost:%PORT%
    echo   API文档: http://localhost:%PORT%/docs
    echo.
    echo 进程信息:
    tasklist /FI "IMAGENAME eq python.exe" /FO TABLE
) else (
    echo ✗ 服务未运行
)
goto end

:logs
if not exist "%LOG_FILE%" (
    echo 日志文件不存在: %LOG_FILE%
    echo.
    echo 提示: 日志默认输出到控制台，请查看运行窗口
    goto end
)

echo 最近50行日志:
echo ----------------------------------------
type "%LOG_FILE%" | more
goto end

:help
echo.
echo 用法: %~nx0 {start^|stop^|restart^|status^|logs}
echo.
echo 命令:
echo   start   - 启动服务
echo   stop    - 停止服务
echo   restart - 重启服务
echo   status  - 查看服务状态
echo   logs    - 查看日志
echo.
echo 示例:
echo   %~nx0 start
echo   %~nx0 status
echo.
goto end

:end
endlocal
