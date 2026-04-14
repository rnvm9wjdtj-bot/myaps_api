#Requires -Version 5.1
<#
.SYNOPSIS
    FastAPI Service Log Viewer
.DESCRIPTION
    Real-time monitoring of FastAPI service log files
.EXAMPLE
    Right-click and select "Run with PowerShell"
#>

# Set output encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Set input encoding to UTF-8
[System.Text.Encoding]::Default = [System.Text.Encoding]::UTF8

# Get project root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$AppLogFile = "$ProjectRoot\logs\app.log"

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
Write-Host "Application Log Viewer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Monitoring log file: $AppLogFile" -ForegroundColor Green
Write-Host "Press Ctrl+C to exit" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Function to filter logs by time (last 24 hours)
function Get-RecentLogs {
    param([string]$LogFile)
    
    $24HoursAgo = (Get-Date).AddHours(-24)
    $recentLogs = @()
    
    try {
        Get-Content $LogFile -Encoding UTF8 | ForEach-Object {
            # Try to extract timestamp from log line
            $line = $_
            if ($line -match '^({4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
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
        $recentLogs = Get-Content $LogFile -Encoding UTF8
    }
    
    return $recentLogs
}

# Display current log file content
Write-Host "[Current Log Content]" -ForegroundColor Magenta

# Show app.log content
if (Test-Path $AppLogFile) {
    Write-Host "[Application Logs (app.log)]" -ForegroundColor Blue
    Write-Host "Showing logs from the last 24 hours..." -ForegroundColor Yellow
    $recentAppLogs = Get-RecentLogs -LogFile $AppLogFile
    if ($recentAppLogs.Count -gt 0) {
        $recentAppLogs | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host "No logs found in the last 24 hours." -ForegroundColor Yellow
    }
    Write-Host ""
} else {
    Write-Host "[Application Logs (app.log)]" -ForegroundColor Blue
    Write-Host "File not found. Will start monitoring when it's created." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "[Real-time Log Updates]" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Cyan

try {
    # Start monitoring app.log
    $job = Start-Job -ScriptBlock {
        param($File)
        if (Test-Path $File) {
            Get-Content $File -Encoding UTF8 -Tail 0 -Wait
        } else {
            # Wait for file to be created
            while (-not (Test-Path $File)) {
                Start-Sleep -Seconds 1
            }
            Get-Content $File -Encoding UTF8 -Tail 0 -Wait
        }
    } -ArgumentList $AppLogFile

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