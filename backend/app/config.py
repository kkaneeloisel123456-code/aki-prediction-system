# -*- coding: utf-8 -*-
"""Backend configuration: paths and the single source of truth for assets."""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/config.py -> backend/app -> backend -> project root
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

APP_DATA = PROJECT_ROOT / "app_data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Deployed artifacts (non-LFS, shipped in the submission package)
FINAL_MODEL = APP_DATA / "final_model.joblib"
SCALER = APP_DATA / "scaler.joblib"
CALIBRATOR = APP_DATA / "calibrator.joblib"
FEATURES_FILE = APP_DATA / "features.txt"
IMPUTE_VALUES = APP_DATA / "impute_values.json"

# Risk bands (must match src/config.py)
RISK_LOW = 0.30
RISK_HIGH = 0.70

# CORS: defaults cover the Vite dev server. Set CORS_ORIGINS to a comma-separated
# list of additional origins for production deployments behind a different host.
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra = os.environ.get("CORS_ORIGINS", "").strip()
if _extra:
    _default_origins.extend(o.strip() for o in _extra.split(",") if o.strip())
CORS_ORIGINS = _default_origins
