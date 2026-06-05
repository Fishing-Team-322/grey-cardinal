@echo off
echo Installing Grey Cardinal Tray Agent dependencies...
pip install -r "%~dp0requirements.txt"
if %errorlevel%==0 (
    echo.
    echo Done! Run start.bat to launch the agent.
) else (
    echo.
    echo ERROR: pip install failed. Make sure Python is installed.
)
pause
