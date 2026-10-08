@echo off
if not exist ".env" (
    python setup.py
)
if not exist ".venv\Scripts\python.exe" (
    echo Create the virtual environment first with: python -m venv .venv
    exit /b 1
)
".venv\Scripts\python.exe" app.py
