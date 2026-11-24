# -*- coding: utf-8 -*-
"""Patient-facing portal: accounts, query codes, reports, appointments and feedback."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response

from . import database as db
from .auth import hash_password, verify_password, _DUMMY_HASH
from .auth_service import (
    LOGIN_LOCK_SECONDS,
    LOGIN_WINDOW_SECONDS,
    MAX_LOGIN_FAILURES,
    clear_login_failures,
    login_rate_limited,
    record_login_failure,
)
from .config import (
    AUTH_COOKIE_SECURE,
    PATIENT_PORTAL_TTL_MINUTES,
    PATIENT_QUERY_TTL_MINUTES,
)
from .database import json_load, new_id, record_audit, row_to_dict, utc_now
from .pdf import generate_clinical_report
from .schemas import (
    AppointmentCreateRequest,
    FeedbackCreateRequest,
    PortalBindRequest,
    PortalLoginRequest,
    PortalQueryRequest,
    PortalRegisterRequest,
)

router = APIRouter(prefix="/api/portal", tags=["patient-portal"])
PORTAL_COOKIE = "aki_portal"


def _err(message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _origin_ok(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host:
        if urlparse(origin).netloc.lower() != host.lower():
            raise _err("请求来源校验失败", 403)
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise _err("请求来源校验失败", 403)


def _set_cookie(response: Response, token: str, ttl_seconds: int) -> None:
    response.set_cookie(
        PORTAL_COOKIE,
        token,
        max_age=ttl_seconds,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        PORTAL_COOKIE,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def _create_portal_session(
    *, account_id: str | None, patient_id: str | None, ttl_seconds: int,
    ip: str | None,
) -> str:
    token = secrets.token_urlsafe(32)
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO portal_sessions
               (id,account_id,patient_id,token_hash,created_at,expires_at,revoked_at,ip)
               VALUES(?,?,?,?,?,?,NULL,?)""",
            (
                new_id("PS"), account_id, patient_id, _digest(token),
                utc_now(), int(time.time()) + ttl_seconds, ip,
            ),
        )
    return token


def _portal_session(
    request: Request, *, require_patient: bool = False, require_account: bool = False
) -> dict[str, Any]:
    token = request.cookies.get(PORTAL_COOKIE)
    if not token:
        raise _err("请先完成患者身份核验或登录", 401)
    with db.transaction() as conn:
        row = conn.execute(
            """SELECT ps.*,pa.username,pa.display_name,pa.active AS account_active,
                      p.name AS patient_name,p.mrn
               FROM portal_sessions ps
               LEFT JOIN patient_accounts pa ON pa.id=ps.account_id
               LEFT JOIN patients p ON p.id=ps.patient_id
               WHERE ps.token_hash=?""",
            (_digest(token),),
        ).fetchone()
        if (
            row is None or int(row["expires_at"]) <= int(time.time())
            or row["revoked_at"] is not None
            or (row["account_id"] and not row["account_active"])
        ):
            raise _err("患者会话已失效，请重新核验", 401)
        if require_patient and not row["patient_id"]:
            raise _err("请先绑定本人患者档案", 403)
        if require_account and not row["account_id"]:
            raise _err("该操作需要患者账号登录", 403)
        return dict(row)


def _revoke_portal_token(token: str) -> None:
    if not token:
        return
    with db.transaction() as conn:
        conn.execute(
            "UPDATE portal_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
            (utc_now(), _digest(token)),
        )


def _throttle_limited(conn: Any, key: str) -> bool:
    now = int(time.time())
    row = conn.execute(
        "SELECT * FROM login_throttle WHERE throttle_key=?", (key,)
    ).fetchone()
    if row is None:
        return False
    if int(row["locked_until"]) > now:
        return True
    if now - int(row["window_start"]) > LOGIN_WINDOW_SECONDS:
        return False
    return int(row["failures"]) >= MAX_LOGIN_FAILURES


def _record_failure(conn: Any, key: str) -> None:
    """Record a failure on the caller's connection to avoid a second write lock."""
    now = int(time.time())
    row = conn.execute(
        "SELECT * FROM login_throttle WHERE throttle_key=?", (key,)
    ).fetchone()
    if row is None or now - int(row["window_start"]) > LOGIN_WINDOW_SECONDS:
        failures, window_start = 1, now
    else:
        failures, window_start = int(row["failures"]) + 1, int(row["window_start"])
    locked_until = now + LOGIN_LOCK_SECONDS if failures >= MAX_LOGIN_FAILURES else 0
    conn.execute(
        """INSERT INTO login_throttle(throttle_key,failures,window_start,locked_until)
           VALUES(?,?,?,?)
           ON CONFLICT(throttle_key) DO UPDATE SET
             failures=excluded.failures,window_start=excluded.window_start,
             locked_until=excluded.locked_until""",
        (key, failures, window_start, locked_until),
    )


def _clear_failures(conn: Any, key: str) -> None:
    conn.execute("DELETE FROM login_throttle WHERE throttle_key=?", (key,))


def _second_factor_ok(patient: Any, certificate_last4: str | None, phone_last4: str | None) -> bool | None:
    """Check a registered certificate/phone suffix.

    Returns True on match, False on mismatch, None when the record has no
    registered second factor at all (the caller turns that into a clear
    "register it first" message rather than a silent pass).
    """
    registered_cert = (patient["certificate_last4"] or "").strip()
    registered_phone = (patient["phone_last4"] or "").strip()
    if not registered_cert and not registered_phone:
        return None
    provided_cert = (certificate_last4 or "").strip()
    provided_phone = (phone_last4 or "").strip()
    if registered_cert and provided_cert and hmac.compare_digest(registered_cert, provided_cert):
        return True
    if registered_phone and provided_phone and hmac.compare_digest(registered_phone, provided_phone):
        return True
    return False


def _verify_query_code(
    conn: Any, mrn: str, name: str, code: str, limit_key: str,
    certificate_last4: str | None = None, phone_last4: str | None = None,
) -> Any:
    now = int(time.time())
    if _throttle_limited(conn, limit_key):
        raise _err("核验尝试次数过多，请稍后再试", 429)
    patient = conn.execute(
        "SELECT * FROM patients WHERE mrn=? COLLATE NOCASE AND name=? AND active=1",
        (mrn.strip(), name.strip()),
    ).fetchone()
    if patient is None:
        _record_failure(conn, limit_key)
        raise _err("姓名、病历号或查询码错误")
    codes = conn.execute(
        """SELECT * FROM patient_query_codes
           WHERE patient_id=? AND revoked_at IS NULL AND expires_at>?
           ORDER BY created_at DESC""",
        (patient["id"], now),
    ).fetchall()
    matched = any(hmac.compare_digest(row["code_hash"], _digest(code.strip().upper())) for row in codes)
    if not matched:
        _record_failure(conn, limit_key)
        raise _err("姓名、病历号或查询码错误")
    factor = _second_factor_ok(patient, certificate_last4, phone_last4)
    if factor is None:
        raise _err("该档案未登记证件或手机号末四位，请先联系医院补登记后再核验")
    if not factor:
        _record_failure(conn, limit_key)
        raise _err("证件或手机号末四位与档案不一致")
    _clear_failures(conn, limit_key)
    return patient


@router.post("/register", status_code=201)
def register(req: PortalRegisterRequest, request: Request):
    _origin_ok(request)
    db.ensure_initialized()
    account_id = new_id("PA")
    now = utc_now()
    with db.transaction(immediate=True) as conn:
        if conn.execute(
            "SELECT 1 FROM patient_accounts WHERE username=? COLLATE NOCASE",
            (req.username,),
        ).fetchone():
            raise _err("账号已存在", 409)
        conn.execute(
            """INSERT INTO patient_accounts
               (id,username,display_name,password_hash,phone_last4,patient_id,active,
                created_at,updated_at)
               VALUES(?,?,?,?,?,NULL,1,?,?)""",
            (account_id, req.username, req.display_name, hash_password(req.password),
             (req.phone_last4 or "").strip() or None, now, now),
        )
        record_audit(
            conn, actor_type="patient_account", actor_id=account_id,
            action="portal_register", entity_type="patient_account",
            entity_id=account_id, ip=_ip(request),
        )
    return {"id": account_id, "username": req.username, "display_name": req.display_name,
            "bound": False}


@router.post("/login")
def login(req: PortalLoginRequest, request: Request, response: Response):
    _origin_ok(request)
    key = f"portal|{_ip(request)}|{req.username.lower()}"
    if login_rate_limited(key):
        raise _err("登录尝试次数过多，请稍后再试", 429)
    with db.reader() as conn:
        account = conn.execute(
            "SELECT * FROM patient_accounts WHERE username=? COLLATE NOCASE AND active=1",
            (req.username,),
        ).fetchone()
        valid = bool(account and verify_password(req.password, account["password_hash"]))
        if account is None:
            verify_password(req.password, _DUMMY_HASH)
    if not valid:
        # Must run outside a read cursor's implicit transaction; SQLite would
        # otherwise hold a lock while a second connection records the failure.
        record_login_failure(key)
        raise _err("账号或密码错误", 401)
    clear_login_failures(key)
    ttl = PATIENT_PORTAL_TTL_MINUTES * 60
    token = _create_portal_session(
        account_id=account["id"], patient_id=account["patient_id"], ttl_seconds=ttl,
        ip=_ip(request),
    )
    _set_cookie(response, token, ttl)
    with db.reader() as conn:
        patient = conn.execute(
            "SELECT id,name,mrn,sex,birth_year FROM patients WHERE id=?",
            (account["patient_id"],),
        ).fetchone() if account["patient_id"] else None
        record_audit(
            conn, actor_type="patient_account", actor_id=account["id"],
            action="portal_login", entity_type="patient_account",
            entity_id=account["id"], ip=_ip(request),
        )
        return {
            "authenticated": True,
            "account": {"id": account["id"], "username": account["username"],
                        "display_name": account["display_name"],
                        "patient_id": account["patient_id"]},
            "patient": dict(patient) if patient else None,
        }


@router.get("/status")
def status(request: Request):
    try:
        session = _portal_session(request)
    except HTTPException:
        return {"authenticated": False, "account": None, "patient": None}
    with db.reader() as conn:
        patient = conn.execute(
            "SELECT id,name,mrn,sex,birth_year FROM patients WHERE id=?",
            (session["patient_id"],),
        ).fetchone() if session["patient_id"] else None
    account = None
    if session["account_id"]:
        account = {
            "id": session["account_id"], "username": session["username"],
            "display_name": session["display_name"],
            "patient_id": session["patient_id"],
        }
    return {
        "authenticated": True,
        "mode": "account" if session["account_id"] else "query_code",
        "account": account,
        "patient": dict(patient) if patient else None,
    }


@router.post("/logout")
def logout(request: Request, response: Response):
    _origin_ok(request)
    _revoke_portal_token(request.cookies.get(PORTAL_COOKIE))
    _clear_cookie(response)
    return {"ok": True}


@router.post("/bind")
def bind_patient(req: PortalBindRequest, request: Request):
    _origin_ok(request)
    session = _portal_session(request, require_account=True)
    if session["patient_id"]:
        raise _err("账号已绑定患者档案，如需更换请联系管理员", 409)
    key = f"bind|{_ip(request)}|{session['account_id']}"
    with db.transaction(immediate=True) as conn:
        patient = _verify_query_code(
            conn, req.mrn, req.name, req.query_code, key,
            req.certificate_last4, req.phone_last4,
        )
        conn.execute("UPDATE patient_accounts SET patient_id=?,updated_at=? WHERE id=?",
                     (patient["id"], utc_now(), session["account_id"]))
        conn.execute("UPDATE portal_sessions SET patient_id=? WHERE id=?",
                     (patient["id"], session["id"]))
        record_audit(
            conn, actor_type="patient_account", actor_id=session["account_id"],
            action="portal_bind_patient", entity_type="patient",
            entity_id=patient["id"], ip=_ip(request),
        )
        return {"ok": True, "patient": {
            "id": patient["id"], "name": patient["name"], "mrn": patient["mrn"],
            "sex": patient["sex"], "birth_year": patient["birth_year"],
        }}


@router.post("/query")
def query_reports(req: PortalQueryRequest, request: Request, response: Response):
    """Anonymous quick report lookup using name, MRN and an 8-character code."""
    _origin_ok(request)
    key = f"query|{_ip(request)}"
    with db.reader() as conn:
        patient = _verify_query_code(
            conn, req.mrn, req.name, req.query_code, key,
            req.certificate_last4, req.phone_last4,
        )
    ttl = PATIENT_QUERY_TTL_MINUTES * 60
    token = _create_portal_session(
        account_id=None, patient_id=patient["id"], ttl_seconds=ttl, ip=_ip(request)
    )
    _set_cookie(response, token, ttl)
    with db.reader() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE patient_id=? AND status='published'",
            (patient["id"],),
        ).fetchone()[0]
        record_audit(
            conn, actor_type="query_code", actor_id=None, action="portal_query",
            entity_type="patient", entity_id=patient["id"], ip=_ip(request),
        )
    return {
        "ok": True, "expires_in": ttl,
        "patient": {"name": patient["name"], "mrn": patient["mrn"]},
        "report_count": count,
    }


@router.get("/doctors")
def doctors(request: Request):
    _portal_session(request)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT u.id,u.display_name,
                      (SELECT AVG(f.rating) FROM feedback f
                       WHERE f.doctor_id=u.id AND f.status='public') AS rating,
                      (SELECT COUNT(*) FROM feedback f
                       WHERE f.doctor_id=u.id AND f.status='public') AS reviews
               FROM users u WHERE u.role='doctor' AND u.active=1
               ORDER BY u.display_name"""
        ).fetchall()
        return {"doctors": [
            {"id": r["id"], "name": r["display_name"],
             "rating": round(float(r["rating"]), 2) if r["rating"] is not None else None,
             "reviews": r["reviews"]}
            for r in rows
        ]}


@router.get("/slots")
def slots(request: Request, doctor_id: str = ""):
    _portal_session(request)
    now = utc_now()
    with db.reader() as conn:
        clauses = ["s.active=1", "s.booked<s.capacity", "s.starts_at>=?"]
        params: list[Any] = [now]
        if doctor_id:
            clauses.append("s.doctor_id=?")
            params.append(doctor_id)
        rows = conn.execute(
            """SELECT s.*,u.display_name AS doctor_name FROM slots s
               JOIN users u ON u.id=s.doctor_id
               WHERE """ + " AND ".join(clauses) +
            " ORDER BY s.starts_at LIMIT 200",
            params,
        ).fetchall()
        return {"slots": [dict(r) for r in rows]}


@router.post("/appointments", status_code=201)
def book_appointment(req: AppointmentCreateRequest, request: Request):
    _origin_ok(request)
    session = _portal_session(request, require_patient=True, require_account=True)
    with db.transaction(immediate=True) as conn:
        slot = conn.execute(
            "SELECT * FROM slots WHERE id=? AND active=1", (req.slot_id,)
        ).fetchone()
        if slot is None:
            raise _err("号源不存在", 404)
        if int(slot["booked"]) >= int(slot["capacity"]):
            raise _err("该号源已约满", 409)
        if slot["starts_at"] < utc_now():
            raise _err("不能预约过去的号源", 409)
        duplicate = conn.execute(
            """SELECT 1 FROM appointments WHERE patient_id=? AND slot_id=?
               AND status IN ('booked','checked_in')""",
            (session["patient_id"], req.slot_id),
        ).fetchone()
        if duplicate:
            raise _err("您已预约该号源", 409)
        appt_id = new_id("AP")
        conn.execute(
            """INSERT INTO appointments
               (id,patient_id,account_id,doctor_id,slot_id,scheduled_at,
                appointment_type,status,reason,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?, 'booked',?,?,?)""",
            (appt_id, session["patient_id"], session["account_id"], slot["doctor_id"],
             slot["id"], slot["starts_at"], slot["appointment_type"],
             req.reason.strip(), utc_now(), utc_now()),
        )
        conn.execute("UPDATE slots SET booked=booked+1 WHERE id=?", (slot["id"],))
        record_audit(
            conn, actor_type="patient_account", actor_id=session["account_id"],
            action="appointment_book", entity_type="appointment", entity_id=appt_id,
            detail={"slot_id": slot["id"]}, ip=_ip(request),
        )
        return {"id": appt_id, "status": "booked", "scheduled_at": slot["starts_at"],
                "doctor_id": slot["doctor_id"], "type": slot["appointment_type"]}


@router.get("/appointments")
def list_appointments(request: Request):
    session = _portal_session(request, require_patient=True)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT a.*,u.display_name AS doctor_name
               FROM appointments a JOIN users u ON u.id=a.doctor_id
               WHERE a.patient_id=? ORDER BY a.scheduled_at DESC LIMIT 100""",
            (session["patient_id"],),
        ).fetchall()
        return {"appointments": [dict(r) for r in rows]}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str, request: Request, reason: str = ""):
    _origin_ok(request)
    session = _portal_session(request, require_patient=True, require_account=True)
    with db.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id=? AND patient_id=?",
            (appointment_id, session["patient_id"]),
        ).fetchone()
        if row is None:
            raise _err("预约不存在", 404)
        if row["status"] not in {"booked", "checked_in"}:
            raise _err("当前预约状态不能取消", 409)
        conn.execute(
            "UPDATE appointments SET status='cancelled',updated_at=? WHERE id=?",
            (utc_now(), appointment_id),
        )
        if row["status"] == "booked":
            conn.execute("UPDATE slots SET booked=MAX(0,booked-1) WHERE id=?", (row["slot_id"],))
        record_audit(
            conn, actor_type="patient_account", actor_id=session["account_id"],
            action="appointment_cancel", entity_type="appointment",
            entity_id=appointment_id, detail={"reason": reason.strip()}, ip=_ip(request),
        )
    return {"ok": True}


@router.post("/feedback", status_code=201)
def create_feedback(req: FeedbackCreateRequest, request: Request):
    _origin_ok(request)
    session = _portal_session(request, require_patient=True, require_account=True)
    with db.transaction(immediate=True) as conn:
        doctor_id = req.doctor_id
        if req.appointment_id:
            appointment = conn.execute(
                """SELECT * FROM appointments WHERE id=? AND patient_id=?
                   AND account_id=?""",
                (req.appointment_id, session["patient_id"], session["account_id"]),
            ).fetchone()
            if appointment is None:
                raise _err("关联的预约不存在", 404)
            if appointment["status"] != "completed":
                raise _err("就诊完成后才能评价", 409)
            doctor_id = appointment["doctor_id"]
        if not doctor_id:
            raise _err("请选择要评价的医生")
        doctor = conn.execute(
            "SELECT 1 FROM users WHERE id=? AND role='doctor' AND active=1", (doctor_id,)
        ).fetchone()
        if not doctor:
            raise _err("医生不存在")
        feedback_id = new_id("FB")
        conn.execute(
            """INSERT INTO feedback
               (id,patient_id,account_id,doctor_id,appointment_id,rating,content,
                status,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?, 'pending',?,?)""",
            (feedback_id, session["patient_id"], session["account_id"], doctor_id,
             req.appointment_id, req.rating, req.content.strip(), utc_now(), utc_now()),
        )
        record_audit(
            conn, actor_type="patient_account", actor_id=session["account_id"],
            action="feedback_create", entity_type="feedback", entity_id=feedback_id,
            ip=_ip(request),
        )
        return {"id": feedback_id, "status": "pending"}


@router.get("/feedback")
def list_my_feedback(request: Request):
    session = _portal_session(request, require_patient=True)
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT f.*,u.display_name AS doctor_name FROM feedback f
               LEFT JOIN users u ON u.id=f.doctor_id
               WHERE f.patient_id=? ORDER BY f.created_at DESC""",
            (session["patient_id"],),
        ).fetchall()
        return {"feedback": [dict(r) for r in rows]}


def _portal_encounter_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return only visit metadata safe for the patient-facing report list.

    The stored snapshot keeps the full clinical payload (including all 35
    measured values and diagnosis text) for the detail view and PDF.  The list
    must not become a side channel that exposes those values before the
    patient opens a report.
    """
    encounter = snapshot.get("encounter", {}) or {}
    return {
        "id": encounter.get("id"),
        "case_ref": encounter.get("case_ref"),
        "occurred_at": encounter.get("occurred_at"),
        "surgery_type": encounter.get("surgery_type"),
    }


def _portal_reports(conn: Any, patient_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT r.* FROM reports r WHERE r.patient_id=? AND r.status='published'
           ORDER BY r.published_at DESC, r.version DESC""",
        (patient_id,),
    ).fetchall()
    result = []
    for row in rows:
        snapshot = json_load(row["snapshot_json"], {})
        prediction = snapshot.get("prediction", {}).get("result", {})
        result.append({
            "id": row["id"], "report_no": row["report_no"], "version": row["version"],
            "published_at": row["published_at"], "risk_level": prediction.get("risk_level"),
            "probability": prediction.get("probability"),
            "encounter": _portal_encounter_summary(snapshot),
        })
    return result


@router.get("/reports")
def portal_reports(request: Request):
    session = _portal_session(request, require_patient=True)
    with db.reader() as conn:
        return {"reports": _portal_reports(conn, session["patient_id"])}


@router.get("/reports/{report_id}")
def portal_report(report_id: str, request: Request):
    session = _portal_session(request, require_patient=True)
    with db.reader() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id=? AND patient_id=? AND status='published'",
            (report_id, session["patient_id"]),
        ).fetchone()
        if row is None:
            raise _err("报告不存在", 404)
        digest = hashlib.sha256(row["snapshot_json"].encode("utf-8")).hexdigest()
        if not secrets.compare_digest(digest, row["sha256"]):
            raise _err("报告完整性校验失败", 409)
        snapshot = json_load(row["snapshot_json"], {})
        # Mask direct identifiers in the patient-facing copy.
        snapshot["patient"] = {
            "name": (snapshot.get("patient", {}).get("name") or "")[:1] + "****",
            "mrn": (snapshot.get("patient", {}).get("mrn") or "")[:4] + "****",
            "sex": snapshot.get("patient", {}).get("sex"),
        }
        snapshot["encounter"].pop("values", None)
        record_audit(
            conn, actor_type="query_code" if not session["account_id"] else "patient_account",
            actor_id=session["account_id"], action="portal_report_view",
            entity_type="report", entity_id=report_id, ip=_ip(request),
        )
        return {"report": {"id": row["id"], "report_no": row["report_no"],
                           "version": row["version"], "published_at": row["published_at"],
                           "status": row["status"], "sha256": row["sha256"],
                           "snapshot": snapshot}}


@router.get("/reports/{report_id}/pdf")
def portal_report_pdf(report_id: str, request: Request):
    session = _portal_session(request, require_patient=True)
    with db.reader() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id=? AND patient_id=? AND status='published'",
            (report_id, session["patient_id"]),
        ).fetchone()
        if row is None:
            raise _err("报告不存在", 404)
        if hashlib.sha256(row["snapshot_json"].encode()).hexdigest() != row["sha256"]:
            raise _err("报告完整性校验失败", 409)
        snapshot = json_load(row["snapshot_json"], {})
        record_audit(
            conn, actor_type="patient_account" if session["account_id"] else "query_code",
            actor_id=session["account_id"], action="portal_report_pdf",
            entity_type="report", entity_id=report_id, ip=_ip(request),
        )
    pdf_bytes = generate_clinical_report(snapshot)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{row["report_no"]}.pdf"',
                 "Cache-Control": "no-store"},
    )
