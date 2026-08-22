# -*- coding: utf-8 -*-
"""Core prediction logic — framework-agnostic, reusable by tests and the API."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from .assets import load_assets
from .config import FEATURE_RANGES, RISK_HIGH, RISK_LOW


def risk_band(prob: float) -> str:
    if prob >= RISK_HIGH:
        return "高"
    if prob >= RISK_LOW:
        return "中"
    return "低"


def _feature_timing(name: str) -> str:
    if name.startswith("ICU"):
        return "icu"
    if name.startswith("术中"):
        return "intraop"
    if name.startswith("术后"):
        return "postop"
    return "preop"


def _is_missing(val: Any) -> bool:
    """Return True for None, NaN, inf, or non-numeric values that must be imputed."""
    if val is None:
        return True
    try:
        f = float(val)
    except (TypeError, ValueError):
        return True
    return math.isnan(f) or math.isinf(f)


# TreeExplainer construction walks the whole booster and costs roughly a
# second; cache it against the (lru_cache'd) model so per-request SHAP
# doesn't rebuild it every call.
_EXPLAINER_CACHE: Tuple[Optional[int], Any] = (None, None)  # (id(model), explainer)


def _get_explainer(shap_model: Any) -> Any:
    global _EXPLAINER_CACHE
    cached_id, cached = _EXPLAINER_CACHE
    if cached is None or cached_id != id(shap_model):
        import shap
        cached = shap.TreeExplainer(shap_model)
        _EXPLAINER_CACHE = (id(shap_model), cached)
    return cached


def build_vector(features: List[str], impute_values: Dict[str, float],
                 inputs: Mapping[str, Optional[float]]) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Assemble the feature vector, median-filling missing values.

    Returns (raw_vector, missing_feature_names, vector_1xN).
    """
    X = np.zeros(len(features))
    missing: List[str] = []
    for i, feat in enumerate(features):
        val = inputs.get(feat, None)
        if not _is_missing(val):
            v = float(val)
            rng = FEATURE_RANGES.get(feat)
            # Mirror the training pipeline: physiologically impossible values
            # were flagged as missing there, so median-fill them here too
            # instead of letting a typo drive the prediction.
            if rng is not None and not (rng[0] <= v <= rng[1]):
                X[i] = impute_values.get(feat, 0.0)
                missing.append(feat)
                continue
            # Clamp to a clinically sane range: huge values overflow float32
            # inside the tree models and crash with a 500.
            X[i] = float(np.clip(v, -1e6, 1e6))
        else:
            X[i] = impute_values.get(feat, 0.0)
            missing.append(feat)
    raw = X.copy()
    return raw, missing, X.reshape(1, -1)


def predict(inputs: Mapping[str, Optional[float]],
            patient_id: Optional[str] = None,
            explain: bool = True) -> Dict[str, Any]:
    """Run the full pipeline: scale -> vote -> calibrate -> SHAP."""
    assets = load_assets()
    model = assets["model"]
    scaler = assets["scaler"]
    calibrator = assets["calibrator"]
    features = assets["features"]
    impute = assets["impute_values"]
    shap_model = assets["shap_model"]

    X_raw, missing_filled, X = build_vector(features, impute, inputs)

    X_scaled = scaler.transform(X)

    if hasattr(model, "predict_proba"):
        prob = float(model.predict_proba(X_scaled)[0, 1])
    else:
        prob = float(model.predict(X_scaled)[0])

    calibrated = False
    if calibrator is not None:
        prob = float(np.clip(calibrator.predict(np.array([prob]))[0], 0.0, 1.0))
        calibrated = True

    # SHAP on the XGBoost sub-model (tree-explainable), aligned with the
    # scaled input the voting ensemble actually scored.
    shap_vals: List[Dict[str, Any]] = []
    expected_value = 0.0

    if explain:
        try:
            explainer = _get_explainer(shap_model)
            sv = explainer.shap_values(X_scaled)
            if isinstance(sv, list):
                sv = sv[1]
            sv = np.asarray(sv)
            # Binary classification may return shape (1, n_features, 2) in some shap/xgboost versions.
            if sv.ndim == 3:
                sv = sv[0, :, 1] if sv.shape[-1] == 2 else sv[0]
            sv = sv.ravel()
            if sv.shape[0] != len(features):
                raise ValueError(f"SHAP shape {sv.shape} does not match {len(features)} features")
            ev = explainer.expected_value
            if isinstance(ev, (list, np.ndarray)):
                ev_arr = np.asarray(ev).ravel()
                expected_value = float(ev_arr[1] if len(ev_arr) > 1 else ev_arr[0])
            else:
                expected_value = float(ev)

            order = np.argsort(np.abs(sv))[::-1]
            for i in order:
                contribution = float(sv[i])
                shap_vals.append({
                    "feature": features[i],
                    "value": float(X_raw[i]),
                    "shap": contribution,
                    "direction": "risk" if contribution > 0 else "protect",
                })
        except Exception as exc:
            # SHAP is explanatory; never fail a prediction because of it.
            import logging
            logging.getLogger("aki_backend").warning("SHAP explanation failed: %s", exc)

    return {
        "patient_id": patient_id,
        "probability": prob,
        "prediction": int(prob >= 0.5),
        "risk_level": risk_band(prob),
        "calibrated": calibrated,
        "shap_values": shap_vals,
        "expected_value": expected_value,
        "missing_filled": missing_filled,
    }


def feature_metas() -> List[Dict[str, Any]]:
    assets = load_assets()
    from .feature_labels import get_label
    metas: List[Dict[str, Any]] = []
    for f in assets["features"]:
        rng = FEATURE_RANGES.get(f)
        metas.append({
            "name": f,
            "median": float(assets["impute_values"].get(f, 0.0)),
            "timing": _feature_timing(f),
            # lo/hi: clinical plausibility bounds used for frontend validation
            # (None when the training side had no range for this feature).
            "lo": rng[0] if rng else None,
            "hi": rng[1] if rng else None,
            **get_label(f),
        })
    return metas
