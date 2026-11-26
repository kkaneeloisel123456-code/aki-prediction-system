# -*- coding: utf-8 -*-
"""In-process API tests for database auth, clinical workflow, import and backup."""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import time
from datetime import date, datetime
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = Path(tempfile.mkdtemp(prefix="aki-api-tests-"))
DB_PATH = TEST_ROOT / "clinical.db"
os.environ["AKI_DB_PATH"] = str(DB_PATH)
os.environ["AKI_BACKUP_DIR"] = str(TEST_ROOT / "backups")
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import database as db  # noqa: E402
from backend.app.auth_service import create_user, get_user, update_user  # noqa: E402
from backend.app.backup import restore_database  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client():
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    shutil.rmtree(TEST_ROOT / "backups", ignore_errors=True)
    db.ensure_initialized()
    create_user(
        actor_id="system", username="admin", display_name="管理员",
        role="admin", password="AdminPass123!", must_change_password=False,
    )
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, username="admin", password="AdminPass123!") -> None:
    response = client.post("/api/auth/login", json={
        "username": username, "password": password, "remember": False,
    })
    assert response.status_code == 200, response.text
    client.headers["x-csrf-token"] = client.cookies.get("aki_csrf")


def _pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "".join(page.extract_text() or "" for page in reader.pages)


def create_doctor(client: TestClient, username="doctor1", must_change=False) -> str:
    response = client.post("/api/admin/users", json={
        "username": username, "display_name": "张医生", "role": "doctor",
        "password": "DoctorPass123!", "must_change_password": must_change,
    })
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def test_auth_csrf_and_logout(client):
    assert client.get("/api/meta").status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "admin", "password": "wrong-password", "remember": False,
    }).status_code == 401
    login(client)
    assert client.get("/api/meta").status_code == 200
    assert client.cookies.get("aki_session")
    assert client.cookies.get("aki_csrf")

    # State-changing requests must carry the CSRF header.
    client.headers.pop("x-csrf-token")
    denied = client.post("/api/auth/logout")
    assert denied.status_code == 403, denied.text
    client.headers["x-csrf-token"] = client.cookies.get("aki_csrf")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_validation_error_is_chinese_and_does_not_echo_secrets(client):
    missing = client.post("/api/auth/login", json={})
    assert missing.status_code == 422, missing.text
    payload = missing.json()
    assert payload["detail"] == "请求字段不符合要求"
    assert "Field required" not in missing.text
    assert {item["field"] for item in payload["errors"]} == {"username", "password"}

    secret = "DoNotEchoThisPassword"
    invalid = client.post("/api/auth/login", json={
        "username": "", "password": secret, "remember": False,
    })
    assert invalid.status_code == 422, invalid.text
    assert secret not in invalid.text
    assert "提交内容" not in invalid.text


def test_revoke_report_uses_json_body_and_admin_only(client):
    login(client)
    case = _published_case(client, mrn="REVOKE-1")
    url = f"/api/reports/{case['report_id']}/revoke"

    no_body = client.post(url)
    assert no_body.status_code == 400, no_body.text
    assert "撤销正式报告必须填写原因" in no_body.text

    blank = client.post(url, json={"reason": "   "})
    assert blank.status_code == 400, blank.text
    assert "撤销正式报告必须填写原因" in blank.text

    _switch_login(client, "doctor1")
    forbidden = client.post(url, json={"reason": "医生无权撤销"})
    assert forbidden.status_code == 403, forbidden.text

    _switch_login(client, "admin", "AdminPass123!")
    revoked = client.post(url, json={"reason": "  复核发现风险分级需要修正  "})
    assert revoked.status_code == 200, revoked.text
    with db.reader() as conn:
        report = conn.execute(
            "SELECT status,revoke_reason FROM reports WHERE id=?",
            (case["report_id"],),
        ).fetchone()
        encounter = conn.execute(
            "SELECT status FROM encounters WHERE id=?",
            (case["encounter_id"],),
        ).fetchone()
    assert report["status"] == "revoked"
    assert report["revoke_reason"] == "复核发现风险分级需要修正"
    assert encounter["status"] == "reviewed"


def test_first_login_password_change_is_enforced(client):
    login(client)
    doctor_id = create_doctor(client, "doctor2", must_change=True)
    client.headers.pop("x-csrf-token")
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={
        "username": "doctor2", "password": "DoctorPass123!", "remember": False,
    })
    assert response.status_code == 200, response.text
    assert response.json()["user"]["must_change_password"] is True
    client.headers["x-csrf-token"] = client.cookies.get("aki_csrf")

    blocked = client.get("/api/patients")
    assert blocked.status_code == 403, blocked.text
    changed = client.post("/api/auth/password", json={
        "current_password": "DoctorPass123!", "new_password": "NewDoctorPass123!",
    })
    assert changed.status_code == 200, changed.text
    assert client.get("/api/patients").status_code == 200
    assert not get_user(doctor_id)["must_change_password"]


def test_clinical_publish_pdf_and_backup(client):
    login(client)
    doctor_id = create_doctor(client)
    patient = client.post("/api/patients", json={
        "mrn": "P0001", "name": "测试患者", "sex": "男", "birth_year": 1960,
        "certificate_last4": "1234", "phone_last4": "5678", "owner_id": doctor_id,
    })
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]

    encounter = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "CASE-1", "occurred_at": "2026-11-20T09:00:00+08:00",
        "surgery_type": "冠脉搭桥", "values": {}, "diagnosis": "", "orders": "",
    })
    assert encounter.status_code == 201, encounter.text
    encounter_id = encounter.json()["id"]
    detail = client.get(f"/api/encounters/{encounter_id}").json()

    from backend.app.assets import load_assets
    assets = load_assets()
    features = {
        name: assets["impute_values"].get(name, 1.0)
        for name in assets["features"]
    }
    features = {k: v for k, v in features.items() if v is not None}
    draft = client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "values": features, "diagnosis": "AKI高风险，需密切监测",
        "orders": "监测肌酐、尿量，必要时请肾内科会诊",
    })
    assert draft.status_code == 200, draft.text
    prediction = client.post(f"/api/encounters/{encounter_id}/predict", json={
        "row_version": detail["row_version"], "features": features,
    })
    assert prediction.status_code == 200, prediction.text

    detail = client.get(f"/api/encounters/{encounter_id}").json()
    review = client.post(f"/api/encounters/{encounter_id}/review", json={
        "row_version": detail["row_version"], "decision": "agree", "reason": "符合临床表现",
    })
    assert review.status_code == 200, review.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    checklist = client.get(f"/api/encounters/{encounter_id}/checklist").json()
    assert checklist["can_publish"] is True
    publish = client.post(f"/api/encounters/{encounter_id}/publish", json={
        "row_version": detail["row_version"], "draft_version": checklist["draft_version"],
        "missing_ack": False,
    })
    assert publish.status_code == 200, publish.text
    report_id = publish.json()["id"]
    published_detail = client.get(f"/api/encounters/{encounter_id}").json()
    assert published_detail["values"] == features, "发布后指标必须回写到就诊记录"

    pdf = client.get(f"/api/reports/{report_id}/pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"
    assert "采纳模型结果" in "".join(_pdf_text(pdf.content).split())
    backup = client.post("/api/admin/backup")
    assert backup.status_code in (200, 201), backup.text
    snapshot = TEST_ROOT / "backups" / backup.json()["filename"]
    assert snapshot.exists()
    restore_database(snapshot, confirm=True)
    with db.reader() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1
    audit = client.get("/api/admin/audit").json()["events"]
    assert any(event["action"] == "report_publish" for event in audit)


def test_csv_import_accepts_metric_less_draft(client):
    login(client)
    doctor_id = create_doctor(client)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["病历号", "姓名", "性别", "出生年份", "就诊编号", "发生时间", "负责人ID", "ICUAdmSCr"])
    writer.writerow(["MRN-IMP-1", "导入患者", "女", "1970", "CASE-IMP-1", "2026-11-20T10:30:00+08:00", doctor_id, ""])
    raw = buffer.getvalue().encode("utf-8-sig")

    preview = client.post(
        "/api/imports/preview",
        files={"file": ("import.csv", raw, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["summary"]["valid"] == 1
    commit = client.post("/api/imports/commit", json={"batch_id": payload["batch_id"]})
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 1
    assert commit.json()["results"][0]["encounter_id"]


# ---------------------------------------------------------------------------
# Phase 1 regression tests (migration, manual review, portal, RBAC, import)
# ---------------------------------------------------------------------------
def _model_features() -> dict[str, float]:
    from backend.app.assets import load_assets
    assets = load_assets()
    features = {
        name: assets["impute_values"].get(name, 1.0)
        for name in assets["features"]
    }
    return {k: v for k, v in features.items() if v is not None}


def _published_case(client: TestClient, mrn: str = "P0001") -> dict:
    """Create a fully published report and return its ids."""
    doctor_id = create_doctor(client)
    patient = client.post("/api/patients", json={
        "mrn": mrn, "name": "测试患者", "sex": "男", "birth_year": 1960,
        "certificate_last4": "1234", "phone_last4": "5678", "owner_id": doctor_id,
    })
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]
    encounter = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "CASE-1", "occurred_at": "2026-11-20T09:00:00+08:00",
        "surgery_type": "冠脉搭桥", "values": {},
        "diagnosis": "术后AKI风险", "orders": "监测肌酐与尿量",
    })
    assert encounter.status_code == 201, encounter.text
    encounter_id = encounter.json()["id"]
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    features = _model_features()
    draft = client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "values": features, "diagnosis": "术后AKI风险", "orders": "监测肌酐与尿量",
    })
    assert draft.status_code == 200, draft.text
    prediction = client.post(f"/api/encounters/{encounter_id}/predict", json={
        "row_version": detail["row_version"], "features": features,
    })
    assert prediction.status_code == 200, prediction.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    review = client.post(f"/api/encounters/{encounter_id}/review", json={
        "row_version": detail["row_version"], "decision": "agree", "reason": "符合临床表现",
    })
    assert review.status_code == 200, review.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    checklist = client.get(f"/api/encounters/{encounter_id}/checklist").json()
    assert checklist["can_publish"] is True, checklist
    publish = client.post(f"/api/encounters/{encounter_id}/publish", json={
        "row_version": detail["row_version"], "draft_version": checklist["draft_version"],
        "missing_ack": False,
    })
    assert publish.status_code == 200, publish.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    return {
        "doctor_id": doctor_id, "patient_id": patient_id, "encounter_id": encounter_id,
        "report_id": publish.json()["id"], "encounter": detail,
        "risk": prediction.json()["prediction"]["risk_level"],
        "probability": prediction.json()["prediction"]["probability"],
    }


def test_predictions_migration_rebuilds_table():
    import sqlite3
    migration_db = TEST_ROOT / "migration.db"
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(migration_db) + suffix)
        if path.exists():
            path.unlink()
    conn = sqlite3.connect(migration_db)
    conn.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            role TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, last_login_at TEXT
        );
        CREATE TABLE patients (
            id TEXT PRIMARY KEY, mrn TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            sex TEXT NOT NULL, birth_year INTEGER, certificate_last4 TEXT, phone_last4 TEXT,
            owner_id TEXT, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE encounters (
            id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id),
            case_ref TEXT NOT NULL, occurred_at TEXT NOT NULL, surgery_type TEXT,
            values_json TEXT NOT NULL DEFAULT '{}', diagnosis TEXT NOT NULL DEFAULT '',
            orders TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft',
            current_prediction_id TEXT, row_version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL, updated_by TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE predictions (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
            patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            actor_id TEXT NOT NULL REFERENCES users(id),
            input_json TEXT NOT NULL, result_json TEXT NOT NULL,
            probability REAL NOT NULL, risk_level TEXT NOT NULL,
            model_version TEXT NOT NULL, model_hash TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'valid', predicted_at TEXT NOT NULL
        );
        CREATE INDEX idx_predictions_encounter ON predictions(encounter_id);
        CREATE TABLE clinical_reviews (
            id TEXT PRIMARY KEY,
            encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
            prediction_id TEXT NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
            reviewer_id TEXT NOT NULL REFERENCES users(id),
            decision TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
            prediction_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL
        );
        INSERT INTO users VALUES('U-1','admin','管理员','admin','x',1,0,'2026-01-01','2026-01-01',NULL);
        INSERT INTO patients VALUES('P-1','MRN-1','旧患者','男',1960,'1234','5678','U-1',1,'2026-01-01','2026-01-01');
        INSERT INTO encounters VALUES('E-1','P-1','CASE-1','2026-11-20T09:00:00+08:00','搭桥','{}','','','predicted','PD-1',1,'U-1','U-1','2026-01-01','2026-01-01');
        INSERT INTO predictions VALUES('PD-1','E-1','P-1','U-1','{}','{}',0.5,'中','V1','hash','fp','valid','2026-01-01');
        INSERT INTO clinical_reviews VALUES('RV-1','E-1','PD-1','U-1','agree','','fp','2026-01-01');
        """
    )
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    conn.close()

    db.reset_initialization_cache()
    db.initialize_database(migration_db)
    db.reset_initialization_cache()
    check = sqlite3.connect(migration_db)
    try:
        version = check.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.SCHEMA_VERSION
        columns = {row[1]: row for row in check.execute("PRAGMA table_info(predictions)")}
        assert "origin" in columns
        for nullable in ("probability", "model_version", "model_hash"):
            assert columns[nullable][3] == 0, f"{nullable} 仍然 NOT NULL"
        assert check.execute("SELECT origin FROM predictions WHERE id='PD-1'").fetchone()[0] == "model"
        review_sql = check.execute(
            "SELECT sql FROM sqlite_master WHERE name='clinical_reviews'"
        ).fetchone()[0]
        assert "REFERENCES predictions" in review_sql
        assert "predictions_new" not in review_sql
        assert check.execute("PRAGMA foreign_key_check").fetchall() == []
        check.execute(
            """INSERT INTO predictions
               (id,encounter_id,patient_id,actor_id,input_json,result_json,probability,
                risk_level,model_version,model_hash,input_fingerprint,status,predicted_at,origin)
               VALUES('PD-M','E-1','P-1','U-1','{}','{}',NULL,'人工审核',NULL,NULL,'fp2','valid','2026-01-01','manual')"""
        )
        assert check.execute(
            "SELECT probability,model_version,origin FROM predictions WHERE id='PD-M'"
        ).fetchone() == (None, None, "manual")
    finally:
        check.close()


def test_manual_review_without_prediction_succeeds(client):
    login(client)
    doctor_id = create_doctor(client)
    patient = client.post("/api/patients", json={
        "mrn": "MAN-1", "name": "人工审核患者", "sex": "女", "birth_year": 1970,
        "owner_id": doctor_id,
    })
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]
    encounter = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "MAN-CASE", "occurred_at": "2026-11-20T09:00:00+08:00",
        "values": {},
    })
    encounter_id = encounter.json()["id"]
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    draft = client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "values": {"术前eGFR": 40}, "diagnosis": "慢性肾脏病 4 期",
        "orders": "复查肌酐、避免肾毒性药物",
    })
    assert draft.status_code == 200, draft.text
    review = client.post(f"/api/encounters/{encounter_id}/review", json={
        "row_version": detail["row_version"], "decision": "manual",
        "reason": "模型不可用，按肌酐与尿量人工判断为中风险",
    })
    assert review.status_code == 200, review.text
    with db.reader() as conn:
        row = conn.execute(
            "SELECT * FROM predictions WHERE encounter_id=? AND origin='manual'",
            (encounter_id,),
        ).fetchone()
        assert row is not None
        assert row["probability"] is None
        assert row["model_version"] is None and row["model_hash"] is None
        assert db.json_load(row["input_json"], {}) == {"术前eGFR": 40}
        enc = conn.execute(
            "SELECT values_json FROM encounters WHERE id=?", (encounter_id,)
        ).fetchone()
        assert db.json_load(enc["values_json"], {}) == {"术前eGFR": 40}

    detail = client.get(f"/api/encounters/{encounter_id}").json()
    checklist = client.get(
        f"/api/encounters/{encounter_id}/checklist", params={"missing_ack": True},
    ).json()
    assert checklist["can_publish"] is True, checklist
    publish = client.post(f"/api/encounters/{encounter_id}/publish", json={
        "row_version": detail["row_version"],
        "draft_version": checklist["draft_version"],
        "missing_ack": True,
    })
    assert publish.status_code == 200, publish.text
    pdf = client.get(f"/api/reports/{publish.json()['id']}/pdf")
    assert pdf.status_code == 200, pdf.text
    pdf_text = "".join(_pdf_text(pdf.content).split())
    assert "人工记录" in pdf_text
    assert "暂缓采纳" not in pdf_text
    assert "人工审核" in pdf_text
    assert "本次未使用模型" in pdf_text
    assert "本次未使用模型，无概率" in pdf_text
    assert "概率未校准" not in pdf_text
    assert "中位数填充" not in pdf_text
    assert "模型版本本次未使用模型" in pdf_text

    encounters = client.get(f"/api/patients/{patient_id}/encounters").json()["encounters"]
    manual = next(item for item in encounters if item["id"] == encounter_id)
    assert manual["latest_prediction"]["origin"] == "manual"
    assert manual["latest_prediction"]["risk_level"] == "人工审核"


def test_portal_report_detail_matches_list_and_requires_second_factor(client):
    login(client)
    case = _published_case(client)
    query_code = client.post(f"/api/patients/{case['patient_id']}/query-code")
    assert query_code.status_code == 200, query_code.text
    code = query_code.json().get("query_code")
    assert code

    missing_factor = client.post("/api/portal/query", json={
        "mrn": "P0001", "name": "测试患者", "query_code": code,
        "certificate_last4": "", "phone_last4": "",
    })
    assert missing_factor.status_code == 400, missing_factor.text
    wrong_factor = client.post("/api/portal/query", json={
        "mrn": "P0001", "name": "测试患者", "query_code": code,
        "certificate_last4": "9999",
    })
    assert wrong_factor.status_code == 400, wrong_factor.text

    ok = client.post("/api/portal/query", json={
        "mrn": "P0001", "name": "测试患者", "query_code": code,
        "certificate_last4": "1234",
    })
    assert ok.status_code == 200, ok.text
    listed = client.get("/api/portal/reports").json()["reports"]
    assert listed and listed[0]["risk_level"] == case["risk"]
    detail = client.get(f"/api/portal/reports/{case['report_id']}")
    assert detail.status_code == 200, detail.text
    report = detail.json()["report"]
    result = report["snapshot"]["prediction"]["result"]
    assert result["risk_level"] == listed[0]["risk_level"]
    assert abs(result["probability"] - listed[0]["probability"]) < 1e-9
    assert report["sha256"]


def test_query_code_and_portal_session_have_separate_ttls(client):
    login(client)
    case = _published_case(client, mrn="TTL-1")
    issued = client.post(f"/api/patients/{case['patient_id']}/query-code")
    assert issued.status_code == 200, issued.text
    issued_payload = issued.json()
    code = issued_payload["query_code"]
    assert "24 小时" in issued_payload["notice"]
    assert abs(int(issued_payload["expires_at"]) - int(time.time()) - 1440 * 60) <= 60

    verified = client.post("/api/portal/query", json={
        "mrn": "TTL-1", "name": "测试患者", "query_code": code,
        "certificate_last4": "1234",
    })
    assert verified.status_code == 200, verified.text
    assert abs(int(verified.json()["expires_in"]) - 30 * 60) <= 2
    with db.reader() as conn:
        portal_session = conn.execute(
            """SELECT expires_at FROM portal_sessions
               WHERE patient_id=? ORDER BY created_at DESC LIMIT 1""",
            (case["patient_id"],),
        ).fetchone()
    assert portal_session is not None
    assert abs(int(portal_session["expires_at"]) - int(time.time()) - 30 * 60) <= 60

    with db.transaction() as conn:
        conn.execute(
            "UPDATE portal_sessions SET expires_at=? WHERE patient_id=?",
            (int(time.time()) - 1, case["patient_id"]),
        )
    expired = client.get("/api/portal/reports")
    assert expired.status_code == 401, expired.text

    # The 30-minute view session expired, but the 24-hour code can be used again.
    again = client.post("/api/portal/query", json={
        "mrn": "TTL-1", "name": "测试患者", "query_code": code,
        "certificate_last4": "1234",
    })
    assert again.status_code == 200, again.text


def test_deactivate_account_and_last_admin_protection(client):
    login(client)
    admin_id = client.get("/api/auth/status").json()["user"]["id"]
    create_doctor(client, "doctor_off")
    doctor_client = TestClient(app)
    try:
        response = doctor_client.post("/api/auth/login", json={
            "username": "doctor_off", "password": "DoctorPass123!", "remember": False,
        })
        assert response.status_code == 200, response.text
        assert doctor_client.get("/api/meta").status_code == 200
        deactivated = client.patch(f"/api/admin/users/{get_user_id('doctor_off')}", json={"active": False})
        assert deactivated.status_code == 200, deactivated.text
        assert deactivated.json()["active"] == 0
        assert doctor_client.get("/api/meta").status_code == 401
    finally:
        doctor_client.close()
    self_off = client.patch(f"/api/admin/users/{admin_id}", json={"active": False})
    assert self_off.status_code == 409, self_off.text
    assert "不能停用" in self_off.text


def test_last_admin_guard_rejects_non_self_actor_at_service_layer(client):
    """正常 API 请求人必须是仍在职管理员，因此“非本人停用唯一管理员”只能由服务层构造。

    API 路径已由上一个用例覆盖停用自己；这里直接验证 targets_active <= 1 时，
    即使 actor 不是被停用对象，最后管理员保护也不会放行。
    """
    login(client)
    admin_id = client.get("/api/auth/status").json()["user"]["id"]
    created = client.post("/api/admin/users", json={
        "username": "admin_second", "display_name": "第二管理员", "role": "admin",
        "password": "AdminSecond123!", "must_change_password": False,
    })
    assert created.status_code == 201, created.text
    second_id = created.json()["id"]
    deactivated = client.patch(f"/api/admin/users/{second_id}", json={"active": False})
    assert deactivated.status_code == 200, deactivated.text

    with pytest.raises(ValueError, match="不能停用"):
        update_user(actor_id=second_id, user_id=admin_id, active=False)
    assert get_user(admin_id)["active"] == 1


def get_user_id(username: str) -> str:
    with db.reader() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    assert row
    return row["id"]


def test_view_only_grant_cannot_publish(client):
    login(client)
    doctor1 = create_doctor(client, "owner_doc")
    doctor2 = create_doctor(client, "view_doc")
    patient = client.post("/api/patients", json={
        "mrn": "RBAC-1", "name": "权限患者", "sex": "男", "birth_year": 1960,
        "owner_id": doctor1,
    })
    patient_id = patient.json()["id"]
    login(client, "owner_doc", "DoctorPass123!")
    encounter = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "RBAC-CASE", "occurred_at": "2026-11-20T09:00:00+08:00",
        "values": {}, "diagnosis": "待评估", "orders": "监测",
    })
    encounter_id = encounter.json()["id"]
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    features = _model_features()
    client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "values": features, "diagnosis": "待评估", "orders": "监测",
    })
    client.post(f"/api/encounters/{encounter_id}/predict", json={
        "row_version": detail["row_version"], "features": features,
    })
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    client.post(f"/api/encounters/{encounter_id}/review", json={
        "row_version": detail["row_version"], "decision": "agree", "reason": "同意",
    })

    login(client)
    grant = client.post(f"/api/patients/{patient_id}/grants", json={
        "doctor_id": doctor2, "permission": "view",
    })
    assert grant.status_code in (200, 201), grant.text
    login(client, "view_doc", "DoctorPass123!")
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    denied = client.post(f"/api/encounters/{encounter_id}/publish", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "missing_ack": True,
    })
    assert denied.status_code == 403, denied.text


def test_import_rejects_invalid_sex_with_chinese_reason(client):
    login(client)
    create_doctor(client, "import_doc")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["病历号", "姓名", "性别", "出生年份", "就诊编号", "发生时间", "负责人ID"])
    writer.writerow(["SEX-BAD", "错误性别", "X", "1970", "SEX-1", "2026-11-20T10:00:00+08:00", "import_doc"])
    writer.writerow(["sex-good", "别名性别", "M", "1970", "SEX-2", "2026-11-20T10:00:00+08:00", "import_doc"])
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("import.csv", buffer.getvalue().encode("utf-8-sig"), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["summary"]["valid"] == 1
    assert payload["summary"]["invalid"] == 1
    bad_row = next(row for row in payload["rows"] if row["mrn"] == "SEX-BAD")
    assert any("性别" in message for message in bad_row["errors"])

    commit = client.post("/api/imports/commit", json={"batch_id": payload["batch_id"]})
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 1
    assert commit.json()["failed"] == 1
    with db.reader() as conn:
        assert conn.execute("SELECT COUNT(*) FROM patients WHERE mrn='SEX-BAD'").fetchone()[0] == 0
        row = conn.execute(
            "SELECT sex,mrn FROM patients WHERE mrn='SEX-GOOD'"
        ).fetchone()
        assert row and row["sex"] == "男"

    with db.reader() as conn:
        before = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    legacy = client.post("/api/imports/commit", json={"rows": [{
        "index": 1, "mrn": "LEGACY-ROW", "name": "旧入口患者", "sex": "男",
        "case_ref": "LEGACY-1", "occurred_at": "2026-11-20T10:00:00+08:00",
        "owner_id": "import_doc", "values": {},
    }]})
    assert legacy.status_code == 400, legacy.text
    assert "批次号" in legacy.json()["detail"]
    with db.reader() as conn:
        after = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert after == before


def test_diagnosis_length_limit(client):
    login(client)
    doctor_id = create_doctor(client)
    patient = client.post("/api/patients", json={
        "mrn": "LEN-1", "name": "长度患者", "sex": "男", "owner_id": doctor_id,
    })
    patient_id = patient.json()["id"]
    response = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "LEN-CASE", "occurred_at": "2026-11-20T09:00:00+08:00",
        "values": {}, "diagnosis": "诊" * 4001,
    })
    assert response.status_code == 422, response.text


def test_dashboard_hides_published_encounters(client):
    login(client)
    case = _published_case(client, mrn="DASH-1")
    summary = client.get("/api/dashboard/summary").json()
    assert summary["pending_total"] == 0
    assert all(item["id"] != case["encounter_id"] for item in summary["recent_encounters"])


def test_restore_removes_stale_wal_and_shm(client):
    login(client)
    backup = client.post("/api/admin/backup")
    assert backup.status_code in (200, 201), backup.text
    snapshot = TEST_ROOT / "backups" / backup.json()["filename"]
    for suffix in ("-wal", "-shm"):
        Path(str(DB_PATH) + suffix).write_bytes(b"stale")
    restore_database(snapshot, confirm=True)
    for suffix in ("-wal", "-shm"):
        assert not Path(str(DB_PATH) + suffix).exists()


def test_restore_with_unmerged_wal_matches_backup_and_keeps_emergency_copy(client):
    """A committed-but-uncheckpointed WAL must not survive a restore."""
    login(client)
    backup = client.post("/api/admin/backup")
    assert backup.status_code in (200, 201), backup.text
    snapshot = TEST_ROOT / "backups" / backup.json()["filename"]
    for path in TEST_ROOT.glob("clinical.db.pre-restore-*"):
        path.unlink()

    # Write an audit marker in WAL mode and copy the main file + WAL while the
    # connection is still open, so the copied pair genuinely has an unmerged
    # committed transaction. Closing the writer afterwards would checkpoint it
    # into the main file and defeat the purpose of this test.
    live = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("PRAGMA wal_autocheckpoint=0")
        # isolation_level=None makes this statement autocommit, leaving the
        # new page only in WAL until a checkpoint (or last-connection close).
        live.execute(
            """INSERT INTO audit_events
               (id,actor_type,actor_id,action,entity_type,entity_id,detail_json,ip,created_at)
               VALUES('AUD-WAL-MARKER','system',NULL,'wal_marker','system',NULL,'{}',NULL,'2026-11-24T10:00:00+08:00')"""
        )
        wal = Path(str(DB_PATH) + "-wal")
        assert wal.exists() and wal.stat().st_size > 0
        main_copy = TEST_ROOT / "unmerged-main.db"
        wal_copy = TEST_ROOT / "unmerged-main.db-wal"
        shutil.copy2(DB_PATH, main_copy)
        shutil.copy2(wal, wal_copy)
    finally:
        live.close()

    for suffix in ("-wal", "-shm"):
        path = Path(str(DB_PATH) + suffix)
        if path.exists():
            path.unlink()
    shutil.copy2(main_copy, DB_PATH)
    shutil.copy2(wal_copy, Path(str(DB_PATH) + "-wal"))

    restore_database(snapshot, confirm=True)

    with db.reader() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action='wal_marker'"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE username='admin'"
        ).fetchone()[0] == 1
    emergencies = sorted(TEST_ROOT.glob("clinical.db.pre-restore-*"))
    assert len(emergencies) == 1
    # The emergency copy is taken before replacement and must include the
    # latest WAL commit, otherwise it is not a usable rollback.
    emergency = sqlite3.connect(emergencies[0])
    try:
        assert emergency.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action='wal_marker'"
        ).fetchone()[0] == 1
    finally:
        emergency.close()


def test_publish_requires_exact_draft_version(client):
    login(client)
    doctor_id = create_doctor(client, "draft_doc")
    patient = client.post("/api/patients", json={
        "mrn": "DRAFT-1", "name": "草稿并发患者", "sex": "男", "birth_year": 1960,
        "owner_id": doctor_id,
    })
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]
    encounter = client.post(f"/api/patients/{patient_id}/encounters", json={
        "case_ref": "DRAFT-CASE", "occurred_at": "2026-11-20T09:00:00+08:00",
        "values": {}, "diagnosis": "待评估", "orders": "监测",
    })
    assert encounter.status_code == 201, encounter.text
    encounter_id = encounter.json()["id"]
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    features = _model_features()

    first = client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": 0,
        "values": features, "diagnosis": "待评估", "orders": "监测",
    })
    assert first.status_code == 200, first.text
    second = client.put(f"/api/encounters/{encounter_id}/draft", json={
        "row_version": detail["row_version"], "draft_version": first.json()["draft_version"],
        "values": features, "diagnosis": "待评估", "orders": "监测",
    })
    assert second.status_code == 200, second.text
    assert second.json()["draft_version"] == 2

    prediction = client.post(f"/api/encounters/{encounter_id}/predict", json={
        "row_version": detail["row_version"], "features": features,
    })
    assert prediction.status_code == 200, prediction.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    review = client.post(f"/api/encounters/{encounter_id}/review", json={
        "row_version": detail["row_version"], "decision": "agree", "reason": "同意",
    })
    assert review.status_code == 200, review.text
    detail = client.get(f"/api/encounters/{encounter_id}").json()
    checklist = client.get(f"/api/encounters/{encounter_id}/checklist").json()
    assert checklist["can_publish"] is True, checklist
    assert checklist["draft_version"] == 2

    base = {"row_version": detail["row_version"], "missing_ack": False}
    stale = client.post(f"/api/encounters/{encounter_id}/publish", json={
        **base, "draft_version": 1,
    })
    assert stale.status_code == 409, stale.text
    # draft_version=0 used to be treated as "no version supplied" and silently
    # bypassed an existing draft version.
    bypass = client.post(f"/api/encounters/{encounter_id}/publish", json={
        **base, "draft_version": 0,
    })
    assert bypass.status_code == 409, bypass.text
    published = client.post(f"/api/encounters/{encounter_id}/publish", json={
        **base, "draft_version": checklist["draft_version"],
    })
    assert published.status_code == 200, published.text


def test_portal_list_does_not_expose_clinical_values(client):
    login(client)
    case = _published_case(client, mrn="PORTAL-MASK")
    code = client.post(f"/api/patients/{case['patient_id']}/query-code").json()["query_code"]
    ok = client.post("/api/portal/query", json={
        "mrn": "PORTAL-MASK", "name": "测试患者", "query_code": code,
        "certificate_last4": "1234",
    })
    assert ok.status_code == 200, ok.text
    listed = client.get("/api/portal/reports").json()["reports"]
    assert listed
    encounter = listed[0]["encounter"]
    assert set(encounter) == {"id", "case_ref", "occurred_at", "surgery_type"}
    for key in ("values", "diagnosis", "orders"):
        assert key not in encounter
    detail = client.get(f"/api/portal/reports/{case['report_id']}").json()["report"]
    assert "values" not in detail["snapshot"]["encounter"]


def test_health_fails_when_database_is_unreadable(client, monkeypatch):
    healthy = client.get("/api/health")
    assert healthy.status_code == 200, healthy.text
    assert healthy.json()["database_ok"] is True
    assert healthy.json()["status"] == "ok"

    broken = TEST_ROOT / "broken.db"
    broken.write_bytes(b"this is not a sqlite database")
    monkeypatch.setenv("AKI_DB_PATH", str(broken))
    response = client.get("/api/health")
    assert response.status_code == 503, response.text
    assert response.json()["database_ok"] is False
    assert response.json()["status"] == "unavailable"


# ---------------------------------------------------------------------------
# Phase 3 import tests: XLSX, sheet choice, mapping, batch id and error export
# ---------------------------------------------------------------------------
FIXTURES = ROOT / "tests" / "fixtures"


def _switch_login(client: TestClient, username: str, password: str = "DoctorPass123!") -> None:
    if client.cookies.get("aki_session"):
        client.post("/api/auth/logout")
    client.cookies.clear()
    client.headers.pop("x-csrf-token", None)
    login(client, username, password)


def _preview_fixture(
    client: TestClient, name: str, *, sheet_name: str = "", mapping: dict | None = None,
):
    path = FIXTURES / name
    suffix = path.suffix.lower()
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".xlsx" else "text/csv"
    )
    data = {}
    if sheet_name:
        data["sheet_name"] = sheet_name
    if mapping:
        data["mapping"] = json.dumps(mapping, ensure_ascii=False)
    return client.post(
        "/api/imports/preview",
        files={"file": (name, path.read_bytes(), media)},
        data=data,
    )


def test_xlsx_template_contains_mapping_columns(client):
    login(client)
    response = client.get("/api/imports/template.xlsx")
    assert response.status_code == 200, response.text
    assert "spreadsheetml" in response.headers["content-type"]
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["导入模板"]
    headers = [cell.value for cell in sheet[1]]
    assert "负责人ID" in headers
    assert "术前Scr" in headers
    assert "病历号" in headers


def test_xlsx_requires_sheet_choice_mapping_and_batch_commit(client):
    login(client)
    create_doctor(client, "doctor1")
    raw = (FIXTURES / "phase3_two_sheets.xlsx").read_bytes()
    initial = client.post(
        "/api/imports/preview",
        files={"file": ("phase3_two_sheets.xlsx", raw, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert initial.status_code == 200, initial.text
    payload = initial.json()
    assert payload["requires_sheet"] is True
    assert payload["sheet_names"] == ["有效数据", "错误数据"]
    assert not payload.get("batch_id")

    auto_preview = _preview_fixture(client, "phase3_two_sheets.xlsx", sheet_name="有效数据")
    assert auto_preview.status_code == 200, auto_preview.text
    auto_payload = auto_preview.json()
    assert auto_payload["columns"]["病历编号"] == "mrn"
    assert auto_payload["columns"]["患者姓名"] == "name"
    assert auto_payload["summary"]["valid"] == 2

    mapping = {
        "病历编号": "mrn", "患者姓名": "name", "性别": "sex", "出生年份": "birth_year",
        "就诊编号": "case_ref", "发生时间": "occurred_at", "负责人ID": "owner_id",
        "术前肌酐": "术前Scr", "术前 eGFR": "术前eGFR",
    }
    preview = _preview_fixture(client, "phase3_two_sheets.xlsx", sheet_name="有效数据", mapping=mapping)
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["batch_id"].startswith("IMP-")
    assert payload["sheet_name"] == "有效数据"
    assert payload["summary"]["valid"] == 2
    assert not payload["header_errors"]
    assert payload["columns"]["病历编号"] == "mrn"
    assert datetime.fromisoformat(payload["rows"][0]["occurred_at"]).astimezone().date() == date(2026, 11, 20)
    assert payload["rows"][0]["values"]["术前Scr"] == 88

    commit = client.post("/api/imports/commit", json={"batch_id": payload["batch_id"]})
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 2
    duplicate_batch = client.post("/api/imports/commit", json={"batch_id": payload["batch_id"]})
    assert duplicate_batch.status_code == 409, duplicate_batch.text
    duplicate_file = _preview_fixture(
        client, "phase3_two_sheets.xlsx", sheet_name="有效数据", mapping=mapping,
    )
    assert duplicate_file.status_code == 409, duplicate_file.text


def test_xlsx_merged_cells_serial_dates_errors_and_export(client):
    login(client)
    create_doctor(client, "doctor1")
    preview = _preview_fixture(client, "phase3_two_sheets.xlsx", sheet_name="错误数据")
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    rows = {row["index"]: row for row in payload["rows"]}
    assert payload["summary"]["invalid"] >= 3
    assert datetime.fromisoformat(rows[2]["occurred_at"]).astimezone().date() == date(2026, 11, 20)
    assert rows[2]["values"]["术中晶体液量"] == 9500
    assert rows[3]["name"] == "合并患者"
    messages = " ".join(
        message for row in payload["rows"] for message in row["errors"]
    )
    assert "姓名不一致" in messages
    assert "性别" in messages
    assert "相同" in messages
    exported = client.get(f"/api/imports/{payload['batch_id']}/errors.xlsx")
    assert exported.status_code == 200, exported.text
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(exported.content))
    sheet = workbook["错误行"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:3] == ["行号", "错误", "提示"]
    assert "病历号" in headers
    assert "术中晶体液量" in headers
    assert sheet.max_row == len([row for row in payload["rows"] if row["errors"]]) + 1


def test_gbk_csv_preview_and_batch_commit(client):
    login(client)
    create_doctor(client, "doctor1")
    preview = _preview_fixture(client, "phase3_gbk.csv")
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["summary"]["valid"] == 2
    assert payload["rows"][0]["name"] == "张建国"
    assert any("未映射" in warning for warning in payload["header_warnings"])
    commit = client.post("/api/imports/commit", json={"batch_id": payload["batch_id"]})
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 2
    with db.reader() as conn:
        names = {row["name"] for row in conn.execute("SELECT name FROM patients")}
    assert {"张建国", "李秀兰"} <= names


def test_doctor_cannot_assign_new_patient_to_another_doctor(client):
    login(client)
    create_doctor(client, "doctor1")
    create_doctor(client, "doctor2")
    _switch_login(client, "doctor1")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["病历号", "姓名", "性别", "就诊编号", "发生时间", "负责人ID"])
    writer.writerow(["RBAC-IMP-1", "越权患者", "男", "RBAC-CASE-1", "2026-11-20 09:00", "doctor2"])
    raw = buffer.getvalue().encode("utf-8-sig")
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("rbac.csv", raw, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["summary"]["valid"] == 0
    assert "医生只能把新患者建在自己名下" in payload["rows"][0]["errors"]
