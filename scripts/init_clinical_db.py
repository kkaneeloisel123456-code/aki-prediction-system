# -*- coding: utf-8 -*-
"""Initialize the clinical SQLite database, import the local admin, and take a first backup."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import database as db  # noqa: E402
from app.auth_service import bootstrap_users_from_config, list_users  # noqa: E402
from app.backup import backup_database  # noqa: E402
from app.config import DATABASE_BACKUP_DIR  # noqa: E402


def main() -> int:
    path = db.ensure_initialized()
    imported = bootstrap_users_from_config()
    users = list_users()
    DATABASE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(DATABASE_BACKUP_DIR.glob("clinical-*.db"))
    first_backup = None
    if not backups and not any(u.get("last_login_at") for u in users):
        first_backup = backup_database(DATABASE_BACKUP_DIR)
    print(f"database: {path}")
    print(f"schema_version: {db.SCHEMA_VERSION}")
    print(f"bootstrap_imported: {imported}")
    print(f"active_users: {sum(1 for u in users if u.get('active'))}")
    print(f"backup_dir: {DATABASE_BACKUP_DIR}")
    if first_backup:
        print(f"initial_backup: {first_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
