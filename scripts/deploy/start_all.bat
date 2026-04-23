@echo off
echo Starting all services...

REM 启动 binlog 监听器
start /b python binlog_listener_service.py

REM 等待监听器启动
timeout /t 5

REM 启动应用
gunicorn -c gunicorn.conf.py main:app