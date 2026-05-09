# MyAPS Project Packaging Script (PowerShell)
# Excludes unnecessary directories and files

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MyAPS Package Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (-not (Test-Path "main.py")) {
    Write-Host "ERROR: Please run this script from project root directory" -ForegroundColor Red
    exit 1
}

$projectDir = Get-Location
$projectName = Split-Path $projectDir -Leaf
$parentDir = Split-Path $projectDir -Parent
$timestamp = Get-Date -Format "yyyyMMdd"
$outputFile = Join-Path $parentDir "${projectName}_${timestamp}.tar.gz"
$tempDir = Join-Path $parentDir "${projectName}_temp"

Write-Host "[1/4] Current project: $projectName" -ForegroundColor Green

# Remove existing temp directory
if (Test-Path $tempDir) {
    Write-Host "[2/4] Cleaning up existing temp directory..." -ForegroundColor Green
    Remove-Item -Recurse -Force $tempDir
}

Write-Host "[2/4] Copying project files (excluding unwanted items)..." -ForegroundColor Green

# Define items to exclude
$excludeItems = @(
    "venv",
    "offline_packages",
    "logs",
    "test",
    "storage",
    "backups",
    ".git",
    "__pycache__",
    ".env"  # 排除 .env 文件，让服务器使用自己的配置
)

# Get all items in project directory
$items = Get-ChildItem -Path $projectDir

foreach ($item in $items) {
    # Skip excluded items
    if ($excludeItems -contains $item.Name) {
        Write-Host "  Skipping: $($item.Name)"
        continue
    }
    
    # Copy the item
    $destPath = Join-Path $tempDir $item.Name
    Copy-Item -Path $item.FullName -Destination $destPath -Recurse -Force
}

Write-Host "[3/4] Removing compiled files from subdirectories..." -ForegroundColor Green

# Remove .pyc files from all subdirectories
Get-ChildItem -Path $tempDir -Recurse -Filter "*.pyc" | Remove-Item -Force
Get-ChildItem -Path $tempDir -Recurse -Filter "*.pyo" | Remove-Item -Force
Get-ChildItem -Path $tempDir -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force

Write-Host "[4/4] Packing..." -ForegroundColor Green

# Create tar.gz
tar -czvf $outputFile -C $parentDir "${projectName}_temp"

# Clean up
Remove-Item -Recurse -Force $tempDir

Write-Host "" -ForegroundColor Cyan
Write-Host "SUCCESS: Package completed!" -ForegroundColor Green
Write-Host "File: $outputFile" -ForegroundColor Green
Write-Host "" -ForegroundColor Cyan
Write-Host "Excluded items:" -ForegroundColor Yellow
Write-Host "- venv (Virtual environment)"
Write-Host "- offline_packages (Offline dependencies)"
Write-Host "- logs (Log files)"
Write-Host "- test (Test code)"
Write-Host "- storage (Local storage)"
Write-Host "- backups (Backup files)"
Write-Host "- .git (Git repository)"
Write-Host "- __pycache__ and *.pyc (Compiled files)"