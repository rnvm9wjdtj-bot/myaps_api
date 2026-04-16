@echo off

REM 设置项目目录
set PROJECT_DIR=JYHDXS

REM 显示当前设置
echo Project Directory: %PROJECT_DIR%
echo Starting database migration...

REM 使用完整路径运行 Python
"%~dp0\..\..\venv\Scripts\python.exe" -m aerich init -t core.database.TORTOISE_ORM

"%~dp0\..\..\venv\Scripts\python.exe" -m aerich migrate --name monitor_models

"%~dp0\..\..\venv\Scripts\python.exe" -m aerich upgrade

echo Database migration completed!
pause
