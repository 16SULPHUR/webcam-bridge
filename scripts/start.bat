@echo off
REM start.bat — start the desktop bridge from a source checkout.
REM The packaged app's Start-menu shortcut does the same thing; this is the
REM equivalent for a git clone. Extra arguments go to the bridge, e.g.:
REM     scripts\start.bat --no-tui --no-browser

setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\desktop\.venv\Scripts\python.exe"

echo ========================================================
echo   Webcam Bridge
echo ========================================================
echo.

if not exist "%PY%" (
    echo Virtual environment not found - run scripts\setup.bat first.
    exit /b 1
)

REM launcher.py downloads adb if needed, sets up the USB forwards, starts the
REM phone app and opens the dashboard. Anything it cannot do shows up on the
REM dashboard's Setup page with a button to fix it.
"%PY%" -m webcam_bridge.launcher %*
endlocal
