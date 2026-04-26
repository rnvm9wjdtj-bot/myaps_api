#Requires -Version 5.1
<#
.SYNOPSIS
    FastAPI Server Startup Script
.DESCRIPTION
    Start FastAPI server with support for both service mode and development mode
.PARAMETER Port
    Server port number (default: 8000, can be overridden from .env file or command line parameter)
.PARAMETER Host
    Server host address (default: 0.0.0.0)
.PARAMETER Mode
    Run mode: "service" for Windows service, "dev" for development (default: "dev")
.EXAMPLE
    .\run.ps1
    .\run.ps1 -Port 8001
    .\run.ps1 -Mode service
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [int]$Port = 8000,

    [Parameter()]
    [string]$HostAddress = "0.0.0.0",

    [Parameter()]
    [ValidateSet("service", "dev")]
    [string]$Mode = "dev"
)

# Set output encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get project root directory
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Set working directory to project root
Set-Location -Path $ProjectRoot
if ($Mode -eq "dev") {
    Write-Host "Working directory set to: $ProjectRoot"
}

# Configuration variables
$App = "main:app"
$LogFile = "$ProjectRoot\logs\fastapi_server.log"
$EnvFile = "$ProjectRoot\.env"

# Function: Write log
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp - $Message"
    try {
        if (-not (Test-Path "$ProjectRoot\logs")) {
            New-Item -ItemType Directory -Path "$ProjectRoot\logs" -Force | Out-Null
        }
        Add-Content -Path $LogFile -Value $logEntry
    } catch {
        # Ignore logging errors
    }
}

# Function: Load .env file
function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Log "WARNING: .env file not found at $Path"
        if ($Mode -eq "dev") {
            Write-Host "WARNING: .env file not found at $Path"
        }
        return
    }

    Write-Log "Loading environment variables from .env file..."
    if ($Mode -eq "dev") {
        Write-Host "Loading environment variables from .env file..."
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()

        # Skip empty lines and comments
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            return
        }

        # Parse KEY=VALUE
        if ($line -match "^([^=]+)=(.*)$") {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()

            # Remove possible quotes
            $value = $value -replace "^[`"']|[`"']$"

            # Set environment variable
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Function: Load project JSON configuration
function Import-ProjectConfig {
    param([string]$ProjectDir, [string]$ProjectJson)

    $configPath = "$ProjectRoot\project_files\$ProjectDir\$ProjectJson.json"

    if (-not (Test-Path $configPath)) {
        Write-Log "WARNING: Project config file not found at $configPath"
        if ($Mode -eq "dev") {
            Write-Host "WARNING: Project config file not found at $configPath"
        }
        return
    }

    Write-Log "Loading project configuration from $configPath"
    if ($Mode -eq "dev") {
        Write-Host "Loading project configuration from $configPath"
    }

    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json

        # Load environment variables from config.env section
        if ($config.env) {
            foreach ($key in $config.env.PSObject.Properties.Name) {
                $value = $config.env.$key
                if ($value -ne $null -and $value -ne "") {
                    [Environment]::SetEnvironmentVariable($key, $value, "Process")
                    Write-Log "Set environment variable: $key"
                }
            }
        }
    } catch {
        Write-Log "ERROR: Failed to load project config: $_"
        if ($Mode -eq "dev") {
            Write-Host "ERROR: Failed to load project config: $_"
        }
    }
}

# Function: Check if port is in use (dev mode only)
function Test-PortInUse {
    param([int]$PortNumber)

    $connections = Get-NetTCPConnection -LocalPort $PortNumber -ErrorAction SilentlyContinue
    if ($connections -eq $null) {
        return $false
    }
    return $connections.Count -gt 0
}

# Function: Get process using port (dev mode only)
function Get-PortProcess {
    param([int]$PortNumber)

    $connection = Get-NetTCPConnection -LocalPort $PortNumber -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection -ne $null) {
        try {
            return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        } catch {
            return $null
        }
    }
    return $null
}

# Function: Clear port usage (dev mode only)
function Clear-Port {
    param([int]$PortNumber)

    if ($Mode -eq "dev") {
        Write-Host "Checking if port $PortNumber is available..."
    }

    $process = Get-PortProcess -PortNumber $PortNumber
    if ($process) {
        # Skip Idle process (PID 0) as it's a system process and cannot be killed
        if ($process.Id -eq 0) {
            if ($Mode -eq "dev") {
                Write-Host "[INFO] Found Idle process (PID: 0), skipping termination as it's a system process" -ForegroundColor Yellow
            }
            Write-Log "Found Idle process (PID: 0), skipping termination"
        } else {
            if ($Mode -eq "dev") {
                Write-Host "[WARNING] Found process $($process.ProcessName) (PID: $($process.Id)) using port $PortNumber" -ForegroundColor Yellow
            }
            Write-Log "Found process $($process.Id) using port $PortNumber"

            if ($Mode -eq "dev") {
                Write-Host "Killing process $($process.Id)..."
            }
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
                Write-Log "Killed process $($process.Id)"
                if ($Mode -eq "dev") {
                    Write-Host "[INFO] Process killed successfully" -ForegroundColor Green
                }
            }
            catch {
                if ($Mode -eq "dev") {
                    Write-Host "[ERROR] Failed to kill process: $_" -ForegroundColor Red
                }
                Write-Log "Failed to kill process $($process.Id): $_"
            }
        }
    }

    # Wait for port release
    Start-Sleep -Seconds 5

    # Verify port is available
    if (Test-PortInUse -PortNumber $PortNumber) {
        # Check if it's still the Idle process
        $process = Get-PortProcess -PortNumber $PortNumber
        if ($process -and $process.Id -eq 0) {
            # Idle process doesn't actually use the port, so consider it available
            if ($Mode -eq "dev") {
                Write-Host "[INFO] Port $PortNumber is available for use (Idle process detected)" -ForegroundColor Green
            }
            Write-Log "Port $PortNumber is available (Idle process detected)"
            return $true
        } else {
            if ($Mode -eq "dev") {
                Write-Host "[ERROR] Port $PortNumber is still in use!" -ForegroundColor Red
            }
            Write-Log "Port $PortNumber is still in use!"
            return $false
        }
    }
    else {
        if ($Mode -eq "dev") {
            Write-Host "[INFO] Port $PortNumber is available for use" -ForegroundColor Green
        }
        Write-Log "Port $PortNumber is available"
        return $true
    }
}

# Function: Find Python interpreter
function Find-Python {
    $venvPython = "$ProjectRoot\venv\Scripts\python.exe"

    if (Test-Path $venvPython) {
        if ($Mode -eq "dev") {
            Write-Host "[DEBUG] Virtual Python found: $venvPython"
        }
        return $venvPython
    }
    else {
        if ($Mode -eq "dev") {
            Write-Host "[DEBUG] Virtual Python not found, using system Python"
        }
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            if ($Mode -eq "dev") {
                Write-Host "[DEBUG] System Python found: $($pythonCmd.Source)"
            }
            return $pythonCmd.Source
        }
        throw "Python not found!"
    }
}

# ==================== Main Program ====================

try {
    # Create log directory
    if (-not (Test-Path "$ProjectRoot\logs")) {
        New-Item -ItemType Directory -Path "$ProjectRoot\logs" -Force | Out-Null
        if ($Mode -eq "dev") {
            Write-Host "[INFO] Logs directory created"
        }
    }

    # Load configuration from .env file (command line parameter has highest priority)
    Import-DotEnv -Path $EnvFile

    # Load project configuration based on PROJECT_DIR and PROJECT_JSON
    $projectDir = $env:PROJECT_DIR
    $projectJson = $env:PROJECT_JSON

    if ($projectDir -and $projectJson) {
        Write-Log "Loading project config: $projectDir/$projectJson"
        if ($Mode -eq "dev") {
            Write-Host "Loading project config: $projectDir/$projectJson"
        }
        Import-ProjectConfig -ProjectDir $projectDir -ProjectJson $projectJson
    } else {
        Write-Log "WARNING: PROJECT_DIR or PROJECT_JSON not set in .env file"
        if ($Mode -eq "dev") {
            Write-Host "WARNING: PROJECT_DIR or PROJECT_JSON not set in .env file"
        }
    }

    # Read default values from environment variables (if not specified in command line)
    if ($PSBoundParameters.ContainsKey("Port") -eq $false -and $env:PORT) {
        $Port = [int]$env:PORT
    }
    if ($PSBoundParameters.ContainsKey("Host") -eq $false -and $env:HOST) {
        $HostAddress = $env:HOST
    }

    # Set environment variables
    [Environment]::SetEnvironmentVariable("PORT", $Port, "Process")
    [Environment]::SetEnvironmentVariable("HOST", $HostAddress, "Process")
    [Environment]::SetEnvironmentVariable("START_MODE", $Mode, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $ProjectRoot, "Process")
    [Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1", "Process")

    # Check if static directory exists
    $staticDir = "$ProjectRoot\static"
    if (Test-Path $staticDir) {
        Write-Log "Static directory found: $staticDir"
        if ($Mode -eq "dev") {
            Write-Host "Static directory found: $staticDir"
        }
    } else {
        Write-Log "WARNING: Static directory not found at $staticDir"
        if ($Mode -eq "dev") {
            Write-Host "WARNING: Static directory not found at $staticDir"
        }
    }

    # Display configuration information (dev mode only)
    if ($Mode -eq "dev") {
        Write-Host ""
        Write-Host "FastAPI Server Starting..." -ForegroundColor Cyan
        Write-Host "Port: $Port, Host: $HostAddress"
        Write-Host "Project Root: $ProjectRoot" -ForegroundColor Yellow
        Write-Host "Mode: $Mode"
        Write-Host "Press Ctrl+C to stop gracefully"
        Write-Host ""
    }

    # Record startup log
    Write-Log "Server starting on port $Port, host $HostAddress, mode $Mode"

    # Check port availability (dev mode only)
    if ($Mode -eq "dev") {
        Write-Host "[INFO] Checking port availability..."
        Clear-Port -PortNumber $Port
    }

    # Find Python
    try {
        $Python = Find-Python
        Write-Log "Found Python: $Python"
        if ($Mode -eq "dev") {
            Write-Host "Python: $Python"
        }
    } catch {
        Write-Log "Failed to find Python: $_"
        if ($Mode -eq "dev") {
            Write-Host "[ERROR] Failed to find Python: $_" -ForegroundColor Red
        }
        exit 1
    }

    # Build uvicorn arguments
    $uvicornArgs = @(
        "-m", "uvicorn",
        $App,
        "--host", $HostAddress,
        "--port", "$Port",
        "--log-level", "info",
        "--access-log"
    )

    Write-Log "Starting uvicorn server: $Python $($uvicornArgs -join ' '); Working directory: $ProjectRoot"
    if ($Mode -eq "dev") {
        Write-Host ""
        Write-Host "Starting uvicorn server..." -ForegroundColor Cyan
        Write-Host "Uvicorn command: $Python $($uvicornArgs -join ' ')" -ForegroundColor Yellow
    }

    # Start server
    if ($Mode -eq "service") {
        # Service mode: use Uvicorn on Windows, Gunicorn on Unix
        try {
            # Check if running on Windows
            if ($env:OS -eq "Windows_NT") {
                # On Windows, use Uvicorn directly
                Write-Log "Running on Windows, using Uvicorn single process..."
                if ($Mode -eq "dev") {
                    Write-Host "Running on Windows, using Uvicorn single process..." -ForegroundColor Cyan
                }
                & $Python $uvicornArgs
            } else {
                # On Unix/Linux, check if Gunicorn is installed
                $gunicornCheck = & $Python -m pip show gunicorn 2>$null
                if ($gunicornCheck) {
                    # Use Gunicorn with multi-process
                    Write-Log "Starting Gunicorn server with multiple processes..."
                    if ($Mode -eq "dev") {
                        Write-Host "Starting Gunicorn server with multiple processes..." -ForegroundColor Cyan
                    }
                    $gunicornConfig = "$ProjectRoot\scripts\deploy\gunicorn_multiprocess.conf.py"
                    & $Python -m gunicorn -c $gunicornConfig main:app
                } else {
                    # Fallback to Uvicorn single process
                    Write-Log "Gunicorn not found, using Uvicorn single process..."
                    if ($Mode -eq "dev") {
                        Write-Host "Gunicorn not found, using Uvicorn single process..." -ForegroundColor Yellow
                    }
                    & $Python $uvicornArgs
                }
            }
        } catch {
            Write-Log "Failed to start server: $_"
            if ($Mode -eq "dev") {
                Write-Host "[ERROR] Failed to start server: $_" -ForegroundColor Red
            }
            exit 1
        }
    } else {
        # Dev mode: run with graceful shutdown support
        try {
            $serverProcess = Start-Process -FilePath $Python -ArgumentList $uvicornArgs -NoNewWindow -PassThru
            if ($Mode -eq "dev") {
                Write-Host "Server process started with PID: $($serverProcess.Id)" -ForegroundColor Green
            }
            Write-Log "Server process started with PID: $($serverProcess.Id)"
        } catch {
            Write-Log "Failed to start server process: $_"
            if ($Mode -eq "dev") {
                Write-Host "[ERROR] Failed to start server process: $_" -ForegroundColor Red
            }
            exit 1
        }

        # Setup graceful shutdown handler
        $shutdownRequested = $false

        $null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
            $script:shutdownRequested = $true
        }

        try {
            # Wait for process to exit
            if ($Mode -eq "dev") {
                Write-Host "[DEBUG] Waiting for server process to exit..."
            }
            Wait-Process -Id $serverProcess.Id -ErrorAction Stop
        } catch {
            if ($shutdownRequested -or $Error[0].Exception.Message -match "was not found") {
                if ($Mode -eq "dev") {
                    Write-Host ""
                    Write-Host "Shutting down server gracefully..." -ForegroundColor Yellow
                }
                Write-Log "Shutting down server gracefully"
                
                # Try graceful shutdown first
                $serverProcess.CloseMainWindow() | Out-Null
                Start-Sleep -Seconds 5
                
                # Force kill if still running
                if (!$serverProcess.HasExited) {
                    if ($Mode -eq "dev") {
                        Write-Host "Force killing server process..." -ForegroundColor Yellow
                    }
                    $serverProcess | Stop-Process -Force -ErrorAction SilentlyContinue
                }
            }
            else {
                if ($Mode -eq "dev") {
                    Write-Host ""
                    Write-Host "[ERROR] Server process error: $_" -ForegroundColor Red
                }
                Write-Log "Server process error: $_"
            }
        }

        # Get actual exit code
        $exitCode = $serverProcess.ExitCode

        # Check exit code
        if ($exitCode -ne 0) {
            if ($Mode -eq "dev") {
                Write-Host ""
                Write-Host "[ERROR] Application failed to start with error code $exitCode" -ForegroundColor Red
            }
            Write-Log "Application failed to start with error code $exitCode"
            exit $exitCode
        }
    }
} catch {
    Write-Log "Error: $_"
    if ($Mode -eq "dev") {
        Write-Host ""
        Write-Host "[ERROR] An error occurred: $_" -ForegroundColor Red
    }
    exit 1
} finally {
    # Cleanup work (dev mode only)
    if ($Mode -eq "dev") {
        Write-Host ""
        Write-Host "Server shutting down..." -ForegroundColor Yellow
    }
    Write-Log "Server shutting down"

    # Clear port usage (dev mode only)
    if ($Mode -eq "dev") {
        Write-Host "Cleaning up any remaining processes on port $Port..."
        $process = Get-PortProcess -PortNumber $Port
        if ($process) {
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                if ($Mode -eq "dev") {
                    Write-Host "Killed process $($process.Id)"
                }
                Write-Log "Killed process $($process.Id) during cleanup"
            } catch {
                # Ignore errors
            }
        }

        Write-Host "Shutdown complete." -ForegroundColor Green
    }
    Write-Log "Server shutdown complete"
}
