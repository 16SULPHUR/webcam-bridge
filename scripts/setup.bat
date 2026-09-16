@echo off
REM setup.bat — create a virtual environment and install the desktop bridge.
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

echo.
where ffmpeg >nul 2>&1 || echo [WARN] ffmpeg not found on PATH - install it or set WEBCAM_BRIDGE_FFMPEG.
where adb    >nul 2>&1 || echo [WARN] adb not found on PATH - install Android platform-tools.
echo.
echo Setup complete. Start the bridge with: scripts\start.bat
endlocal
