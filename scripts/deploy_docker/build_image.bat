@echo off
chcp 65001 >nul
echo ========================================
echo   MyAPS Docker Build Script
echo ========================================
echo.

cd /d "%~dp0..\.."

echo [1/2] Building myaps_api image...
docker build -t myaps_api:latest .

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to build application image!
    pause
    exit /b 1
)

echo.
echo [2/2] Pulling base service images...
docker-compose -f scripts/deploy_docker/docker-compose.yml pull postgres redis nginx

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Some base images failed to pull, check network connection
)

echo.
echo ========================================
echo   Build completed!
echo ========================================
echo.
echo Images:
docker images | findstr myaps
echo.
echo Next steps:
echo   1. Run export_image.bat to export images
echo   2. Copy image files to internal Ubuntu server
echo   3. Run import_image.sh on server
echo.
pause