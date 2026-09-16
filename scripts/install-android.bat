@echo off
REM install-android.bat — build the Android app from source and install it on
REM the connected phone. Needs JDK 17 (JAVA_HOME) and the Android SDK
REM (ANDROID_HOME or android\local.properties).
REM Prefer the prebuilt APK from the GitHub Releases page if you just want to use the app.

setlocal
cd /d "%~dp0..\android"

echo [1/2] Building debug APK...
call gradlew.bat assembleDebug
if errorlevel 1 (
    echo ERROR: Gradle build failed. Check JAVA_HOME points to JDK 17.
    exit /b 1
)

echo [2/2] Installing on phone...
adb install -r app\build\outputs\apk\debug\app-debug.apk
if errorlevel 1 (
    echo ERROR: adb install failed. Is the phone connected with USB debugging on?
    exit /b 1
)
echo Done.
endlocal
