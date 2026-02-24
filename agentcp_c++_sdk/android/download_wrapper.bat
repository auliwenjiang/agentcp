@echo off
REM Download Gradle Wrapper JAR

echo Downloading gradle-wrapper.jar...

set WRAPPER_JAR=gradle\wrapper\gradle-wrapper.jar
set WRAPPER_URL=https://github.com/gradle/gradle/raw/v8.4.0/gradle/wrapper/gradle-wrapper.jar

if not exist "gradle\wrapper" mkdir "gradle\wrapper"

powershell -Command "Invoke-WebRequest -Uri '%WRAPPER_URL%' -OutFile '%WRAPPER_JAR%'"

if exist "%WRAPPER_JAR%" (
    echo Download completed successfully!
    echo You can now run: gradlew.bat assembleRelease
) else (
    echo Download failed. Please download manually from:
    echo %WRAPPER_URL%
    echo And save to: %WRAPPER_JAR%
)

pause
