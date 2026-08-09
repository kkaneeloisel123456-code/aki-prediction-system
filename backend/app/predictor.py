# -*- coding: utf-8 -*-
"""Core prediction logic — framework-agnostic, reusable by tests and the API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .assets import load_assets
from .config import RISK_HIGH, RISK_LOW


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


def build_vector(features: List[str], impute_values: Dict[str, float],
                 inputs: Dict[str, Optional[float]]) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """Assemble the feature vector, median-filling missing values.

    Returns (raw_vector, missing_feature_names, vector_1xN).
    """
    X = np.zeros(len(features))
    missing: List[str] = []
    for i, feat in enumerate(features):
        val = inputs.get(feat, None)
        if val is not None:
            try:
                X[i] = float(val)
                continue
            except (TypeError, ValueError):
                pass
        X[i] = float(impute_values.get(feat, 0.0))
        missing.append(feat)
    raw = X.copy()
    return raw, missing, X.reshape(1, -1)


def predict(inputs: Dict[str, Optional[float]],
            patient_id: Optional[str] = None) -> Dict[str, Any]:
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
        prob = float(np.clip(calibrator.predict(np.array([[prob]]))[0], 0.0, 1.0))
        calibrated = True

    # SHAP on the XGBoost sub-model (tree-explainable), aligned with the
    # scaled input the voting ensemble actually scored.
    shap_vals: List[Dict[str, Any]] = []
    expected_value = 0.0
    try:
        import shap
        explainer = shap.TreeExplainer(shap_model)
        sv = explainer.shap_values(X_scaled)
        if isinstance(sv, list):
            sv = sv[1]
        sv = np.asarray(sv).ravel()
        ev = explainer.expected_value
        if isinstance(ev, (list, np.ndarray)):
            expected_value = float(ev[1] if len(ev) > 1 else ev[0])
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
    except Exception:
        # SHAP is explanatory; never fail a prediction because of it.
        pass

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
    return [
        {
            "name": f,
            "median": float(assets["impute_values"].get(f, 0.0)),
            "timing": _feature_timing(f),
        }
        for f in assets["features"]
    ]
