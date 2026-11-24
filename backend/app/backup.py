# -*- coding: utf-8 -*-
"""Database backup and restore helpers for the clinical SQLite store."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .database import connect, database_path, initialize_database


def _consistent_copy(source: Path, target: Path) -> None:
    """Copy a SQLite database through the backup API.

    A plain file copy of the main database can miss committed pages that still
    live in ``-wal``.  The backup API reads the main file and WAL together and
    writes a standalone destination, so the result is consistent even when the
    source has not checkpointed yet.
    """
    src = connect(source)
    target.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    dest = sqlite3.connect(target)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()


def backup_database(target_dir: Path | None = None, *, source_path: Path | None = None) -> Path:
    source = Path(source_path or database_path())
    if not source.exists():
        initialize_database(source)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(target_dir or (source.parent / "backups")) / f"clinical-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    _consistent_copy(source, target)
    # Integrity-check the produced snapshot instead of trusting file size.
    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"备份完整性检查失败: {result}")
    finally:
        check.close()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
    return target


def restore_database(source: Path, *, confirm: bool = False) -> Path:
    if not confirm:
        raise ValueError("恢复数据库需要显式确认")
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    check = sqlite3.connect(source)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("备份文件完整性检查失败")
    finally:
        check.close()
    digest_file = source.with_suffix(".sha256")
    if digest_file.exists():
        expected = digest_file.read_text(encoding="utf-8").strip().lower()
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if not expected or actual != expected:
            raise RuntimeError("备份文件 SHA-256 校验失败")
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        emergency = target.with_name(
            target.name + ".pre-restore-" + datetime.now().strftime("%Y%m%d%H%M%S")
        )
        try:
            # Include committed WAL pages in the emergency copy; copying only
            # the main file would silently discard the most recent writes.
            _consistent_copy(target, emergency)
        except sqlite3.DatabaseError:
            # A stale or corrupt sidecar must not block the requested restore.
            # Keep a best-effort main-file copy so the operator still has it.
            shutil.copy2(target, emergency)
    temp = target.with_name(target.name + ".restoring")
    temp.unlink(missing_ok=True)
    _consistent_copy(source, temp)
    temp.replace(target)
    # WAL/SHM belong to the replaced main file; leaving them would replay the
    # old log into the restored database on the next open.
    for suffix in ("-wal", "-shm"):
        sidecar = target.with_name(target.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    initialize_database(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="创建一致性备份")
    backup.add_argument("--target-dir", type=Path)
    restore = sub.add_parser("restore", help="从备份恢复（危险操作）")
    restore.add_argument("source", type=Path)
    restore.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if args.command == "backup":
        print(backup_database(args.target_dir))
        return 0
    print(restore_database(args.source, confirm=args.confirm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
