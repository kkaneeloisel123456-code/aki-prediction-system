@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   AKI Prediction System - One-Click Launcher
echo ============================================
echo.

set "PY_INIT="
python --version >nul 2>nul
if not errorlevel 1 set "PY_INIT=python"
if not defined PY_INIT (
    for %%V in (3.13 3.12 3.11 3.10 3) do (
        if not defined PY_INIT (
            py -%%V --version >nul 2>nul
            if not errorlevel 1 set "PY_INIT=py -%%V"
        )
    )
)
if not defined PY_INIT (
    echo [ERROR] Python not found.
    echo Please install Python 3.10 or newer first.
    echo Remember to check "Add Python to PATH".
    pause
    exit /b 1
)

echo Using Python: %PY_INIT%

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
    echo [1/4] Creating virtual environment...
    %PY_INIT% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

if not exist "%PY%" (
    echo [ERROR] Virtual environment creation failed.
    pause
    exit /b 1
)

echo [2/4] Installing dependencies...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

if not exist "models\final_voting_model.pkl" (
    echo [3/4] Model not found, training final model...
    "%PY%" run_clean.py
    if errorlevel 1 (
        echo [ERROR] Model training failed.
        pause
        exit /b 1
    )
) else (
    if not exist "app_data\final_model.joblib" (
        echo [3/4] Deployment files missing, syncing from models...
        "%PY%" -c "import joblib, pathlib, pickle; joblib.dump(pickle.load(open('models/final_voting_model.pkl','rb')), 'app_data/final_model.joblib'); joblib.dump(pickle.load(open('models/scaler.pkl','rb')), 'app_data/scaler.joblib'); pathlib.Path('app_data/features.txt').write_text(pathlib.Path('models/selected_features.txt').read_text(encoding='utf-8'), encoding='utf-8')"
        if errorlevel 1 (
            echo [ERROR] Failed to sync deployment files.
            pause
            exit /b 1
        )
    ) else (
        echo [3/4] Model found, skip training.
    )
)

echo [4/4] Starting Streamlit Web App...
echo.
echo If the browser does not open automatically, visit:
echo   http://localhost:8501
echo.
powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process 'http://localhost:8501'"
"%PY%" -m streamlit run streamlit_app.py
pause
