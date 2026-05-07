param (
    [string]$ServiceName = "",
    [string]$LogDir = "",
    [string]$ProjectDir = "",
    [string]$EmailEnabled = "false",
    [string]$EmailTo = "",
    [string]$EmailFrom = "",
    [string]$SmtpServer = "",
    [int]$SmtpPort = 587,
    [string]$SmtpUser = "",
    [string]$SmtpPassword = "",
    [bool]$SystemNotification = $true,
    [bool]$AutoRestart = $true,
    [string]$EnvFile = ""
)

# Calculate project root (parent directory of scripts)
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath

# Set default EnvFile if not provided
if ([string]::IsNullOrEmpty($EnvFile)) {
    $EnvFile = Join-Path $projectRoot ".env"
}

# Set default LogDir if not provided
if ([string]::IsNullOrEmpty($LogDir)) {
    $LogDir = Join-Path $projectRoot "logs"
}

function Read-EnvFile {
    param (
        [string]$EnvFilePath
    )
    
    if (-not (Test-Path $EnvFilePath)) {
        Write-Log "Environment file not found: $EnvFilePath" -Level "WARN"
        return @{}
    }
    
    try {
        $envContent = Get-Content $EnvFilePath -Raw
        $envVariables = @{}
        
        $lines = $envContent -split "`n"
        foreach ($line in $lines) {
            $line = $line.Trim()
            if ($line -and $line -notlike "#*" -and $line -match "=") {
                $key, $value = $line -split "=", 2
                $key = $key.Trim()
                $value = $value.Trim()
                $envVariables[$key] = $value
            }
        }
        
        return $envVariables
    } catch {
        Write-Log "Failed to read environment file: $_" -Level "ERROR"
        return @{}
    }
}

# Read configuration from .env file
if (Test-Path $EnvFile) {
    $envVariables = Read-EnvFile -EnvFilePath $EnvFile
    
    # Service configuration
    if ($envVariables.ContainsKey("SERVICE_NAME")) { $ServiceName = $envVariables["SERVICE_NAME"] }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_LOG_DIR")) { $LogDir = $envVariables["SERVICE_DAEMON_LOG_DIR"] }
    
    # Project directory (tenant)
    if ($envVariables.ContainsKey("PROJECT_DIR")) { $ProjectDir = $envVariables["PROJECT_DIR"] }
    
    # Email configuration
    if ($envVariables.ContainsKey("SERVICE_DAEMON_EMAIL_ENABLED")) { $EmailEnabled = $envVariables["SERVICE_DAEMON_EMAIL_ENABLED"].ToLower() }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_EMAIL_TO")) {
        $emailToValue = $envVariables["SERVICE_DAEMON_EMAIL_TO"]
        if ($emailToValue -match ",") {
            $EmailTo = $emailToValue -split "," | ForEach-Object { $_.Trim() }
        } else {
            $EmailTo = $emailToValue
        }
    }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_EMAIL_FROM")) { $EmailFrom = $envVariables["SERVICE_DAEMON_EMAIL_FROM"] }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_SMTP_SERVER")) { $SmtpServer = $envVariables["SERVICE_DAEMON_SMTP_SERVER"] }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_SMTP_PORT")) { $SmtpPort = [int]$envVariables["SERVICE_DAEMON_SMTP_PORT"] }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_SMTP_USER")) { $SmtpUser = $envVariables["SERVICE_DAEMON_SMTP_USER"] }
    if ($envVariables.ContainsKey("SERVICE_DAEMON_SMTP_PASSWORD")) { $SmtpPassword = $envVariables["SERVICE_DAEMON_SMTP_PASSWORD"] }
    
    # Notifications configuration
    if ($envVariables.ContainsKey("SERVICE_DAEMON_SYSTEM_NOTIFICATION")) {
        $SystemNotification = [bool]::Parse($envVariables["SERVICE_DAEMON_SYSTEM_NOTIFICATION"])
    }
    
    # Recovery configuration
    if ($envVariables.ContainsKey("SERVICE_DAEMON_AUTO_RESTART")) {
        $AutoRestart = [bool]::Parse($envVariables["SERVICE_DAEMON_AUTO_RESTART"])
    }
    
    Write-Log "Configuration loaded from .env file: $EnvFile" -Level "INFO"
}

# Set default service name if not found
if ([string]::IsNullOrEmpty($ServiceName)) {
    $ServiceName = "MyAPS_API"
    Write-Log "Using default service name: $ServiceName" -Level "INFO"
}

$logFile = Join-Path $LogDir "service_daemon.log"
$errorLogFile = Join-Path $LogDir "service_daemon_errors.log"

function Write-Log {
    param (
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    try {
        Add-Content -Path $logFile -Value $logMessage -ErrorAction Stop
    } catch {
        Write-Output "Failed to write to log file: $_"
    }
    
    if ($Level -eq "ERROR") {
        try {
            Add-Content -Path $errorLogFile -Value $logMessage -ErrorAction Stop
        } catch {
            Write-Output "Failed to write to error log file: $_"
        }
    }
}

function Send-EmailNotification {
    param (
        [string]$Subject,
        [string]$Body,
        [string]$Level = "error"
    )
    
    if ($EmailEnabled -ne "true") {
        Write-Log "Email notification disabled, skipping email send"
        return
    }
    
    # 优先使用租户的 remind.py 脚本
    if (-not [string]::IsNullOrEmpty($ProjectDir)) {
        $remindScript = Join-Path $projectRoot "project_files\$ProjectDir\remind.py"
        
        if (Test-Path $remindScript) {
            try {
                $pythonExe = "python"
                $result = & $pythonExe $remindScript --message $Body --level $Level --subject $Subject 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Log "Email notification sent via tenant script: $Subject"
                    return
                } else {
                    Write-Log "Tenant remind.py failed (exit code: $LASTEXITCODE): $result" -Level "WARN"
                    # 继续尝试使用 PowerShell 发送作为降级方案
                }
            } catch {
                Write-Log "Failed to execute tenant remind.py: $_" -Level "WARN"
                # 继续尝试使用 PowerShell 发送作为降级方案
            }
        } else {
            Write-Log "Tenant remind.py not found: $remindScript" -Level "WARN"
        }
    }
    
    # 降级方案：使用 PowerShell Send-MailMessage
    if (([string]::IsNullOrEmpty($EmailTo) -and $EmailTo -isnot [array]) -or [string]::IsNullOrEmpty($EmailFrom) -or [string]::IsNullOrEmpty($SmtpServer)) {
        Write-Log "Email configuration incomplete, skipping email send" -Level "WARN"
        return
    }
    
    try {
        $securePassword = ConvertTo-SecureString $SmtpPassword -AsPlainText -Force
        $credential = New-Object System.Management.Automation.PSCredential ($SmtpUser, $securePassword)
        
        Send-MailMessage -From $EmailFrom -To $EmailTo -Subject $Subject -Body $Body -SmtpServer $SmtpServer -Port $SmtpPort -Credential $credential -UseSsl -ErrorAction Stop
        
        # Log the recipients
        if ($EmailTo -is [array]) {
            $recipients = $EmailTo -join ", "
        } else {
            $recipients = $EmailTo
        }
        Write-Log "Email notification sent via PowerShell to $recipients: $Subject"
    } catch {
        Write-Log "Failed to send email notification: $_" -Level "ERROR"
    }
}

function Send-SystemNotification {
    param (
        [string]$Title,
        [string]$Message
    )
    
    if (-not $SystemNotification) {
        Write-Log "System notification disabled, skipping notification"
        return
    }
    
    try {
        Add-Type -AssemblyName System.Windows.Forms
        
        $notifyIcon = New-Object System.Windows.Forms.NotifyIcon
        $notifyIcon.Icon = [System.Drawing.SystemIcons]::Warning
        $notifyIcon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
        $notifyIcon.BalloonTipTitle = $Title
        $notifyIcon.BalloonTipText = $Message
        $notifyIcon.Visible = $true
        
        $notifyIcon.ShowBalloonTip(10000)
        
        Start-Sleep -Seconds 10
        $notifyIcon.Dispose()
        
        Write-Log "System notification sent: $Title"
    } catch {
        Write-Log "Failed to send system notification: $_" -Level "ERROR"
    }
}

function Check-ServiceStatus {
    Write-Log "Starting service status check for: $ServiceName"
    
    try {
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        
        if ($service.Status -eq "Running") {
            Write-Log "Service $ServiceName is running normally"
            return $true
        } else {
            $message = "Service $ServiceName status is abnormal: $($service.Status)"
            Write-Log $message -Level "ERROR"
            
            Send-EmailNotification -Subject "服务异常：$ServiceName" -Body $message -Level "error"
            Send-SystemNotification -Title "服务异常" -Message $message
            
            if ($AutoRestart) {
                Write-Log "Attempting to restart service: $ServiceName"
                try {
                    Start-Service -Name $ServiceName -ErrorAction Stop
                    Start-Sleep -Seconds 5
                    
                    $serviceAfterRestart = Get-Service -Name $ServiceName -ErrorAction Stop
                    if ($serviceAfterRestart.Status -eq "Running") {
                        $successMessage = "Service $ServiceName restarted successfully"
                        Write-Log $successMessage
                        Send-EmailNotification -Subject "服务已重启：$ServiceName" -Body $successMessage -Level "info"
                        Send-SystemNotification -Title "服务已重启" -Message $successMessage
                        return $true
                    } else {
                        $failMessage = "Service $ServiceName restart failed, current status: $($serviceAfterRestart.Status)"
                        Write-Log $failMessage -Level "ERROR"
                        Send-EmailNotification -Subject "服务重启失败：$ServiceName" -Body $failMessage -Level "error"
                        Send-SystemNotification -Title "服务重启失败" -Message $failMessage
                        return $false
                    }
                } catch {
                    $errorMessage = "Failed to restart service $ServiceName: $_"
                    Write-Log $errorMessage -Level "ERROR"
                    Send-EmailNotification -Subject "服务重启失败：$ServiceName" -Body $errorMessage -Level "error"
                    Send-SystemNotification -Title "服务重启失败" -Message $errorMessage
                    return $false
                }
            }
            
            return $false
        }
    } catch {
        $errorMessage = "Service $ServiceName not found or access denied: $_"
        Write-Log $errorMessage -Level "ERROR"
        Send-EmailNotification -Subject "服务不存在：$ServiceName" -Body $errorMessage -Level "error"
        Send-SystemNotification -Title "服务不存在" -Message $errorMessage
        return $false
    }
}

function Check-ServiceHealth {
    Write-Log "Starting service health check for: $ServiceName"
    
    try {
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        
        if ($service.Status -ne "Running") {
            Write-Log "Service is not running, skipping health check" -Level "WARN"
            return $false
        }
        
        $logPath = Join-Path $LogDir "nssm_stderr.log"
        if (Test-Path $logPath) {
            $lastErrorTime = (Get-Item $logPath).LastWriteTime
            $timeSinceLastError = (Get-Date) - $lastErrorTime
            
            if ($timeSinceLastError.TotalMinutes -lt 5) {
                $errorCount = (Get-Content $logPath -Tail 100 | Select-String -Pattern "ERROR|Exception|Failed" | Measure-Object).Count
                if ($errorCount -gt 0) {
                    $message = "Service $ServiceName has recent errors in log file: $errorCount errors in last 5 minutes"
                    Write-Log $message -Level "WARN"
                    Send-EmailNotification -Subject "服务日志异常：$ServiceName" -Body $message -Level "warning"
                    Send-SystemNotification -Title "服务日志异常" -Message $message
                    return $false
                }
            }
        }
        
        Write-Log "Service health check passed for: $ServiceName"
        return $true
    } catch {
        Write-Log "Health check failed for service $ServiceName: $_" -Level "ERROR"
        return $false
    }
}

function Main {
    Write-Log "========================================"
    Write-Log "Service Daemon Started"
    Write-Log "Service Name: $ServiceName"
    Write-Log "Email Enabled: $EmailEnabled"
    Write-Log "System Notification: $SystemNotification"
    Write-Log "Auto Restart: $AutoRestart"
    Write-Log "========================================"
    
    $statusCheck = Check-ServiceStatus
    
    if ($statusCheck) {
        $healthCheck = Check-ServiceHealth
        if (-not $healthCheck) {
            Write-Log "Service health check failed" -Level "WARN"
        }
    }
    
    Write-Log "Service Daemon Completed"
    Write-Log "========================================"
}

try {
    Main
} catch {
    Write-Log "Fatal error in service daemon: $_" -Level "ERROR"
    Send-EmailNotification -Subject "守护脚本错误" -Body "Service daemon script encountered a fatal error: $_" -Level "error"
    Send-SystemNotification -Title "守护脚本错误" -Message "Service daemon script encountered a fatal error"
    exit 1
}

exit 0