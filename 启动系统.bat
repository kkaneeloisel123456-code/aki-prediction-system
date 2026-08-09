@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   AKI Full-Stack Launcher (FastAPI + React)
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
set "NEED_VENV=0"
if not exist "%PY%" (
    set "NEED_VENV=1"
) else (
    "%PY%" --version >nul 2>nul
    if errorlevel 1 set "NEED_VENV=1"
)
if "%NEED_VENV%"=="1" (
    if exist ".venv" (
        echo [WARN] Existing .venv is broken, recreating...
        rmdir /s /q ".venv"
    )
    echo [1/5] Creating virtual environment...
    %PY_INIT% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Virtual environment found.
)

rem ---------- Install backend dependencies ----------
"%PY%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [2/5] Installing backend dependencies...
    "%PY%" -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
) else (
    echo [2/5] Backend dependencies found.
)

rem ---------- Install frontend dependencies ----------
if not exist "frontend\node_modules" (
    echo [3/5] Installing frontend dependencies, please wait...
    cd /d "%~dp0frontend"
    call npm install
    if errorlevel 1 (
        cd /d "%~dp0"
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
    cd /d "%~dp0"
) else (
    echo [3/5] Frontend dependencies found.
)

rem ---------- Build frontend ----------
echo [4/5] Building frontend...
cd /d "%~dp0frontend"
call npm run build
if errorlevel 1 (
    cd /d "%~dp0"
    echo [ERROR] Frontend build failed.
    pause
    exit /b 1
)
cd /d "%~dp0"

rem ---------- Start backend ----------
echo [5/5] Starting backend...
echo.
echo ============================================
echo   App is running at:  http://localhost:8000
echo   API docs:           http://localhost:8000/docs
echo.
echo   Close this window to stop the server.
echo ============================================
echo.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://localhost:8000'"
"%PY%" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
pause
