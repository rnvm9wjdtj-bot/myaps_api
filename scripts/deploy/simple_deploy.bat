@echo off

rem Enable delayed expansion for variable substitution
setlocal enabledelayedexpansion

rem Set console codepage to UTF-8
chcp 65001 >nul

rem Clear screen
cls

rem Read PYTHON_VENV_DIR from .env file
set "PYTHON_VENV_DIR=venv"
set "ENV_FILE=%~dp0..\..\.env"
if exist "%ENV_FILE%" (
    for /f "tokens=1,2 delims==" %%a in ('findstr "PYTHON_VENV_DIR" "%ENV_FILE%"') do (
        set "PYTHON_VENV_DIR=%%b"
        rem Remove spaces
        set "PYTHON_VENV_DIR=!PYTHON_VENV_DIR: =!"
    )
)
echo Python virtual environment directory: %PYTHON_VENV_DIR%

rem Set Python executable path
set "PYTHON_EXE=python"
set "PROJECT_ROOT=%~dp0..\.."
set "VENV_DIR=%PROJECT_ROOT%\%PYTHON_VENV_DIR%"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
echo Project root: %PROJECT_ROOT%
echo Virtual environment directory: %VENV_DIR%
echo Virtual environment Python: %VENV_PYTHON%

rem Check if virtual environment exists
if exist "%VENV_DIR%" (
    echo Virtual environment directory exists: %VENV_DIR%
    if exist "%VENV_PYTHON%" (
        set PYTHON_EXE=%VENV_PYTHON%
        echo Using virtual environment Python: !PYTHON_EXE!
    ) else (
        echo Virtual environment Python executable not found: %VENV_PYTHON%
        echo Using system Python: %PYTHON_EXE%
    )
) else (
    echo Virtual environment directory not found: %VENV_DIR%
    echo Using system Python: %PYTHON_EXE%
)

echo ================================================================================
echo                          MyAPS_API Service Deployment Tool
echo ================================================================================
echo.
echo This is a user-friendly deployment tool for users without IT background.
echo Please follow the prompts to select the function you need.
echo.
echo ================================================================================
echo.

rem Set path variables safely
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" (
echo Error: Cannot get script directory!
pause
exit /b 1
)

echo Script directory: %SCRIPT_DIR%

set "NSSM_EXE=%SCRIPT_DIR%..\nssm.exe"
if not exist "%NSSM_EXE%" (
echo Error: NSSM executable not found!
echo Please make sure nssm.exe is in the scripts directory.
pause
exit /b 1
)

echo NSSM path: %NSSM_EXE%

set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
if not exist "%PROJECT_ROOT%" (
echo Error: Project root directory not found!
pause
exit /b 1
)

echo Project root: %PROJECT_ROOT%

rem Check for administrator privileges
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

echo Administrator privileges confirmed!
echo.

:MENU
cls
echo ================================================================================
echo                          MyAPS_API Service Deployment Tool
echo ================================================================================
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
echo 0. Exit
echo.
echo ================================================================================
echo.

rem Get user input safely
set "choice="
set /p choice=Please enter number to select operation: 

rem Check if input is empty
if "%choice%"=="" (
echo Error: Please enter a valid number!
pause
goto :MENU
)

rem Check if input is a number
set "is_number=1"
for /f "delims=0123456789" %%i in ("%choice%") do set "is_number=0"
if "%is_number%"=="0" (
echo Error: Please enter a valid number!
pause
goto :MENU
)

rem Process user choice
if "%choice%"=="1" goto :INSTALL
if "%choice%"=="2" goto :START
if "%choice%"=="3" goto :STOP
if "%choice%"=="4" goto :RESTART
if "%choice%"=="5" goto :UNINSTALL
if "%choice%"=="6" goto :STATUS
if "%choice%"=="7" goto :CHECK_ENV
if "%choice%"=="8" goto :CLEAN_LOGS
if "%choice%"=="9" goto :HELP
if "%choice%"=="0" goto :EXIT

echo Invalid choice, please try again!
pause
goto :MENU

:INSTALL
cls
echo ================================================================================
echo                          Install service (multi-process mode)
echo ================================================================================
echo.
echo Checking system environment...
echo.

rem Check if Python is installed
%PYTHON_EXE% --version >nul 2>&1
if %errorLevel% neq 0 (
echo Error: Python not found!
echo.
echo Please install Python 3.7 or higher first.
echo Download URL: https://www.python.org/downloads/
echo.
pause
goto :MENU
)

rem Check if Gunicorn is installed
%PYTHON_EXE% -m pip show gunicorn >nul 2>&1
if %errorLevel% neq 0 (
echo Installing Gunicorn...
%PYTHON_EXE% -m pip install gunicorn uvicorn[standard]
if %errorLevel% neq 0 (
echo Error: Failed to install Gunicorn!
echo.
pause
goto :MENU
)
echo Gunicorn installed successfully!
echo.
)

rem Check dependencies
echo Checking project dependencies...
if exist "%PROJECT_ROOT%\requirements.txt" (
%PYTHON_EXE% -m pip install -r "%PROJECT_ROOT%\requirements.txt"
if %errorLevel% neq 0 (
echo Warning: Error occurred while installing dependencies, but will continue to install service.
echo.
)
)

rem Create logs directory
if not exist "%PROJECT_ROOT%\logs" (
echo Creating logs directory...
mkdir "%PROJECT_ROOT%\logs"
)

rem Install service
echo Installing service...
echo.

set "SERVICE_NAME=MyAPS_API"
set "RUN_PS1=%SCRIPT_DIR%..\run.ps1"

"%NSSM_EXE%" install "%SERVICE_NAME%" powershell.exe
"%NSSM_EXE%" set "%SERVICE_NAME%" AppParameters "-ExecutionPolicy Bypass -NoProfile -File %RUN_PS1% -Mode service"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%PROJECT_ROOT%"
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%PROJECT_ROOT%\logs\nssm_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%PROJECT_ROOT%\logs\nssm_stderr.log"

rem Configure auto-restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 60000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 300000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 1 Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit 0 Restart

echo.
echo Service installed successfully!
echo.
echo Service name: %SERVICE_NAME%
echo Run mode: Multi-process
echo Log directory: %PROJECT_ROOT%\logs
echo.
echo Next step: Start service (select option 2)
echo.
pause
goto :MENU

:START
cls
echo ================================================================================
echo                              Start service
echo ================================================================================
echo.
echo Starting service...
echo.

set "SERVICE_NAME=MyAPS_API"
"%NSSM_EXE%" start "%SERVICE_NAME%"

if %errorLevel% neq 0 (
echo Error: Failed to start service!
echo.
echo Possible reasons:
echo 1. Port 8000 is occupied
echo 2. Python dependencies missing
echo 3. Configuration file error
echo.
echo Please check log files: %PROJECT_ROOT%\logs
echo.
pause
goto :MENU
)

echo Service started successfully!
echo.
echo Service name: %SERVICE_NAME%
echo Access address: http://localhost:8000
echo.
pause
goto :MENU

:STOP
cls
echo ================================================================================
echo                              Stop service
echo ================================================================================
echo.
echo Stopping service...
echo.

set "SERVICE_NAME=MyAPS_API"
"%NSSM_EXE%" stop "%SERVICE_NAME%"

echo Service stopped!
echo.
pause
goto :MENU

:RESTART
cls
echo ================================================================================
echo                              Restart service
echo ================================================================================
echo.
echo Restarting service...
echo.

set "SERVICE_NAME=MyAPS_API"
"%NSSM_EXE%" restart "%SERVICE_NAME%"

echo Service restarted successfully!
echo.
pause
goto :MENU

:UNINSTALL
cls
echo ================================================================================
echo                              Uninstall service
echo ================================================================================
echo.
echo Uninstalling service...
echo.

set "SERVICE_NAME=MyAPS_API"
"%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm

echo Service uninstalled successfully!
echo.
pause
goto :MENU

:STATUS
cls
echo ================================================================================
echo                              Service status
echo ================================================================================
echo.
echo Checking service status...
echo.

set "SERVICE_NAME=MyAPS_API"
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
echo ================================================================================
echo                              System environment check
echo ================================================================================
echo.

rem Check operating system
echo Operating system:
ver
echo.

rem Check Python
echo Python version:
%PYTHON_EXE% --version
echo.

rem Check pip
echo pip version:
%PYTHON_EXE% -m pip --version
echo.

rem Check Gunicorn
echo Gunicorn version:
%PYTHON_EXE% -m pip show gunicorn | findstr "Version"
echo.

rem Check Uvicorn
echo Uvicorn version:
%PYTHON_EXE% -m pip show uvicorn | findstr "Version"
echo.

rem Check port
echo Port 8000 status:
netstat -ano | findstr :8000
if %errorLevel% neq 0 (
echo Port 8000 is available
)
echo.

rem Check project directory
echo Project directory:
echo %PROJECT_ROOT%
echo.

rem Check requirements file
if exist "%PROJECT_ROOT%\requirements.txt" (
echo Requirements file: Exists
) else (
echo Requirements file: Not exists
)
echo.

pause
goto :MENU

:CLEAN_LOGS
cls
echo ================================================================================
echo                              Clean log files
echo ================================================================================
echo.
echo Cleaning log files...
echo Keeping logs from the last 10 days...
echo.

rem Execute PowerShell command safely
powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "$logDir = '%PROJECT_ROOT%\logs'; $daysToKeep = 10; $cutoffDate = (Get-Date).AddDays(-$daysToKeep); if (Test-Path $logDir) { $oldLogs = Get-ChildItem -Path $logDir -Recurse -File | Where-Object { $_.LastWriteTime -lt $cutoffDate }; if ($oldLogs.Count -gt 0) { Write-Host 'Found ' $oldLogs.Count ' old log files:'; $oldLogs | ForEach-Object { Write-Host '- ' $_.Name ' (Last modified: ' $_.LastWriteTime ')' }; try { $oldLogs | Remove-Item -Force; Write-Host 'Successfully deleted ' $oldLogs.Count ' old log files.'; } catch { Write-Host 'Error deleting log files: ' $_ -ForegroundColor Red; } } else { Write-Host 'No old log files found. All logs are within the last ' $daysToKeep ' days.'; } } else { Write-Host 'Log directory does not exist: ' $logDir -ForegroundColor Yellow; }"

echo.
echo Log cleaning completed!
echo.
pause
goto :MENU

:HELP
cls
echo ================================================================================
echo                              Help information
echo ================================================================================
echo.
echo MyAPS_API Service Deployment Tool Usage:
echo.
echo 1. Install service: Install service as Windows system service, run in multi-process mode
echo 2. Start service: Start the installed service
echo 3. Stop service: Stop the running service
echo 4. Restart service: Restart the service
echo 5. Uninstall service: Remove service from system
echo 6. Check status: Check service running status and configuration
echo 7. Check environment: Check system environment and dependencies
echo 8. Clean logs: Clean old log files
echo 9. View help: Display this help information
echo 0. Exit: Exit the tool
echo.
echo Common issues:
echo - Port occupied: Check if other programs are using port 8000
echo - Dependencies missing: Make sure all necessary Python packages are installed
echo - Insufficient permissions: Run this script as administrator
echo.
echo Technical support:
echo - Contact developer for help
echo.
pause
goto :MENU

:EXIT
cls
echo ================================================================================
echo                             Exit deployment tool
echo ================================================================================
echo.
echo Thank you for using MyAPS_API Service Deployment Tool!
echo.
pause
exit