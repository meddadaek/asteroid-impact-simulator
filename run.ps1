#Requires -Version 5.1
<#
    Orbital Sentinel launcher.

    First run:   .\run.ps1 -Setup
    Every run:   .\run.ps1
#>
param(
    [switch]$Setup,
    [switch]$Train,
    [int]$Port = 8712
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root 'backend\.venv'
$py = Join-Path $venv 'Scripts\python.exe'

if ($Setup -or -not (Test-Path $py)) {
    Write-Host 'Creating virtual environment...' -ForegroundColor Cyan
    python -m venv $venv

    # pip builds in %TEMP%; keep that off a full system drive
    $tmp = Join-Path $root '.pip-tmp'
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $env:TMP = $tmp; $env:TEMP = $tmp

    Write-Host 'Installing dependencies...' -ForegroundColor Cyan
    & $py -m pip install -q --upgrade pip
    & $py -m pip install -q -r (Join-Path $root 'backend\requirements-build.txt')

    Push-Location (Join-Path $root 'backend\app')
    Write-Host 'Downloading catalogues and imagery...' -ForegroundColor Cyan
    & $py fetch_data.py
    Write-Host 'Building assets (land mask, cities, NEO index)...' -ForegroundColor Cyan
    & $py build_assets.py
    Pop-Location
}

if ($Train) {
    Write-Host 'Training models (several minutes)...' -ForegroundColor Cyan
    Push-Location (Join-Path $root 'backend\app')
    & $py train.py
    Pop-Location
}

$models = Join-Path $root 'backend\models\orbit_impact_clf.pkl'
if (-not (Test-Path $models)) {
    Write-Host 'No trained models found. Run: .\run.ps1 -Train' -ForegroundColor Yellow
    Write-Host 'The analytic physics still works without them.' -ForegroundColor Yellow
}

Write-Host "Serving on http://127.0.0.1:$Port" -ForegroundColor Green
& $py -m uvicorn main:app --app-dir (Join-Path $root 'backend\app') `
    --host 127.0.0.1 --port $Port
