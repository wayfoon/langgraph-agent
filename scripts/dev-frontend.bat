@echo off
REM ============================================================================
REM  LangGraph Agent - frontend launcher (Windows CMD)
REM
REM  Usage:
REM    scripts\dev-frontend.bat
REM
REM  Open a second CMD window and run this so backend logs stay readable.
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
set "FRONTEND=%ROOT%\frontend"

echo [frontend] project root : %ROOT%
echo [frontend] starting Vite dev server on localhost:5173/app/ ...
echo.

cd /d "%FRONTEND%"
if errorlevel 1 (
    echo [ERROR] cannot enter directory: %FRONTEND%
    exit /b 1
)

if not exist "node_modules" (
    echo [ERROR] node_modules not found. Run: cd frontend ^&^& npm install
    exit /b 1
)

call npm run dev

endlocal
