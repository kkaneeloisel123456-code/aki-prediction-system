@echo off
setlocal
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

rem ---------- Install backend deps if ANY runtime dep is missing ----------
rem Probe every package the server imports, not just fastapi/uvicorn: a
rem previously interrupted pip install could leave the others missing.
"%PY%" -c "import fastapi,uvicorn,pandas,numpy,sklearn,joblib,shap,fpdf,xgboost,pydantic" >nul 2>nul
if errorlevel 1 (
    echo [2/5] Installing backend dependencies, please wait...
    "%PY%" -m pip install -r backend\requirements.txt
    if errorlevel 1 ( echo [ERROR] Backend install failed. & pause & exit /b 1 )
) else (
    echo [2/5] Backend dependencies found.
)

rem ---------- Check Node.js before touching npm ----------
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js / npm not found.
    echo Please install Node.js 18+ from https://nodejs.org and re-run.
    pause
    exit /b 1
)

rem ---------- Install frontend deps if missing ----------
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

rem ---------- Build frontend (skip only if dist is newer than ALL sources) ----------
rem Sources include index.html / vite.config.ts / package.json, not just src/.
powershell -NoProfile -Command "$dist=(Get-Item 'frontend\dist\index.html' -ErrorAction SilentlyContinue); if (-not $dist) { exit 1 }; $files=@(); $files+=Get-ChildItem 'frontend\src' -Recurse -File; foreach ($n in 'index.html','vite.config.ts','package.json') { $p=Join-Path 'frontend' $n; if (Test-Path $p) { $files+=Get-Item $p } }; $src=$files | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if (-not $src) { exit 0 }; if ($src.LastWriteTime -gt $dist.LastWriteTime) { exit 1 } else { exit 0 }"
if errorlevel 1 (
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
) else (
    echo [4/5] Frontend up-to-date. Skipping rebuild.
)

rem ---------- Port check: free port 8000 so startup always succeeds ----------
rem Detect stale AKI instances through CIM by command line (works even where
rem netstat is unavailable), then stop them with taskkill.
rem Goto-based flow on purpose: nested parenthesized blocks are fragile in cmd.
set "AKI_PIDS=%TEMP%\aki_stale_pids.txt"
if exist "%AKI_PIDS%" del "%AKI_PIDS%" >nul 2>nul
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' } | ForEach-Object { $_.ProcessId } | Set-Content '%AKI_PIDS%'"
if not exist "%AKI_PIDS%" goto :stale_done
for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do echo [INFO] Stopping stale AKI instance, PID %%P ...
for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do taskkill /PID %%P /F >nul 2>nul
del "%AKI_PIDS%" >nul 2>nul
timeout /t 2 /nobreak >nul

:stale_done
rem Second pass: if one is still holding on, retry once.
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; $p=Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' }; if($p){exit 1}else{exit 0}"
if not errorlevel 1 goto :port_ready
echo [WARN] An AKI instance is still holding on. Retrying...
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' } | ForEach-Object { $_.ProcessId } | Set-Content '%AKI_PIDS%'"
if not exist "%AKI_PIDS%" goto :port_ready
for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do taskkill /PID %%P /F >nul 2>nul
del "%AKI_PIDS%" >nul 2>nul
timeout /t 2 /nobreak >nul

:port_ready

rem ---------- Start backend and open browser when ready ----------
rem Bound to 127.0.0.1 by default: the one-click launcher is for local/demo
rem use and the API has no auth. Set AKI_HOST=0.0.0.0 to expose it on LAN.
set "HOST=127.0.0.1"
if defined AKI_HOST set "HOST=%AKI_HOST%"

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

"%PY%" -m uvicorn backend.app.main:app --host %HOST% --port 8000
pause
goto :eof
