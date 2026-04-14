#Requires -Version 5.1
<#
.SYNOPSIS
    FastAPI Server Log Viewer
.DESCRIPTION
    Real-time monitoring of FastAPI server log file
.EXAMPLE
    Right-click and select "Run with PowerShell"
#>

# Set output encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get project root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$FastapiLogFile = "$ProjectRoot\logs\fastapi_server.log"

# Check if log directory exists
if (-not (Test-Path "$ProjectRoot\logs")) {
    Write-Host "[ERROR] Log directory not found: $ProjectRoot\logs" -ForegroundColor Red
    Write-Host "Please ensure the service is running and has generated log files" -ForegroundColor Yellow
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') | Out-Null
    exit 1
}

# Display welcome message
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FastAPI Server Log Viewer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Monitoring log file: $FastapiLogFile" -ForegroundColor Green
Write-Host "Press Ctrl+C to exit" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to filter logs by time (last 24 hours)
function Get-RecentLogs {
    param([string]$LogFile)
    
    $24HoursAgo = (Get-Date).AddHours(-24)
    $recentLogs = @()
    
    try {
        Get-Content $LogFile | ForEach-Object {
            # Try to extract timestamp from log line
            $line = $_
            if ($line -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
                $logTime = [datetime]::ParseExact($matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
                if ($logTime -ge $24HoursAgo) {
                    $recentLogs += $line
                }
            } else {
                # If no timestamp, include the line (might be part of a multi-line log)
                if ($recentLogs.Count -gt 0) {
                    $recentLogs += $line
                }
            }
        }
    } catch {
        # If parsing fails, return all logs
        $recentLogs = Get-Content $LogFile
    }
    
    return $recentLogs
}

# Display current log file content
Write-Host "[Current Log Content]" -ForegroundColor Magenta

# Show fastapi_server.log content
if (Test-Path $FastapiLogFile) {
    Write-Host "[FastAPI Server Logs (fastapi_server.log)]" -ForegroundColor Blue
    Write-Host "Showing logs from the last 24 hours..." -ForegroundColor Yellow
    $recentServerLogs = Get-RecentLogs -LogFile $FastapiLogFile
    if ($recentServerLogs.Count -gt 0) {
        $recentServerLogs | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host "No logs found in the last 24 hours." -ForegroundColor Yellow
    }
    Write-Host ""
} else {
    Write-Host "[FastAPI Server Logs (fastapi_server.log)]" -ForegroundColor Blue
    Write-Host "File not found. Will start monitoring when it's created." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "[Real-time Log Updates]" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Cyan

try {
    # Start monitoring fastapi_server.log
    $job = Start-Job -ScriptBlock {
        param($File)
        if (Test-Path $File) {
            Get-Content $File -Tail 0 -Wait
        } else {
            # Wait for file to be created
            while (-not (Test-Path $File)) {
                Start-Sleep -Seconds 1
            }
            Get-Content $File -Tail 0 -Wait
        }
    } -ArgumentList $FastapiLogFile

    # Monitor the job
    while ($job.State -eq 'Running') {
        if ($job.HasMoreData) {
            Receive-Job $job | ForEach-Object {
                Write-Host $_
            }
        }
        Start-Sleep -Milliseconds 500
    }
} catch {
    Write-Host ""
    Write-Host "[INFO] Log viewing stopped" -ForegroundColor Yellow
} finally {
    # Clean up jobs
    if ($job) { Stop-Job $job -ErrorAction SilentlyContinue }
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Log viewer exited" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Press any key to close..." -ForegroundColor Yellow
    $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') | Out-Null
}