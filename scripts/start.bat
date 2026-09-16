@echo off
REM start.bat — connect to the phone over USB and start the desktop bridge.
REM Extra arguments are passed to the bridge, e.g.:  scripts\start.bat --no-tui

setlocal
set "ROOT=%~dp0.."
set "PY=%ROOT%\desktop\.venv\Scripts\python.exe"
set "APP_ID=io.github.sulphur16.webcambridge"
if "%WEBCAM_BRIDGE_PORT%"=="" set "WEBCAM_BRIDGE_PORT=5134"

echo ========================================================
echo   Webcam Bridge
echo ========================================================
echo.

if not exist "%PY%" (
    echo Virtual environment not found - run scripts\setup.bat first.
    exit /b 1
)

where adb >nul 2>&1
if errorlevel 1 (
    echo ERROR: adb not found. Install Android platform-tools and add it to PATH.
    exit /b 1
)

echo Waiting for phone (USB debugging must be enabled)...
adb wait-for-device
echo [OK] Phone connected
adb shell am start -n %APP_ID%/.MainActivity >nul 2>&1 && echo [OK] App launched || echo [WARN] Open the Webcam Bridge app manually.

REM Phone camera stream -> PC
adb forward tcp:8080 tcp:8080 || (echo ERROR: adb forward failed & exit /b 1)
REM Phone remote control -> PC dashboard (lets the app use 127.0.0.1)
adb reverse tcp:%WEBCAM_BRIDGE_PORT% tcp:%WEBCAM_BRIDGE_PORT% >nul 2>&1 || echo [WARN] adb reverse failed - phone remote control needs Wi-Fi mode.
echo [OK] Port forwarding ready
echo.

"%PY%" -m webcam_bridge --port %WEBCAM_BRIDGE_PORT% %*
endlocal
