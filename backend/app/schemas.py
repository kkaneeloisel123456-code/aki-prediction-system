# -*- coding: utf-8 -*-
"""Pydantic request/response schemas (the API contract)."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Feature values keyed by the model's feature names.

    Any omitted feature is filled with its training median. Extra keys are
    ignored (so callers may send demographics that aren't model features).
    """
    features: Dict[str, float] = Field(
        default_factory=dict,
        description="Map of feature name -> value. Missing keys use training medians.",
    )
    patient_id: Optional[str] = Field(
        default=None, description="Optional label echoed back in the response."
    )
    override_prob: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Optional override for the final probability (used for UI demo mocks). Must be in [0, 1].",
    )


class ShapContribution(BaseModel):
    feature: str
    value: float
    shap: float
    direction: str  # "risk" (increases) or "protect" (decreases)


class PredictResponse(BaseModel):
    patient_id: Optional[str] = None
    probability: float
    prediction: int
    risk_level: str            # 低 / 中 / 高
    calibrated: bool
    shap_values: List[ShapContribution]
    expected_value: float
    missing_filled: List[str]


class BatchPredictResponse(BaseModel):
    count: int
    results: List[PredictResponse]


class FeatureMeta(BaseModel):
    name: str
    median: float
    timing: str  # preop / intraop / icu / postop
    label: str | None = None
    unit: str | None = None
    reference: str | None = None
    input: str | None = "number"
    # Clinical plausibility bounds for form validation (None when the
    # training side had no range for this feature).
    lo: float | None = None
    hi: float | None = None


class FeaturesResponse(BaseModel):
    features: List[str]
    metas: List[FeatureMeta]
    risk_low: float
    risk_high: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    n_features: int
