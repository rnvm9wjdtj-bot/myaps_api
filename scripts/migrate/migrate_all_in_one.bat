@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PYTHON_VENV_DIR=venv"

echo ========================================
echo   Monitor Models - Setup Tool
echo ========================================
echo [INFO] Current dir: %cd%
echo [INFO] Script path: %~dp0

echo.
echo [INFO] Checking required files...

if not exist "%~dp0\..\..\.env" (
    echo [ERROR] .env file not found!
    pause
    exit /b 1
)
echo [OK] .env file exists

for /f "tokens=2 delims==" %%a in ('findstr "^PYTHON_VENV_DIR=" "%~dp0\..\..\.env"') do set "PYTHON_VENV_DIR=%%a"
set "PYTHON_VENV_DIR=%PYTHON_VENV_DIR: =%"
echo [INFO] Virtual env dir: %PYTHON_VENV_DIR%

if not exist "%~dp0\..\..\%PYTHON_VENV_DIR%\Scripts\python.exe" (
    echo [ERROR] Python not found in venv!
    pause
    exit /b 1
)
echo [OK] Python exists

echo.

:menu
cls
echo ========================================
echo   Monitor Models - Migration Tool
echo ========================================
echo.
echo  Default option [1] runs auto migration
echo.
echo  Please select an operation:
echo.
echo    [1] Auto Migration (Recommended)
echo        - Backup database automatically
echo        - Create missing tables
echo        - Add missing fields
echo        - Preserve existing data
echo.
echo    [2] Create tables with Tortoise
echo        - Only create new tables
echo.
echo    [3] Reset migrations
echo        - Delete all migrations and re-init
echo.
echo    [5] Backup only
echo        - Just backup database
echo.
echo    [Q] Exit
echo.
echo ========================================
set /p choice="Enter option (default: 1): "

if /i "%choice%"=="" goto :auto_migrate
if /i "%choice%"=="1" goto :auto_migrate
if /i "%choice%"=="2" goto :tortoise
if /i "%choice%"=="3" goto :reset
if /i "%choice%"=="5" goto :backup_only
if /i "%choice%"=="Q" goto :end
if /i "%choice%"=="q" goto :end

echo [ERROR] Invalid option, please try again
pause
goto :menu

:backup_only
echo.
echo ========================================
echo  [5] Backup Only
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [Step 1] Checking database file...
if not exist "storage\%SQLITE_FILE%.sqlite3" (
    echo [ERROR] Database not found: storage\%SQLITE_FILE%.sqlite3
    pause
    goto :end
)

echo [OK] Database exists

echo.
echo [Step 2] Creating backup...
set "BACKUP_DIR=backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set "TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "TIMESTAMP=%TIMESTAMP: =0%"
set "BACKUP_FILE=%BACKUP_DIR%\%SQLITE_FILE%_%TIMESTAMP%.sqlite3"

copy "storage\%SQLITE_FILE%.sqlite3" "%BACKUP_FILE%"
if errorlevel 1 (
    echo [ERROR] Backup failed
    pause
    goto :end
)

echo [OK] Backup successful: %BACKUP_FILE%

echo.
echo ========================================
echo  Backup completed!
echo ========================================
goto :end

:auto_migrate
echo.
echo ========================================
echo  [1] Auto Migration
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [INFO] Running auto migration...
echo.

%PYTHON_VENV_DIR%\Scripts\python.exe scripts\migrate\auto_migrate.py
if errorlevel 1 goto :error

goto :success

:tortoise
echo.
echo ========================================
echo  [2] Create tables with Tortoise
echo ========================================
call :setup_env
if errorlevel 1 goto :end

echo.
echo [INFO] This option only creates new tables

echo.
%PYTHON_VENV_DIR%\Scripts\python.exe scripts\migrate\migrate_with_tortoise.py
if errorlevel 1 goto :error
goto :success

:reset
echo.
echo ========================================
echo  [3] Reset migrations
echo ========================================
echo.
echo [WARNING] This will delete all migrations!

choice /C YN /M "Are you sure"

if errorlevel 2 (
    echo [INFO] Cancelled
    goto :end
)

call :setup_env
if errorlevel 1 goto :end

echo.
echo [1/2] Deleting migrations...
if exist "migrations\monitor_models" (
    rmdir /s /q "migrations\monitor_models"
    echo [OK] Deleted
)

if exist "migrations" (
    for /d %%d in (migrations\*) do rmdir /s /q "%%d"
    echo [OK] All deleted
)

echo.
echo [2/2] Re-creating tables with Tortoise...
%PYTHON_VENV_DIR%\Scripts\python.exe scripts\migrate\migrate_with_tortoise.py
if errorlevel 1 goto :error

echo.
echo ========================================
echo  Migrations reset!
echo ========================================
goto :end

:setup_env
cd /d "%~dp0\..\.."
set "PROJECT_DIR="
set "SQLITE_FILE=local_data"

for /f "tokens=2 delims==" %%a in ('findstr "^PROJECT_DIR=" "%~dp0\..\..\.env"') do set "PROJECT_DIR=%%a"
for /f "tokens=2 delims==" %%a in ('findstr "^SQLITE_FILE=" "%~dp0\..\..\.env"') do set "SQLITE_FILE=%%a"

if "%PROJECT_DIR%"=="" (
    echo [ERROR] PROJECT_DIR not found in .env
    pause
    exit /b 1
)

setx PROJECT_DIR "%PROJECT_DIR%" >nul 2>&1
set PROJECT_DIR=%PROJECT_DIR%

set "SQLITE_FILE=%SQLITE_FILE:.sqlite3=%"

echo Project Directory: %PROJECT_DIR%
echo SQLite File: %SQLITE_FILE%

if not exist "storage" (
    echo [INFO] Creating storage...
    mkdir storage
    if errorlevel 1 (
        echo [ERROR] Failed to create storage
        pause
        exit /b 1
    )
    echo [OK] Created
)

exit /b 0

:success
echo.
echo ========================================
echo  Operation completed successfully!
echo ========================================
goto :end

:error
echo.
echo ========================================
echo  Operation failed!
echo ========================================
pause
exit /b 1

:end
echo.
pause