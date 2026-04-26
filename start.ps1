# Jarvis RAG - Start All Services (No Docker Required)
# Run this once in PowerShell to launch Qdrant + FastAPI backend

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Jarvis RAG Backend - Native Windows Launcher" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# Refresh PATH so Python/pip are available
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 1. Start Qdrant
$qdrantExe = "$ROOT\qdrant-bin\qdrant.exe"
$qdrantStorage = "$ROOT\qdrant-bin\storage"
New-Item -ItemType Directory -Force -Path $qdrantStorage | Out-Null

Write-Host "[1/2] Starting Qdrant vector database on port 6333..." -ForegroundColor Yellow
$qdrantProc = Start-Process -FilePath $qdrantExe `
    -ArgumentList "--storage-path", $qdrantStorage `
    -WindowStyle Hidden `
    -PassThru

Write-Host "      Qdrant PID: $($qdrantProc.Id)" -ForegroundColor Green
Start-Sleep -Seconds 3

# Quick health check
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:6333/readyz" -TimeoutSec 5
    Write-Host "      Qdrant: READY" -ForegroundColor Green
} catch {
    Write-Host "      Qdrant: Still starting (this is normal on first run)" -ForegroundColor Yellow
}

# 2. Start FastAPI
Write-Host ""
Write-Host "[2/2] Starting Jarvis FastAPI backend on port 10000..." -ForegroundColor Yellow
Write-Host "      (First run downloads embedding models - may take 2-3 minutes)" -ForegroundColor DarkYellow
Write-Host ""

Set-Location $ROOT
$pythonExe = "C:\Users\Slytherin Dinu\AppData\Local\Programs\Python\Python311\python.exe"
if (-Not (Test-Path $pythonExe)) {
    Write-Host "Python 3.11 not found at $pythonExe. Falling back to 'python'." -ForegroundColor Yellow
    $pythonExe = "python"
}

$apiProc = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000", "--reload" `
    -WindowStyle Normal `
    -PassThru

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Services Started!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Qdrant Dashboard : http://localhost:6333/dashboard"
Write-Host "  Jarvis API       : http://localhost:10000"
Write-Host "  API Docs         : http://localhost:10000/docs"
Write-Host "  Health Check     : http://localhost:10000/health"
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

# Save PIDs for stop script
@{QdrantPID=$qdrantProc.Id; APIPid=$apiProc.Id} | ConvertTo-Json | Out-File "$ROOT\.pids.json"

# Keep this window alive to show logs
Wait-Process -Id $apiProc.Id
