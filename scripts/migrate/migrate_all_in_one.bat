@echo off
setlocal

:menu
cls
echo ========================================
echo   🔧 Monitor Models - 全功能迁移工具
echo ========================================
echo.
echo  请选择要执行的操作:
echo.
echo    [1] 使用 Tortoise 直接生成表 (推荐)
echo        - 最可靠，不依赖 aerich
echo        - 直接调用 generate_schemas()
echo.
echo    [2] 使用 Aerich 迁移系统
echo        - 标准 aerich 流程
echo        - 支持版本回滚
echo.
echo    [3] 重置所有迁移 (aerich)
echo        - 删除 migrations 文件夹
echo        - 重新初始化
echo.
echo    [Q] 退出
echo.
echo ========================================
set /p choice="请输入选项 (1/2/3/Q): "

if /i "%choice%"=="1" goto :tortoise
if /i "%choice%"=="2" goto :aerich
if /i "%choice%"=="3" goto :reset
if /i "%choice%"=="Q" goto :end
if /i "%choice%"=="q" goto :end

echo [ERROR] 无效选项，请重新选择
pause
goto :menu

:tortoise
echo.
echo ========================================
echo  [1] 使用 Tortoise 直接生成表
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
venv\Scripts\python.exe scripts\migrate\migrate_with_tortoise.py
if errorlevel 1 goto :error
goto :success

:aerich
echo.
echo ========================================
echo  [2] 使用 Aerich 迁移系统
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
echo  [3] 重置所有迁移 (aerich)
echo ========================================
echo.
echo [WARNING] This will delete all existing aerich migrations!
echo.
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
echo Now you can run this script again and choose option [2]
goto :end

:setup_env
cd /d "%~dp0\..\.."
set "PROJECT_DIR="
for /f "tokens=2 delims==" %%a in ('findstr "^PROJECT_DIR=" "%~dp0\..\..\.env"') do set "PROJECT_DIR=%%a"

if "%PROJECT_DIR%"=="" (
    echo [ERROR] PROJECT_DIR not found in .env file
    pause
    exit /b 1
)

setx PROJECT_DIR "%PROJECT_DIR%" >nul 2>&1
set PROJECT_DIR=%PROJECT_DIR%

echo Project Directory: %PROJECT_DIR%

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
echo  ✅ Migration completed successfully!
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
