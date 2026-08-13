@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   AKI Full-Stack Launcher (FastAPI + Vue 3)
echo ============================================
echo.

rem ---------- Find a usable Python ----------
set "PY_INIT="
python --version >nul 2>nul
if not errorlevel 1 set "PY_INIT=python"
if not defined PY_INIT (
    for %%V in (3.14 3.13 3.12 3.11 3.10 3) do (
        if not defined PY_INIT (
            py -%%V --version >nul 2>nul
            if not errorlevel 1 set "PY_INIT=py -%%V"
        )
    )
)
if not defined PY_INIT (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ and check "Add Python to PATH".
    pause
    exit /b 1
)
echo Using Python: %PY_INIT%

rem ---------- Create / repair venv ----------
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    if exist ".venv" rmdir /s /q ".venv"
    echo [1/5] Creating virtual environment...
    %PY_INIT% -m venv .venv
    if errorlevel 1 ( echo [ERROR] Failed to create venv. & pause & exit /b 1 )
) else (
    echo [1/5] Virtual environment found.
)

rem ---------- Install backend deps if missing ----------
"%PY%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [2/5] Installing backend dependencies...
    "%PY%" -m pip install -r backend\requirements.txt
    if errorlevel 1 ( echo [ERROR] Backend install failed. & pause & exit /b 1 )
) else (
    echo [2/5] Backend dependencies found.
)

rem ---------- Install frontend deps if missing ----------
if not exist "frontend\node_modules" (
    echo [3/5] Installing frontend dependencies, please wait...
    pushd frontend
    call npm install
    set "NPM_ERR=!errorlevel!"
    popd
    if not "!NPM_ERR!"=="0" ( echo [ERROR] npm install failed. & pause & exit /b 1 )
) else (
    echo [3/5] Frontend dependencies found.
)

rem ---------- Build frontend (skip if dist is newer than all sources) ----------
set "NEED_BUILD=0"
if not exist "frontend\dist\index.html" (
    set "NEED_BUILD=1"
) else (
    rem Find newest source file under frontend/src
    set "NEWEST_SRC=0"
    for /f "delims=" %%F in ('dir /b /s /a-d "frontend\src\*" 2^>nul') do (
        if "%%~tF" gtr "!NEWEST_SRC!" set "NEWEST_SRC=%%~tF"
    )
    set "DIST_TIME=0"
    for %%F in ("frontend\dist\index.html") do set "DIST_TIME=%%~tF"
    if "!NEWEST_SRC!" gtr "!DIST_TIME!" set "NEED_BUILD=1"
)
if "!NEED_BUILD!"=="0" (
    echo [4/5] Frontend up-to-date. Skipping rebuild.
) else (
    echo [4/5] Building frontend...
    pushd frontend
    call npm run build
    set "BUILD_ERR=!errorlevel!"
    popd
    if not "!BUILD_ERR!"=="0" ( echo [ERROR] Frontend build failed. & pause & exit /b 1 )
)

rem ---------- Start server & open browser when it is ready ----------
echo [5/5] Starting server...
echo.
echo ============================================
echo   App will open at:  http://localhost:8000
echo   API docs:          http://localhost:8000/docs
echo.
echo   Close this window to stop the server.
echo ============================================
echo.

rem Wait for the server to respond (up to 60s), then open the browser.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2|Out-Null; Start-Process 'http://localhost:8000'; break}catch{Start-Sleep -Seconds 1}}"

"%PY%" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
pause
