# -*- coding: utf-8 -*-
"""FastAPI application exposing the AKI prediction model."""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import predictor
from .assets import load_assets
from .config import CORS_ORIGINS, OUTPUTS_DIR, RISK_HIGH, RISK_LOW
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

app = FastAPI(
    title="AKI Prediction API",
    version="1.0.0",
    description="急性肾损伤预测：单患者/批量预测、SHAP解释、PDF报告。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warmup() -> None:
    """Load models at startup so the first request isn't slow."""
    try:
        load_assets()
        logger.info("Model assets loaded.")
    except Exception as exc:
        logger.error("Failed to load assets: %s", exc)


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
    result = predictor.predict(req.features, patient_id=req.patient_id)
    return PredictResponse(**result)


@app.post("/api/predict/batch", response_model=BatchPredictResponse)
def predict_batch(rows: List[Dict[str, Any]]) -> BatchPredictResponse:
    if not rows:
        raise HTTPException(status_code=400, detail="rows must not be empty")
    results = [PredictResponse(**predictor.predict(r)) for r in rows]
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


@app.post("/api/report/pdf")
def report_pdf(req: PredictRequest) -> Response:
    result = predictor.predict(req.features, patient_id=req.patient_id)
    pdf_bytes = generate_pdf(
        {"id": req.patient_id or "N/A", "age": req.features.get("年龄")},
        result,
    )
    filename = f"AKI_Report_{req.patient_id or 'patient'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/predict/csv")
async def predict_csv(file: UploadFile = File(...)) -> StreamingResponse:
    """Upload a CSV; one prediction per row; columns are feature names."""
    try:
        raw = await file.read()
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parse failed: {exc}")

    rows = df.to_dict(orient="records")
    results = []
    for i, row in enumerate(rows):
        # NaN -> missing (median-filled by predictor)
        clean = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        r = predictor.predict(clean, patient_id=str(clean.get("ID", i + 1)))
        results.append({
            "patient_id": r["patient_id"],
            "probability": round(r["probability"], 4),
            "risk_level": r["risk_level"],
            "prediction": r["prediction"],
        })

    out = io.StringIO()
    pd.DataFrame(results).to_csv(out, index=False, encoding="utf-8-sig")
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="AKI_predictions.csv"'},
    )


@app.get("/api/performance")
def performance() -> Dict[str, Any]:
    """Return model performance metrics from outputs/tables for the UI."""
    tables = OUTPUTS_DIR / "tables"
    data: Dict[str, Any] = {}

    cv = tables / "final_cv_results.csv"
    if cv.exists():
        df = pd.read_csv(cv)
        data["cv"] = df.to_dict(orient="records")

    cal = tables / "calibration_metrics.csv"
    if cal.exists():
        df = pd.read_csv(cal)
        data["calibration"] = df.to_dict(orient="records")

    summary = tables / "model_summary_clean.csv"
    if summary.exists():
        df = pd.read_csv(summary)
        data["summary"] = df.to_dict(orient="records")

    hl = tables / "HL检验.csv"
    if hl.exists():
        df = pd.read_csv(hl)
        data["hosmer_lemeshow"] = df.to_dict(orient="records")

    return data


# --- Outputs: figures, tables, and the synthetic workstation cohort -----
from pathlib import Path
from fastapi.responses import FileResponse

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
            names.update(p.name for p in d.glob("*.png"))
    return sorted(names)


@app.get("/api/figures/{name}")
def get_figure(name: str):
    """Serve a PNG figure from outputs (first match wins)."""
    for d in (_FIG_DIR, _P1_FIG, _PHASE3_FIG):
        candidate = d / name
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate), media_type="image/png")
    raise HTTPException(status_code=404, detail=f"Figure {name} not found")


@app.get("/api/tables", response_model=List[str])
def list_tables() -> List[str]:
    if not _TAB_DIR.exists():
        return []
    return sorted(p.name for p in _TAB_DIR.iterdir() if p.is_file())


@app.get("/api/tables/{name}")
def get_table(name: str) -> Response:
    """Return a table as JSON (CSV/JSON converted) or raw text."""
    candidate = _TAB_DIR / name
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Table {name} not found")
    if name.endswith(".csv"):
        df = pd.read_csv(candidate)
        return Response(df.to_json(orient="records", force_ascii=False),
                        media_type="application/json")
    if name.endswith(".json"):
        return FileResponse(str(candidate), media_type="application/json")
    return Response(candidate.read_text(encoding="utf-8"), media_type="text/plain")


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
            best_auc = float(df[auc_col].max())
    return {
        "n_features": len(assets["features"]),
        "n_models": 5,
        "best_auc": best_auc,
        "risk_low": RISK_LOW,
        "risk_high": RISK_HIGH,
    }


@app.get("/api/workstation/cohort")
def workstation_cohort() -> Dict[str, Any]:
    """Synthetic 20-patient cohort (seed=42), predicted by the real model.

    Mirrors streamlit_app.page_doctor_workstation; demo data only.
    """
    import numpy as np
    rng = np.random.RandomState(42)
    n = 20
    surgery_types = [
        "心脏瓣膜手术", "冠状动脉旁路移植术", "联合手术",
        "结构性心脏病手术", "大血管疾病手术",
    ]
    patients = []
    for i in range(n):
        age = int(rng.randint(25, 85))
        scr = round(float(rng.uniform(50, 180)), 1)
        egfr = round(max(15.0, 120 - age * 0.8 + float(rng.normal(0, 10))), 1)
        apache = int(rng.randint(5, 35))
        surgery = str(rng.choice(surgery_types))
        sex = "男" if rng.choice([True, False]) else "女"
        features = {
            "年龄": float(age),
            "性别": 1.0 if sex == "男" else 2.0,
            "术前Scr": scr,
            "术前eGFR": egfr,
            "APACHEII": float(apache),
        }
        pred = predictor.predict(features)
        patients.append({
            "id": f"P{1001+i:04d}",
            "age": age, "sex": sex, "surgery": surgery,
            "preScr": scr, "preEgfr": egfr, "apache": apache,
            "probability": pred["probability"],
            "riskLevel": pred["risk_level"],
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
    """Hard-coded demo data for the management dashboard (mirrors Streamlit)."""
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


# --- Serve the built React frontend in production (MUST be last) -----
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    from fastapi.responses import FileResponse as _FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa(full_path: str):
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return _FileResponse(candidate)
        return _FileResponse(_FRONTEND_DIST / "index.html")
