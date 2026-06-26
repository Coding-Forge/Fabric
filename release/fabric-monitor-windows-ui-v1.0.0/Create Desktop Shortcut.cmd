@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "SHORTCUT=%USERPROFILE%\Desktop\Fabric Monitor UI.lnk"
set "TARGET=%SCRIPT_DIR%Run Fabric Monitor UI.cmd"
set "ICON=%SCRIPT_DIR%icons\monitor-dashboard.ico"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell = New-Object -ComObject WScript.Shell; " ^
  "$shortcut = $shell.CreateShortcut('%SHORTCUT%'); " ^
  "$shortcut.TargetPath = '%TARGET%'; " ^
  "$shortcut.WorkingDirectory = '%SCRIPT_DIR%'; " ^
  "$shortcut.Description = 'Run Fabric Monitor Windows UI'; " ^
  "$shortcut.IconLocation = '%ICON%'; " ^
  "$shortcut.Save()"

if errorlevel 1 (
    echo Failed to create desktop shortcut.
    pause
    exit /b 1
)

echo Created desktop shortcut:
echo %SHORTCUT%
pause

