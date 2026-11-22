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


def backup_database(target_dir: Path | None = None) -> Path:
    source = database_path()
    if not source.exists():
        initialize_database(source)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = Path(target_dir or (source.parent / "backups")) / f"clinical-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    src = connect(source)
    dest = sqlite3.connect(target)
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
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
    target = database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        emergency = target.with_name(
            target.name + ".pre-restore-" + datetime.now().strftime("%Y%m%d%H%M%S")
        )
        shutil.copy2(target, emergency)
    temp = target.with_name(target.name + ".restoring")
    shutil.copy2(source, temp)
    temp.replace(target)
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
