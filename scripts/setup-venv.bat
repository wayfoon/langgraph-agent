@echo off
REM ============================================================================
REM  LangGraph Agent - virtual environment bootstrap (Windows CMD)
REM
REM  Creates backend\.venv, installs dependencies, and applies the two
REM  Windows-specific fixes this project needs:
REM
REM    1. PYTHONUTF8=1 in activate.bat
REM       Chinese Windows uses GBK (cp936) as the ANSI codepage. Python's
REM       default encoding then follows the locale, and LangGraph reads UTF-8
REM       files without an explicit encoding argument
REM       (site-packages/openapi.json, backend\.env). Under GBK that raises
REM       UnicodeDecodeError and the server refuses to start. UTF-8 mode
REM       fixes every such read at once.
REM
REM    2. backend\.env kept ASCII-only
REM       Belt and braces: even without UTF-8 mode our own config file
REM       stays readable under any codepage.
REM
REM  Usage:
REM    scripts\setup-venv.bat
REM
REM  Chinese documentation: scripts\README.md
REM
REM  NOTE ON ENCODING: keep this file's comments ASCII-only. CMD parses .bat
REM  files using the system ANSI codepage (GBK on Chinese Windows), so UTF-8
REM  Chinese comments would be executed as commands and break the script.
REM  ASCII is a subset of UTF-8, so the file stays UTF-8 encoded and works
REM  under every codepage. Chinese docs live in scripts\README.md.
REM ============================================================================

setlocal

set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."
set "BACKEND=%ROOT%\backend"
set "MIRROR=https://mirrors.aliyun.com/pypi/simple/"

echo ==========================================================
echo  LangGraph Agent - venv bootstrap
echo  Root   : %ROOT%
echo  Mirror : %MIRROR%
echo ==========================================================
echo.

cd /d "%BACKEND%"
if errorlevel 1 (
    echo [ERROR] cannot enter directory: %BACKEND%
    exit /b 1
)

if exist ".venv" (
    echo [1/4] Removing existing .venv ...
    rmdir /s /q ".venv"
)

echo [2/4] Creating virtual environment ...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found in PATH. Install Python 3.11+ first.
    exit /b 1
)
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] failed to create the virtual environment.
    exit /b 1
)

echo [3/4] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel -i %MIRROR%
if errorlevel 1 (
    echo [ERROR] failed to install build tools.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install --no-build-isolation -e . "langgraph-cli[inmem]" colorama -i %MIRROR%
if errorlevel 1 (
    echo [ERROR] failed to install project dependencies.
    exit /b 1
)

echo [4/4] Applying UTF-8 mode to activate.bat ...
".venv\Scripts\python.exe" "%ROOT%\scripts\patch_activate_utf8.py"
if errorlevel 1 (
    echo [WARN] could not patch activate.bat automatically.
    echo        Add these lines before the ':END' label in .venv\Scripts\activate.bat:
    echo            set "PYTHONUTF8=1"
    echo            set "PYTHONIOENCODING=utf-8"
)

echo.
echo ==========================================================
echo  Done.
echo  Start the backend with : scripts\dev-backend.bat
echo  Or activate manually   : .venv\Scripts\activate
echo ==========================================================

endlocal
