@echo off
setlocal

:menu
cls
echo ========================================
echo   🔧 Monitor Models - 全功能迁移工具
echo ========================================
echo.
echo  默认选项 [1] 会自动完成所有迁移操作，无需手动选择
echo.
echo  请选择要执行的操作:
echo.
echo    [1] 🚀 智能自动迁移 (推荐)
echo        - 自动备份数据库
echo        - 自动创建缺失的表
echo        - 自动添加缺失的字段
echo        - 保留现有数据
echo        - 一键完成，无需干预
echo.
echo    [2] 使用 Tortoise 直接生成表
echo        - 仅创建不存在的表，不修改现有表
echo.
echo    [3] 使用 Aerich 迁移系统
echo        - 标准 aerich 流程，支持版本回滚
echo.
echo    [4] 重置所有迁移 (aerich)
echo        - 删除 migrations 文件夹，重新初始化
echo.
echo    [5] 仅备份数据库
echo        - 只备份，不执行迁移
echo.
echo    [Q] 退出
echo.
echo ========================================
set /p choice="请输入选项 (默认: 1): "

if /i "%choice%"=="" goto :auto_migrate
if /i "%choice%"=="1" goto :auto_migrate
if /i "%choice%"=="2" goto :tortoise
if /i "%choice%"=="3" goto :aerich
if /i "%choice%"=="4" goto :reset
if /i "%choice%"=="5" goto :backup_only
if /i "%choice%"=="Q" goto :end
if /i "%choice%"=="q" goto :end

echo [ERROR] 无效选项，请重新选择
pause
goto :menu

:backup_only
echo.
echo ========================================
echo  [5] 仅备份数据库
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [Step 1] 检查数据库文件...
if not exist "storage\%SQLITE_FILE%.sqlite3" (
    echo [ERROR] 数据库文件不存在: storage\%SQLITE_FILE%.sqlite3
    pause
    goto :end
)

echo [OK] 数据库文件存在

echo.
echo [Step 2] 创建备份...
set "BACKUP_DIR=backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
set "BACKUP_FILE=%BACKUP_DIR%\%SQLITE_FILE%_%TIMESTAMP%.sqlite3"

copy "storage\%SQLITE_FILE%.sqlite3" "%BACKUP_FILE%"
if errorlevel 1 (
    echo [ERROR] 备份失败
    pause
    goto :end
)

echo [OK] 备份成功: %BACKUP_FILE%

echo.
echo ========================================
echo  ✅ 数据库备份完成!
echo ========================================
goto :end

:auto_migrate
echo.
echo ========================================
echo  [1] 🚀 智能自动迁移
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [INFO] 正在自动执行迁移，请稍候...
echo.

venv\Scripts\python.exe scripts\migrate\auto_migrate.py
if errorlevel 1 goto :error

goto :success

:tortoise
echo.
echo ========================================
echo  [2] 使用 Tortoise 直接生成表
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [INFO] 此选项仅创建不存在的表，不会修改现有表结构

echo.
venv\Scripts\python.exe scripts\migrate\migrate_with_tortoise.py
if errorlevel 1 goto :error
goto :success

:aerich
echo.
echo ========================================
echo  [3] 使用 Aerich 迁移系统
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [Step 1] 检查 aerich 配置...
if exist "migrations\monitor_models" (
    echo [OK] Migration folder already exists
) else (
    echo [INFO] Initializing aerich...
    venv\Scripts\python.exe -m aerich init -t scripts.migrate.migrate_with_tortoise.monitor_orm_config
    if errorlevel 1 (
        echo [WARN] Init failed, continuing...
    )
)

echo.
echo [Step 2] 初始化数据库...
venv\Scripts\python.exe -m aerich init-db
if errorlevel 1 (
    echo [INFO] init-db may have already been run - that's ok
)

echo.
echo [Step 3] 生成迁移文件...
set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
venv\Scripts\python.exe -m aerich migrate --name "auto_migrate_%TIMESTAMP%"
if errorlevel 1 (
    echo [INFO] No new migrations found - database is up to date
    goto :skip_upgrade
)

echo.
echo [Step 4] 执行数据库升级...
venv\Scripts\python.exe -m aerich upgrade
if errorlevel 1 goto :error

goto :success

:skip_upgrade
echo.
echo ========================================
echo  ℹ️  No changes to migrate - already up to date
echo ========================================
goto :end

:reset
echo.
echo ========================================
echo  [4] 重置所有迁移 (aerich)
echo ========================================
echo.
echo [WARNING] This will delete all existing aerich migrations!
echo [INFO] 数据库数据不会被删除

choice /C YN /M "Are you sure you want to continue"

if errorlevel 2 (
    echo [INFO] Cancelled by user
    goto :end
)

call :setup_env
if errorlevel 1 goto :end

echo.
echo [1/3] Deleting migrations folder...
if exist "migrations\monitor_models" (
    rmdir /s /q "migrations\monitor_models"
    echo [OK] migrations\monitor_models deleted
) else (
    echo [INFO] migrations\monitor_models does not exist
)

if exist "migrations" (
    for /d %%d in (migrations\*) do rmdir /s /q "%%d"
    echo [OK] All migration folders deleted
)

echo.
echo [2/3] Re-initializing aerich...
venv\Scripts\python.exe -m aerich init -t scripts.migrate.migrate_with_tortoise.monitor_orm_config
if errorlevel 1 goto :error
echo [OK] Aerich initialized

echo.
echo [3/3] Running init-db...
venv\Scripts\python.exe -m aerich init-db
if errorlevel 1 (
    echo [WARN] init-db may have failed, but continue...
)

echo.
echo ========================================
echo  ✅ Migrations reset successfully!
echo ========================================
echo.
echo Now you can run this script again and choose option [1], [2] or [3]
goto :end

:setup_env
cd /d "%~dp0\..\.."
set "PROJECT_DIR="
set "SQLITE_FILE=local_data"

for /f "tokens=2 delims==" %%a in ('findstr "^PROJECT_DIR=" "%~dp0\..\..\.env"') do set "PROJECT_DIR=%%a"
for /f "tokens=2 delims==" %%a in ('findstr "^SQLITE_FILE=" "%~dp0\..\..\.env"') do set "SQLITE_FILE=%%a"

if "%PROJECT_DIR%"=="" (
    echo [ERROR] PROJECT_DIR not found in .env file
    pause
    exit /b 1
)

setx PROJECT_DIR "%PROJECT_DIR%" >nul 2>&1
set PROJECT_DIR=%PROJECT_DIR%

rem 清理 SQLITE_FILE 中的 .sqlite3 后缀
set "SQLITE_FILE=%SQLITE_FILE:.sqlite3=%"

echo Project Directory: %PROJECT_DIR%
echo SQLite File: %SQLITE_FILE%

if not exist "storage" (
    echo [INFO] Creating storage directory...
    mkdir storage
    if errorlevel 1 (
        echo [ERROR] Failed to create storage directory
        pause
        exit /b 1
    )
    echo [OK] Storage directory created
)

exit /b 0

:success
echo.
echo ========================================
echo  ✅ Operation completed successfully!
echo ========================================
goto :end

:error
echo.
echo ========================================
echo  ❌ Operation failed!
echo ========================================
pause
exit /b 1

:end
echo.
pause