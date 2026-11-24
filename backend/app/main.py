# -*- coding: utf-8 -*-
"""FastAPI application exposing the AKI prediction model."""
from __future__ import annotations

import io
import logging
import math
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import predictor
from .assets import load_assets
from .auth import AuthTokenError
from .auth_service import (
    authenticate,
    change_password,
    cleanup_expired,
    clear_login_failures,
    create_session,
    is_configured,
    login_rate_limited,
    public_user,
    read_session,
    record_login_failure,
    revoke_session,
    verify_csrf,
)
from .config import (
    AUTH_COOKIE_NAME,
    AUTH_CSRF_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    AUTH_REMEMBER_DAYS,
    AUTH_SESSION_HOURS,
    CORS_ORIGINS,
    FEATURE_RANGES,
    OUTPUTS_DIR,
    RISK_HIGH,
    RISK_LOW,
)
from .clinical_api import router as clinical_router
from .admin_api import router as admin_router
from .patient_portal_api import router as portal_router
from .import_api import router as import_router
from .database import database_path, ensure_initialized, utc_now
from .schemas import (
    AuthStatusResponse,
    AuthUser,
    BatchPredictResponse,
    FeaturesResponse,
    HealthResponse,
    LoginRequest,
    PredictRequest,
    PredictResponse,
)

logger = logging.getLogger("aki_backend")
logging.basicConfig(level=logging.INFO)


def _safe_join(base: Path, name: str) -> Path:
    """Join name under base and prevent path traversal.

    Raises HTTP 404 if the resolved path escapes base. Only a single path
    segment (filename) is accepted.
    """
    if (not name or "/" in name or "\\" in name or name in (".", "..")
            or "\x00" in name):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = (base / name).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


@asynccontextmanager
async def _lifespan(application: FastAPI):  # noqa: ARG001
    """Initialize the business database and load model assets once at startup."""
    ensure_initialized()
    cleanup_expired()
    load_assets()
    logger.info("Clinical database and model assets ready.")
    yield


app = FastAPI(
    title="AKI Prediction API",
    version="1.0.0",
    description="急性肾损伤预测：患者档案、接诊预测、医生复核、报告发布与患者服务。",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clinical_router)
app.include_router(admin_router)
app.include_router(portal_router)
app.include_router(import_router)

_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_MUST_CHANGE_ALLOWED = {
    "/api/auth/password",
    "/api/auth/status",
    "/api/auth/logout",
}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _with_security_headers(response: Response) -> Response:
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


@app.middleware("http")
async def protect_api(request: Request, call_next):
    """Require a DB-backed session and CSRF token for staff APIs."""
    path = request.url.path.rstrip("/") or "/"
    if request.method == "OPTIONS":
        return _with_security_headers(await call_next(request))
    # Patient portal handles its own portal session and Origin checks.
    if path.startswith("/api/portal"):
        return _with_security_headers(await call_next(request))
    if not path.startswith("/api") or path in _PUBLIC_API_PATHS:
        return _with_security_headers(await call_next(request))

    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return _with_security_headers(JSONResponse(
            status_code=401, content={"detail": "登录状态已失效，请重新登录"}
        ))
    try:
        user, csrf_hash = read_session(token)
    except AuthTokenError:
        return _with_security_headers(JSONResponse(
            status_code=401, content={"detail": "登录状态已失效，请重新登录"}
        ))
    request.state.user = user
    request.state.csrf_hash = csrf_hash
    request.state.session_token = token

    if user.get("must_change_password") and path not in _MUST_CHANGE_ALLOWED:
        return _with_security_headers(JSONResponse(
            status_code=403, content={"detail": "首次登录必须修改初始密码"}
        ))
    if request.method not in _SAFE_METHODS:
        cookie_csrf = request.cookies.get(AUTH_CSRF_COOKIE_NAME)
        header_csrf = request.headers.get("x-csrf-token")
        if not verify_csrf(csrf_hash, header_csrf, cookie_csrf):
            return _with_security_headers(JSONResponse(
                status_code=403, content={"detail": "CSRF 校验失败，请刷新页面后重试"}
            ))
    return _with_security_headers(await call_next(request))


@app.post("/api/auth/login", response_model=AuthStatusResponse)
def auth_login(req: LoginRequest, request: Request, response: Response) -> AuthStatusResponse:
    username = req.username.strip()
    host = request.client.host if request.client else "unknown"
    rate_key = f"{host}|{username.lower()}"
    if login_rate_limited(rate_key):
        raise HTTPException(status_code=429, detail="登录尝试次数过多，请 5 分钟后再试")
    try:
        user = authenticate(username, req.password)
    except Exception as exc:
        logger.exception("Authentication backend unavailable")
        raise HTTPException(status_code=503, detail="认证服务暂不可用") from exc
    if user is None:
        record_login_failure(rate_key)
        raise HTTPException(status_code=401, detail="账号或密码错误")

    clear_login_failures(rate_key)
    ttl_seconds = (
        AUTH_REMEMBER_DAYS * 24 * 3600 if req.remember
        else AUTH_SESSION_HOURS * 3600
    )
    token, csrf, _ = create_session(
        user, ttl_seconds,
        ip=host, user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        AUTH_COOKIE_NAME, token,
        max_age=ttl_seconds if req.remember else None,
        path="/", secure=AUTH_COOKIE_SECURE, httponly=True, samesite="lax",
    )
    # Double-submit CSRF cookie is intentionally readable by the same-origin
    # frontend; it contains no credential by itself.
    response.set_cookie(
        AUTH_CSRF_COOKIE_NAME, csrf,
        max_age=ttl_seconds if req.remember else None,
        path="/", secure=AUTH_COOKIE_SECURE, httponly=False, samesite="lax",
    )
    return AuthStatusResponse(
        authenticated=True, configured=True, user=AuthUser(**user),
    )


@app.post("/api/auth/logout", response_model=AuthStatusResponse)
def auth_logout(request: Request, response: Response) -> AuthStatusResponse:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        try:
            _, csrf_hash = read_session(token)
            if not verify_csrf(
                csrf_hash, request.headers.get("x-csrf-token"),
                request.cookies.get(AUTH_CSRF_COOKIE_NAME),
            ):
                raise HTTPException(status_code=403, detail="CSRF 校验失败")
            revoke_session(token)
        except AuthTokenError:
            pass
    response.delete_cookie(
        AUTH_COOKIE_NAME, path="/", secure=AUTH_COOKIE_SECURE,
        httponly=True, samesite="lax",
    )
    response.delete_cookie(
        AUTH_CSRF_COOKIE_NAME, path="/", secure=AUTH_COOKIE_SECURE,
        httponly=False, samesite="lax",
    )
    try:
        configured = is_configured()
    except Exception:
        configured = False
    return AuthStatusResponse(authenticated=False, configured=configured, user=None)


@app.get("/api/auth/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    try:
        configured = is_configured()
    except Exception:
        logger.exception("Auth status check failed")
        return AuthStatusResponse(authenticated=False, configured=False, user=None)
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return AuthStatusResponse(authenticated=False, configured=configured, user=None)
    try:
        user, _ = read_session(token)
    except AuthTokenError:
        return AuthStatusResponse(authenticated=False, configured=configured, user=None)
    return AuthStatusResponse(authenticated=True, configured=configured, user=AuthUser(**user))


@app.get("/api/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    model_loaded = False
    n_features = 0
    try:
        assets = load_assets()
        model_loaded = True
        n_features = len(assets["features"])
    except Exception as exc:
        logger.error("Health check model load failed: %s", exc)

    database_ok = False
    path = database_path()
    if path.is_file():
        try:
            # Read-only URI: a health probe must never create or migrate the
            # database.  Touching the users table proves the file is a readable
            # clinical store, not merely a file that happens to open.
            probe = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5.0)
            try:
                probe.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            finally:
                probe.close()
            database_ok = True
        except sqlite3.Error as exc:
            logger.error("Health check database probe failed for %s: %s", path, exc)

    if not database_ok:
        response.status_code = 503
        return HealthResponse(
            status="unavailable", model_loaded=model_loaded,
            n_features=n_features, database_ok=False,
        )
    return HealthResponse(
        status="ok" if model_loaded else "degraded",
        model_loaded=model_loaded, n_features=n_features, database_ok=True,
    )


@app.post("/api/predict", response_model=PredictResponse)
def predict_single(req: PredictRequest) -> PredictResponse:
    # Tolerate stray whitespace in caller-supplied keys (copy-paste from
    # spreadsheets) so features aren't silently median-filled.
    feats = {k.strip(): v for k, v in req.features.items()}
    result = predictor.predict(feats, patient_id=req.patient_id)
    return PredictResponse(**result)


# Same cap as /api/predict/csv so a huge JSON payload can't starve the
# threadpool workers (per-row predict is CPU-bound).
_BATCH_MAX_ROWS = 5000


@app.post("/api/predict/batch", response_model=BatchPredictResponse)
def predict_batch(rows: List[Dict[str, Any]]) -> BatchPredictResponse:
    if not rows:
        raise HTTPException(status_code=400, detail="rows must not be empty")
    if len(rows) > _BATCH_MAX_ROWS:
        raise HTTPException(status_code=413,
                            detail=f"单次最多 {_BATCH_MAX_ROWS} 行，当前 {len(rows)} 行")
    results = []
    for i, r in enumerate(rows):
        pid = r.get("ID") or r.get("patient_id") or i + 1
        feats = {k.strip(): v for k, v in r.items() if k not in ("ID", "patient_id")}
        # Batch callers don't render SHAP; skipping it keeps throughput sane.
        out = predictor.predict(feats, patient_id=str(pid), explain=False)
        results.append(PredictResponse(**out))
    return BatchPredictResponse(count=len(results), results=results)


@app.get("/api/features", response_model=FeaturesResponse)
def features() -> FeaturesResponse:
    assets = load_assets()
    metas = predictor.feature_metas()
    return FeaturesResponse(
        features=assets["features"],
        metas=metas,
        risk_low=RISK_LOW,
        risk_high=RISK_HIGH,
    )


@app.get("/api/data/imputation")
def data_imputation() -> Dict[str, Any]:
    """Return each feature's training-phase imputation median.

    Used by the data-governance page to let users look up which features
    have imputation values (i.e., which features had missing values in the
    training cohort and were median-filled before model training).
    """
    assets = load_assets()
    rows = [
        {"feature": feat, "median": assets["impute_values"].get(feat)}
        for feat in assets["features"]
    ]
    return {"count": len(rows), "features": rows}


def _csv_dupe_columns(raw: bytes) -> list:
    """Detect duplicate headers from the raw CSV bytes.

    pandas 3.0 removed mangle_dupe_cols and silently renames duplicate
    columns to x, x.1, ... which would hide a data-entry mistake.
    """
    import csv as _csv
    text = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    reader = _csv.reader(io.StringIO(text.split(chr(10), 1)[0]))
    header = next(reader, [])
    seen = set()
    dupes = set()
    for h in header:
        h = h.strip()
        if h in seen:
            dupes.add(h)
        seen.add(h)
    return sorted(dupes)


@app.post("/api/predict/csv")
def predict_csv(file: UploadFile = File(...)) -> StreamingResponse:
    """Upload a CSV; one prediction per row; columns are feature names.

    Synchronous `def` so FastAPI runs it in the threadpool (the per-row
    predict() call is CPU-bound). Non-numeric cells are treated as missing
    and median-filled by the predictor; an optional ``ID`` column is echoed
    back as ``patient_id``.
    """
    try:
        raw = file.file.read()
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV 文件过大（上限 10MB）")
        # utf-8-sig transparently strips a BOM so the first column name is
        # not mangled when Excel exports a UTF-8 CSV. Fall back to GBK for
        # Excel's default CSV export on Chinese Windows.
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw), encoding="gbk")
        if len(df) > 5000:
            raise HTTPException(status_code=413, detail=f"单次最多 5000 行，当前 {len(df)} 行")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parse failed: {exc}")

    # Normalize header whitespace so the match-check below and the per-row
    # key lookups in the predictor agree; otherwise a padded header passes
    # validation but the column is silently median-filled.
    df.columns = [c.strip() for c in df.columns]

    rows = df.to_dict(orient="records")
    assets = load_assets()
    model_feats = set(assets["features"])
    matched = [c for c in df.columns if c in model_feats]
    # pandas silently renames duplicate headers (x -> x, x.1); detect them
    # from the raw header line instead so a data-entry mistake is surfaced.
    dupes = _csv_dupe_columns(raw)
    if dupes:
        raise HTTPException(
            status_code=400,
            detail=f"CSV 存在重复列名：{'、'.join(dupes)}。请删除重复列后重新上传。")
    missing_cols = sorted(model_feats - set(matched))
    if missing_cols:
        preview = "、".join(missing_cols[:8])
        more = f" 等 {len(missing_cols)} 列" if len(missing_cols) > 8 else ""
        raise HTTPException(
            status_code=400,
            detail=(f"CSV 缺少 {len(missing_cols)} 个模型特征列（{preview}{more}）。"
                    "数值可以留空（留空将用训练中位数填充），但 35 个特征列必须齐全，"
                    "请对照模板修正列名。"))
    if not rows:
        raise HTTPException(status_code=400, detail="CSV 没有数据行，请至少填写一行患者数据")

    results = []
    for i, row in enumerate(rows):
        pid = row.get("ID", row.get("patient_id", i + 1))
        # Empty ID cells read back as NaN; fall back to the row number instead
        # of echoing "nan" into the results file.
        if pid is None or (isinstance(pid, float) and math.isnan(pid)) or str(pid).strip().lower() == "nan":
            pid = i + 1
        clean: Dict[str, Optional[float]] = {}
        invalid: List[str] = []
        for k, v in row.items():
            if not isinstance(k, str) or k in ("ID", "patient_id"):
                continue
            # NaN -> None; non-numeric strings -> None (median-filled by predictor)
            if pd.isna(v):
                clean[k] = None
                continue
            try:
                fv = float(v)
                clean[k] = None if math.isnan(fv) or math.isinf(fv) else fv
                if math.isinf(fv):
                    invalid.append(k)
                else:
                    # Out-of-range values are median-filled by the predictor
                    # (same rule as training) - list them so the caller knows.
                    rng = FEATURE_RANGES.get(k)
                    if rng is not None and not (rng[0] <= fv <= rng[1]):
                        invalid.append(k)
            except (TypeError, ValueError):
                clean[k] = None
                # A non-empty cell that isn't a finite number was REPLACED,
                # not just left blank - surface it so the caller can fix it.
                if str(v).strip():
                    invalid.append(k)
        r = predictor.predict(clean, patient_id=str(pid), explain=False)
        results.append({
            "patient_id": r["patient_id"],
            "probability": round(r["probability"], 4),
            "risk_level": r["risk_level"],
            "prediction": r["prediction"],
            "无效值已替换为中位数": "、".join(invalid) if invalid else "",
        })

    # Write to BytesIO with utf-8-sig so Excel on Windows reads Chinese correctly.
    out = io.BytesIO()
    pd.DataFrame(results).to_csv(out, index=False, encoding="utf-8-sig")
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="AKI_predictions.csv"'},
    )


def _read_csv_records(path: Path) -> List[Dict[str, Any]]:
    """Read a CSV into JSON-safe records (NaN -> None, numpy scalars -> Python)."""
    df = pd.read_csv(path)
    records = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                clean[k] = None
            elif hasattr(v, "item"):  # numpy scalar -> Python scalar
                clean[k] = v.item()
            else:
                clean[k] = v
        records.append(clean)
    return records


@app.get("/api/performance")
def performance() -> Dict[str, Any]:
    """Return model performance metrics from outputs/tables for the UI."""
    tables = OUTPUTS_DIR / "tables"
    data: Dict[str, Any] = {}

    cv = tables / "final_cv_results.csv"
    if cv.exists():
        data["cv"] = _read_csv_records(cv)

    cal = tables / "calibration_metrics.csv"
    if cal.exists():
        data["calibration"] = _read_csv_records(cal)

    summary = tables / "model_summary_clean.csv"
    if summary.exists():
        data["summary"] = _read_csv_records(summary)

    hl = tables / "HL检验.csv"
    if hl.exists():
        data["hosmer_lemeshow"] = _read_csv_records(hl)

    return data


# --- Outputs: figures, tables, and the synthetic workstation cohort -----
_FIG_DIR = OUTPUTS_DIR / "figures"
_TAB_DIR = OUTPUTS_DIR / "tables"
_P1_FIG = OUTPUTS_DIR / "p1"
_PHASE3_FIG = OUTPUTS_DIR / "phase3" / "figures"


@app.get("/api/figures", response_model=List[str])
def list_figures() -> List[str]:
    """List available figure filenames (searched across outputs dirs)."""
    names: set[str] = set()
    for d in (_FIG_DIR, _P1_FIG, _PHASE3_FIG):
        if d.exists():
            for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                names.update(p.name for p in d.glob(pattern))
    return sorted(names)


@app.get("/api/figures/{name}")
def get_figure(name: str):
    """Serve a figure from outputs (first match wins); images only."""
    ext = Path(name).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    # outputs/figures also holds a few CSV sidecars; never serve them as images.
    if ext not in media_map:
        raise HTTPException(status_code=404, detail=f"Unsupported figure type: {ext or '(none)'}")
    for d in (_FIG_DIR, _P1_FIG, _PHASE3_FIG):
        candidate = _safe_join(d, name)
        if candidate.is_file():
            return FileResponse(str(candidate), media_type=media_map[ext])
    raise HTTPException(status_code=404, detail=f"Figure {name} not found")


@app.get("/api/tables", response_model=List[str])
def list_tables() -> List[str]:
    if not _TAB_DIR.exists():
        return []
    return sorted(p.name for p in _TAB_DIR.iterdir() if p.is_file())


@app.get("/api/tables/{name}")
def get_table(name: str) -> Response:
    """Return a table as JSON (CSV/JSON converted) or raw text."""
    candidate = _safe_join(_TAB_DIR, name)
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Table {name} not found")
    if name.lower().endswith(".csv"):
        df = pd.read_csv(candidate)
        # pandas 3.0 emits null for NaN by default; the na_rep kwarg was removed.
        df = df.where(pd.notna(df), other=float("nan"))
        body = df.to_json(orient="records", force_ascii=False)
        return Response(body, media_type="application/json")
    if name.endswith(".json"):
        return FileResponse(str(candidate), media_type="application/json")
    # errors="replace" keeps a stray non-UTF-8 file from turning into a 500.
    return Response(candidate.read_text(encoding="utf-8", errors="replace"), media_type="text/plain")


@app.get("/api/template.csv")
def download_template():
    """CSV template for batch prediction: ID + 35 feature columns (UTF-8 BOM)."""
    import csv
    assets = load_assets()
    buf = io.BytesIO()
    # Write BOM + text so Excel on Windows opens Chinese column names correctly.
    buf.write(b"\xef\xbb\xbf")
    text_buf = io.StringIO()
    w = csv.writer(text_buf)
    w.writerow(["ID"] + list(assets["features"]))
    # One example row (placeholder ID + each feature's training median) shows
    # the expected numeric format; replace or delete it before uploading.
    w.writerow(["P001"] + [assets["impute_values"].get(f, "") for f in assets["features"]])
    buf.write(text_buf.getvalue().encode("utf-8"))
    buf.seek(0)
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="AKI_prediction_template.csv"'},
    )


@app.get("/api/meta")
def app_meta() -> Dict[str, Any]:
    """Aggregate metadata for the home/dashboard pages."""
    assets = load_assets()
    best_auc = None
    cv_csv = _TAB_DIR / "final_cv_results.csv"
    if cv_csv.exists():
        df = pd.read_csv(cv_csv)
        auc_col = "50次CV AUC均值" if "50次CV AUC均值" in df.columns else "AUC"
        if auc_col in df.columns:
            value = df[auc_col].max()
            if pd.notna(value):
                best_auc = float(value)
    return {
        "n_features": len(assets["features"]),
        "n_models": 4,
        "best_auc": best_auc,
        "risk_low": RISK_LOW,
        "risk_high": RISK_HIGH,
    }


def _data_types() -> dict:
    """Count dtypes across ALL columns in the data dictionary (98 columns)."""
    counts = {"float64": 0, "int64": 0, "object": 0}
    dd = _TAB_DIR / "data_dictionary.csv"
    if dd.exists():
        try:
            ddf = pd.read_csv(dd)
            type_col = next((c for c in ddf.columns if "类型" in c), None)
            if type_col:
                for t in ddf[type_col].astype(str):
                    t = t.strip()
                    if not t or t.lower() == "nan":
                        continue  # skip blank/trailing rows
                    if "int" in t: counts["int64"] += 1
                    elif "float" in t or "数值" in t: counts["float64"] += 1
                    else: counts["object"] += 1
                return counts
        except Exception:
            pass
    return counts


@app.get("/api/data/quality")
def data_quality_dashboard() -> Dict[str, Any]:
    """Serve data quality metrics for the interactive dashboard frontend."""
    assets = load_assets()
    n_features = len(assets["features"])
    # Real stats from the training cohort (420 patients, 125 AKI / 295 non-AKI)
    missing_rates: list = []
    total_missing_cells = 0.0
    n_cols = 98  # fallback if the dictionary is absent
    if _TAB_DIR.exists():
        dd = _TAB_DIR / "data_dictionary.csv"
        if dd.exists():
            try:
                ddf = pd.read_csv(dd)
                n_cols = len(ddf)
                name_col = ddf.columns[0]
                miss_col = next((c for c in ddf.columns if "缺失" in c), None)
                if miss_col:
                    for _, r in ddf.iterrows():
                        try:
                            cnt = float(str(r[miss_col]).replace("%", ""))
                            if cnt > 0:
                                # 缺失列存的是单元格数量；转换为百分比 (cnt/420*100)
                                pct = round(cnt / 420 * 100, 2)
                                missing_rates.append({"feature": str(r[name_col]), "rate": pct})
                        except (ValueError, TypeError):
                            pass
                    missing_rates.sort(key=lambda x: -x["rate"])
                    total_missing_cells = sum(x["rate"] * 420 / 100 for x in missing_rates)
                    missing_rates = missing_rates[:6]
            except Exception:
                pass
    completeness_rates = [
        {"feature": r["feature"], "rate": round(100 - r["rate"], 1)}
        for r in missing_rates
    ]
    # Missing rate over the full raw matrix (420 rows x ~97 columns), reported
    # to 2 decimals so a small but non-zero rate doesn't round away to 0.0%.
    total_cells = 420 * max(n_cols, 1)
    missing_pct = total_missing_cells / total_cells * 100
    return {
        "stats": {
            "samples": 420,
            "features": n_features,
            "missingRate": f"{missing_pct:.2f}%",
            "completeness": f"{100 - missing_pct:.2f}%",
            "duplicates": 0
        },
        "completenessRates": completeness_rates,
        "classBalance": {"aki": 125, "nonAki": 295},
        "dataTypes": _data_types()
    }


# --- Serve the built Vue frontend in production (MUST be last) -----
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@app.get("/{full_path:path}", include_in_schema=False)
def _spa(full_path: str):
    # Unknown /api/* routes must return JSON 404, not the SPA index.html
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    index = _FRONTEND_DIST / "index.html"
    # Check dist at request time: registering this route conditionally at
    # import time would require a backend restart whenever the frontend is
    # (re)built after the server is already running.
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    if "\x00" in full_path:
        raise HTTPException(status_code=404, detail="Not Found")
    # Only serve files that resolve inside frontend/dist (block path traversal)
    candidate = (_FRONTEND_DIST / full_path).resolve()
    try:
        candidate.relative_to(_FRONTEND_DIST.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Not Found")
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    # index.html references hashed asset filenames; it must never be
    # cached, otherwise browsers keep loading a stale entry page after
    # each frontend rebuild. Hashed assets themselves stay cacheable.
    return FileResponse(
        index,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
