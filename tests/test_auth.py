# -*- coding: utf-8 -*-
"""In-process API tests for database auth, clinical workflow, import and backup."""
from __future__ import annotations

import csv
import io
import os
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
from backend.app.auth_service import create_user, get_user  # noqa: E402
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

    pdf = client.get(f"/api/reports/{report_id}/pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"
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
    assert preview.json()["summary"]["valid"] == 1
    commit = client.post("/api/imports/commit", json={"rows": preview.json()["rows"]})
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 1
    assert commit.json()["results"][0]["encounter_id"]
