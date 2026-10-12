@echo off
setlocal

pushd "%~dp0" || exit /b 1
call gradlew.bat jar
set "BUILD_EXIT=%ERRORLEVEL%"
popd
if not "%BUILD_EXIT%"=="0" exit /b %BUILD_EXIT%

echo Output: %~dp0build\libs\burp-mcp-full.jar
echo Install: Burp Suite -^> Extensions -^> Add -^> Java -^> Select the output jar
exit /b 0
