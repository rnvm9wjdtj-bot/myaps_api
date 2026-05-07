@echo off
setlocal

chcp 936 >nul
cls

set "PYTHON_VENV_DIR=venv"
set "ENV_FILE=%~dp0..\..\.env"
set "SERVICE_NAME=MyAPS_API"

if exist "%ENV_FILE%" (
    for /f "tokens=1,2 delims==" %%a in ('findstr "PYTHON_VENV_DIR" "%ENV_FILE%"') do (
        set "PYTHON_VENV_DIR=%%b"
        set "PYTHON_VENV_DIR=%PYTHON_VENV_DIR: =%"
    )
    for /f "tokens=1,2 delims==" %%a in ('findstr /C:"SERVICE_NAME" "%ENV_FILE%"') do (
        set "SERVICE_NAME=%%b"
        set "SERVICE_NAME=%SERVICE_NAME: =%"
    )
)

set "PYTHON_EXE=python"
set "PROJECT_ROOT=%~dp0..\.."
set "VENV_DIR=%PROJECT_ROOT%\%PYTHON_VENV_DIR%"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_DIR%" (
    if exist "%VENV_PYTHON%" (
        set PYTHON_EXE=%VENV_PYTHON%
    )
)

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" (
    echo Error: Cannot get script directory!
    pause
    exit /b 1
)

set "NSSM_EXE=%SCRIPT_DIR%..\nssm.exe"
if not exist "%NSSM_EXE%" (
    echo Error: NSSM executable not found!
    pause
    exit /b 1
)

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: Please run this script as administrator!
    echo.
    echo Steps:
    echo 1. Right-click this script file
    echo 2. Select "Run as administrator"
    echo.
    pause
    exit /b 1
)

:MENU
cls
echo ============================================================
echo                    MyAPS_API Service Deployment Tool
echo ============================================================
echo.
echo Please select an operation:
echo.
echo 1. Install service (multi-process mode)
echo 2. Start service
echo 3. Stop service
echo 4. Restart service
echo 5. Uninstall service
echo 6. Check service status
echo 7. Check system environment
echo 8. Clean log files
echo 9. View help
echo A. Health check (HTTP endpoint)
echo B. Rolling update (graceful restart)
echo 0. Exit
echo.
echo ============================================================
echo.

set "choice="
set /p choice=Please enter option (0-9, A-B): 

for /f "tokens=*" %%a in ("%choice%") do set "choice=%%a"

if "%choice%"=="" (
    echo Error: Please enter a valid option!
    pause
    goto :MENU
)

if "%choice%"=="1" goto :INSTALL
if "%choice%"=="2" goto :START
if "%choice%"=="3" goto :STOP
if "%choice%"=="4" goto :RESTART
if "%choice%"=="5" goto :UNINSTALL
if "%choice%"=="6" goto :STATUS
if "%choice%"=="7" goto :CHECK_ENV
if "%choice%"=="8" goto :CLEAN_LOGS
if "%choice%"=="9" goto :HELP
if /i "%choice%"=="A" goto :HEALTH_CHECK
if /i "%choice%"=="B" goto :ROLLING_UPDATE
if "%choice%"=="0" goto :EXIT

echo Invalid choice: [%choice%]
echo Please try again!
pause
goto :MENU

:INSTALL
cls
echo ============================================================
echo                Install service (multi-process mode)
echo ============================================================
echo.

%PYTHON_EXE% --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: Python not found!
    pause
    goto :MENU
)

%PYTHON_EXE% -m pip show gunicorn >nul 2>&1
if %errorLevel% neq 0 (
    echo Installing Gunicorn...
    %PYTHON_EXE% -m pip install gunicorn uvicorn[standard]
    if %errorLevel% neq 0 (
        echo Error: Failed to install Gunicorn!
        pause
        goto :MENU
    )
)

if exist "%PROJECT_ROOT%\requirements.txt" (
    echo Installing dependencies...
    %PYTHON_EXE% -m pip install -r "%PROJECT_ROOT%\requirements.txt"
)

if not exist "%PROJECT_ROOT%\logs" (
    mkdir "%PROJECT_ROOT%\logs"
)

set "RUN_PS1=%SCRIPT_DIR%..\run.ps1"

"%NSSM_EXE%" install "%SERVICE_NAME%" powershell.exe
"%NSSM_EXE%" set "%SERVICE_NAME%" AppParameters "-ExecutionPolicy Bypass -NoProfile -File %RUN_PS1% -Mode service"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%PROJECT_ROOT%"
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%PROJECT_ROOT%\logs\nssm_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%PROJECT_ROOT%\logs\nssm_stderr.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 60000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 300000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 1 Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 0 Restart

echo.
echo Service installed successfully!
echo Service name: %SERVICE_NAME%
echo.
pause
goto :MENU

:START
cls
echo ============================================================
echo                        Start service
echo ============================================================
echo.

"%NSSM_EXE%" start "%SERVICE_NAME%"

if %errorLevel% neq 0 (
    echo Error: Failed to start service!
    echo Please check log files: %PROJECT_ROOT%\logs
    pause
    goto :MENU
)

echo Service started successfully!
echo Access address: http://localhost:8000
echo.
pause
goto :MENU

:STOP
cls
echo ============================================================
echo                        Stop service
echo ============================================================
echo.

"%NSSM_EXE%" stop "%SERVICE_NAME%"

echo Service stopped!
echo.
pause
goto :MENU

:RESTART
cls
echo ============================================================
echo                      Restart service
echo ============================================================
echo.

"%NSSM_EXE%" restart "%SERVICE_NAME%"

echo Service restarted successfully!
echo.
pause
goto :MENU

:UNINSTALL
cls
echo ============================================================
echo                     Uninstall service
echo ============================================================
echo.

"%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm

echo Service uninstalled successfully!
echo.
pause
goto :MENU

:STATUS
cls
echo ============================================================
echo                      Service status
echo ============================================================
echo.

"%NSSM_EXE%" status "%SERVICE_NAME%"
echo.
echo Service configuration:
"%NSSM_EXE%" get "%SERVICE_NAME%" AppParameters
"%NSSM_EXE%" get "%SERVICE_NAME%" AppDirectory
echo.
pause
goto :MENU

:CHECK_ENV
cls
echo ============================================================
echo                  System environment check
echo ============================================================
echo.

echo Operating system:
ver
echo.

echo Python version:
%PYTHON_EXE% --version
echo.

echo pip version:
%PYTHON_EXE% -m pip --version
echo.

echo Gunicorn version:
%PYTHON_EXE% -m pip show gunicorn | findstr "Version"
echo.

echo Port 8000 status:
netstat -ano | findstr :8000
if %errorLevel% neq 0 (
    echo Port 8000 is available
)
echo.
pause
goto :MENU

:CLEAN_LOGS
cls
echo ============================================================
echo                      Clean log files
echo ============================================================
echo.

powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "$logDir = '%PROJECT_ROOT%\logs'; $daysToKeep = 10; $cutoffDate = (Get-Date).AddDays(-$daysToKeep); if (Test-Path $logDir) { $oldLogs = Get-ChildItem -Path $logDir -Recurse -File | Where-Object { $_.LastWriteTime -lt $cutoffDate }; if ($oldLogs) { Write-Host 'Cleaning old log files...'; $oldLogs | Remove-Item -Force; Write-Host 'Clean completed.' } else { Write-Host 'No old log files found.' } } else { Write-Host 'Log directory does not exist.' }"

echo.
pause
goto :MENU

:HELP
cls
echo ============================================================
echo                        Help information
echo ============================================================
echo.

echo 1. Install service: Install service as Windows system service
echo 2. Start service: Start the installed service
echo 3. Stop service: Stop the running service
echo 4. Restart service: Restart the service
echo 5. Uninstall service: Remove service from system
echo 6. Check status: Check service running status
echo 7. Check environment: Check system environment
echo 8. Clean logs: Clean old log files
echo 9. View help: Display this help
echo A. Health check: Perform HTTP health check
echo B. Rolling update: Graceful restart for updates
echo 0. Exit: Exit the tool
echo.
pause
goto :MENU

:HEALTH_CHECK
cls
echo ============================================================
echo                   Health Check (HTTP Endpoint)
echo ============================================================
echo.

set "CHECK_SCRIPT=%SCRIPT_DIR%check_health.bat"
if not exist "%CHECK_SCRIPT%" (
    echo Error: check_health.bat not found!
    pause
    goto :MENU
)

call "%CHECK_SCRIPT%"
echo.
pause
goto :MENU

:ROLLING_UPDATE
cls
echo ============================================================
echo               Rolling Update (Graceful Restart)
echo ============================================================
echo.

echo [DEBUG] SCRIPT_DIR: %SCRIPT_DIR%
echo [DEBUG] NSSM_EXE: %NSSM_EXE%
echo Using service name: %SERVICE_NAME%
echo.

if not exist "%NSSM_EXE%" (
    echo [ERROR] NSSM executable not found at: %NSSM_EXE%
    pause
    goto :MENU
)

echo Checking service status...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Service "%SERVICE_NAME%" is not installed!
    pause
    goto :MENU
)

"%NSSM_EXE%" status "%SERVICE_NAME%" | findstr "Running" >nul 2>&1
if %errorLevel% neq 0 (
    echo [WARN] Service not running. Starting...
    "%NSSM_EXE%" start "%SERVICE_NAME%"
    timeout /t 5 /nobreak >nul
)
echo Service is running.
echo.

set "CONFIRM="
set /p CONFIRM=Continue with rolling update? (Y/N): 
if /i not "%CONFIRM%"=="Y" (
    echo Update cancelled.
    pause
    goto :MENU
)
echo.

echo Step 1: Sending stop signal...
"%NSSM_EXE%" stop "%SERVICE_NAME%"

echo Waiting for graceful shutdown...
timeout /t 10 /nobreak >nul

echo Step 2: Starting service...
"%NSSM_EXE%" start "%SERVICE_NAME%"

echo Step 3: Service restarted!
echo.
echo Rolling update completed.
echo.
pause
goto :MENU

:EXIT
cls
echo ============================================================
echo                       Exit deployment tool
echo ============================================================
echo.
echo Thank you for using MyAPS_API Service Deployment Tool!
echo.
pause
exit