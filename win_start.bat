@echo off
REM FH5 DualSense — Windows stub launcher. Downloads the latest release into ./app and runs it.

set "IS_ADMIN=0"
net session >nul 2>&1
if not errorlevel 1 set "IS_ADMIN=1"
if "%IS_ADMIN%"=="1" (echo Running as administrator.) else (echo Running as standard user.)

setlocal enabledelayedexpansion
set "REPO=HamzaYslmn/Forza-Horizon-DualSense-Python"
set "ROOT=%~dp0"
set "APP=%ROOT%app"
set "PYPROJECT=%APP%\src\pyproject.toml"
set "GAME_CMD=%*"

REM --- Resolve latest release tag ---
echo Checking latest release...
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "try { (Invoke-RestMethod -UseBasicParsing -Uri 'https://api.github.com/repos/%REPO%/releases/latest' -Headers @{'User-Agent'='fh5ds-launcher'}).tag_name } catch { '' }"`) do set "LATEST=%%v"

set "SOURCE=release"
if "!LATEST!"=="" (
    echo No release found. Falling back to 'main' branch.
    set "LATEST=main"
    set "SOURCE=branch"
)

REM --- Read installed version from pyproject.toml ---
set "CURRENT="
if exist "%PYPROJECT%" (
    for /f "tokens=1* delims==" %%a in ('findstr /b /r /c:"^version" "%PYPROJECT%"') do (
        if not defined CURRENT (
            set "v=%%b"
            set "v=!v: =!"
            set "v=!v:"=!"
            set "CURRENT=v!v!"
        )
    )
)

if "!CURRENT!"=="!LATEST!" if "!SOURCE!"=="release" (
    echo Up to date ^(!CURRENT!^).
    goto :run
)
if "!CURRENT!"=="" (
    echo Installing !LATEST!...
    goto :install
)
if "!SOURCE!"=="branch" (
    echo Refreshing 'main' branch ^(installed: !CURRENT!^)...
    goto :install
)
echo Update available: !CURRENT! -^> !LATEST!
set /p "ans=Update now? [Y/n]: "
if /I "!ans!"=="n" goto :run

:install
set "ZIP=%ROOT%fh5ds.zip"
set "EXTRACT=%ROOT%_extract"
if "!SOURCE!"=="branch" (
    set "DLURL=https://github.com/%REPO%/archive/refs/heads/!LATEST!.zip"
) else (
    set "DLURL=https://github.com/%REPO%/archive/refs/tags/!LATEST!.zip"
)
echo Downloading !LATEST!...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri '!DLURL!' -OutFile '%ZIP%'"
if errorlevel 1 (
    echo Download failed.
    if not exist "%APP%\src\main.py" (pause & exit /b 1)
    goto :run
)
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%"
echo Extracting...
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%EXTRACT%' -Force"
if exist "%APP%" rmdir /s /q "%APP%"
for /d %%d in ("%EXTRACT%\*") do (move "%%d" "%APP%" >nul & goto :moved)
:moved
rmdir /s /q "%EXTRACT%"
del "%ZIP%"
echo Installed !LATEST!.

:run
where uv >nul 2>nul
if errorlevel 1 (
    echo uv was not found. Installing from https://astral.sh/uv/ ...
    powershell -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    where uv >nul 2>nul
    if errorlevel 1 (
        echo uv installed but not on PATH. Restart your terminal.
        pause
        exit /b 1
    )
)

cd /d "%APP%\src"
if defined GAME_CMD (
    echo Launching game: !GAME_CMD!
    start "" !GAME_CMD!
)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "FH5DS_IS_ADMIN=%IS_ADMIN%"
uv run main.py
set "EXITCODE=%ERRORLEVEL%"
echo.
echo App exited with code %EXITCODE%.
if not defined GAME_CMD (
    echo Press Enter to close this window...
    pause >nul
)
endlocal
