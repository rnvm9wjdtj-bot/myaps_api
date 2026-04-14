@echo off

rem Simple service management script
setlocal

set "SCRIPT_DIR=%~dp0"
set "NSSM_EXE=%SCRIPT_DIR%nssm.exe"
set "RUN_PS1=%SCRIPT_DIR%run.ps1"

rem Calculate project root (parent directory of scripts)
for %%i in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fi"

rem Read service name from .env file
if exist "%PROJECT_ROOT%\.env" (
    for /f "tokens=1,2 delims==" %%a in ('findstr "^SERVICE_DAEMON_NAME=" "%PROJECT_ROOT%\.env"') do (
        set "SERVICE_NAME=%%b"
    )
)

rem Set default service name if not found in .env
if "%SERVICE_NAME%"=="" set "SERVICE_NAME=MyAPS_API"

set "LOG_DIR=%PROJECT_ROOT%\logs"

rem Check if NSSM exists
if not exist "%NSSM_EXE%" (
    echo ERROR: NSSM not found at %NSSM_EXE%
    echo Please download NSSM and place it in the scripts directory
    pause
    exit /b 1
)

rem Check if run.ps1 exists
if not exist "%RUN_PS1%" (
    echo ERROR: run.ps1 not found at %RUN_PS1%
    echo Please create run.ps1 script in the scripts directory
    pause
    exit /b 1
)

rem Check admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Please run as administrator
    pause
    exit /b 1
)

:MENU
cls
echo FastAPI Service Management
echo 1. Install service
echo 2. Start service
echo 3. Stop service
echo 4. Restart service
echo 5. Uninstall service
echo 6. Check status
echo 7. Test run.ps1 (dev mode)
echo 8. Test run.ps1 (service mode)
echo 9. Clean old logs (keep 10 days)
echo 0. Exit

echo.
set /p choice=Enter choice: 

if "%choice%"=="1" goto :INSTALL
if "%choice%"=="2" goto :START
if "%choice%"=="3" goto :STOP
if "%choice%"=="4" goto :RESTART
if "%choice%"=="5" goto :UNINSTALL
if "%choice%"=="6" goto :STATUS
if "%choice%"=="7" goto :TEST_RUNPS1_DEV
if "%choice%"=="8" goto :TEST_RUNPS1_SERVICE
if "%choice%"=="9" goto :CLEAN_LOGS
if "%choice%"=="0" goto :EXIT

echo Invalid choice
pause
goto :MENU

:INSTALL
    echo Installing service...
    echo Using run.ps1: %RUN_PS1%
    echo Project root: %PROJECT_ROOT%
    
    rem Create logs directory
    if not exist "%LOG_DIR%" (
        echo Creating logs directory...
        mkdir "%LOG_DIR%"
    )
    
    echo Installing service with AppDirectory: %PROJECT_ROOT%
    "%NSSM_EXE%" install "%SERVICE_NAME%" powershell.exe
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppParameters "-ExecutionPolicy Bypass -NoProfile -File %RUN_PS1% -Mode service"
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%PROJECT_ROOT%"
    "%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%LOG_DIR%\nssm_stdout.log"
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%LOG_DIR%\nssm_stderr.log"
    
    rem Configure automatic restart on failure
    echo Configuring automatic restart settings...
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 60000
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 300000
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 1 Restart
    "%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 0 Restart
    
    echo Service installed
    echo Logs will be saved to: %LOG_DIR%
    pause
    goto :MENU

:START
    echo Starting service...
    "%NSSM_EXE%" start "%SERVICE_NAME%"
    if %errorLevel% neq 0 (
        echo ERROR: Failed to start service
        echo Possible reasons:
        echo 1. run.ps1 script has errors
        echo 2. PowerShell execution policy issues
        echo 3. Missing dependencies
        echo 4. Working directory issues
        echo.
        echo Check logs at: %LOG_DIR%
    )
    pause
    goto :MENU

:STOP
    echo Stopping service...
    "%NSSM_EXE%" stop "%SERVICE_NAME%"
    pause
    goto :MENU

:RESTART
    echo Restarting service...
    "%NSSM_EXE%" restart "%SERVICE_NAME%"
    pause
    goto :MENU

:UNINSTALL
    echo Uninstalling service...
    "%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
    "%NSSM_EXE%" remove "%SERVICE_NAME%" confirm
    pause
    goto :MENU

:STATUS
    echo Checking status...
    "%NSSM_EXE%" status "%SERVICE_NAME%"
    echo.
    echo Service configuration:
    "%NSSM_EXE%" get "%SERVICE_NAME%" AppParameters
    "%NSSM_EXE%" get "%SERVICE_NAME%" AppDirectory
    pause
    goto :MENU

:TEST_RUNPS1_DEV
    echo Testing run.ps1 script in dev mode...
    echo Running: %RUN_PS1% -Mode dev
    echo Working directory: %PROJECT_ROOT%
    echo.
    echo Output:
    echo ----------------------------------------
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File %RUN_PS1% -Mode dev
    echo ----------------------------------------
    echo.
    echo Test completed.
    echo If you see errors above, fix them before starting the service.
    pause
    goto :MENU

:TEST_RUNPS1_SERVICE
    echo Testing run.ps1 script in service mode...
    echo Running: %RUN_PS1% -Mode service
    echo Working directory: %PROJECT_ROOT%
    echo.
    echo Output:
    echo ----------------------------------------
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File %RUN_PS1% -Mode service
    echo ----------------------------------------
    echo.
    echo Test completed.
    echo If you see errors above, fix them before starting the service.
    pause
    goto :MENU

:CLEAN_LOGS
    echo Cleaning old logs...
    echo Log directory: %LOG_DIR%
    echo Keeping logs from the last 10 days...
    echo.
    
    rem Use PowerShell to clean logs older than 10 days
    powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "& {
        $logDir = '%LOG_DIR%';
        $daysToKeep = 10;
        $cutoffDate = (Get-Date).AddDays(-$daysToKeep);
        
        if (Test-Path $logDir) {
            $oldLogs = Get-ChildItem -Path $logDir -Recurse -File | Where-Object { $_.LastWriteTime -lt $cutoffDate };
            
            if ($oldLogs.Count -gt 0) {
                Write-Host "Found $($oldLogs.Count) old log files to delete:";
                $oldLogs | ForEach-Object { Write-Host "- $($_.Name) (Last modified: $($_.LastWriteTime))" };
                
                try {
                    $oldLogs | Remove-Item -Force;
                    Write-Host "Successfully deleted $($oldLogs.Count) old log files.";
                } catch {
                    Write-Host "Error deleting log files: $_" -ForegroundColor Red;
                }
            } else {
                Write-Host "No old log files found. All logs are within the last $daysToKeep days.";
            }
        } else {
            Write-Host "Log directory does not exist: $logDir" -ForegroundColor Yellow;
        }
    }"
    
    echo.
    echo Log cleaning completed.
    pause
    goto :MENU

:EXIT
echo Exiting...
pause
