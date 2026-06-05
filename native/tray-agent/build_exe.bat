@echo off
:: Build standalone .exe with PyInstaller (no Python needed to run)
:: Requires: pip install pyinstaller
set SCRIPT_DIR=%~dp0
echo Building Grey Cardinal Tray Agent .exe...
pyinstaller --onefile --windowed --noconsole ^
    --name "GreyCardinalAgent" ^
    --icon "%SCRIPT_DIR%icon.ico" ^
    "%SCRIPT_DIR%tray_agent.py"
echo.
echo Output: dist\GreyCardinalAgent.exe
pause
