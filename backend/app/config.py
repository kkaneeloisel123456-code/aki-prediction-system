# -*- coding: utf-8 -*-
"""Backend configuration: paths and the single source of truth for assets."""
from __future__ import annotations

from pathlib import Path

# backend/app/config.py -> backend/app -> backend -> project root
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

APP_DATA = PROJECT_ROOT / "app_data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
WEB_DIR = PROJECT_ROOT / "backend"

# Deployed artifacts (non-LFS, shipped in the submission package)
FINAL_MODEL = APP_DATA / "final_model.joblib"
SCALER = APP_DATA / "scaler.joblib"
CALIBRATOR = APP_DATA / "calibrator.joblib"
FEATURES_FILE = APP_DATA / "features.txt"
IMPUTE_VALUES = APP_DATA / "impute_values.json"

# Bundled CJK font for PDF export
CJK_FONT = WEB_DIR / "assets" / "fonts" / "NotoSansSC-Regular.otf"

# Risk bands (must match src/config.py)
RISK_LOW = 0.30
RISK_HIGH = 0.70

# CORS: in local dev the Vite dev server runs on this origin
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
