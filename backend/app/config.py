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

# Clinical plausibility ranges. Most match the training filter in
# src/data/prepare.py CLINICAL_RANGES: a typo like SBP=1200 is rejected
# instead of driving the prediction. APACHE II uses the full clinical
# scale, 0–71; the old training cap of 50 rejected real high scores.
FEATURE_RANGES: dict[str, tuple[float, float]] = {
    "APACHEII": (0, 71),
    "手术时间": (30, 1440),
    "术中失血量": (0, 5000),
    "术中晶体液量": (0, 10000),
    "术前SBP": (60, 250),
    "术前PaO2": (30, 600),
    "术后PaO2": (30, 600),
    "术后BE": (-20, 20),
    "术后Lactate": (0, 20),
    "术后CRP": (0, 300),
    "术前WBC": (1, 50),
    "术后PLT": (20, 800),
    "术前PLT": (20, 800),
    "术前Scr": (20, 500),
    "ICUAdmSCr": (20, 500),
    "术前eGFR": (5, 200),
    "ICUAdmeGFR": (5, 200),
    "术后Urea": (1, 40),
    "术后UA": (50, 1000),
    "术前BNP": (0, 50000),
    "术后BNP": (0, 50000),
}

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

# Local authentication. The JSON file contains PBKDF2 password hashes and the
# HMAC session secret, never plaintext passwords. It is intentionally ignored
# by Git; scripts/init_auth.py creates and maintains it.
AUTH_CONFIG_FILE = Path(
    os.environ.get("AKI_AUTH_CONFIG", str(BACKEND_DIR / "auth_config.json"))
).expanduser()
CLINICAL_DB_FILE = Path(
    os.environ.get("AKI_DB_PATH", str(BACKEND_DIR / "clinical.db"))
).expanduser()
DATABASE_BACKUP_DIR = Path(
    os.environ.get("AKI_BACKUP_DIR", str(BACKEND_DIR / "backups"))
).expanduser()
AUTH_COOKIE_NAME = "aki_session"
AUTH_CSRF_COOKIE_NAME = "aki_csrf"
AUTH_COOKIE_SECURE = os.environ.get("AKI_AUTH_SECURE_COOKIE", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
AUTH_SESSION_HOURS = max(1, int(os.environ.get("AKI_AUTH_SESSION_HOURS", "12")))
AUTH_REMEMBER_DAYS = max(1, int(os.environ.get("AKI_AUTH_REMEMBER_DAYS", "7")))
PATIENT_PORTAL_TTL_MINUTES = max(5, int(os.environ.get("AKI_PORTAL_TTL_MINUTES", "720")))
PATIENT_QUERY_TTL_MINUTES = max(5, int(os.environ.get("AKI_QUERY_TTL_MINUTES", "1440")))
PATIENT_QUERY_SESSION_MINUTES = max(1, int(os.environ.get("AKI_QUERY_SESSION_MINUTES", "30")))
