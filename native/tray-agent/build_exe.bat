@echo off
:: Build standalone .exe with PyInstaller (no Python needed to run).
:: First: pip install -r requirements.txt pyinstaller
set SCRIPT_DIR=%~dp0
echo Building Grey Cardinal Tray Agent .exe...
pyinstaller --onefile --windowed --noconsole ^
    --name "GreyCardinalAgent" ^
    --collect-all sounddevice ^
    --collect-all pystray ^
    "%SCRIPT_DIR%tray_agent.py"
echo.
echo Output: dist\GreyCardinalAgent.exe
pause
