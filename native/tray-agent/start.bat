@echo off
:: Grey Cardinal Tray Agent launcher
:: Starts in background (no console window)
set SCRIPT_DIR=%~dp0
pythonw "%SCRIPT_DIR%tray_agent.py"
if %errorlevel% neq 0 (
    echo ERROR: pythonw not found or script failed.
    echo Try running: python tray_agent.py
    pause
)
