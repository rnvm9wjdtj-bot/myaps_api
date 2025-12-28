@echo off
chcp 65001 >nul

echo FastAPI Simple Health Monitor Starting...
echo.

REM Setup
set PORT=8000
set HOST=0.0.0.0
set APP=main:app
set CHECK_INTERVAL=30
REM No lock file needed - using port-based locking

REM Find Python
if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    echo Using virtual Python
) else (
    set PYTHON=python
    echo Using system Python
)

echo Starting FastAPI with health monitoring...
echo Port: %PORT%, Check every %CHECK_INTERVAL% seconds
echo Press Ctrl+C to stop gracefully
echo.

REM Port-based Lock Check
echo Checking if port %PORT% is already in use...
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [ERROR] Port %PORT% is already in use
    echo Please stop existing server or kill the process manually
    echo.
    netstat -ano | findstr ":%PORT%" | findstr "LISTENING"
    echo.
    pause
    exit /b 1
) else (
    echo [INFO] Port %PORT% is available for use
)

REM Clean up existing processes
echo Cleaning up existing processes...
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%i >nul 2>&1
    echo Killed process %%i
)
timeout /t 2 /nobreak >nul

REM Start application
echo Starting application...
start "FastAPI Server" /min cmd /c "%PYTHON% -m uvicorn %APP% --host %HOST% --port %PORT%"

REM Wait for startup
echo Waiting for startup...
timeout /t 15 /nobreak >nul

echo.
echo ========================================
echo Server started - Entering health check loop
echo ========================================
echo.

REM Simple monitoring loop
:CHECK

echo [%time%] Health check...

REM Check if port is listening
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Port %PORT% not listening - restarting...
    taskkill /F /IM uvicorn.exe >nul 2>&1
    timeout /t 3 /nobreak >nul
    start "FastAPI Server" cmd /c "%PYTHON% -m uvicorn %APP% --host %HOST% --port %PORT%"
    timeout /t 15 /nobreak >nul
    goto CHECK
)

REM Check HTTP response
powershell -Command "try { Invoke-WebRequest -Uri 'http://localhost:%PORT%/' -TimeoutSec 3 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Service responding
) else (
    echo [WARNING] HTTP check failed - restarting...
    taskkill /F /IM uvicorn.exe >nul 2>&1
    timeout /t 3 /nobreak >nul
    start "FastAPI Server" cmd /c "%PYTHON% -m uvicorn %APP% --host %HOST% --port %PORT%"
    timeout /t 15 /nobreak >nul
)

echo Next check in %CHECK_INTERVAL% seconds...
echo.

REM Wait loop
set /a counter=0
:WAIT
timeout /t 1 /nobreak >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto CLEANUP
set /a counter+=1
if %counter% GEQ %CHECK_INTERVAL% goto CHECK
goto WAIT

:CLEANUP
echo.
echo ========================================
echo Ctrl+C detected - Shutting down
echo ========================================
echo.

REM Kill processes
taskkill /F /IM uvicorn.exe >nul 2>&1
for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%PORT%"') do (
    taskkill /F /PID %%i >nul 2>&1
)

REM No lock file to remove - using port-based locking

echo Shutdown complete.
echo.
exit /b 0