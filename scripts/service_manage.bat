@echo off

rem Simple service management script
setlocal

set "SCRIPT_DIR=%~dp0"
set "NSSM_EXE=%SCRIPT_DIR%nssm.exe"
set "SERVICE_NAME=MyAPS_API"
set "RUN_PS1=%SCRIPT_DIR%run.ps1"

rem Calculate project root (parent directory of scripts)
for %%i in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fi"
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

:EXIT
echo Exiting...
pause
