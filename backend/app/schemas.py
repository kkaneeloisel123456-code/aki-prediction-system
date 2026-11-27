# -*- coding: utf-8 -*-
"""Pydantic request/response schemas (the API contract)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    # Bounds for form validation. None when this feature has no hard limit.
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
    database_ok: bool = True


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)
    remember: bool = False


class AuthUser(BaseModel):
    id: str = ""
    username: str
    display_name: str = ""
    role: str
    must_change_password: bool = False


class AuthStatusResponse(BaseModel):
    authenticated: bool
    configured: bool
    user: Optional[AuthUser] = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class UserCreateRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{2,64}$")
    display_name: str = Field(min_length=1, max_length=80)
    role: str = Field(pattern=r"^(admin|doctor)$")
    password: str = Field(min_length=12, max_length=1024)
    must_change_password: bool = True


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=80)
    role: Optional[str] = Field(default=None, pattern=r"^(admin|doctor)$")
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=1024)
    must_change_password: Optional[bool] = None


class PatientCreateRequest(BaseModel):
    mrn: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    sex: str = Field(default="未知", pattern=r"^(男|女|未知)$")
    birth_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    birth_date: Optional[str] = Field(default=None, max_length=32)
    certificate_last4: Optional[str] = Field(default=None, max_length=8)
    phone_last4: Optional[str] = Field(default=None, max_length=8)
    owner_id: Optional[str] = None


class PatientUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    sex: Optional[str] = Field(default=None, pattern=r"^(男|女|未知)$")
    birth_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    birth_date: Optional[str] = Field(default=None, max_length=32)
    certificate_last4: Optional[str] = Field(default=None, max_length=8)
    phone_last4: Optional[str] = Field(default=None, max_length=8)
    active: Optional[bool] = None
    owner_id: Optional[str] = None


class PatientGrantRequest(BaseModel):
    doctor_id: str
    permission: str = Field(pattern=r"^(view|edit)$")


class EncounterCreateRequest(BaseModel):
    case_ref: str = Field(min_length=1, max_length=60)
    occurred_at: str
    surgery_type: Optional[str] = Field(default=None, max_length=100)
    values: Dict[str, Any] = Field(default_factory=dict)
    diagnosis: str = Field(default="", max_length=4000)
    orders: str = Field(default="", max_length=4000)


class EncounterUpdateRequest(BaseModel):
    row_version: int
    values: Dict[str, Any] = Field(default_factory=dict)
    diagnosis: str = Field(default="", max_length=4000)
    orders: str = Field(default="", max_length=4000)


class DraftSaveRequest(BaseModel):
    row_version: int
    draft_version: int = 0
    values: Dict[str, Any] = Field(default_factory=dict)
    diagnosis: str = Field(default="", max_length=4000)
    orders: str = Field(default="", max_length=4000)


class ClinicalReviewRequest(BaseModel):
    row_version: int
    decision: str = Field(pattern=r"^(agree|adjust|defer|manual)$")
    reason: str = ""


class ClinicalPredictRequest(BaseModel):
    row_version: int
    features: Dict[str, Any]


class ReportPublishRequest(BaseModel):
    row_version: int
    draft_version: int = 0
    missing_ack: bool = False


class ReportRevokeRequest(BaseModel):
    """Reason supplied by an administrator when revoking a published report."""
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalise_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("撤销原因不能为空")
        return value


class PortalRegisterRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{4,64}$")
    display_name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=12, max_length=1024)
    phone_last4: Optional[str] = Field(default=None, max_length=8)


class PortalLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class PortalBindRequest(BaseModel):
    mrn: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    query_code: str = Field(min_length=6, max_length=32)
    # One second factor is required by the API: certificate last 4 or phone
    # last 4, matching the value already registered on the patient record.
    certificate_last4: Optional[str] = Field(default=None, max_length=4)
    phone_last4: Optional[str] = Field(default=None, max_length=4)


class PortalQueryRequest(PortalBindRequest):
    pass


class SlotCreateRequest(BaseModel):
    doctor_id: Optional[str] = None
    starts_at: str
    appointment_type: str = Field(pattern=r"^(门诊|检查)$")
    capacity: int = Field(default=5, ge=1, le=100)


class SlotUpdateRequest(BaseModel):
    capacity: Optional[int] = Field(default=None, ge=1, le=100)
    active: Optional[bool] = None


class AppointmentCreateRequest(BaseModel):
    slot_id: str
    reason: str = Field(default="", max_length=500)


class StaffAppointmentCreateRequest(BaseModel):
    patient_id: str
    slot_id: str
    reason: str = Field(default="", max_length=500)


class AppointmentStatusRequest(BaseModel):
    status: str = Field(pattern=r"^(checked_in|completed|cancelled|no_show)$")


class FeedbackCreateRequest(BaseModel):
    doctor_id: Optional[str] = None
    appointment_id: Optional[str] = None
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=2000)


class FeedbackModerationRequest(BaseModel):
    status: str = Field(pattern=r"^(pending|public|hidden)$")


class PatientAccountAdminUpdate(BaseModel):
    active: Optional[bool] = None
    patient_id: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=1024)


class ImportCommitRequest(BaseModel):
    batch_id: Optional[str] = Field(default=None, max_length=80)
