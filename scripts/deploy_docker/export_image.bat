@echo off
chcp 65001 >nul
echo ========================================
echo   MyAPS Docker Export Script
echo ========================================
echo.

cd /d "%~dp0"

set EXPORT_DIR=..\..\docker_images
set DATETIME=%date:~0,4%%date:~5,2%%date:~8,2%
set ALL_SUCCESS=true

if not exist "%EXPORT_DIR%" mkdir "%EXPORT_DIR%"

echo Exporting myaps_api:latest ...
docker save -o "%EXPORT_DIR%\myaps_api_%DATETIME%.tar" myaps_api:latest
if %errorlevel% neq 0 (
    echo [ERROR] Failed to export myaps_api!
    set ALL_SUCCESS=false
)

echo.
echo Exporting postgres:15-alpine ...
docker save -o "%EXPORT_DIR%\postgres_15-alpine_%DATETIME%.tar" postgres:15-alpine
if %errorlevel% neq 0 (
    echo [WARNING] Failed to export postgres, skipping...
    set ALL_SUCCESS=false
)

echo.
echo Exporting redis:7-alpine ...
docker save -o "%EXPORT_DIR%\redis_7-alpine_%DATETIME%.tar" redis:7-alpine
if %errorlevel% neq 0 (
    echo [WARNING] Failed to export redis, skipping...
    set ALL_SUCCESS=false
)

echo.
echo Exporting nginx:alpine ...
docker save -o "%EXPORT_DIR%\nginx_alpine_%DATETIME%.tar" nginx:alpine
if %errorlevel% neq 0 (
    echo [WARNING] Failed to export nginx, skipping...
    set ALL_SUCCESS=false
)

echo.
echo ========================================
if "%ALL_SUCCESS%"=="true" (
    echo   Export completed!
) else (
    echo   Export completed with warnings!
)
echo ========================================
echo.
echo Export directory: %EXPORT_DIR%
echo Files:
dir /b "%EXPORT_DIR%\*.tar" 2>nul || echo (empty)
echo.
echo Next steps:
echo   1. Copy %EXPORT_DIR% to internal Ubuntu server
echo   2. Run import_image.sh on server: chmod +x import_image.sh && ./import_image.sh
echo.
pause