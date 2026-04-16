@echo off
set "PROJECT_DIR="
for /f "tokens=2 delims==" %%a in ('findstr "^PROJECT_DIR=" "%~dp0\..\..\.env"') do set "PROJECT_DIR=%%a"

cd /d "%~dp0\..\.."

if "%PROJECT_DIR%"=="" (
    echo Error: PROJECT_DIR not found in .env file
    pause
    exit /b 1
)

set PROJECT_DIR=%PROJECT_DIR%

echo Project Directory: %PROJECT_DIR%
echo Starting monitor models database migration...

REM 检查是否已存在迁移文件夹，若存在则跳过初始化
if exist "migrations\monitor_models" (
    echo Migration folder already exists, skipping init...
) else (
    echo Initializing aerich for monitor_models...
    venv\Scripts\python.exe -m aerich init -t scripts.migrate.monitor_orm_config.monitor_orm_config
    if errorlevel 1 (
        echo Init failed, trying init-db anyway...
    )
)

REM 初始化数据库
echo Running init-db...
venv\Scripts\python.exe -m aerich init-db
if errorlevel 1 (
    echo init-db may have already been run, continuing...
)

REM 执行迁移
echo Running migrate...
venv\Scripts\python.exe -m aerich migrate --name monitor_models
if errorlevel 1 (
    echo Migrate failed, checking if already up to date...
)

REM 执行升级
echo Running upgrade...
venv\Scripts\python.exe -m aerich upgrade
if errorlevel 1 (
    echo Upgrade failed or already at latest version.
    goto :end
)

echo Monitor models database migration completed successfully!
:end
pause
