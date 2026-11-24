# -*- coding: utf-8 -*-
"""Deployment packaging regression tests (Dockerfile / .dockerignore)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerignore_excludes_patient_database_and_auth_secrets():
    rules = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    required = {
        "backend/clinical.db",
        "backend/clinical.db-*",
        "backend/auth_config.json",
        "backend/auth_config.json.tmp",
        "backend/backups",
        "backend/*.restore-tmp",
        "backend/*.log",
    }
    assert required <= rules


def test_dockerfile_uses_explicit_runtime_copies_and_non_root_user():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . ." not in text
    for source in ("backend", "app_data", "outputs", "scripts"):
        assert f"COPY --chown=aki:aki {source} ./{source}" in text
    assert "USER aki" in text
    assert "AKI_DB_PATH=/data/clinical.db" in text
    assert "AKI_AUTH_CONFIG=/data/auth_config.json" in text
    assert "AKI_BACKUP_DIR=/data/backups" in text
