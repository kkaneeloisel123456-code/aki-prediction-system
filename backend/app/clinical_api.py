# -*- coding: utf-8 -*-
"""Clinical workflow API: patients, encounters, drafts, review and reports."""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from . import database as db
from . import predictor
from .assets import load_assets
from .config import FEATURE_RANGES, RISK_HIGH, RISK_LOW, PATIENT_QUERY_TTL_MINUTES
from .database import json_dump, json_load, new_id, record_audit, row_to_dict, utc_now
from .pdf import generate_clinical_report
from .schemas import (
    ClinicalPredictRequest,
    ClinicalReviewRequest,
    DraftSaveRequest,
    EncounterCreateRequest,
    EncounterUpdateRequest,
    PatientCreateRequest,
    PatientGrantRequest,
    PatientUpdateRequest,
    ReportPublishRequest,
)

router = APIRouter(prefix="/api", tags=["clinical"])


def _err(message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


def _user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if not user:
        raise _err("请先登录", 401)
    return user


def _admin(user: dict[str, Any]) -> None:
    if user["role"] != "admin":
        raise _err("仅管理员可执行此操作", 403)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise _err(f"{field}格式无效") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mask(last4: str | None, prefix: str = "****") -> str:
    return f"{prefix}{last4}" if last4 else ""


def _patient_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "mrn": row["mrn"],
        "name": row["name"],
        "sex": row["sex"],
        "birth_year": row["birth_year"],
        "certificate": _mask(row["certificate_last4"]),
        "phone": _mask(row["phone_last4"]),
        "owner_id": row["owner_id"],
        "owner_name": row["owner_name"] if "owner_name" in row.keys() else None,
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "encounter_count": row["encounter_count"] if "encounter_count" in row.keys() else 0,
        "latest_prediction": row["latest_prediction"] if "latest_prediction" in row.keys() else None,
    }


def _patient_query(conn: Any, user: dict[str, Any], *, include_inactive: bool = False) -> str:
    base = """
        SELECT p.*, u.display_name AS owner_name,
               (SELECT COUNT(*) FROM encounters e WHERE e.patient_id=p.id) AS encounter_count,
               (SELECT pr.probability FROM predictions pr
                JOIN encounters e2 ON e2.id=pr.encounter_id
                WHERE e2.patient_id=p.id AND pr.status='valid'
                ORDER BY pr.predicted_at DESC LIMIT 1) AS latest_prediction
        FROM patients p LEFT JOIN users u ON u.id=p.owner_id
    """
    clauses: list[str] = []
    params: list[Any] = []
    if not include_inactive:
        clauses.append("p.active=1")
    if user["role"] != "admin":
        clauses.append(
            "(p.owner_id=? OR EXISTS(SELECT 1 FROM patient_grants g "
            "WHERE g.patient_id=p.id AND g.doctor_id=?))"
        )
        params.extend([user["id"], user["id"]])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return base + where, params


def _require_patient(conn: Any, user: dict[str, Any], patient_id: str, write: bool = False) -> Any:
    row = conn.execute(
        """SELECT p.*,u.display_name AS owner_name FROM patients p
           LEFT JOIN users u ON u.id=p.owner_id WHERE p.id=?""",
        (patient_id,),
    ).fetchone()
    if row is None:
        raise _err("患者不存在", 404)
    if user["role"] != "admin":
        if row["owner_id"] == user["id"]:
            allowed = True
        else:
            grant = conn.execute(
                """SELECT permission FROM patient_grants
                   WHERE patient_id=? AND doctor_id=?""",
                (patient_id, user["id"]),
            ).fetchone()
            allowed = bool(grant and (grant["permission"] == "edit" or not write))
        if not allowed:
            raise _err("无权访问该患者档案", 403)
    return row


def _access_map(conn: Any, user: dict[str, Any], patient_id: str) -> dict[str, Any]:
    if user["role"] == "admin":
        return {"view": True, "edit": True, "owner": False}
    patient = conn.execute("SELECT owner_id FROM patients WHERE id=?", (patient_id,)).fetchone()
    owner = bool(patient and patient["owner_id"] == user["id"])
    if owner:
        return {"view": True, "edit": True, "owner": True}
    grant = conn.execute(
        "SELECT permission FROM patient_grants WHERE patient_id=? AND doctor_id=?",
        (patient_id, user["id"]),
    ).fetchone()
    return {
        "view": bool(grant),
        "edit": bool(grant and grant["permission"] == "edit"),
        "owner": False,
    }


def _encounter_dict(row: Any, *, include_values: bool = True) -> dict[str, Any]:
    values = json_load(row["values_json"], {})
    result = {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "patient_name": row["patient_name"] if "patient_name" in row.keys() else None,
        "mrn": row["mrn"] if "mrn" in row.keys() else None,
        "case_ref": row["case_ref"],
        "occurred_at": row["occurred_at"],
        "surgery_type": row["surgery_type"],
        "diagnosis": row["diagnosis"],
        "orders": row["orders"],
        "status": row["status"],
        "current_prediction_id": row["current_prediction_id"],
        "row_version": row["row_version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "created_by": row["created_by"],
        "updated_by": row["updated_by"],
        "latest_prediction": None,
        "latest_review": None,
        "latest_report": None,
    }
    if include_values:
        result["values"] = values
    if "prediction_json" in row.keys() and row["prediction_json"]:
        result["latest_prediction"] = {
            "id": row["current_prediction_id"],
            **json_load(row["prediction_json"], {}),
        }
    if "review_json" in row.keys() and row["review_json"]:
        result["latest_review"] = json_load(row["review_json"], {})
    if "report_id" in row.keys() and row["report_id"]:
        result["latest_report"] = {
            "id": row["report_id"],
            "report_no": row["report_no"],
            "version": row["report_version"],
            "published_at": row["report_published_at"],
            "status": row["report_status"],
        }
    return result


_ENCOUNTER_SELECT = """
    SELECT e.*, p.name AS patient_name, p.mrn,
           pr.result_json AS prediction_json,
           (SELECT rv.decision || '|' || rv.reason || '|' || rv.created_at || '|' || rv.reviewer_id
            FROM clinical_reviews rv WHERE rv.encounter_id=e.id
            ORDER BY rv.created_at DESC LIMIT 1) AS review_json,
           rp.id AS report_id, rp.report_no AS report_no, rp.version AS report_version,
           rp.published_at AS report_published_at, rp.status AS report_status
    FROM encounters e
    JOIN patients p ON p.id=e.patient_id
    LEFT JOIN predictions pr ON pr.id=e.current_prediction_id
    LEFT JOIN reports rp ON rp.id=(
        SELECT r.id FROM reports r WHERE r.encounter_id=e.id AND r.status='published'
        ORDER BY r.version DESC LIMIT 1
    )
"""


def _get_encounter(conn: Any, user: dict[str, Any], encounter_id: str, write: bool = False) -> Any:
    row = conn.execute(_ENCOUNTER_SELECT + " WHERE e.id=?", (encounter_id,)).fetchone()
    if row is None:
        raise _err("就诊记录不存在", 404)
    _require_patient(conn, user, row["patient_id"], write)
    return row


def _normalise_values(
    values: Any, *, allow_incomplete: bool = False
) -> tuple[dict[str, Any], dict[str, float], list[str]]:
    """Validate feature keys/types. Returns (stored_values, numeric_values, invalid)."""
    if not isinstance(values, dict):
        raise _err("指标格式无效")
    features = load_assets()["features"]
    unknown = sorted(set(values) - set(features))
    if unknown:
        raise _err(f"包含未知指标：{', '.join(unknown[:5])}")
    stored: dict[str, Any] = {}
    numeric: dict[str, float] = {}
    invalid: list[str] = []
    for key, raw in values.items():
        if raw is None:
            continue
        if isinstance(raw, bool):
            raise _err(f"指标 {key} 格式无效")
        if isinstance(raw, str):
            text = raw.strip()
            if not text or text == "-":
                continue
            try:
                value = float(text)
            except ValueError:
                if allow_incomplete:
                    stored[key] = text[:40]
                    invalid.append(key)
                    continue
                raise _err(f"指标 {key} 不是有效数字") from None
        elif isinstance(raw, (int, float)):
            value = float(raw)
        else:
            raise _err(f"指标 {key} 格式无效")
        if not math.isfinite(value) or abs(value) > 1e9:
            raise _err(f"指标 {key} 超出可处理范围")
        bounds = FEATURE_RANGES.get(key)
        if bounds and not (bounds[0] <= value <= bounds[1]):
            invalid.append(key)
            if allow_incomplete:
                stored[key] = value
                continue
            raise _err(
                f"指标 {key} 超出临床合理范围 {bounds[0]:g}–{bounds[1]:g}，当前 {value:g}"
            )
        stored[key] = value
        numeric[key] = value
    return stored, numeric, invalid


def _fingerprint_input(values: dict[str, float], model_hash: str) -> str:
    return hashlib.sha256(
        json_dump({"values": values, "model_hash": model_hash}).encode("utf-8")
    ).hexdigest()


def _latest_review(conn: Any, encounter_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT rv.*,u.display_name AS reviewer_name FROM clinical_reviews rv
           JOIN users u ON u.id=rv.reviewer_id
           WHERE rv.encounter_id=? ORDER BY rv.created_at DESC LIMIT 1""",
        (encounter_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "decision": row["decision"],
        "reason": row["reason"],
        "reviewer_id": row["reviewer_id"],
        "reviewer_name": row["reviewer_name"],
        "prediction_id": row["prediction_id"],
        "prediction_fingerprint": row["prediction_fingerprint"],
        "created_at": row["created_at"],
    }


def _latest_report(conn: Any, encounter_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT * FROM reports WHERE encounter_id=? AND status='published'
           ORDER BY version DESC LIMIT 1""",
        (encounter_id,),
    ).fetchone()
    return dict(row) if row else None


def _checklist(
    conn: Any, user: dict[str, Any], encounter: Any, values: dict[str, Any],
    prediction: dict[str, Any] | None, review: dict[str, Any] | None,
    missing_ack: bool = False,
) -> dict[str, Any]:
    patient = _require_patient(conn, user, encounter["patient_id"])
    numeric_values, numeric, invalid = _normalise_values(values, allow_incomplete=True)
    missing = [k for k in load_assets()["features"] if k not in numeric]
    result_payload = (prediction or {}).get("result", {})
    model_prediction_valid = bool(
        prediction and prediction.get("id")
        and result_payload and not result_payload.get("manual")
        and result_payload.get("probability") is not None
    )
    manual_review = bool(
        review and review["decision"] == "manual"
        and review.get("prediction_id") == (prediction or {}).get("id")
        and review.get("prediction_fingerprint") == (prediction or {}).get("input_fingerprint")
        and review["reason"].strip()
    )
    fingerprint_match = manual_review
    if model_prediction_valid:
        current_fp = _fingerprint_input(numeric, prediction.get("model", {}).get("hash", ""))
        fingerprint_match = current_fp == prediction.get("input_fingerprint")
    review_valid = False
    if review:
        if model_prediction_valid:
            review_valid = (
                review["decision"] in {"agree", "adjust"}
                and review.get("prediction_id") == prediction.get("id")
                and review.get("prediction_fingerprint") == prediction.get("input_fingerprint")
                and (review["decision"] == "agree" or bool(review["reason"].strip()))
            )
        else:
            review_valid = manual_review
    items = [
        {"key": "identity", "label": "患者身份完整",
         "ok": bool(patient["name"] and patient["mrn"]), "detail": "姓名与病历号必须完整"},
        {"key": "values", "label": "至少一项合法实测指标",
         "ok": bool(numeric) and not invalid, "detail": f"已录入 {len(numeric)} 项"},
        {"key": "prediction", "label": "模型预测或明确人工审核",
         "ok": model_prediction_valid or manual_review,
         "detail": "全空或超出合理范围不能预测" if not numeric else "需取得模型概率或完成人工审核"},
        {"key": "prediction_current", "label": "预测与当前指标一致",
         "ok": fingerprint_match, "detail": "指标已修改，请重新预测或重新人工审核"},
        {"key": "diagnosis", "label": "已填写临床诊断", "ok": bool(encounter["diagnosis"].strip())},
        {"key": "orders", "label": "已填写医嘱或随访建议", "ok": bool(encounter["orders"].strip())},
        {"key": "review", "label": "医生复核有效", "ok": review_valid,
         "detail": "调整、暂缓或人工审核必须填写理由"},
        {"key": "missing", "label": "缺失指标已确认",
         "ok": not missing or missing_ack, "detail": f"缺失 {len(missing)} 项"},
    ]
    return {
        "can_publish": all(i["ok"] for i in items),
        "items": items,
        "missing_features": missing,
        "missing_count": len(missing),
        "review": review,
        "prediction_current": fingerprint_match,
        "manual_review": manual_review,
    }


# ---------------------------------------------------------------------------
# Patients and access grants
# ---------------------------------------------------------------------------
@router.get("/patients")
def list_patients(request: Request, query: str = "", limit: int = 100, offset: int = 0):
    user = _user(request)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    db.ensure_initialized()
    with db.reader() as conn:
        sql, params = _patient_query(conn, user)
        if query.strip():
            sql += " AND (p.name LIKE ? OR p.mrn LIKE ?)"
            token = f"%{query.strip()}%"
            params.extend([token, token])
        sql += " ORDER BY p.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        total_sql, total_params = _patient_query(conn, user)
        if query.strip():
            total_sql += " AND (p.name LIKE ? OR p.mrn LIKE ?)"
            total_params.extend([f"%{query.strip()}%", f"%{query.strip()}%"])
        total = conn.execute(total_sql, total_params).fetchall()
        return {"patients": [_patient_dict(r) for r in rows], "total": len(total)}


@router.post("/patients", status_code=201)
def create_patient(req: PatientCreateRequest, request: Request):
    user = _user(request)
    db.ensure_initialized()
    owner_id = req.owner_id if user["role"] == "admin" and req.owner_id else user["id"]
    if user["role"] != "admin" and req.owner_id and req.owner_id != user["id"]:
        raise _err("医生不能指定其他账号为档案负责人", 403)
    now = utc_now()
    with db.transaction(immediate=True) as conn:
        owner = conn.execute(
            "SELECT 1 FROM users WHERE id=? AND active=1 AND role='doctor'", (owner_id,)
        ).fetchone()
        if not owner:
            raise _err("负责人账号不存在或不是有效医生")
        patient_id = new_id("P")
        try:
            conn.execute(
                """INSERT INTO patients
                   (id,mrn,name,sex,birth_year,certificate_last4,phone_last4,
                    owner_id,active,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                (
                    patient_id, req.mrn.strip(), req.name.strip(), req.sex, req.birth_year,
                    (req.certificate_last4 or "").strip() or None,
                    (req.phone_last4 or "").strip() or None,
                    owner_id, now, now,
                ),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise _err("病历号已存在", 409) from None
            raise
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="patient_create",
            entity_type="patient", entity_id=patient_id,
            detail={"mrn": req.mrn.strip(), "owner_id": owner_id}, ip=_ip(request),
        )
        row = conn.execute(
            """SELECT p.*,u.display_name AS owner_name FROM patients p
               LEFT JOIN users u ON u.id=p.owner_id WHERE p.id=?""",
            (patient_id,),
        ).fetchone()
        return _patient_dict(row)


@router.get("/patients/{patient_id}")
def get_patient(patient_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        row = _require_patient(conn, user, patient_id)
        grants = conn.execute(
            """SELECT g.*,u.display_name,u.username FROM patient_grants g
               JOIN users u ON u.id=g.doctor_id WHERE g.patient_id=?""",
            (patient_id,),
        ).fetchall()
        result = _patient_dict(row)
        result["access"] = _access_map(conn, user, patient_id)
        result["grants"] = [dict(g) for g in grants]
        latest_code = conn.execute(
            """SELECT created_at,expires_at,revoked_at FROM patient_query_codes
               WHERE patient_id=? ORDER BY created_at DESC LIMIT 1""",
            (patient_id,),
        ).fetchone()
        result["query_code"] = dict(latest_code) if latest_code else None
        return result


@router.patch("/patients/{patient_id}")
def update_patient(patient_id: str, req: PatientUpdateRequest, request: Request):
    user = _user(request)
    with db.transaction(immediate=True) as conn:
        row = _require_patient(conn, user, patient_id)
        if user["role"] != "admin" and row["owner_id"] != user["id"]:
            raise _err("仅档案负责人或管理员可修改基本信息", 403)
        owner_id = row["owner_id"]
        if req.owner_id is not None:
            _admin(user)
            doctor = conn.execute(
                "SELECT 1 FROM users WHERE id=? AND active=1 AND role='doctor'",
                (req.owner_id,),
            ).fetchone()
            if not doctor:
                raise _err("新负责人不是有效医生")
            owner_id = req.owner_id
        conn.execute(
            """UPDATE patients SET name=?,sex=?,birth_year=?,certificate_last4=?,
                   phone_last4=?,active=?,owner_id=?,updated_at=? WHERE id=?""",
            (
                req.name.strip() if req.name is not None else row["name"],
                req.sex if req.sex is not None else row["sex"],
                req.birth_year if req.birth_year is not None else row["birth_year"],
                req.certificate_last4 if req.certificate_last4 is not None
                else row["certificate_last4"],
                req.phone_last4 if req.phone_last4 is not None else row["phone_last4"],
                row["active"] if req.active is None else int(req.active),
                owner_id,
                utc_now(),
                patient_id,
            ),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="patient_update",
            entity_type="patient", entity_id=patient_id, ip=_ip(request),
        )
        fresh = conn.execute(
            """SELECT p.*,u.display_name AS owner_name FROM patients p
               LEFT JOIN users u ON u.id=p.owner_id WHERE p.id=?""",
            (patient_id,),
        ).fetchone()
        return _patient_dict(fresh)


@router.post("/patients/{patient_id}/grants")
def grant_patient_access(patient_id: str, req: PatientGrantRequest, request: Request):
    user = _user(request)
    _admin(user)
    with db.transaction(immediate=True) as conn:
        _require_patient(conn, user, patient_id)
        doctor = conn.execute(
            "SELECT 1 FROM users WHERE id=? AND active=1 AND role='doctor'",
            (req.doctor_id,),
        ).fetchone()
        if not doctor:
            raise _err("授权对象不是有效医生")
        conn.execute(
            """INSERT INTO patient_grants(patient_id,doctor_id,permission,granted_by,created_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(patient_id,doctor_id) DO UPDATE SET
                 permission=excluded.permission,granted_by=excluded.granted_by,
                 created_at=excluded.created_at""",
            (patient_id, req.doctor_id, req.permission, user["id"], utc_now()),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="patient_grant",
            entity_type="patient", entity_id=patient_id,
            detail={"doctor_id": req.doctor_id, "permission": req.permission},
            ip=_ip(request),
        )
        return {"ok": True}


@router.delete("/patients/{patient_id}/grants/{doctor_id}")
def revoke_patient_access(patient_id: str, doctor_id: str, request: Request):
    user = _user(request)
    _admin(user)
    with db.transaction(immediate=True) as conn:
        _require_patient(conn, user, patient_id)
        conn.execute(
            "DELETE FROM patient_grants WHERE patient_id=? AND doctor_id=?",
            (patient_id, doctor_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="patient_grant_revoke",
            entity_type="patient", entity_id=patient_id,
            detail={"doctor_id": doctor_id}, ip=_ip(request),
        )
    return {"ok": True}


@router.post("/patients/{patient_id}/query-code")
def issue_query_code(patient_id: str, request: Request):
    user = _user(request)
    with db.transaction(immediate=True) as conn:
        patient = _require_patient(conn, user, patient_id)
        if user["role"] != "admin" and patient["owner_id"] != user["id"]:
            raise _err("仅档案负责人或管理员可生成查询码", 403)
        code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(8))
        now = int(time.time())
        expires = now + PATIENT_QUERY_TTL_MINUTES * 60
        conn.execute(
            "UPDATE patient_query_codes SET revoked_at=? WHERE patient_id=? AND revoked_at IS NULL",
            (utc_now(), patient_id),
        )
        conn.execute(
            """INSERT INTO patient_query_codes
               (id,patient_id,code_hash,created_by,created_at,expires_at,revoked_at)
               VALUES(?,?,?,?,?,?,NULL)""",
            (new_id("QC"), patient_id, hashlib.sha256(code.encode()).hexdigest(),
             user["id"], utc_now(), expires),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="query_code_issue",
            entity_type="patient", entity_id=patient_id, ip=_ip(request),
        )
        return {"query_code": code, "expires_at": expires,
                "notice": "查询码仅显示一次，请交给患者本人；重新生成会使旧码立即失效。"}


# ---------------------------------------------------------------------------
# Encounters and drafts
# ---------------------------------------------------------------------------
@router.get("/patients/{patient_id}/encounters")
def list_encounters(patient_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        _require_patient(conn, user, patient_id)
        rows = conn.execute(
            _ENCOUNTER_SELECT + " WHERE e.patient_id=? ORDER BY e.occurred_at DESC",
            (patient_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = _encounter_dict(row)
            # Convert the pipe-packed review from SQL into a readable object.
            review_raw = row["review_json"]
            if review_raw:
                decision, reason, created_at, reviewer_id = str(review_raw).split("|", 3)
                item["latest_review"] = {
                    "decision": decision, "reason": reason,
                    "created_at": created_at, "reviewer_id": reviewer_id,
                }
                item["latest_review"].update(_latest_review(conn, row["id"]) or {})
            result.append(item)
        return {"encounters": result}


@router.post("/patients/{patient_id}/encounters", status_code=201)
def create_encounter(patient_id: str, req: EncounterCreateRequest, request: Request):
    user = _user(request)
    occurred = _parse_datetime(req.occurred_at, "就诊时间")
    if occurred > datetime.now(timezone.utc):
        raise _err("就诊时间不能晚于当前时间")
    stored, _, _ = _normalise_values(req.values, allow_incomplete=True)
    now = utc_now()
    with db.transaction(immediate=True) as conn:
        _require_patient(conn, user, patient_id, write=True)
        encounter_id = new_id("E")
        try:
            conn.execute(
                """INSERT INTO encounters
                   (id,patient_id,case_ref,occurred_at,surgery_type,values_json,
                    diagnosis,orders,status,current_prediction_id,row_version,
                    created_by,updated_by,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,'draft',NULL,1,?,?,?,?)""",
                (
                    encounter_id, patient_id, req.case_ref.strip(), occurred.isoformat(),
                    (req.surgery_type or "").strip() or None,
                    json_dump(stored), req.diagnosis.strip(), req.orders.strip(),
                    user["id"], user["id"], now, now,
                ),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise _err("该患者已存在相同就诊编号", 409) from None
            raise
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="encounter_create",
            entity_type="encounter", entity_id=encounter_id,
            detail={"patient_id": patient_id}, ip=_ip(request),
        )
        return _encounter_dict(_get_encounter(conn, user, encounter_id))


@router.get("/encounters/{encounter_id}")
def get_encounter(encounter_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        row = _get_encounter(conn, user, encounter_id)
        result = _encounter_dict(row)
        result["latest_review"] = _latest_review(conn, encounter_id)
        draft = conn.execute(
            "SELECT * FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        ).fetchone()
        if draft:
            result["draft"] = {
                "draft_version": draft["draft_version"],
                "base_row_version": draft["base_row_version"],
                "updated_at": draft["updated_at"],
                "payload": json_load(draft["payload_json"], {}),
                "stale": draft["base_row_version"] != row["row_version"],
            }
        else:
            result["draft"] = None
        result["can_edit"] = _access_map(conn, user, row["patient_id"])["edit"]
        return result


@router.patch("/encounters/{encounter_id}")
def update_encounter(encounter_id: str, req: EncounterUpdateRequest, request: Request):
    user = _user(request)
    stored, _, invalid = _normalise_values(req.values, allow_incomplete=False)
    with db.transaction(immediate=True) as conn:
        row = _get_encounter(conn, user, encounter_id, write=True)
        if req.row_version != row["row_version"]:
            raise _err("就诊记录已在其他页面更新，请重新载入", 409)
        conn.execute(
            """UPDATE encounters SET values_json=?,diagnosis=?,orders=?,status='draft',
                   current_prediction_id=NULL,row_version=row_version+1,updated_by=?,
                   updated_at=? WHERE id=?""",
            (json_dump(stored), req.diagnosis.strip(), req.orders.strip(),
             user["id"], utc_now(), encounter_id),
        )
        conn.execute(
            "UPDATE predictions SET status='superseded' WHERE encounter_id=? AND status='valid'",
            (encounter_id,),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="encounter_update",
            entity_type="encounter", entity_id=encounter_id,
            detail={"invalid_features": invalid}, ip=_ip(request),
        )
        return _encounter_dict(_get_encounter(conn, user, encounter_id))


@router.put("/encounters/{encounter_id}/draft")
def save_draft(encounter_id: str, req: DraftSaveRequest, request: Request):
    user = _user(request)
    stored, _, invalid = _normalise_values(req.values, allow_incomplete=True)
    with db.transaction(immediate=True) as conn:
        row = _get_encounter(conn, user, encounter_id, write=True)
        if req.row_version != row["row_version"]:
            raise _err("就诊记录已更新，草稿未覆盖，请重新载入", 409)
        existing = conn.execute(
            "SELECT * FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        ).fetchone()
        expected = existing["draft_version"] if existing else 0
        if req.draft_version != expected:
            raise _err("草稿已在其他页面更新，请重新载入", 409)
        payload = json_dump({
            "row_version": row["row_version"],
            "values": stored,
            "diagnosis": req.diagnosis.strip(),
            "orders": req.orders.strip(),
            "invalid_features": invalid,
        })
        conn.execute(
            """INSERT INTO encounter_drafts
               (user_id,encounter_id,base_row_version,draft_version,payload_json,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(user_id,encounter_id) DO UPDATE SET
                 base_row_version=excluded.base_row_version,draft_version=excluded.draft_version,
                 payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
            (user["id"], encounter_id, row["row_version"], expected + 1, payload, utc_now()),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="draft_save",
            entity_type="encounter", entity_id=encounter_id,
            detail={"draft_version": expected + 1}, ip=_ip(request),
        )
        return {"draft_version": expected + 1, "base_row_version": row["row_version"],
                "updated_at": utc_now(), "invalid_features": invalid}


@router.delete("/encounters/{encounter_id}/draft")
def delete_draft(encounter_id: str, request: Request, draft_version: int = -1):
    user = _user(request)
    with db.transaction(immediate=True) as conn:
        _get_encounter(conn, user, encounter_id, write=True)
        row = conn.execute(
            "SELECT * FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        ).fetchone()
        if row and draft_version != row["draft_version"]:
            raise _err("草稿已被其他页面更新，请重新载入", 409)
        conn.execute(
            "DELETE FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="draft_delete",
            entity_type="encounter", entity_id=encounter_id, ip=_ip(request),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Prediction, review, checklist and publishing
# ---------------------------------------------------------------------------
@router.post("/encounters/{encounter_id}/predict")
def clinical_predict(encounter_id: str, req: ClinicalPredictRequest, request: Request):
    user = _user(request)
    stored, numeric, invalid = _normalise_values(req.features, allow_incomplete=False)
    if not numeric:
        raise _err("全部指标为空，不能执行预测；请至少录入一项合法实测指标")
    if invalid:
        raise _err("存在超出临床合理范围的指标，请核对后再预测")
    assets = load_assets()
    with db.transaction(immediate=True) as conn:
        row = _get_encounter(conn, user, encounter_id, write=True)
        if req.row_version != row["row_version"]:
            raise _err("就诊记录已更新，请重新载入后再预测", 409)
        result = predictor.predict(numeric, patient_id=row["patient_id"], explain=True)
        pid = new_id("PD")
        fingerprint = _fingerprint_input(numeric, assets["model_hash"])
        conn.execute(
            """INSERT INTO predictions
               (id,encounter_id,patient_id,actor_id,input_json,result_json,probability,
                risk_level,model_version,model_hash,input_fingerprint,status,predicted_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,'valid',?)""",
            (
                pid, encounter_id, row["patient_id"], user["id"], json_dump(stored),
                json_dump(result), result["probability"], result["risk_level"],
                assets["model_version"], assets["model_hash"], fingerprint, utc_now(),
            ),
        )
        conn.execute(
            "UPDATE predictions SET status='superseded' WHERE encounter_id=? AND id<>? AND status='valid'",
            (encounter_id, pid),
        )
        conn.execute(
            """UPDATE encounters SET current_prediction_id=?,status='predicted',
                   row_version=row_version+1,updated_by=?,updated_at=? WHERE id=?""",
            (pid, user["id"], utc_now(), encounter_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="prediction_run",
            entity_type="encounter", entity_id=encounter_id,
            detail={"prediction_id": pid, "model_version": assets["model_version"],
                    "missing": len(result["missing_filled"]), "measured": len(numeric)},
            ip=_ip(request),
        )
        updated = _get_encounter(conn, user, encounter_id)
        response = _encounter_dict(updated)
        response["prediction"] = {
            "id": pid, **result, "model_version": assets["model_version"],
            "model_hash": assets["model_hash"], "input_fingerprint": fingerprint,
        }
        response["row_version"] = updated["row_version"]
        return response


@router.post("/encounters/{encounter_id}/review")
def review_encounter(encounter_id: str, req: ClinicalReviewRequest, request: Request):
    user = _user(request)
    if req.decision not in {"agree", "adjust", "defer", "manual"}:
        raise _err("复核结论无效")
    reason = req.reason.strip()
    if req.decision in {"adjust", "defer", "manual"} and not reason:
        raise _err("调整判断、暂缓采纳或人工审核时必须填写理由")
    with db.transaction(immediate=True) as conn:
        row = _get_encounter(conn, user, encounter_id, write=True)
        if req.row_version != row["row_version"]:
            raise _err("就诊记录已更新，请重新核对预测结果", 409)
        prediction = conn.execute(
            "SELECT * FROM predictions WHERE id=? AND encounter_id=? AND status='valid'",
            (row["current_prediction_id"], encounter_id),
        ).fetchone()
        if req.decision == "manual":
            if prediction:
                raise _err("已有有效模型结果，请选择认可、调整或暂缓")
        elif prediction is None:
            raise _err("请先完成有效预测，或明确选择人工审核并填写理由")
        if prediction is None:
            pid = new_id("PD-MANUAL")
            fingerprint = hashlib.sha256(
                json_dump({"manual": True, "row_version": row["row_version"]}).encode()
            ).hexdigest()
            conn.execute(
                """INSERT INTO predictions
                   (id,encounter_id,patient_id,actor_id,input_json,result_json,probability,
                    risk_level,model_version,model_hash,input_fingerprint,status,predicted_at)
                   VALUES(?,?,?,?,?,?,NULL,'人工审核',?,?,?, 'valid',?)""",
                (pid, encounter_id, row["patient_id"], user["id"],
                 json_dump(json_load(row["values_json"], {})),
                 json_dump({"manual": True}), "N/A", "N/A", fingerprint, utc_now()),
            )
            conn.execute(
                "UPDATE encounters SET current_prediction_id=? WHERE id=?", (pid, encounter_id)
            )
            prediction = conn.execute("SELECT * FROM predictions WHERE id=?", (pid,)).fetchone()
        rid = new_id("RV")
        conn.execute(
            """INSERT INTO clinical_reviews
               (id,encounter_id,prediction_id,reviewer_id,decision,reason,
                prediction_fingerprint,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (rid, encounter_id, prediction["id"], user["id"], req.decision, reason,
             prediction["input_fingerprint"], utc_now()),
        )
        new_status = "predicted" if req.decision == "defer" else "reviewed"
        conn.execute(
            """UPDATE encounters SET status=?,row_version=row_version+1,
                   updated_by=?,updated_at=? WHERE id=?""",
            (new_status, user["id"], utc_now(), encounter_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="clinical_review",
            entity_type="encounter", entity_id=encounter_id,
            detail={"decision": req.decision, "review_id": rid}, ip=_ip(request),
        )
        updated = _get_encounter(conn, user, encounter_id)
        response = _encounter_dict(updated)
        response["latest_review"] = _latest_review(conn, encounter_id)
        return response


@router.get("/encounters/{encounter_id}/checklist")
def report_checklist(encounter_id: str, request: Request, missing_ack: bool = False):
    user = _user(request)
    with db.reader() as conn:
        row = _get_encounter(conn, user, encounter_id)
        draft = conn.execute(
            "SELECT * FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        ).fetchone()
        values = json_load(row["values_json"], {})
        diagnosis, orders = row["diagnosis"], row["orders"]
        if draft:
            payload = json_load(draft["payload_json"], {})
            values = payload.get("values", values)
            diagnosis = payload.get("diagnosis", diagnosis)
            orders = payload.get("orders", orders)
        prediction = conn.execute(
            "SELECT * FROM predictions WHERE id=? AND status='valid'",
            (row["current_prediction_id"],),
        ).fetchone() if row["current_prediction_id"] else None
        pred_obj = None
        if prediction:
            pred_obj = {
                "id": prediction["id"],
                "model": {"hash": prediction["model_hash"],
                          "version": prediction["model_version"]},
                "input_fingerprint": prediction["input_fingerprint"],
                "result": json_load(prediction["result_json"], {}),
            }
        # Checklist needs diagnosis/orders from the effective payload, not the
        # stale encounter row if a newer draft exists.
        effective = dict(row)
        effective["diagnosis"] = diagnosis
        effective["orders"] = orders
        checklist = _checklist(conn, user, effective, values, pred_obj,
                               _latest_review(conn, encounter_id), missing_ack)
        checklist["draft_version"] = draft["draft_version"] if draft else 0
        return checklist


@router.post("/encounters/{encounter_id}/publish")
def publish_report(encounter_id: str, req: ReportPublishRequest, request: Request):
    user = _user(request)
    now = utc_now()
    with db.transaction(immediate=True) as conn:
        row = _get_encounter(conn, user, encounter_id)
        if req.row_version != row["row_version"]:
            raise _err("就诊记录已更新，请重新核对发布内容", 409)
        draft = conn.execute(
            "SELECT * FROM encounter_drafts WHERE user_id=? AND encounter_id=?",
            (user["id"], encounter_id),
        ).fetchone()
        if draft:
            if req.draft_version and draft["draft_version"] != req.draft_version:
                raise _err("草稿已更新，请重新核对", 409)
            payload = json_load(draft["payload_json"], {})
            values = payload.get("values", {})
            diagnosis = payload.get("diagnosis", row["diagnosis"])
            orders = payload.get("orders", row["orders"])
        else:
            if req.draft_version:
                raise _err("草稿不存在，请重新核对", 409)
            values = json_load(row["values_json"], {})
            diagnosis, orders = row["diagnosis"], row["orders"]
        prediction = conn.execute(
            "SELECT * FROM predictions WHERE id=? AND status='valid'",
            (row["current_prediction_id"],),
        ).fetchone() if row["current_prediction_id"] else None
        if not prediction:
            raise _err("发布正式报告前必须取得当前预测，或完成明确的人工审核")
        pred_obj = {
            "id": prediction["id"],
            "model": {"hash": prediction["model_hash"],
                      "version": prediction["model_version"]},
            "input_fingerprint": prediction["input_fingerprint"],
            "result": json_load(prediction["result_json"], {}),
        }
        review = _latest_review(conn, encounter_id)
        effective = dict(row)
        effective["diagnosis"] = diagnosis
        effective["orders"] = orders
        checklist = _checklist(conn, user, effective, values, pred_obj,
                               review, req.missing_ack)
        failed = [item["label"] for item in checklist["items"] if not item["ok"]]
        if failed:
            raise _err("发布核对未完成：" + "；".join(failed), 422)
        patient = _require_patient(conn, user, row["patient_id"])
        version = conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM reports WHERE encounter_id=?",
            (encounter_id,),
        ).fetchone()[0]
        report_id = new_id("R")
        report_no = f"RPT-{datetime.now().strftime('%Y%m%d')}-{report_id.split('-')[-1][:6]}"
        snapshot = {
            "report_no": report_no,
            "version": version,
            "generated_at": now,
            "patient": {
                "id": patient["id"], "mrn": patient["mrn"], "name": patient["name"],
                "sex": patient["sex"], "birth_year": patient["birth_year"],
                "certificate": _mask(patient["certificate_last4"]),
            },
            "encounter": {
                "id": encounter_id, "case_ref": row["case_ref"],
                "occurred_at": row["occurred_at"], "surgery_type": row["surgery_type"],
                "values": values, "diagnosis": diagnosis, "orders": orders,
            },
            "prediction": {
                "id": prediction["id"], "result": json_load(prediction["result_json"], {}),
                "model_version": prediction["model_version"],
                "model_hash": prediction["model_hash"],
                "input_fingerprint": prediction["input_fingerprint"],
                "predicted_at": prediction["predicted_at"],
            },
            "review": review,
            "published_by": {"id": user["id"], "name": user["display_name"]},
            "missing_features": checklist["missing_features"],
        }
        snapshot_json = json_dump(snapshot)
        digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT INTO reports
               (id,report_no,encounter_id,version,patient_id,snapshot_json,sha256,
                created_by,reviewer_id,status,published_at,revoked_at,revoke_reason)
               VALUES(?,?,?,?,?,?,?,?,?, 'published',?,NULL,NULL)""",
            (report_id, report_no, encounter_id, version, patient["id"],
             snapshot_json, digest, user["id"], review["reviewer_id"], now),
        )
        conn.execute(
            """UPDATE encounters SET diagnosis=?,orders=?,status='published',
                   row_version=row_version+1,updated_by=?,updated_at=? WHERE id=?""",
            (diagnosis, orders, user["id"], now, encounter_id),
        )
        conn.execute(
            "DELETE FROM encounter_drafts WHERE encounter_id=? AND user_id=?",
            (encounter_id, user["id"]),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="report_publish",
            entity_type="report", entity_id=report_id,
            detail={"encounter_id": encounter_id, "version": version,
                    "sha256": digest, "model_version": prediction["model_version"]},
            ip=_ip(request),
        )
        return {
            "id": report_id, "report_no": report_no, "version": version,
            "status": "published", "sha256": digest,
            "encounter_id": encounter_id, "published_at": now,
        }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def _require_report(conn: Any, user: dict[str, Any], report_id: str) -> Any:
    row = conn.execute(
        """SELECT r.*,p.name AS patient_name,p.mrn,p.owner_id
           FROM reports r JOIN patients p ON p.id=r.patient_id WHERE r.id=?""",
        (report_id,),
    ).fetchone()
    if row is None:
        raise _err("报告不存在", 404)
    _require_patient(conn, user, row["patient_id"])
    return row


def _report_view(row: Any, *, include_snapshot: bool = True) -> dict[str, Any]:
    snapshot = json_load(row["snapshot_json"], {})
    result = {
        "id": row["id"],
        "report_no": row["report_no"],
        "version": row["version"],
        "patient_id": row["patient_id"],
        "patient_name": row["patient_name"],
        "mrn": row["mrn"],
        "encounter_id": row["encounter_id"],
        "status": row["status"],
        "sha256": row["sha256"],
        "published_at": row["published_at"],
        "revoked_at": row["revoked_at"],
        "revoke_reason": row["revoke_reason"],
        "risk_level": (snapshot.get("prediction", {}).get("result", {}) or {}).get("risk_level")
        or ("人工审核" if snapshot.get("prediction", {}).get("result", {}).get("manual") else None),
        "probability": (snapshot.get("prediction", {}).get("result", {}) or {}).get("probability"),
    }
    if include_snapshot:
        result["snapshot"] = snapshot
    return result


@router.get("/reports")
def list_reports(
    request: Request,
    patient_id: str = "",
    status: str = "published",
    query: str = "",
    limit: int = 200,
):
    user = _user(request)
    limit = max(1, min(int(limit), 500))
    with db.reader() as conn:
        clauses = ["p.active=1"]
        params: list[Any] = []
        if status in {"published", "revoked", "all"}:
            if status != "all":
                clauses.append("r.status=?")
                params.append(status)
        else:
            raise _err("报告状态筛选无效")
        if patient_id:
            clauses.append("r.patient_id=?")
            params.append(patient_id)
        if query.strip():
            clauses.append("(r.report_no LIKE ? OR p.name LIKE ? OR p.mrn LIKE ?)")
            token = f"%{query.strip()}%"
            params.extend([token, token, token])
        if user["role"] != "admin":
            clauses.append(
                "(p.owner_id=? OR EXISTS(SELECT 1 FROM patient_grants g "
                "WHERE g.patient_id=p.id AND g.doctor_id=?))"
            )
            params.extend([user["id"], user["id"]])
        rows = conn.execute(
            """SELECT r.*,p.name AS patient_name,p.mrn,p.owner_id FROM reports r
               JOIN patients p ON p.id=r.patient_id
               WHERE """ + " AND ".join(clauses) +
            " ORDER BY r.published_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return {"reports": [_report_view(r, include_snapshot=False) for r in rows]}


@router.get("/reports/{report_id}")
def get_report(report_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        row = _require_report(conn, user, report_id)
        result = _report_view(row)
        result["can_revoke"] = user["role"] == "admin" and result["status"] == "published"
        return result


@router.get("/reports/{report_id}/pdf")
def download_report_pdf(report_id: str, request: Request):
    user = _user(request)
    with db.reader() as conn:
        row = _require_report(conn, user, report_id)
        digest = hashlib.sha256(row["snapshot_json"].encode("utf-8")).hexdigest()
        if not secrets.compare_digest(digest, row["sha256"]):
            raise _err("报告完整性校验失败，已阻止下载", 409)
        snapshot = json_load(row["snapshot_json"], {})
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="report_pdf_download",
            entity_type="report", entity_id=report_id, ip=_ip(request),
        )
    pdf_bytes = generate_clinical_report(snapshot)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{row["report_no"]}.pdf"',
            "X-Report-SHA256": row["sha256"],
        },
    )


@router.post("/reports/{report_id}/revoke")
def revoke_report(report_id: str, request: Request, reason: str = ""):
    user = _user(request)
    _admin(user)
    if not reason.strip():
        raise _err("撤销正式报告必须填写原因")
    with db.transaction(immediate=True) as conn:
        row = _require_report(conn, user, report_id)
        if row["status"] != "published":
            raise _err("该报告已撤销", 409)
        conn.execute(
            """UPDATE reports SET status='revoked',revoked_at=?,revoke_reason=?
               WHERE id=?""",
            (utc_now(), reason.strip()[:1000], report_id),
        )
        encounter = conn.execute(
            "SELECT * FROM encounters WHERE id=?", (row["encounter_id"],)
        ).fetchone()
        if encounter and encounter["status"] == "published":
            remaining = conn.execute(
                """SELECT 1 FROM reports WHERE encounter_id=? AND status='published'
                   LIMIT 1""",
                (row["encounter_id"],),
            ).fetchone()
            if not remaining:
                conn.execute(
                    """UPDATE encounters SET status='reviewed',row_version=row_version+1,
                       updated_by=?,updated_at=? WHERE id=?""",
                    (user["id"], utc_now(), row["encounter_id"]),
                )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="report_revoke",
            entity_type="report", entity_id=report_id,
            detail={"reason": reason.strip()}, ip=_ip(request),
        )
        return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard and workstation summaries (real database, no synthetic cohort)
# ---------------------------------------------------------------------------
def _access_sql(user: dict[str, Any]) -> tuple[str, list[Any]]:
    if user["role"] == "admin":
        return "1=1", []
    return (
        "(p.owner_id=? OR EXISTS(SELECT 1 FROM patient_grants g "
        "WHERE g.patient_id=p.id AND g.doctor_id=?))",
        [user["id"], user["id"]],
    )


@router.get("/dashboard/summary")
def dashboard_summary(request: Request):
    user = _user(request)
    access, params = _access_sql(user)
    with db.reader() as conn:
        patient_count = conn.execute(
            f"SELECT COUNT(*) FROM patients p WHERE p.active=1 AND {access}", params
        ).fetchone()[0]
        encounters = conn.execute(
            f"""SELECT e.*,p.name AS patient_name FROM encounters e
                JOIN patients p ON p.id=e.patient_id
                WHERE p.active=1 AND {access} ORDER BY e.occurred_at DESC""",
            params,
        ).fetchall()
        predictions = conn.execute(
            f"""SELECT pr.* FROM predictions pr JOIN patients p ON p.id=pr.patient_id
                WHERE pr.status='valid' AND p.active=1 AND {access}""",
            params,
        ).fetchall()
        reports = conn.execute(
            f"""SELECT r.* FROM reports r JOIN patients p ON p.id=r.patient_id
                WHERE p.active=1 AND {access}""",
            params,
        ).fetchall()
        appointments = conn.execute(
            f"""SELECT a.* FROM appointments a JOIN patients p ON p.id=a.patient_id
                WHERE p.active=1 AND {access}""",
            params,
        ).fetchall()
    risk = {"高": 0, "中": 0, "低": 0}
    for pred in predictions:
        level = pred["risk_level"]
        if level in risk:
            risk[level] += 1
    monthly: dict[str, dict[str, int]] = {}
    now = datetime.now(timezone.utc)
    years_months = []
    year, month = now.year, now.month
    for _ in range(6):
        years_months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    for key in reversed(years_months):
        monthly[key] = {"encounters": 0, "reports": 0}
    for enc in encounters:
        key = str(enc["occurred_at"])[:7]
        if key in monthly:
            monthly[key]["encounters"] += 1
    for report in reports:
        if report["status"] != "published":
            continue
        key = str(report["published_at"])[:7]
        if key in monthly:
            monthly[key]["reports"] += 1
    dept: dict[str, int] = {}
    for enc in encounters:
        name = enc["surgery_type"] or "未分类"
        dept[name] = dept.get(name, 0) + 1
    pending = sum(1 for e in encounters if e["status"] != "published")
    today = now.date().isoformat()
    today_appointments = sum(
        1 for a in appointments
        if str(a["scheduled_at"])[:10] == today
        and a["status"] in {"booked", "checked_in"}
    )
    published_reports = sum(1 for r in reports if r["status"] == "published")
    return {
        "patients_total": patient_count,
        "encounters_total": len(encounters),
        "pending_total": pending,
        "reports_total": published_reports,
        "today_appointments": today_appointments,
        "risk_distribution": risk,
        "monthly": [
            {"month": k, **v} for k, v in monthly.items()
        ],
        "departments": [
            {"name": k, "cases": v} for k, v in sorted(
                dept.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "recent_encounters": [
            {
                "id": e["id"], "patient_id": e["patient_id"],
                "patient_name": e["patient_name"], "case_ref": e["case_ref"],
                "occurred_at": e["occurred_at"], "status": e["status"],
                "row_version": e["row_version"],
            }
            for e in encounters[:8]
        ],
    }


@router.get("/workstation/summary")
def workstation_summary(request: Request):
    """Compact patient/encounter view for the reception workbench."""
    user = _user(request)
    access, params = _access_sql(user)
    with db.reader() as conn:
        patients = conn.execute(
            f"""SELECT p.*,u.display_name AS owner_name,
                       (SELECT COUNT(*) FROM encounters e WHERE e.patient_id=p.id) AS encounter_count,
                       (SELECT pr.probability FROM predictions pr
                        JOIN encounters e2 ON e2.id=pr.encounter_id
                        WHERE e2.patient_id=p.id AND pr.status='valid'
                        ORDER BY pr.predicted_at DESC LIMIT 1) AS latest_prediction,
                       (SELECT pr.risk_level FROM predictions pr
                        JOIN encounters e2 ON e2.id=pr.encounter_id
                        WHERE e2.patient_id=p.id AND pr.status='valid'
                        ORDER BY pr.predicted_at DESC LIMIT 1) AS latest_risk
                FROM patients p LEFT JOIN users u ON u.id=p.owner_id
                WHERE p.active=1 AND {access}
                ORDER BY p.updated_at DESC LIMIT 100""",
            params,
        ).fetchall()
        pending = conn.execute(
            f"""SELECT COUNT(*) FROM encounters e JOIN patients p ON p.id=e.patient_id
                WHERE p.active=1 AND e.status<>'published' AND {access}""",
            params,
        ).fetchone()[0]
    risk = {"高": 0, "中": 0, "低": 0}
    for p in patients:
        level = p["latest_risk"] if "latest_risk" in p.keys() else None
        if level in risk:
            risk[level] += 1
    return {
        "patients": [
            {**_patient_dict(p), "latest_risk": p["latest_risk"] if "latest_risk" in p.keys() else None}
            for p in patients
        ],
        "summary": {
            "total": len(patients), "pending": pending,
            "high": risk["高"], "mid": risk["中"], "low": risk["低"],
        },
    }
