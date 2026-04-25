# Stop all Jarvis RAG services
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidsFile = "$ROOT\.pids.json"

if (Test-Path $pidsFile) {
    $pids = Get-Content $pidsFile | ConvertFrom-Json
    try { Stop-Process -Id $pids.QdrantPID -Force; Write-Host "Qdrant stopped." -ForegroundColor Green } catch {}
    try { Stop-Process -Id $pids.APIPid -Force; Write-Host "FastAPI stopped." -ForegroundColor Green } catch {}
    Remove-Item $pidsFile
} else {
    # Fallback: kill by name
    Get-Process -Name "qdrant" -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host "All Jarvis RAG services stopped." -ForegroundColor Yellow
}
