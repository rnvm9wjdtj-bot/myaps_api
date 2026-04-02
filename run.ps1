#Requires -Version 5.1
<#
.SYNOPSIS
    FastAPI Server Startup Script (PowerShell Version)
.DESCRIPTION
    Start FastAPI server with environment variable configuration, port checking and auto cleanup
.PARAMETER Port
    Server port number (default: 8000, can be overridden from .env file or command line parameter)
.PARAMETER Host
    Server host address (default: 0.0.0.0)
.EXAMPLE
    .\run.ps1
    .\run.ps1 -Port 8001
    .\run.ps1 -Port 8001 -Host 127.0.0.1
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [int]$Port = 8000,

    [Parameter()]
    [string]$HostAddress = "0.0.0.0"
)

# Set output encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Configuration variables
$App = "main:app"
$LogFile = "logs\fastapi_server.log"
$EnvFile = ".env"

# Function: Write log
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp - $Message"
    Add-Content -Path $LogFile -Value $logEntry -ErrorAction SilentlyContinue
}

# Function: Load .env file
function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Write-Host "Loading environment variables from .env file..."

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

# Function: Check if port is in use
function Test-PortInUse {
    param([int]$PortNumber)

    $connections = Get-NetTCPConnection -LocalPort $PortNumber -ErrorAction SilentlyContinue
    return $connections.Count -gt 0
}

# Function: Get process using port
function Get-PortProcess {
    param([int]$PortNumber)

    $connection = Get-NetTCPConnection -LocalPort $PortNumber -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    }
    return $null
}

# Function: Clear port usage
function Clear-Port {
    param([int]$PortNumber)

    Write-Host "Checking if port $PortNumber is available..."

    $process = Get-PortProcess -PortNumber $PortNumber
    if ($process) {
        Write-Host "[WARNING] Found process $($process.ProcessName) (PID: $($process.Id)) using port $PortNumber" -ForegroundColor Yellow
        Write-Log "Found process $($process.Id) using port $PortNumber"

        Write-Host "Killing process $($process.Id)..."
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            Write-Log "Killed process $($process.Id)"
            Write-Host "[INFO] Process killed successfully" -ForegroundColor Green
        }
        catch {
            Write-Host "[ERROR] Failed to kill process: $_" -ForegroundColor Red
            Write-Log "Failed to kill process $($process.Id): $_"
        }
    }

    # Wait for port release
    Start-Sleep -Seconds 3

    # Verify port is available
    if (Test-PortInUse -PortNumber $PortNumber) {
        Write-Host "[ERROR] Port $PortNumber is still in use!" -ForegroundColor Red
        Write-Log "Port $PortNumber is still in use!"
        return $false
    }
    else {
        Write-Host "[INFO] Port $PortNumber is available for use" -ForegroundColor Green
        Write-Log "Port $PortNumber is available"
        return $true
    }
}

# Function: Find Python interpreter
function Find-Python {
    $venvPython = "venv\Scripts\python.exe"

    if (Test-Path $venvPython) {
        Write-Host "Using virtual Python"
        return (Resolve-Path $venvPython).Path
    }
    else {
        Write-Host "Using system Python"
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            return $pythonCmd.Source
        }
        throw "Python not found!"
    }
}

# ==================== Main Program ====================

try {
    # Create log directory
    if (-not (Test-Path "logs")) {
        New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    }
    Write-Host "[INFO] Logs directory ensured"

    # Load configuration from .env file (command line parameter has highest priority)
    Import-DotEnv -Path $EnvFile

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
    [Environment]::SetEnvironmentVariable("PYTHONPATH", (Get-Location).Path, "Process")
    # Set unbuffered output for better log display
    [Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", "1", "Process")

    # Display configuration information
    Write-Host ""
    Write-Host "FastAPI Server Starting..." -ForegroundColor Cyan
    Write-Host "Port: $Port, Host: $HostAddress"
    Write-Host "Press Ctrl+C to stop gracefully"
    Write-Host ""

    # Record startup log
    Write-Log "Server starting on port $Port"

    # Clear port usage
    if (-not (Clear-Port -PortNumber $Port)) {
        Read-Host "Press Enter to exit"
        exit 1
    }

    # Find Python
    $Python = Find-Python
    Write-Host "Python: $Python"

    # Start server
    Write-Host ""
    Write-Host "Starting uvicorn server with host $HostAddress and port $Port..." -ForegroundColor Cyan
    Write-Log "Starting uvicorn server with host $HostAddress and port $Port"

    # Build uvicorn arguments
    $uvicornArgs = @(
        "-m", "uvicorn",
        $App,
        "--host", $HostAddress,
        "--port", "$Port",
        "--log-level", "debug"
    )

    # Start process directly for better output
    & $Python @uvicornArgs

    # Check exit code
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[ERROR] Application failed to start with error code $LASTEXITCODE" -ForegroundColor Red
        Write-Log "Application failed to start with error code $LASTEXITCODE"
        Read-Host "Press Enter to exit"
        exit $LASTEXITCODE
    }
}
catch {
    Write-Host ""
    Write-Host "[ERROR] An error occurred: $_" -ForegroundColor Red
    Write-Log "Error: $_"
    Read-Host "Press Enter to exit"
    exit 1
}
finally {
    # Cleanup work
    Write-Host ""
    Write-Host "Server shutting down..." -ForegroundColor Yellow
    Write-Log "Server shutting down"

    # Clear port usage
    Write-Host "Cleaning up any remaining processes on port $Port..."
    $process = Get-PortProcess -PortNumber $Port
    if ($process) {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Write-Host "Killed process $($process.Id)"
            Write-Log "Killed process $($process.Id) during cleanup"
        }
        catch {
            # Ignore errors
        }
    }

    Write-Host "Shutdown complete." -ForegroundColor Green
    Write-Log "Server shutdown complete"
    Write-Host ""
}

