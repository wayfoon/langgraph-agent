@echo off
REM ============================================================================
REM  LangGraph Agent - start both servers (Windows CMD)
REM
REM  Usage:
REM    scripts\dev.bat
REM
REM  Opens two separate CMD windows so backend and frontend logs stay
REM  independent. Close them with Ctrl+C or just close the windows.
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

echo Starting backend  -> 127.0.0.1:2024  (new window)
start "LangGraph Backend" cmd /k ""%SCRIPT_DIR%dev-backend.bat""

echo Waiting 6s for the backend to come up...
timeout /t 6 /nobreak >nul

echo Starting frontend -> localhost:5173/app/  (new window)
start "LangGraph Frontend" cmd /k ""%SCRIPT_DIR%dev-frontend.bat""

echo.
echo ==========================================================
echo  Frontend : http://localhost:5173/app/
echo  Backend  : http://127.0.0.1:2024
echo  API docs : http://127.0.0.1:2024/docs
echo.
echo  Two CMD windows were opened. Close them to stop.
echo ==========================================================

endlocal
