@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   AKI 全栈启动器 (FastAPI + Vue 3)
echo ============================================
echo 首次运行需安装依赖，约 3-10 分钟，请耐心等待
echo.

rem ---------- 查找 Python (要求 3.10+) ----------
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
    echo [错误] 未找到 Python。请安装 Python 3.10+ 并勾选"Add Python to PATH"。
    pause
    exit /b 1
)
rem 版本闸门：Python 3.9 以下在启动时直接报错，避免装完依赖后才发现不兼容
%PY_INIT% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [错误] Python 版本过低，需要 3.10+。当前版本：
    %PY_INIT% --version
    pause
    exit /b 1
)
%PY_INIT% -c "import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)" >nul 2>nul
if not errorlevel 1 (
    echo [警告] Python 3.14+ 尚未完成完整兼容性验证，建议使用 Python 3.11-3.13。
)
echo 使用 Python: %PY_INIT%

rem ---------- 创建 / 修复 venv ----------
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    if exist ".venv" rmdir /s /q ".venv"
    echo [1/5] 创建虚拟环境...
    %PY_INIT% -m venv .venv
    if errorlevel 1 ( echo [错误] 创建虚拟环境失败。 & pause & exit /b 1 )
) else (
    echo [1/5] 虚拟环境已就绪。
)

rem ---------- 安装后端依赖（含修复循环）----------
rem 探测全部运行时依赖；漏掉 python-multipart 会导致启动即崩
:check_deps
"%PY%" -c "import fastapi,uvicorn,pandas,numpy,sklearn,joblib,shap,fpdf,xgboost,pydantic,multipart" >nul 2>nul
if not errorlevel 1 goto :deps_ok

echo [2/5] 安装后端依赖，请等待...
call :pip_install
"%PY%" -c "import fastapi,uvicorn,pandas,numpy,sklearn,joblib,shap,fpdf,xgboost,pydantic,multipart" >nul 2>nul
if not errorlevel 1 goto :deps_ok

rem 探测再次失败：venv 可能损坏，重建
echo [警告] 虚拟环境可能损坏，正在重建...
rmdir /s /q ".venv" 2>nul
%PY_INIT% -m venv .venv --clear
if errorlevel 1 ( echo [错误] 重建虚拟环境失败。 & pause & exit /b 1 )
call :pip_install
"%PY%" -c "import fastapi,uvicorn,pandas,numpy,sklearn,joblib,shap,fpdf,xgboost,pydantic,multipart" >nul 2>nul
if errorlevel 1 ( echo [错误] 依赖安装失败，请检查网络连接。 & pause & exit /b 1 )
goto :deps_ok

:pip_install
"%PY%" -m pip install -r backend\requirements.txt
if errorlevel 1 ( echo [错误] 后端依赖安装失败。 & pause & exit /b 1 )
exit /b 0

:deps_ok
echo [2/5] 后端依赖已就绪。

rem ---------- 前端依赖与构建（无 Node 时可跳过）----------
rem 只在需要重新构建时才检查 Node.js；dist 可用时后端本身不依赖 Node
set "NEED_BUILD=1"
powershell -NoProfile -Command "$dist=(Get-Item 'frontend\dist\index.html' -ErrorAction SilentlyContinue); if (-not $dist) { exit 1 }; $files=@(); $files+=Get-ChildItem 'frontend\src' -Recurse -File; foreach ($n in 'index.html','vite.config.ts','package.json') { $p=Join-Path 'frontend' $n; if (Test-Path $p) { $files+=Get-Item $p } }; $src=$files | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if (-not $src) { exit 0 }; if ($src.LastWriteTime -gt $dist.LastWriteTime) { exit 1 } else { exit 0 }"
if not errorlevel 1 (
    echo [3/5] 前端已是最新构建，跳过。
    set "NEED_BUILD=0"
)
if "%NEED_BUILD%"=="1" (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [错误] 需要重新构建前端但未找到 Node.js / npm。
        echo 请安装 Node.js 18+ 后重试，或从提交包中获取已构建的 frontend\dist。
        pause
        exit /b 1
    )
    if not exist "frontend\node_modules" (
        echo [3/5] 安装前端依赖，请等待...
        cd /d "%~dp0frontend"
        if exist "frontend\package-lock.json" (
            call npm ci
        ) else (
            call npm install
        )
        if errorlevel 1 (
            cd /d "%~dp0"
            echo [错误] 前端依赖安装失败。
            pause
            exit /b 1
        )
        cd /d "%~dp0"
    ) else (
        echo [3/5] 前端依赖已就绪。
    )
    echo [4/5] 构建前端...
    cd /d "%~dp0frontend"
    call npm run build
    if errorlevel 1 (
        cd /d "%~dp0"
        echo [错误] 前端构建失败。可尝试删除 frontend\node_modules 后重试。
        pause
        exit /b 1
    )
    cd /d "%~dp0"
) else (
    echo [4/5] 前端构建跳过。
)

if not exist "app_data\final_model.joblib" (
    echo [错误] 缺少 app_data\final_model.joblib，无法启动预测服务。
    pause
    exit /b 1
)

rem ---------- 端口检查：释放旧实例，检测占用 ----------
set "AKI_PIDS=%TEMP%\aki_stale_pids.txt"
if exist "%AKI_PIDS%" del "%AKI_PIDS%" >nul 2>nul
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' } | ForEach-Object { $_.ProcessId } | Set-Content '%AKI_PIDS%'"
if not exist "%AKI_PIDS%" goto :stale_done
for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do echo [信息] 正在停止旧 AKI 实例，PID %%P...
for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do taskkill /PID %%P /F >nul 2>nul
del "%AKI_PIDS%" >nul 2>nul
timeout /t 2 /nobreak >nul

:stale_done
rem 第二轮重试
powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; $p=Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' }; if($p){exit 1}else{exit 0}"
if errorlevel 1 (
    echo [警告] 旧实例仍在运行，重试停止...
    powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | Where-Object { $_.CommandLine -match 'backend\.app\.main' } | ForEach-Object { $_.ProcessId } | Set-Content '%AKI_PIDS%'"
    if exist "%AKI_PIDS%" (
        for /f "usebackq delims=" %%P in ("%AKI_PIDS%") do taskkill /PID %%P /F >nul 2>nul
        del "%AKI_PIDS%" >nul 2>nul
        timeout /t 2 /nobreak >nul
    )
)

rem 如 8000 仍被占用（非本系统进程），自动尝试 8001-8010 备用端口
set "PORT=8000"
for /L %%P in (8000,1,8010) do (
    powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; $l=(Get-NetTCPConnection -LocalPort %%P -ErrorAction SilentlyContinue); if($l){exit 1}else{exit 0}"
    if not errorlevel 1 (
        set "PORT=%%P"
        goto :port_found
    )
)
echo [错误] 8000-8010 端口均被占用，无法启动。
pause
exit /b 1

:port_found
if "%PORT%"=="8000" (echo [信息] 端口 8000 可用。) else (echo [信息] 8000 被占用，已自动切换到端口 %PORT%。)

rem ---------- 启动服务 ----------
set "HOST=127.0.0.1"
if defined AKI_HOST set "HOST=%AKI_HOST%"

echo [5/5] 启动服务...
echo.
echo ============================================
echo   系统地址:  http://localhost:%PORT%
echo   API 文档:  http://localhost:%PORT%/docs
echo.
echo   关闭本窗口即可停止服务。
echo ============================================
echo.

rem 轮询后端健康检查（最多 60 秒），待模型加载完毕再打开浏览器
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){try{$r=Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/api/health' -TimeoutSec 2; if($r.status -eq 'ok'){Start-Process 'http://localhost:%PORT%'; break}}catch{Start-Sleep -Seconds 1}}"

"%PY%" -m uvicorn backend.app.main:app --host %HOST% --port %PORT%
pause
goto :eof
