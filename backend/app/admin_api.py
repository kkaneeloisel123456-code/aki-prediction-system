# -*- coding: utf-8 -*-
"""Administrative, scheduling and feedback APIs for authenticated staff."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from . import database as db
from .auth import hash_password
from .auth_service import (
    create_user,
    change_password,
    list_users,
    update_user,
)
from .backup import backup_database
from .clinical_api import _access_map, _err, _ip, _parse_datetime, _require_patient, _user
from .config import DATABASE_BACKUP_DIR
from .database import json_dump, new_id, record_audit, utc_now
from .schemas import (
    AppointmentStatusRequest,
    FeedbackModerationRequest,
    PatientAccountAdminUpdate,
    PasswordChangeRequest,
    SlotCreateRequest,
    SlotUpdateRequest,
    StaffAppointmentCreateRequest,
    UserCreateRequest,
    UserUpdateRequest,
)

router = APIRouter(prefix="/api", tags=["administration"])


def _admin(user: dict[str, Any]) -> None:
    if user["role"] != "admin":
        raise _err("仅管理员可执行此操作", 403)


@router.post("/auth/password")
def change_own_password(req: PasswordChangeRequest, request: Request):
    user = _user(request)
    token = request.cookies.get("aki_session")
    try:
        change_password(
            user["id"], req.current_password, req.new_password,
            keep_session_token=token, ip=_ip(request),
        )
    except ValueError as exc:
        raise _err(str(exc)) from exc
    return {"ok": True}


@router.get("/doctors")
def list_doctors(request: Request):
    _user(request)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT id,username,display_name FROM users
               WHERE role='doctor' AND active=1 ORDER BY display_name"""
        ).fetchall()
        return {"doctors": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# Staff account management
# ---------------------------------------------------------------------------
@router.get("/admin/users")
def admin_users(request: Request):
    user = _user(request)
    _admin(user)
    return {"users": list_users()}


@router.post("/admin/users", status_code=201)
def admin_create_user(req: UserCreateRequest, request: Request):
    user = _user(request)
    _admin(user)
    try:
        created = create_user(
            actor_id=user["id"], username=req.username,
            display_name=req.display_name, role=req.role,
            password=req.password, must_change_password=req.must_change_password,
            ip=_ip(request),
        )
    except ValueError as exc:
        raise _err(str(exc), 409) from exc
    return {k: created[k] for k in
            ("id", "username", "display_name", "role", "active",
             "must_change_password", "created_at")}


@router.patch("/admin/users/{user_id}")
def admin_update_user(user_id: str, req: UserUpdateRequest, request: Request):
    user = _user(request)
    _admin(user)
    try:
        updated = update_user(
            actor_id=user["id"], user_id=user_id, display_name=req.display_name,
            role=req.role, active=req.active, password=req.password,
            must_change_password=req.must_change_password, ip=_ip(request),
        )
    except ValueError as exc:
        raise _err(str(exc), 409) from exc
    return {k: updated[k] for k in
            ("id", "username", "display_name", "role", "active",
             "must_change_password", "created_at", "updated_at", "last_login_at")}


# ---------------------------------------------------------------------------
# Patient portal accounts (admin view)
# ---------------------------------------------------------------------------
@router.get("/admin/patient-accounts")
def admin_patient_accounts(request: Request):
    user = _user(request)
    _admin(user)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT pa.id,pa.username,pa.display_name,pa.phone_last4,pa.patient_id,
                      pa.active,pa.created_at,pa.updated_at,p.name AS patient_name,p.mrn
               FROM patient_accounts pa LEFT JOIN patients p ON p.id=pa.patient_id
               ORDER BY pa.created_at DESC"""
        ).fetchall()
        return {"accounts": [dict(r) for r in rows]}


@router.patch("/admin/patient-accounts/{account_id}")
def admin_update_patient_account(
    account_id: str, req: PatientAccountAdminUpdate, request: Request
):
    user = _user(request)
    _admin(user)
    with db.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT * FROM patient_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise _err("患者账号不存在", 404)
        patient_id = row["patient_id"] if req.patient_id is None else req.patient_id
        if req.patient_id:
            patient = conn.execute(
                "SELECT 1 FROM patients WHERE id=? AND active=1", (req.patient_id,)
            ).fetchone()
            if not patient:
                raise _err("患者档案不存在")
            already = conn.execute(
                "SELECT 1 FROM patient_accounts WHERE patient_id=? AND id<>?",
                (req.patient_id, account_id),
            ).fetchone()
            if already:
                raise _err("该患者档案已绑定其他账号", 409)
        password_hash = row["password_hash"]
        if req.password:
            password_hash = hash_password(req.password)
            conn.execute(
                "UPDATE portal_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                (utc_now(), account_id),
            )
        active = row["active"] if req.active is None else int(req.active)
        if not active:
            conn.execute(
                "UPDATE portal_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                (utc_now(), account_id),
            )
        conn.execute(
            """UPDATE patient_accounts SET patient_id=?,active=?,password_hash=?,
                   updated_at=? WHERE id=?""",
            (patient_id, active, password_hash, utc_now(), account_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="patient_account_update",
            entity_type="patient_account", entity_id=account_id,
            detail={"active": active, "bound": bool(patient_id),
                    "password_reset": bool(req.password)}, ip=_ip(request),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Slots and staff-side appointments
# ---------------------------------------------------------------------------
@router.get("/slots")
def staff_slots(request: Request, doctor_id: str = ""):
    user = _user(request)
    clauses = ["1=1"]
    params: list[Any] = []
    if user["role"] != "admin":
        clauses.append("s.doctor_id=?")
        params.append(user["id"])
    elif doctor_id:
        clauses.append("s.doctor_id=?")
        params.append(doctor_id)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT s.*,u.display_name AS doctor_name FROM slots s
               JOIN users u ON u.id=s.doctor_id WHERE """ + " AND ".join(clauses) +
            " ORDER BY s.starts_at DESC LIMIT 500",
            params,
        ).fetchall()
        return {"slots": [dict(r) for r in rows]}


@router.post("/slots", status_code=201)
def create_slot(req: SlotCreateRequest, request: Request):
    user = _user(request)
    doctor_id = req.doctor_id if user["role"] == "admin" and req.doctor_id else user["id"]
    if user["role"] != "admin" and doctor_id != user["id"]:
        raise _err("医生只能为自己创建号源", 403)
    starts = _parse_datetime(req.starts_at, "出诊时间")
    if starts <= datetime.now(timezone.utc):
        raise _err("不能创建过去的号源")
    with db.transaction(immediate=True) as conn:
        doctor = conn.execute(
            "SELECT 1 FROM users WHERE id=? AND role='doctor' AND active=1", (doctor_id,)
        ).fetchone()
        if not doctor:
            raise _err("医生账号不存在")
        slot_id = new_id("SL")
        try:
            conn.execute(
                """INSERT INTO slots
                   (id,doctor_id,starts_at,appointment_type,capacity,booked,active,created_at)
                   VALUES(?,?,?,?,?,0,1,?)""",
                (slot_id, doctor_id, starts.isoformat(), req.appointment_type,
                 req.capacity, utc_now()),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise _err("同一医生、同一时间已存在同类号源", 409) from None
            raise
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="slot_create",
            entity_type="slot", entity_id=slot_id, detail={"capacity": req.capacity},
            ip=_ip(request),
        )
    return {"id": slot_id}


@router.patch("/slots/{slot_id}")
def update_slot(slot_id: str, req: SlotUpdateRequest, request: Request):
    user = _user(request)
    with db.transaction(immediate=True) as conn:
        row = conn.execute("SELECT * FROM slots WHERE id=?", (slot_id,)).fetchone()
        if row is None:
            raise _err("号源不存在", 404)
        if user["role"] != "admin" and row["doctor_id"] != user["id"]:
            raise _err("无权修改该号源", 403)
        capacity = row["capacity"] if req.capacity is None else req.capacity
        if capacity < row["booked"]:
            raise _err(f"容量不能低于已预约数量 {row['booked']}")
        active = row["active"] if req.active is None else int(req.active)
        conn.execute(
            "UPDATE slots SET capacity=?,active=? WHERE id=?",
            (capacity, active, slot_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="slot_update",
            entity_type="slot", entity_id=slot_id,
            detail={"capacity": capacity, "active": active}, ip=_ip(request),
        )
    return {"ok": True}


@router.get("/appointments")
def staff_appointments(
    request: Request, status: str = "", doctor_id: str = "", date: str = ""
):
    user = _user(request)
    clauses = ["1=1"]
    params: list[Any] = []
    if user["role"] != "admin":
        clauses.append("a.doctor_id=?")
        params.append(user["id"])
    elif doctor_id:
        clauses.append("a.doctor_id=?")
        params.append(doctor_id)
    if status:
        clauses.append("a.status=?")
        params.append(status)
    if date:
        clauses.append("substr(a.scheduled_at,1,10)=?")
        params.append(date)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT a.*,p.name AS patient_name,p.mrn,u.display_name AS doctor_name
               FROM appointments a JOIN patients p ON p.id=a.patient_id
               JOIN users u ON u.id=a.doctor_id WHERE """ + " AND ".join(clauses) +
            " ORDER BY a.scheduled_at ASC LIMIT 500",
            params,
        ).fetchall()
        return {"appointments": [dict(r) for r in rows]}


@router.post("/appointments", status_code=201)
def staff_create_appointment(req: StaffAppointmentCreateRequest, request: Request):
    user = _user(request)
    with db.transaction(immediate=True) as conn:
        _require_patient(conn, user, req.patient_id, write=True)
        slot = conn.execute(
            "SELECT * FROM slots WHERE id=? AND active=1", (req.slot_id,)
        ).fetchone()
        if slot is None:
            raise _err("号源不存在", 404)
        if user["role"] != "admin" and slot["doctor_id"] != user["id"]:
            raise _err("只能使用自己的号源", 403)
        if int(slot["booked"]) >= int(slot["capacity"]):
            raise _err("号源已满", 409)
        if slot["starts_at"] < db.utc_now():
            raise _err("不能使用过去的号源", 409)
        appointment_id = new_id("AP")
        conn.execute(
            """INSERT INTO appointments
               (id,patient_id,account_id,doctor_id,slot_id,scheduled_at,
                appointment_type,status,reason,created_at,updated_at)
               VALUES(?,?,NULL,?,?,?,?, 'booked',?,?,?)""",
            (appointment_id, req.patient_id, slot["doctor_id"], slot["id"],
             slot["starts_at"], slot["appointment_type"], req.reason.strip(),
             utc_now(), utc_now()),
        )
        conn.execute("UPDATE slots SET booked=booked+1 WHERE id=?", (slot["id"],))
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="appointment_staff_create",
            entity_type="appointment", entity_id=appointment_id,
            detail={"patient_id": req.patient_id}, ip=_ip(request),
        )
    return {"id": appointment_id}


@router.post("/appointments/{appointment_id}/status")
def staff_update_appointment(
    appointment_id: str, req: AppointmentStatusRequest, request: Request
):
    user = _user(request)
    allowed = {
        "booked": {"checked_in", "cancelled", "no_show"},
        "checked_in": {"completed", "cancelled", "no_show"},
    }
    with db.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id=?", (appointment_id,)
        ).fetchone()
        if row is None:
            raise _err("预约不存在", 404)
        if user["role"] != "admin" and row["doctor_id"] != user["id"]:
            raise _err("无权操作该预约", 403)
        if req.status not in allowed.get(row["status"], set()):
            raise _err(f"预约状态不能从 {row['status']} 变更为 {req.status}", 409)
        conn.execute(
            "UPDATE appointments SET status=?,updated_at=? WHERE id=?",
            (req.status, utc_now(), appointment_id),
        )
        if req.status == "cancelled" and row["status"] == "booked":
            conn.execute("UPDATE slots SET booked=MAX(0,booked-1) WHERE id=?", (row["slot_id"],))
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="appointment_status",
            entity_type="appointment", entity_id=appointment_id,
            detail={"from": row["status"], "to": req.status}, ip=_ip(request),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Feedback moderation
# ---------------------------------------------------------------------------
@router.get("/feedback")
def staff_feedback(request: Request, status: str = ""):
    user = _user(request)
    clauses = ["1=1"]
    params: list[Any] = []
    if user["role"] != "admin":
        clauses.append("f.doctor_id=?")
        params.append(user["id"])
    if status:
        clauses.append("f.status=?")
        params.append(status)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT f.*,p.name AS patient_name,u.display_name AS doctor_name
               FROM feedback f JOIN patients p ON p.id=f.patient_id
               LEFT JOIN users u ON u.id=f.doctor_id
               WHERE """ + " AND ".join(clauses) +
            " ORDER BY f.created_at DESC LIMIT 300",
            params,
        ).fetchall()
        return {"feedback": [dict(r) for r in rows]}


@router.post("/feedback/{feedback_id}/moderate")
def moderate_feedback(
    feedback_id: str, req: FeedbackModerationRequest, request: Request
):
    user = _user(request)
    _admin(user)
    with db.transaction(immediate=True) as conn:
        row = conn.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
        if row is None:
            raise _err("评价不存在", 404)
        conn.execute(
            "UPDATE feedback SET status=?,updated_at=? WHERE id=?",
            (req.status, utc_now(), feedback_id),
        )
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="feedback_moderate",
            entity_type="feedback", entity_id=feedback_id,
            detail={"from": row["status"], "to": req.status}, ip=_ip(request),
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Audit and production operations
# ---------------------------------------------------------------------------
@router.get("/admin/audit")
def audit_events(
    request: Request, action: str = "", entity_type: str = "",
    entity_id: str = "", limit: int = 100,
):
    user = _user(request)
    _admin(user)
    limit = max(1, min(int(limit), 500))
    clauses = ["1=1"]
    params: list[Any] = []
    for column, value in (
        ("action", action), ("entity_type", entity_type), ("entity_id", entity_id)
    ):
        if value:
            clauses.append(f"{column}=?")
            params.append(value)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT a.*,u.display_name AS actor_name FROM audit_events a
               LEFT JOIN users u ON u.id=a.actor_id
               WHERE """ + " AND ".join(clauses) +
            " ORDER BY a.created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["detail"] = json.loads(item.pop("detail_json") or "{}")
            except json.JSONDecodeError:
                item["detail"] = {}
            result.append(item)
        return {"events": result}


@router.get("/admin/system")
def system_overview(request: Request):
    user = _user(request)
    _admin(user)
    with db.reader() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "users", "patients", "encounters", "predictions",
                "reports", "appointments", "feedback", "audit_events",
            )
        }
        db_path = db.database_path()
        db_size = db_path.stat().st_size if db_path.exists() else 0
        backups = sorted(DATABASE_BACKUP_DIR.glob("clinical-*.db"), reverse=True) \
            if DATABASE_BACKUP_DIR.exists() else []
        backup_list = [
            {"name": p.name, "bytes": p.stat().st_size,
             "created_at": p.stat().st_mtime}
            for p in backups[:10]
        ]
    return {
        "counts": counts,
        "database": {"filename": db_path.name, "bytes": db_size
                     },
        "backup_count": len(backups),
        "backups": backup_list,
        "model_version": _model_version(),
    }


def _model_version() -> str:
    try:
        from .assets import load_assets
        return str(load_assets()["model_version"])
    except Exception:
        return "UNAVAILABLE"


@router.post("/admin/backup", status_code=201)
def create_backup(request: Request):
    user = _user(request)
    _admin(user)
    target = backup_database(DATABASE_BACKUP_DIR)
    with db.transaction() as conn:
        record_audit(
            conn, actor_type="user", actor_id=user["id"], action="database_backup",
            entity_type="system", entity_id=None,
            detail={"filename": target.name, "bytes": target.stat().st_size},
            ip=_ip(request),
        )
    return {"filename": target.name, "bytes": target.stat().st_size}
