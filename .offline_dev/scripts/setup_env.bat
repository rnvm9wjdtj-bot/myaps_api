@echo off
chcp 65001 >nul
REM ============================================================
REM MyAPS API - 环境配置向导 (内网 Windows 机器执行)
REM ============================================================
REM 用途: 交互式生成 .env 配置文件
REM ============================================================

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
cd /d "%PROJECT_ROOT%"

set "ENV_FILE=%PROJECT_ROOT%\.env"
set "ENV_EXAMPLE=%PROJECT_ROOT%\.env.example"

echo.
echo ========================================
echo   MyAPS API 环境配置向导
echo ========================================
echo.

REM 检查 .env.example
echo [1/4] 检查环境模板...
if not exist "%ENV_EXAMPLE%" (
    echo 错误: 未找到 .env.example
    pause
    exit /b 1
)
echo   模板文件: %ENV_EXAMPLE%

REM 备份现有 .env
echo [2/4] 备份现有配置...
if exist "%ENV_FILE%" (
    copy /Y "%ENV_FILE%" "%ENV_FILE%.backup.%date:~0,4%%date:~5,2%%date:~8,2%" >nul
    echo   已备份到: %ENV_FILE%.backup.%date:~0,4%%date:~5,2%%date:~8,2%
)

REM 复制模板
copy /Y "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
echo   已创建: %ENV_FILE%

REM 交互式配置
echo [3/4] 配置环境变量...
echo.
echo 请根据内网环境填写以下配置（直接回车使用默认值）:
echo.

REM 应用端口
set /p "APP_PORT=应用端口 [8000]: "
if "!APP_PORT!"=="" set "APP_PORT=8000"

REM MySQL配置
set /p "MYSQL_HOST=MySQL 主机地址 [localhost]: "
if "!MYSQL_HOST!"=="" set "MYSQL_HOST=localhost"

set /p "MYSQL_PORT=MySQL 端口 [3306]: "
if "!MYSQL_PORT!"=="" set "MYSQL_PORT=3306"

set /p "MYSQL_USER=MySQL 用户名 [root]: "
if "!MYSQL_USER!"=="" set "MYSQL_USER=root"

set /p "MYSQL_PASSWORD=MySQL 密码: "
if "!MYSQL_PASSWORD!"=="" set "MYSQL_PASSWORD=your_password"

set /p "MYSQL_DB_SET=数据库列表（逗号分隔）[db1,db2]: "
if "!MYSQL_DB_SET!"=="" set "MYSQL_DB_SET=db1,db2"

set /p "MYSQL_MAIN_DB=主数据库 [db1]: "
if "!MYSQL_MAIN_DB!"=="" set "MYSQL_MAIN_DB=db1"

REM PostgreSQL配置
echo.
echo PostgreSQL 配置（用于数据清洗，可选）:
set /p "PG_HOST=PostgreSQL 主机地址 [localhost]: "
if "!PG_HOST!"=="" set "PG_HOST=localhost"

set /p "PG_PORT=PostgreSQL 端口 [5432]: "
if "!PG_PORT!"=="" set "PG_PORT=5432"

set /p "PG_USER=PostgreSQL 用户名 [postgres]: "
if "!PG_USER!"=="" set "PG_USER=postgres"

set /p "PG_PASSWORD=PostgreSQL 密码: "
if "!PG_PASSWORD!"=="" set "PG_PASSWORD=your_password"

set /p "PG_DB=PostgreSQL 数据库名 [appsmith]: "
if "!PG_DB!"=="" set "PG_DB=appsmith"

REM Redis配置
echo.
echo Redis 配置:
set /p "REDIS_HOST=Redis 主机地址 [127.0.0.1]: "
if "!REDIS_HOST!"=="" set "REDIS_HOST=127.0.0.1"

set /p "REDIS_PORT=Redis 端口 [6379]: "
if "!REDIS_PORT!"=="" set "REDIS_PORT=6379"

REM 项目配置
echo.
echo 项目配置:
set /p "PROJECT_DIR=租户项目目录 [HACYXS]: "
if "!PROJECT_DIR!"=="" set "PROJECT_DIR=HACYXS"

set /p "PROJECT_JSON=配置文件名 [dev]: "
if "!PROJECT_JSON!"=="" set "PROJECT_JSON=dev"

REM 写入配置
echo [4/4] 写入配置...
(
echo # MyAPS API 环境变量配置
echo # 生成时间: %date% %time%
echo.
echo # 应用配置
echo PORT=!APP_PORT!
echo HOST=0.0.0.0
echo LOG_LEVEL=INFO
echo TIMEZONE=+8
echo.
echo # 项目目录配置
echo PROJECT_DIR=!PROJECT_DIR!
echo PROJECT_JSON=!PROJECT_JSON!
echo.
echo # 数据库配置 - MySQL
echo MYAPS_DB_HOST=!MYSQL_HOST!
echo MYAPS_DB_PORT=!MYSQL_PORT!
echo MYAPS_DB_USER=!MYSQL_USER!
echo MYAPS_DB_PASSWORD=!MYSQL_PASSWORD!
echo MYAPS_DB_SET=!MYSQL_DB_SET!
echo MYAPS_MAIN_DB=!MYSQL_MAIN_DB!
echo.
echo # 数据库配置 - PostgreSQL
echo THIS_DB_HOST=!PG_HOST!
echo THIS_DB_PORT=!PG_PORT!
echo THIS_DB_USER=!PG_USER!
echo THIS_DB_PASSWORD=!PG_PASSWORD!
echo THIS_DB_NAME=!PG_DB!
echo.
echo # Redis配置
echo REDIS_HOST=!REDIS_HOST!
echo REDIS_PORT=!REDIS_PORT!
echo REDIS_DB=0
echo REDIS_PASSWORD=
echo.
echo # 功能开关
echo TURNON_BINLOG_LISTENER=false
echo TRUNON_SCHEDULER=false
echo.
echo # 日志配置
echo LOG_LEVEL=INFO
echo LOG_DIR=logs
echo TO_CONSOLE=true
echo TO_FILE=true
echo TO_DATABASE=true
echo TO_WEBSOCKET=true
echo.
echo # 旧版兼容
echo USE_UNIFIED_LOGGER=true
) > "%ENV_FILE%"

echo   配置已写入: %ENV_FILE%
echo.
echo ========================================
echo   配置完成!
echo ========================================
echo.
echo 请检查配置是否正确，然后运行:
echo   scripts\dev_server.bat start
echo.
pause
