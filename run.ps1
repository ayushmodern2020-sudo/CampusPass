if (!(Test-Path ".env")) {
    python setup.py
}
if (!(Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Create the virtual environment first with: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}
& ".venv\Scripts\python.exe" app.py
