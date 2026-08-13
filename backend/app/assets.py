# -*- coding: utf-8 -*-
"""Lazy-loaded model assets shared across API requests.

Loads the deployed Voting ensemble + scaler + calibrator from app_data/
(non-LFS files shipped with the submission). The per-fold XGBoost sub-model
is derived from the voting ensemble itself, so SHAP works even when
models/*.pkl are unresolved Git-LFS pointers.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, List

import joblib
import numpy as np

from .config import (
    CALIBRATOR, FEATURES_FILE, FINAL_MODEL, IMPUTE_VALUES, SCALER,
)

logger = logging.getLogger("aki_backend")


@lru_cache(maxsize=1)
def load_assets() -> Dict[str, Any]:
    """Load and cache all model artifacts. Raises on missing critical files."""
    model = joblib.load(FINAL_MODEL)
    scaler = joblib.load(SCALER)
    calibrator = joblib.load(CALIBRATOR) if CALIBRATOR.exists() else None

    features: List[str] = [
        ln.strip() for ln in FEATURES_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    impute_values: Dict[str, float] = json.loads(
        IMPUTE_VALUES.read_text(encoding="utf-8")
    )

    # SHAP needs a tree model. VotingClassifier is not a tree, but it carries
    # its fitted XGBoost sub-estimator — use that instead of relying on the
    # LFS-tracked models/XGBoost.pkl (which may be a 128-byte pointer).
    shap_model = model
    named = getattr(model, "named_estimators_", None)
    if named is not None and "XGBoost" in named:
        shap_model = named["XGBoost"]

    # Validate consistency between the feature list and the imputation dictionary.
    # A mismatch means deployment artifacts are out of sync — fail fast rather
    # than silently filling model features with 0.0 at inference time.
    missing = [f for f in features if f not in impute_values]
    if missing:
        raise RuntimeError(
            f"impute_values.json is missing medians for features: {missing}. "
            "Re-run training or copy a complete impute_values.json into app_data/."
        )

    return {
        "model": model,
        "scaler": scaler,
        "calibrator": calibrator,
        "features": features,
        "impute_values": impute_values,
        "shap_model": shap_model,
    }
