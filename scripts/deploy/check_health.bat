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
set "TIMEOUT_SECONDS=10"
set "RETRY_COUNT=3"
set "RETRY_INTERVAL=5"

echo ================================================================================
echo                          MyAPS_API Health Check Tool
echo ================================================================================
echo.
echo Using service name: %SERVICE_NAME%
echo Health check URL: %HEALTH_CHECK_URL%
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
    echo [WARN] Service "%SERVICE_NAME%" is not running!
    echo.
    echo Starting service automatically...
    echo.
    nssm start "%SERVICE_NAME%"
    if %errorLevel% neq 0 (
        echo [ERROR] Failed to start service!
        pause
        exit /b 1
    )
    echo Waiting for service to start...
    timeout /t 10 /nobreak >nul
)
echo Service is running.
echo.

:HEALTH_CHECK
echo -------------------------------------------------------------------------------
echo Performing HTTP health check...
echo Target URL: %HEALTH_CHECK_URL%
echo Timeout: %TIMEOUT_SECONDS% seconds
echo Retry count: %RETRY_COUNT%
echo -------------------------------------------------------------------------------
echo.

set "SUCCESS_COUNT=0"
set "FAIL_COUNT=0"

for /L %%i in (1,1,%RETRY_COUNT%) do (
    echo [Attempt %%i/%RETRY_COUNT%] Checking health endpoint...
    
    powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "
        $startTime = Get-Date
        try {
            $response = Invoke-WebRequest -Uri '%HEALTH_CHECK_URL%' -Method GET -TimeoutSec %TIMEOUT_SECONDS% -UseBasicParsing
            $endTime = Get-Date
            $duration = ($endTime - $startTime).TotalMilliseconds
            Write-Host '[SUCCESS] HTTP ' $response.StatusCode ' - Response time: ' $duration 'ms'
            exit 0
        } catch {
            $endTime = Get-Date
            $duration = ($endTime - $startTime).TotalMilliseconds
            Write-Host '[FAIL] ' $_.Exception.Message ' (Time: ' $duration 'ms)'
            exit 1
        }
    "
    
    if !errorLevel! equ 0 (
        set /a SUCCESS_COUNT+=1
        echo [OK] Health check passed
    ) else (
        set /a FAIL_COUNT+=1
        echo [FAIL] Health check failed
    )
    echo.
    
    if %%i lss %RETRY_COUNT% (
        echo Waiting %RETRY_INTERVAL% seconds before next attempt...
        timeout /t %RETRY_INTERVAL% /nobreak >nul
    )
)

echo ================================================================================
echo                              Health Check Summary
echo ================================================================================
echo.
echo Total attempts: %RETRY_COUNT%
echo Passed: %SUCCESS_COUNT%
echo Failed: %FAIL_COUNT%
echo.

if %FAIL_COUNT% equ 0 (
    echo [SUCCESS] All health checks passed!
    echo Service is operating normally.
    echo.
    exit /b 0
) else (
    if %SUCCESS_COUNT% gtr 0 (
        echo [WARNING] Some health checks failed, but some passed
        echo Service may be experiencing intermittent issues.
        echo Consider checking logs: %PROJECT_ROOT%\logs
        echo.
        exit /b 1
    ) else (
        echo [CRITICAL] All health checks failed!
        echo.
        echo Possible issues:
        echo 1. Service process is running but not responding to requests
        echo 2. Port 8000 may be blocked
        echo 3. Application may be in a deadlock state
        echo.
        echo Taking action: Attempting to restart service...
        echo.
        
        echo Stopping service...
        nssm stop "%SERVICE_NAME%"
        timeout /t 3 /nobreak >nul
        
        echo Starting service...
        nssm start "%SERVICE_NAME%"
        
        if !errorLevel! equ 0 (
            echo Service restarted successfully.
            echo Waiting 15 seconds for service to initialize...
            timeout /t 15 /nobreak >nul
            
            echo.
            echo Verifying service after restart...
            powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "
                try {
                    $response = Invoke-WebRequest -Uri '%HEALTH_CHECK_URL%' -Method GET -TimeoutSec %TIMEOUT_SECONDS% -UseBasicParsing
                    Write-Host '[SUCCESS] Service is responding after restart'
                    exit 0
                } catch {
                    Write-Host '[FAIL] Service still not responding after restart'
                    Write-Host 'Please check logs: %PROJECT_ROOT%\logs'
                    exit 1
                }
            "
            
            if !errorLevel! equ 0 (
                echo.
                echo [OK] Service recovered successfully!
                exit /b 0
            ) else (
                echo.
                echo [CRITICAL] Service failed to recover!
                echo Please manually check the service status and logs.
                pause
                exit /b 1
            )
        ) else (
            echo [CRITICAL] Failed to restart service!
            echo Please check service configuration and logs.
            pause
            exit /b 1
        )
    )
)