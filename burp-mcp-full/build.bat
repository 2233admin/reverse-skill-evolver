@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 exit /b 1

if defined JAVA_HOME (
    set "JAVAC=%JAVA_HOME%\bin\javac.exe"
    set "JAR=%JAVA_HOME%\bin\jar.exe"
) else (
    set "JAVAC=javac.exe"
    set "JAR=jar.exe"
)
set "SRC=src\main\java\com\burpmcp"
set "LIB=lib"
set "OUT=build\classes"
set "DIST=build\libs"
set "ARTIFACT=%DIST%\burp-mcp-full.jar"

echo [1/4] Downloading dependencies...
if not exist "%LIB%" mkdir "%LIB%"
if not exist "%LIB%\montoya-api.jar" (
    echo Downloading montoya-api...
    curl -fsSL -o "%LIB%\montoya-api.jar.tmp" "https://repo1.maven.org/maven2/net/portswigger/burp/extensions/montoya-api/2025.5/montoya-api-2025.5.jar"
    if errorlevel 1 exit /b 1
    if not exist "%LIB%\montoya-api.jar.tmp" exit /b 1
    for %%D in ("%LIB%\montoya-api.jar.tmp") do if %%~zD LEQ 0 exit /b 1
    move /y "%LIB%\montoya-api.jar.tmp" "%LIB%\montoya-api.jar" >nul
    if errorlevel 1 exit /b 1
)
if not exist "%LIB%\gson.jar" (
    echo Downloading gson...
    curl -fsSL -o "%LIB%\gson.jar.tmp" "https://repo1.maven.org/maven2/com/google/code/gson/gson/2.11.0/gson-2.11.0.jar"
    if errorlevel 1 exit /b 1
    if not exist "%LIB%\gson.jar.tmp" exit /b 1
    for %%D in ("%LIB%\gson.jar.tmp") do if %%~zD LEQ 0 exit /b 1
    move /y "%LIB%\gson.jar.tmp" "%LIB%\gson.jar" >nul
    if errorlevel 1 exit /b 1
)
if not exist "%LIB%\nanohttpd.jar" (
    echo Downloading nanohttpd...
    curl -fsSL -o "%LIB%\nanohttpd.jar.tmp" "https://repo1.maven.org/maven2/org/nanohttpd/nanohttpd/2.3.1/nanohttpd-2.3.1.jar"
    if errorlevel 1 exit /b 1
    if not exist "%LIB%\nanohttpd.jar.tmp" exit /b 1
    for %%D in ("%LIB%\nanohttpd.jar.tmp") do if %%~zD LEQ 0 exit /b 1
    move /y "%LIB%\nanohttpd.jar.tmp" "%LIB%\nanohttpd.jar" >nul
    if errorlevel 1 exit /b 1
)
if not exist "%LIB%\re2j.jar" (
    echo Downloading re2j...
    curl -fsSL -o "%LIB%\re2j.jar.tmp" "https://repo1.maven.org/maven2/com/google/re2j/re2j/1.8/re2j-1.8.jar"
    if errorlevel 1 exit /b 1
    if not exist "%LIB%\re2j.jar.tmp" exit /b 1
    for %%D in ("%LIB%\re2j.jar.tmp") do if %%~zD LEQ 0 exit /b 1
    move /y "%LIB%\re2j.jar.tmp" "%LIB%\re2j.jar" >nul
    if errorlevel 1 exit /b 1
)

rem PowerShell compares UTC timestamps; missing output, equal times, or scan errors rebuild.
powershell -NoProfile -Command "try { $jar = Get-Item -LiteralPath $env:ARTIFACT -ErrorAction Stop; if ($jar.Length -le 0) { exit 1 }; $inputs = @(Get-ChildItem -LiteralPath 'src' -Recurse -File -Filter '*.java' -ErrorAction Stop) + @(Get-ChildItem -LiteralPath $env:LIB -Recurse -File -Filter '*.jar' -ErrorAction Stop) + @(Get-Item -LiteralPath 'build.bat' -ErrorAction Stop) + @(Get-Item -LiteralPath 'build.sh' -ErrorAction Stop); foreach ($source in $inputs) { if ($source.LastWriteTimeUtc -ge $jar.LastWriteTimeUtc) { exit 1 } }; exit 0 } catch { exit 1 }"
if errorlevel 1 goto compile
echo [2/4] Compilation skipped (JAR is newer than all inputs).
echo [3/4] Packaging skipped.
goto done

:compile
echo [2/4] Compiling...
if not exist "%OUT%" mkdir "%OUT%"
set "SOURCES=%OUT%\sources.list"
if exist "%SOURCES%" del "%SOURCES%"
for /r "src" %%S in (*.java) do (
    set "SOURCE_PATH=%%~fS"
    echo "!SOURCE_PATH:\=/!">>"%SOURCES%"
)
"%JAVAC%" -cp "%LIB%\montoya-api.jar;%LIB%\gson.jar;%LIB%\nanohttpd.jar;%LIB%\re2j.jar" -d "%OUT%" @"%SOURCES%"
set "COMPILE_RESULT=%ERRORLEVEL%"
del "%SOURCES%"
if not "%COMPILE_RESULT%"=="0" (
    echo COMPILE FAILED
    exit /b 1
)

echo [3/4] Packaging fat jar...
if not exist "%DIST%" mkdir "%DIST%"
pushd "%OUT%"
if errorlevel 1 exit /b 1
"%JAR%" xf "..\..\%LIB%\gson.jar" com
if errorlevel 1 goto package_failed
"%JAR%" xf "..\..\%LIB%\nanohttpd.jar" fi
if errorlevel 1 goto package_failed
"%JAR%" xf "..\..\%LIB%\re2j.jar" com
if errorlevel 1 goto package_failed
popd
"%JAR%" cf "%ARTIFACT%" -C "%OUT%" .
if errorlevel 1 exit /b 1

:done
echo [4/4] Done!
echo Output: %ARTIFACT%
echo.
echo Install: Burp Suite -^> Extensions -^> Add -^> Java -^> Select %ARTIFACT%
exit /b 0

:package_failed
popd
echo PACKAGING FAILED
exit /b 1
