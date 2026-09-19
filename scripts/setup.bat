@echo off
REM setup.bat — create a virtual environment and install the desktop bridge.
REM Only needed for a source checkout; the released installer does all of this.
REM Usage: scripts\setup.bat            (core features)
REM        scripts\setup.bat rvm        (also install PyTorch for RVM segmentation)

setlocal
set "ROOT=%~dp0.."
set "VENV=%ROOT%\desktop\.venv"

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

if not exist "%VENV%\Scripts\python.exe" (
    echo Creating virtual environment in desktop\.venv ...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo ERROR: Python 3.10+ is required. Install it from https://python.org
        exit /b 1
    )
)

"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if /i "%~1"=="rvm" (
    "%VENV%\Scripts\python.exe" -m pip install -e "%ROOT%\desktop[rvm]"
) else (
    "%VENV%\Scripts\python.exe" -m pip install -e "%ROOT%\desktop"
)
if errorlevel 1 exit /b 1

REM Built-in virtual camera: release zips ship the DLLs, git checkouts download them.
if not exist "%ROOT%\desktop\webcam_bridge\bin\x64\webcam_bridge_cam.dll" (
    "%VENV%\Scripts\python.exe" -m webcam_bridge.fetch vcam
)
"%VENV%\Scripts\webcam-bridge.exe" camera status | find "not installed" >nul
if %errorlevel%==0 (
    echo.
    echo Installing the "Webcam Bridge" virtual camera - approve the administrator prompt.
    "%VENV%\Scripts\webcam-bridge.exe" camera install || echo [WARN] Camera not installed - OBS Virtual Camera will be used instead.
)

echo.
echo Setup complete. Start the bridge with: scripts\start.bat
echo The dashboard's Setup page checks the rest (adb, the phone, the app).
endlocal
