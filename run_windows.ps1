$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment not found. Run .\setup_windows.ps1 first." }
$env:PYTHONPATH = "$root\src" + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })
& $python -m ai_cleaner @args
