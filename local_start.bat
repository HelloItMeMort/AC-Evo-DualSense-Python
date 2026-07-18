@echo off
REM Local launcher - uses existing app/acevo.zuv.py without any GitHub update check.
setlocal EnableDelayedExpansion

set "DIR=%~dp0"
set "BUNDLE=%DIR%app\acevo.zuv.py"

if not exist "%BUNDLE%" (
    echo app/acevo.zuv.py not found. Build it first:
    echo   cd src ^&^& uvx zuv build src -o ..\app\acevo.zuv.py
    pause & exit /b 1
)

where uv >nul 2>nul
if errorlevel 1 (
    echo Installing uv...
    powershell -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>nul || (echo uv not on PATH - restart terminal. & pause & exit /b 1)
)

REM Don't let host Python env leak into the bundled venv.
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "UV_PYTHON_PREFERENCE=only-managed"

uv run "%BUNDLE%"
endlocal
exit /b %ERRORLEVEL%
