@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM Load environment variables from .env file
for /f "usebackq tokens=*" %%a in (".env") do (
    set "line=%%a"
    set "firstchar=!line:~0,1!"
    if not "!firstchar!"=="#" if not "!line!"=="" (
        for /f "tokens=1,2 delims==" %%b in ("%%a") do (
            set "%%b=%%c"
        )
    )
)

REM Configuration (defaults if not set in .env)
if "%PORT%"=="" set PORT=8000
if "%HOST%"=="" set HOST=0.0.0.0
set APP=main:app
set LOG_FILE=logs\fastapi_server.log

REM Command line arguments support (highest priority)
if not "%~1"=="" set PORT=%~1

REM Set PORT as environment variable so the application uses it
set "PORT=%PORT%"

REM Find Python
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    echo Using virtual Python
) else (
    set PYTHON=python
    echo Using system Python
)

REM Create logs directory if it doesn't exist
mkdir logs 2>nul
echo [INFO] Logs directory ensured

REM Display configuration
echo FastAPI Server Starting...
echo Port: %PORT%, Host: %HOST%
echo Press Ctrl+C to stop gracefully
echo.

REM Setup logging
echo %date% %time% - Server starting on port %PORT% >> %LOG_FILE%

REM Port check and cleanup
echo Checking if port %PORT% is available...
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%PORT%"') do (
    echo [WARNING] Found process %%i using port %PORT%
    echo %date% %time% - Found process %%i using port %PORT% >> %LOG_FILE%
    echo Killing process %%i...
    taskkill /F /PID %%i >nul 2>&1
    echo %date% %time% - Killed process %%i >> %LOG_FILE%
)
timeout /t 3 /nobreak >nul

REM Verify port is available
netstat -ano | findstr ":%PORT%"
if %errorlevel% equ 0 (
    echo [ERROR] Port %PORT% is still in use!
    echo %date% %time% - Port %PORT% is still in use! >> %LOG_FILE%
    pause
    exit /b 1
) else (
    echo [INFO] Port %PORT% is available for use
    echo %date% %time% - Port %PORT% is available >> %LOG_FILE%
)

REM Set environment variables
set "ENV_FILE=.env"
set "PYTHONPATH=%CD%"

REM Load .env file if it exists, but preserve PORT from command line
set "SAVED_PORT=%PORT%"
if exist %ENV_FILE% (
    echo Loading environment variables from .env file...
    for /f "tokens=1,2 delims==" %%a in (%ENV_FILE%) do (
        if not "%%a"=="PORT" set "%%a=%%b"
    )
)

REM Restore PORT from command line
set "PORT=%SAVED_PORT%"

REM Start the application using uvicorn with explicit parameters
echo Starting uvicorn server with host %HOST% and port %PORT%...
echo %date% %time% - Starting uvicorn server with host %HOST% and port %PORT% >> %LOG_FILE%

REM Run the application with explicit parameters to override any environment settings
REM Use the same log level as in main.py
REM access-log is disabled by default in main.py
%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port %PORT% --log-level debug

REM Handle error codes
if %errorlevel% neq 0 (
    echo [ERROR] Application failed to start with error code %errorlevel%
    echo %date% %time% - Application failed to start with error code %errorlevel% >> %LOG_FILE%
    pause
    exit /b %errorlevel%
)

REM Handle cleanup after Ctrl+C
echo.
echo Server shutting down...
echo %date% %time% - Server shutting down >> %LOG_FILE%

echo Cleaning up any remaining processes on port %PORT%...
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%PORT%"') do (
    taskkill /F /PID %%i >nul 2>&1
    echo Killed process %%i
    echo %date% %time% - Killed process %%i during cleanup >> %LOG_FILE%
)

echo Shutdown complete.
echo %date% %time% - Server shutdown complete >> %LOG_FILE%
echo.
exit /b 0