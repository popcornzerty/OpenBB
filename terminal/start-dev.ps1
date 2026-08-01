# Lance le backend et le frontend en développement, dans deux fenêtres.
#
#   .\start-dev.ps1
#
# Pour la fenêtre native, utiliser plutôt : cd frontend ; npm run tauri dev

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "..\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "Environnement virtuel introuvable : $python`nCréez-le avec : python -m venv .venv ; .venv\Scripts\pip install openbb"
}

$universe = Join-Path $root "backend\data\universe_eu.csv"
if (-not (Test-Path $universe)) {
    Write-Host "Univers absent — construction (quelques minutes)…" -ForegroundColor Yellow
    Push-Location (Join-Path $root "backend")
    & $python scripts\build_universe.py
    Pop-Location
}

Write-Host "Backend  -> http://127.0.0.1:8801" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$(Join-Path $root "backend")'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8801 --reload"
)

Write-Host "Frontend -> http://localhost:5180" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$(Join-Path $root "frontend")'; npm run dev"
)
