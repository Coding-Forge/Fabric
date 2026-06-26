@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Creating local Python virtual environment...
    py -3 -m venv "%SCRIPT_DIR%.venv" 2>nul
    if errorlevel 1 (
        python -m venv "%SCRIPT_DIR%.venv"
    )
)

if not exist "%PYTHON_EXE%" (
    echo.
    echo Unable to create or find .venv\Scripts\python.exe.
    echo Install Python 3.10 or later and try again.
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%.venv\.fabric-monitor-deps-installed" (
    echo Installing Fabric Monitor dependencies...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    if errorlevel 1 goto :error
    "%PYTHON_EXE%" -m pip install -r "%SCRIPT_DIR%requirements.txt"
    if errorlevel 1 goto :error
    echo installed>"%SCRIPT_DIR%.venv\.fabric-monitor-deps-installed"
)

echo Starting Fabric Monitor UI...
"%PYTHON_EXE%" -m app.windows_ui
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Fabric Monitor UI failed to start.
echo Review the error above, then press any key to close this window.
pause >nul
exit /b 1

