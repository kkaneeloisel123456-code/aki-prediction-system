# -*- coding: utf-8 -*-
"""FastAPI application exposing the AKI prediction model."""
from __future__ import annotations

import io
import logging
import math
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import predictor
from .assets import load_assets
from .config import CORS_ORIGINS, FEATURE_RANGES, OUTPUTS_DIR, RISK_HIGH, RISK_LOW
from .pdf import generate_pdf
from .schemas import (
    BatchPredictResponse,
    FeaturesResponse,
    HealthResponse,
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


def _safe_filename(pid: Optional[str]) -> str:
    """Sanitize a patient ID for safe use in a Content-Disposition filename."""
    if not pid:
        return "patient"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pid)[:64]


@asynccontextmanager
async def _lifespan(application: FastAPI):  # noqa: ARG001
    """Load model assets once at startup; fail fast if critical files are missing."""
    load_assets()
    logger.info("Model assets loaded.")
    yield


app = FastAPI(
    title="AKI Prediction API",
    version="1.0.0",
    description="急性肾损伤预测：单患者/批量预测、SHAP解释、PDF报告。",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        assets = load_assets()
        return HealthResponse(status="ok", model_loaded=True,
                             n_features=len(assets["features"]))
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return HealthResponse(status="degraded", model_loaded=False, n_features=0)


@app.post("/api/predict", response_model=PredictResponse)
def predict_single(req: PredictRequest) -> PredictResponse:
    # override_prob is a demo-only knob for /api/report/pdf; accepting it here
    # would let callers believe they can force the JSON prediction path.
    if req.override_prob is not None:
        raise HTTPException(
            status_code=422,
            detail="override_prob 仅用于 /api/report/pdf 的演示场景，/api/predict 不接受该参数")
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


@app.post("/api/report/pdf")
def report_pdf(req: PredictRequest) -> Response:
    # Same key-whitespace tolerance as /api/predict so both endpoints agree
    # on the same payload (padded keys otherwise get median-filled here but
    # not there).
    feats = {k.strip(): v for k, v in req.features.items()}
    result = predictor.predict(feats, patient_id=req.patient_id)
    if req.override_prob is not None:
        result["probability"] = req.override_prob
        result["risk_level"] = predictor.risk_band(req.override_prob)
        result["prediction"] = int(req.override_prob >= 0.5)
        result["calibrated"] = False
        # The PDF draws a visible banner when this is set, so a demo report
        # can never be mistaken for a real model prediction.
        result["probability_overridden"] = True
    pdf_bytes = generate_pdf(
        {"id": req.patient_id or "N/A", "age": feats.get("年龄")},
        result,
    )
    safe = _safe_filename(req.patient_id)
    filename = f"AKI_Report_{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



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


@app.get("/api/workstation/cohort")
def workstation_cohort() -> Dict[str, Any]:
    """Synthetic 20-patient cohort (seed=42), predicted by the real model.

    Demo data only — not real patients.
    """
    import random
    rng = random.Random(42)
    n = 20
    surgery_types = [
        "心脏瓣膜手术", "冠状动脉旁路移植术", "联合手术",
        "结构性心脏病手术", "大血管疾病手术",
    ]
    patients = []
    for i in range(n):
        age    = rng.randint(45, 81)
        sex = "男" if rng.choice([True, False]) else "女"
        surgery = rng.choice(surgery_types)
        apache = rng.randint(8, 29)
        # Pre-op values (clinically plausible, correlated with age)
        pre_scr  = round(rng.uniform(60, 130), 1)
        pre_egfr = round(max(35.0, 110 - age * 0.55 + rng.gauss(0, 12)), 1)
        pre_bnp  = round(max(50.0, 300 + (age - 55) * 18 + rng.gauss(0, 250)), 1)
        pre_hstn = round(max(2.0, 8 + (age - 55) * 0.25 + rng.gauss(0, 6)), 2)
        pre_wbc  = round(max(3.5, 7 + rng.gauss(0, 2)), 2)
        # ICU admission values — the model's top drivers; vary widely so the
        # cohort shows a realistic mix of low / medium / high risk.
        icu_scr  = round(max(45.0, pre_scr * rng.uniform(0.8, 2.6) + rng.gauss(0, 12)), 1)
        icu_egfr = round(max(10.0, pre_egfr * rng.uniform(0.4, 1.15) + rng.gauss(0, 8)), 1)
        # Post-op biomarkers (elevated in AKI)
        post_lac = round(max(0.8, 2.5 + (icu_scr - pre_scr) * 0.04 + rng.gauss(0, 1.6)), 2)
        post_b2m = round(max(1.0, 1.5 + (icu_scr - pre_scr) * 0.025 + rng.gauss(0, 0.9)), 2)
        post_mb  = round(max(100.0, 250 + rng.gauss(0, 180) + (post_lac - 2.5) * 80), 1)
        post_urea= round(max(3.0, 5.0 + (icu_scr - pre_scr) * 0.05 + rng.gauss(0, 2.5)), 2)
        post_alb = round(min(42.0, 33 - (post_lac - 2.5) * 0.8 + rng.gauss(0, 2)), 1)
        post_be  = round(max(-10.0, -2.5 - (post_lac - 2.5) * 1.2 + rng.gauss(0, 1.5)), 2)
        post_hstn= round(max(50.0, pre_hstn * rng.uniform(1.5, 8) + rng.gauss(0, 200)), 1)
        surg_time = int(max(120.0, rng.gauss(290, 90)))
        blood_loss= int(max(100.0, rng.gauss(400, 250)))
        crystalloid=int(max(200.0, rng.gauss(600, 250)))
        features = {
            "年龄": float(age),
            "性别": 1.0 if sex == "男" else 2.0,
            "术前Scr": pre_scr,
            "术前eGFR": pre_egfr,
            "术前BNP": pre_bnp,
            "术前hsTn": pre_hstn,
            "术前WBC": pre_wbc,
            "APACHEII": float(apache),
            "ICUAdmSCr": icu_scr,
            "ICUAdmeGFR": icu_egfr,
            "术后Lactate": post_lac,
            "术后β2MG": post_b2m,
            "术后Mb": post_mb,
            "术后Urea": post_urea,
            "术后Alb": post_alb,
            "术后BE": post_be,
            "术后hsTn": post_hstn,
            "手术时间": float(surg_time),
            "术中失血量": float(blood_loss),
            "术中晶体液量": float(crystalloid),
        }
        pred = predictor.predict(features, explain=False)
        patients.append({
            "id": f"P{1001+i:04d}",
            "age": age, "sex": sex, "surgery": surgery,
            "preScr": pre_scr, "preEgfr": pre_egfr, "apache": apache,
            "probability": pred["probability"],
            "riskLevel": pred["risk_level"],
            # Full feature vector so "查看" can pre-fill the prediction form.
            "features": features,
        })
    high = sum(1 for p in patients if p["riskLevel"] == "高")
    mid = sum(1 for p in patients if p["riskLevel"] == "中")
    low = sum(1 for p in patients if p["riskLevel"] == "低")
    return {
        "patients": patients,
        "summary": {"high": high, "mid": mid, "low": low, "total": n},
    }


@app.get("/api/dashboard/demo")
def dashboard_demo() -> Dict[str, Any]:
    """Hard-coded demo data for the management dashboard (not real statistics)."""
    return {
        "trend": {
            "months": ["2025-09","2025-10","2025-11","2025-12","2026-01",
                       "2026-02","2026-03","2026-04","2026-05","2026-06"],
            "akiRates": [32.5,31.2,33.8,30.1,29.5,28.7,27.3,28.1,26.8,25.9],
            "totalCases": [38,42,35,40,45,41,48,39,43,46],
        },
        "departments": [
            {"name": "心血管外科", "cases": 180, "akiRate": 32.2},
            {"name": "心脏大血管外科", "cases": 95, "akiRate": 28.4},
            {"name": "结构性心脏病科", "cases": 72, "akiRate": 25.0},
            {"name": "胸外科", "cases": 45, "akiRate": 22.2},
            {"name": "其他", "cases": 28, "akiRate": 35.7},
        ],
        "akiRate": 29.8,
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
