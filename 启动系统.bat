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

rem ---------- Use prebuilt frontend if available (no Node.js needed) ----------
if exist "frontend\dist\index.html" (
    echo [3/5] Using prebuilt frontend. Skipping npm install/build.
    goto start_server
)

rem ---------- Build frontend from source (requires Node.js) ----------
echo [3/5] Prebuilt frontend not found, building from source...
pushd frontend
call npm install
set "NPM_ERR=!errorlevel!"
if "!NPM_ERR!"=="0" call npm run build
set "BUILD_ERR=!errorlevel!"
popd
if not "!NPM_ERR!"=="0" ( echo [ERROR] npm install failed. & pause & exit /b 1 )
if not "!BUILD_ERR!"=="0" ( echo [ERROR] Frontend build failed. & pause & exit /b 1 )

:start_server

rem ---------- Start server & open browser when it is ready ----------
echo [4/5] Starting server...
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
