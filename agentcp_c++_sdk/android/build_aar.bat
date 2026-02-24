@echo off
REM AgentCP Android AAR Build Script for Windows

setlocal enabledelayedexpansion

echo ==========================================
echo AgentCP Android AAR Build
echo ==========================================

cd /d "%~dp0"

REM Check for Android SDK
if "%ANDROID_HOME%"=="" (
    if "%ANDROID_SDK_ROOT%"=="" (
        echo Error: ANDROID_HOME or ANDROID_SDK_ROOT environment variable not set
        exit /b 1
    )
)

REM Clean previous builds
echo [1/4] Cleaning previous builds...
call gradlew.bat clean
if errorlevel 1 goto :error

REM Build debug AAR
echo [2/4] Building debug AAR...
call gradlew.bat assembleDebug
if errorlevel 1 goto :error

REM Build release AAR
echo [3/4] Building release AAR...
call gradlew.bat assembleRelease
if errorlevel 1 goto :error

REM Publish to local repository
echo [4/4] Publishing to local Maven repository...
call gradlew.bat publishReleasePublicationToLocalRepository
if errorlevel 1 goto :error

echo.
echo ==========================================
echo Build completed successfully!
echo ==========================================
echo.
echo Output files:
echo   Debug AAR:   build\outputs\aar\agentcp-android-debug.aar
echo   Release AAR: build\outputs\aar\agentcp-android-release.aar
echo   Maven repo:  build\repo\com\agentcp\agentcp-sdk\0.1.0\
echo.
goto :end

:error
echo.
echo Build failed with error!
exit /b 1

:end
endlocal
