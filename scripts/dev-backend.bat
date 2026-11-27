@echo off
REM ============================================================================
REM  LangGraph Agent - backend launcher (Windows CMD)
REM
REM  Why this script exists:
REM    On Chinese Windows the system ANSI codepage is GBK (cp936). Python's
REM    default encoding then follows the locale, and several files read by
REM    LangGraph are UTF-8 without an explicit encoding argument:
REM       - backend/.env                      (langgraph_api/cli.py -> DotEnv)
REM       - site-packages/openapi.json       (langgraph_api/validation.py)
REM    Reading them under GBK raises UnicodeDecodeError and the server
REM    refuses to start.
REM    Setting PYTHONUTF8=1 puts Python in UTF-8 mode, which fixes every
REM    such read at once.
REM
REM  Usage:
REM    scripts\dev-backend.bat
REM
REM  LangGraph emits UTC timestamps by default. This script starts the server
REM  through backend\dev_server.py, which installs an East-Asia (+08:00)
REM  timestamp processor before the LangGraph CLI configures logging.
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

REM Force UTF-8 mode for this process and all children.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Resolve project root from this script's location (parent of scripts\).
set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."
set "BACKEND=%ROOT%\backend"

echo [backend] project root : %ROOT%
echo [backend] python mode : UTF-8 (PYTHONUTF8=1)
echo [backend] starting LangGraph dev server on 127.0.0.1:2024 ...
echo.

cd /d "%BACKEND%"
if errorlevel 1 (
    echo [ERROR] cannot enter directory: %BACKEND%
    exit /b 1
)

if not exist ".venv\Scripts\langgraph.exe" (
    echo [ERROR] virtual environment not found: %BACKEND%\.venv
    echo         Run scripts\setup-venv.bat first.
    exit /b 1
)

".venv\Scripts\python.exe" dev_server.py dev --no-browser --port 2024

endlocal
