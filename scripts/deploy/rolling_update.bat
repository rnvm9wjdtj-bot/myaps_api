@echo off
setlocal enabledelayedexpansion

chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
set "ENV_FILE=%PROJECT_ROOT%\.env"

if exist "%ENV_FILE%" (
    for /f "tokens=1,2 delims==" %%a in ('findstr /C:"SERVICE_DAEMON_NAME" "%ENV_FILE%"') do (
        set "SERVICE_DAEMON_NAME=%%b"
        set "SERVICE_DAEMON_NAME=!SERVICE_DAEMON_NAME: =!"
    )
)

if "%SERVICE_DAEMON_NAME%"=="" (
    set "SERVICE_NAME=MyAPS_API"
) else (
    set "SERVICE_NAME=%SERVICE_DAEMON_NAME%"
)

rem Read PROTOCOL and PORT from .env file
set "PROTOCOL=http://"
set "PORT=8000"
if exist "%ENV_FILE%" (
    for /f "tokens=1,2 delims==" %%a in ('findstr /C:"PROTOCOL" "%ENV_FILE%"') do (
        set "PROTOCOL=%%b"
        set "PROTOCOL=!PROTOCOL: =!"
    )
    for /f "tokens=1,2 delims==" %%a in ('findstr /C:"PORT" "%ENV_FILE%"') do (
        set "PORT=%%b"
        set "PORT=!PORT: =!"
    )
)

rem Construct health check URL
set "HEALTH_CHECK_URL=%PROTOCOL%127.0.0.1:%PORT%/health"
set "GRACEFUL_TIMEOUT=30"
set "MAX_WAIT=60"

echo ================================================================================
echo                          MyAPS_API Rolling Update Tool
echo ================================================================================
echo.
echo This tool performs a graceful restart to minimize downtime during updates.
echo.
echo Using service name: %SERVICE_NAME%
echo Health check URL: %HEALTH_CHECK_URL%

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARN] Not running as administrator. Some features may not work.
    echo.
)

echo Checking service status...
echo.

nssm status "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Service "%SERVICE_NAME%" is not installed!
    echo Please install the service first using simple_deploy.bat option 1.
    echo.
    pause
    exit /b 1
)

nssm status "%SERVICE_NAME%" | findstr "Running" >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Service "%SERVICE_NAME%" is not running!
    echo Please start the service first using simple_deploy.bat option 2.
    echo.
    pause
    exit /b 1
)
echo Service is running.
echo.

:CONFIRM_UPDATE
echo -------------------------------------------------------------------------------
echo                          Rolling Update Procedure
echo -------------------------------------------------------------------------------
echo.
echo This operation will:
echo 1. Send graceful stop signal to service
echo 2. Wait for current requests to complete (max %GRACEFUL_TIMEOUT% seconds)
echo 3. Start service again
echo 4. Verify service health
echo.
echo During the update:
echo - Incoming requests may be queued or rejected briefly
echo - Active connections will be handled gracefully
echo.
set "CONFIRM="
set /p CONFIRM=Continue with rolling update? (Y/N):
if /i not "%CONFIRM%"=="Y" (
    echo Update cancelled.
    echo.
    pause
    exit /b 0
)
echo.

:PERFORM_UPDATE
echo ================================================================================
echo                          Step 1: Graceful Stop
echo ================================================================================
echo.
echo Sending stop signal to service...
echo.

nssm stop "%SERVICE_NAME%"
if %errorLevel% neq 0 (
    echo [ERROR] Failed to send stop signal to service!
    echo.
    pause
    exit /b 1
)
echo Stop signal sent successfully.
echo Waiting for graceful shutdown (max %GRACEFUL_TIMEOUT% seconds)...
echo.

set "WAIT_COUNT=0"
:WAIT_LOOP
timeout /t 1 /nobreak >nul
set /a WAIT_COUNT+=1

nssm status "%SERVICE_NAME%" | findstr "Running" >nul 2>&1
if %errorLevel% neq 0 (
    echo Service stopped gracefully.
    goto :START_SERVICE
)

if %WAIT_COUNT% lss %GRACEFUL_TIMEOUT% (
    if %WAIT_COUNT% equ 10 (
        echo Still waiting... (%WAIT_COUNT%/%GRACEFUL_TIMEOUT% seconds)
    )
    if %WAIT_COUNT% equ 20 (
        echo Still waiting... (%WAIT_COUNT%/%GRACEFUL_TIMEOUT% seconds)
    )
    if %WAIT_COUNT% equ 30 (
        echo Still waiting... (%WAIT_COUNT%/%GRACEFUL_TIMEOUT% seconds)
    )
    goto :WAIT_LOOP
)

echo.
echo [WARN] Graceful shutdown timeout. Forcing stop...
nssm stop "%SERVICE_NAME%" /force
timeout /t 2 /nobreak >nul

:START_SERVICE
echo.
echo ================================================================================
echo                          Step 2: Start Service
echo ================================================================================
echo.
echo Starting service...
echo.

nssm start "%SERVICE_NAME%"
if %errorLevel% neq 0 (
    echo [ERROR] Failed to start service!
    echo.
    echo Please check:
    echo 1. Service configuration
    echo 2. Log files: %PROJECT_ROOT%\logs
    echo.
    pause
    exit /b 1
)
echo Service start command sent.
echo.

:VERIFY_SERVICE
echo ================================================================================
echo                          Step 3: Verify Service
echo ================================================================================
echo.
echo Waiting for service to initialize...
timeout /t 5 /nobreak >nul

echo Performing health check...
set "HEALTH_OK=0"
set "WAIT_COUNT=0"

:HEALTH_WAIT_LOOP
timeout /t 3 /nobreak >nul
set /a WAIT_COUNT+=3

powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "
    try {
        $response = Invoke-WebRequest -Uri '%HEALTH_CHECK_URL%' -Method GET -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Host '[OK] Health check passed'
            exit 0
        } else {
            Write-Host '[WARN] Unexpected status code:' $response.StatusCode
            exit 1
        }
    } catch {
        Write-Host '[WAIT] Service not ready yet...'
        exit 1
    }
"

if !errorLevel! equ 0 (
    set "HEALTH_OK=1"
    goto :UPDATE_SUCCESS
)

if %WAIT_COUNT% lss %MAX_WAIT% (
    echo Waiting for service... (%WAIT_COUNT%/%MAX_WAIT% seconds)
    goto :HEALTH_WAIT_LOOP
)

:UPDATE_SUCCESS
echo.
echo ================================================================================
echo                          Rolling Update Complete
echo ================================================================================
echo.

if %HEALTH_OK% equ 1 (
    echo [SUCCESS] Rolling update completed successfully!
    echo.
    echo Service is running and responding to requests.
) else (
    echo [WARNING] Rolling update completed, but health check is pending.
    echo Service may still be initializing.
    echo.
    echo Please verify service manually:
    echo 1. Check service status in simple_deploy.bat
    echo 2. Check logs: %PROJECT_ROOT%\logs
    echo 3. Access http://127.0.0.1:8000/health
    echo.
)

echo -------------------------------------------------------------------------------
echo                          Update Log
echo -------------------------------------------------------------------------------
echo Update timestamp: %date% %time%
echo Graceful stop wait time: %WAIT_COUNT% seconds
echo Health check status: %HEALTH_OK%
echo -------------------------------------------------------------------------------
echo.

pause
exit /b 0