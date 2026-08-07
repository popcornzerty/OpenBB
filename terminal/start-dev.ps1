# Lance le backend et le frontend en développement, dans deux fenêtres.
#
#   .\start-dev.ps1
#
# Pour la fenêtre native, utiliser plutôt : cd frontend ; npm run tauri dev

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# L'environnement vit à la racine du projet. Le chercher aussi un niveau
# au-dessus permet de fonctionner depuis le dépôt d'origine, où le projet
# était logé dans un sous-dossier partageant le venv du parent.
$python = $null
foreach ($candidat in @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "..\.venv\Scripts\python.exe")
)) {
    if (Test-Path $candidat) { $python = $candidat; break }
}

if (-not $python) {
    Write-Error (
        "Environnement virtuel introuvable sous $root. " +
        "Créez-le : python -m venv .venv " +
        "puis .venv\Scripts\pip install -r backend\requirements.txt"
    )
}

$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

$universe = Join-Path $backend "data\universe_eu.csv"
if (-not (Test-Path $universe)) {
    Write-Host "Univers absent — construction (quelques minutes)…" -ForegroundColor Yellow
    Push-Location $backend
    & $python scripts\build_universe.py
    Pop-Location
}

# Les chemins sont calculés au préalable : PowerShell 5.1 refuse les
# guillemets doubles imbriqués dans un $(...) au sein d'une chaîne entre
# guillemets doubles, ce qui rendait ce script impossible à analyser.
$cmdBackend = "Set-Location '$backend'; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8801 --reload"
$cmdFrontend = "Set-Location '$frontend'; npm run dev"

Write-Host "Backend  -> http://127.0.0.1:8801" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $cmdBackend)

Write-Host "Frontend -> http://localhost:5180" -ForegroundColor Cyan
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $cmdFrontend)

Write-Host ""
Write-Host "Ouvrez http://localhost:5180 dans un navigateur." -ForegroundColor Green
