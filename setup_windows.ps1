$ErrorActionPreference = "Stop"
Write-Host "AI File Cleaner - Windows setup" -ForegroundColor Cyan
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher 'py' was not found. Install Python 3.11+ from python.org and enable the launcher." }
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Setup complete. Run: .\run_windows.ps1" -ForegroundColor Green
