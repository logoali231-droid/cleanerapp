$ErrorActionPreference = "Stop"
Write-Host "AI File Cleaner - Windows build" -ForegroundColor Cyan
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment not found. Run .\setup_windows.ps1 first." }
& $python -m pip install pyinstaller
& $python -m PyInstaller --noconfirm --clean --windowed --name "AI File Cleaner" --paths "$root\src" "$root\src\ai_cleaner\__main__.py"
Write-Host "Build complete: dist\AI File Cleaner\" -ForegroundColor Green
