@echo off
REM start.bat — run the bridge from a source checkout (after scripts\setup.bat).
REM The bridge finds the phone, installs the app and sets up adb forwarding itself.
REM Extra arguments are passed through, e.g.:  scripts\start.bat --no-tui

setlocal
set "ROOT=%~dp0.."
set "EXE=%ROOT%\desktop\.venv\Scripts\webcam-bridge.exe"

if not exist "%EXE%" (
    echo Virtual environment not found - run scripts\setup.bat first.
    exit /b 1
)
"%EXE%" %*
endlocal
