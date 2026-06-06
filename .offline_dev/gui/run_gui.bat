@echo off
chcp 65001 >nul
REM MyAPS API - 离线迁移工具启动脚本 (Windows)
cd /d "%~dp0.."
echo Starting MyAPS API Offline Migration Tool...
python gui/main.py
if %errorlevel% neq 0 (
    echo.
    echo Error: Failed to start GUI.
    echo Please ensure Python is installed and in your PATH.
    echo.
    pause
)
