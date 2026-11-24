# -*- coding: utf-8 -*-
"""SQLite persistence and small shared helpers for the clinical workflow.

The database is intentionally local-file based so a single hospital workstation
can be deployed without an external database service. Connections are short
lived, WAL-enabled and always enforce foreign keys.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import BACKEND_DIR

_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()

SCHEMA_VERSION = 4

# Prediction rows come from two origins:
#   model  - produced by the deployed model; probability/model_version/model_hash set
#   manual - clinician-entered risk when no model result exists; model fields NULL
# ``probability`` and the model fields are nullable so manual rows stay honest
# instead of writing sentinel strings such as "N/A" into statistics.
_PREDICTIONS_COLUMNS = """(
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL REFERENCES users(id),
    input_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    probability REAL,
    risk_level TEXT NOT NULL,
    model_version TEXT,
    model_hash TEXT,
    input_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'valid' CHECK(status IN ('valid','superseded')),
    predicted_at TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'model' CHECK(origin IN ('model','manual'))
)"""


def database_path() -> Path:
    """Return the active database path (environment-aware for isolated tests)."""
    raw = os.environ.get("AKI_DB_PATH", "").strip()
    path = Path(raw).expanduser() if raw else BACKEND_DIR / "clinical.db"
    return path.resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6).upper()}"


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path or database_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def transaction(*, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a transaction and commit/rollback atomically."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def reader() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','doctor')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at TEXT,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS login_throttle (
    throttle_key TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0,
    window_start INTEGER NOT NULL,
    locked_until INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    mrn TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    sex TEXT NOT NULL CHECK(sex IN ('男','女','未知')),
    birth_year INTEGER,
    certificate_last4 TEXT,
    phone_last4 TEXT,
    owner_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patients_owner ON patients(owner_id);

CREATE TABLE IF NOT EXISTS patient_grants (
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL CHECK(permission IN ('view','edit')),
    granted_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(patient_id, doctor_id)
);

CREATE TABLE IF NOT EXISTS encounters (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    case_ref TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    surgery_type TEXT,
    values_json TEXT NOT NULL DEFAULT '{}',
    diagnosis TEXT NOT NULL DEFAULT '',
    orders TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','predicted','reviewed','published')),
    current_prediction_id TEXT,
    row_version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL REFERENCES users(id),
    updated_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(patient_id, case_ref)
);
CREATE INDEX IF NOT EXISTS idx_encounters_patient ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_status ON encounters(status);

CREATE TABLE IF NOT EXISTS encounter_drafts (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
    base_row_version INTEGER NOT NULL,
    draft_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, encounter_id)
);

CREATE TABLE IF NOT EXISTS predictions
""" + _PREDICTIONS_COLUMNS + """
;
CREATE INDEX IF NOT EXISTS idx_predictions_encounter ON predictions(encounter_id);
CREATE INDEX IF NOT EXISTS idx_predictions_patient ON predictions(patient_id);

CREATE TABLE IF NOT EXISTS clinical_reviews (
    id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
    prediction_id TEXT NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL CHECK(decision IN ('agree','adjust','defer','manual')),
    reason TEXT NOT NULL DEFAULT '',
    prediction_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_encounter ON clinical_reviews(encounter_id);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    report_no TEXT NOT NULL UNIQUE,
    encounter_id TEXT NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    snapshot_json TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL CHECK(status IN ('published','revoked')),
    published_at TEXT NOT NULL,
    revoked_at TEXT,
    revoke_reason TEXT,
    UNIQUE(encounter_id, version)
);
CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);

CREATE TABLE IF NOT EXISTS patient_query_codes (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_query_codes_patient ON patient_query_codes(patient_id);

CREATE TABLE IF NOT EXISTS patient_accounts (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    phone_last4 TEXT,
    patient_id TEXT REFERENCES patients(id) ON DELETE SET NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patient_accounts_patient ON patient_accounts(patient_id);

CREATE TABLE IF NOT EXISTS portal_sessions (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES patient_accounts(id) ON DELETE CASCADE,
    patient_id TEXT REFERENCES patients(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_portal_sessions_expiry ON portal_sessions(expires_at);

CREATE TABLE IF NOT EXISTS slots (
    id TEXT PRIMARY KEY,
    doctor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_at TEXT NOT NULL,
    appointment_type TEXT NOT NULL CHECK(appointment_type IN ('门诊','检查')),
    capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 100),
    booked INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(doctor_id, starts_at, appointment_type)
);

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES patient_accounts(id) ON DELETE SET NULL,
    doctor_id TEXT NOT NULL REFERENCES users(id),
    slot_id TEXT NOT NULL REFERENCES slots(id),
    scheduled_at TEXT NOT NULL,
    appointment_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked'
        CHECK(status IN ('booked','checked_in','completed','cancelled','no_show')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES patient_accounts(id) ON DELETE SET NULL,
    doctor_id TEXT REFERENCES users(id),
    appointment_id TEXT REFERENCES appointments(id) ON DELETE SET NULL,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','public','hidden')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_doctor ON feedback(doctor_id);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    total INTEGER NOT NULL DEFAULT 0,
    imported INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    detail_json TEXT NOT NULL DEFAULT '{}',
    preview_json TEXT NOT NULL DEFAULT '{}',
    mapping_json TEXT NOT NULL DEFAULT '{}',
    file_hash TEXT NOT NULL DEFAULT '',
    sheet_name TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_import_batches_created ON import_batches(created_at);
"""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_predictions_v3(conn: sqlite3.Connection, target: Path) -> bool:
    """Rebuild ``predictions`` so manual rows can carry NULL model fields.

    SQLite has no ``ALTER COLUMN``; the only way to drop the NOT NULL
    constraints is a table rebuild.  The child table ``clinical_reviews``
    references ``predictions(id)`` by name, so the old table must NOT be
    renamed (that rewrites the child's FK clause to the new name).  Instead:
    create the replacement, copy rows, drop the old table, then rename the
    replacement back to ``predictions``.

    Returns True when a migration ran.
    """
    columns = _table_columns(conn, "predictions")
    if not columns or "origin" in columns:
        return False
    # A file copy is the approved rollback point; a failure to copy is
    # logged by the caller but must not silently skip the migration.
    try:
        from .backup import backup_database
        from .config import DATABASE_BACKUP_DIR

        backup_database(DATABASE_BACKUP_DIR, source_path=target)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[database] 迁移前备份失败（继续，事务内失败会回滚）：{exc}")

    # foreign_keys can only be toggled outside a transaction.
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("CREATE TABLE predictions_new " + _PREDICTIONS_COLUMNS)
        conn.execute(
            """INSERT INTO predictions_new
               (id,encounter_id,patient_id,actor_id,input_json,result_json,probability,
                risk_level,model_version,model_hash,input_fingerprint,status,predicted_at,origin)
               SELECT id,encounter_id,patient_id,actor_id,input_json,result_json,probability,
                      risk_level,model_version,model_hash,input_fingerprint,status,predicted_at,
                      'model'
               FROM predictions"""
        )
        conn.execute("DROP TABLE predictions")
        conn.execute("ALTER TABLE predictions_new RENAME TO predictions")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_encounter ON predictions(encounter_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_patient ON predictions(patient_id)"
        )
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            detail = ", ".join(str(dict(row)) for row in broken[:3])
            raise RuntimeError(f"迁移后外键检查失败：{detail}")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"迁移后完整性检查失败：{integrity}")
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    return True


def _migrate_import_batches_v4(conn: sqlite3.Connection) -> bool:
    """Add the preview/mapping metadata used by the XLSX import flow.

    The columns are additive and nullable by default, so existing completed
    batches remain readable without a table rebuild.
    """
    columns = _table_columns(conn, "import_batches")
    if not columns:
        return False
    additions = {
        "preview_json": "TEXT NOT NULL DEFAULT '{}'",
        "mapping_json": "TEXT NOT NULL DEFAULT '{}'",
        "file_hash": "TEXT NOT NULL DEFAULT ''",
        "sheet_name": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
    }
    changed = False
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE import_batches ADD COLUMN {name} {declaration}")
            changed = True
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_import_batches_hash ON import_batches(file_hash)"
    )
    return changed


def initialize_database(path: Path | None = None) -> Path:
    target = Path(path or database_path())
    key = str(target)
    with _INIT_LOCK:
        if key in _INITIALIZED and target.exists():
            return target
        conn = connect(target)
        try:
            conn.executescript(_SCHEMA)
            _migrate_predictions_v3(conn, target)
            _migrate_import_batches_v4(conn)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        finally:
            conn.close()
        _INITIALIZED.add(key)
    return target


def ensure_initialized() -> Path:
    path = database_path()
    if str(path) in _INITIALIZED and path.exists():
        return path
    return initialize_database(path)


def reset_initialization_cache() -> None:
    """Used by tests when AKI_DB_PATH changes at runtime."""
    with _INIT_LOCK:
        _INITIALIZED.clear()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_load(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def record_audit(
    conn: sqlite3.Connection,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    detail: Any = None,
    ip: str | None = None,
) -> str:
    event_id = new_id("AUD")
    conn.execute(
        """INSERT INTO audit_events
           (id,actor_type,actor_id,action,entity_type,entity_id,detail_json,ip,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            actor_type,
            actor_id,
            action,
            entity_type,
            entity_id,
            json_dump(detail or {}),
            ip,
            utc_now(),
        ),
    )
    return event_id
