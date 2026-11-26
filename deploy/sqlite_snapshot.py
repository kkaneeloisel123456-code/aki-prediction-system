"""Run inside a Docker helper, with the application stopped during restore.

Uses only the standard library, so it also works with the old application image.
No patient rows or authentication data are printed.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import sys


def validate(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check failed")


def snapshot(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() or target.with_suffix(".sha256").exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
    validate(target)
    target.with_suffix(".sha256").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + "\n", encoding="ascii"
    )


def restore(source: Path, target: Path, emergency: Path) -> None:
    validate(source)
    expected = source.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Snapshot SHA-256 mismatch")
    if target.is_file():
        # Preserve data written by a failed migration as a separate recovery file.
        try:
            snapshot(target, emergency)
        except sqlite3.DatabaseError:
            # A broken migration must not prevent restoring a verified snapshot.
            shutil.copyfile(target, emergency.with_suffix(".corrupt"))
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(target) + suffix)
                if sidecar.exists():
                    shutil.copyfile(sidecar, Path(str(emergency) + suffix))
    temporary = target.with_name(target.name + ".deploy-restoring")
    if temporary.exists():
        raise FileExistsError(temporary)
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(temporary)) as dst:
            src.backup(dst)
    validate(temporary)
    os.replace(temporary, target)
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)


def clone(source: Path, target_dir: Path) -> None:
    validate(source)
    if (target_dir / "clinical.db").exists():
        raise FileExistsError(target_dir / "clinical.db")
    shutil.copyfile(source, target_dir / "clinical.db")
    auth = source.parent.parent / "auth_config.json"
    if auth.is_file():
        shutil.copyfile(auth, target_dir / "auth_config.json")
    # The helper runs as root for a newly created empty Docker volume.
    os.chown(target_dir, 10001, 10001)
    for path in target_dir.iterdir():
        os.chown(path, 10001, 10001)


def prune(directory: Path, keep: int) -> None:
    # Only prune snapshots produced by this deployer, never application backups.
    for pattern, limit in (("release-*.db", max(keep, 1)), ("preflight-*.db", 2)):
        files = sorted(directory.glob(pattern), reverse=True)
        for path in files[limit:]:
            path.unlink()
            path.with_suffix(".sha256").unlink(missing_ok=True)


if __name__ == "__main__":
    os.umask(0o077)
    action, *args = sys.argv[1:]
    if action == "snapshot":
        snapshot(Path(args[0]), Path(args[1]))
    elif action == "restore":
        restore(Path(args[0]), Path(args[1]), Path(args[2]))
    elif action == "clone":
        clone(Path(args[0]), Path(args[1]))
    elif action == "prune":
        prune(Path(args[0]), int(args[1]))
    else:
        raise SystemExit("Unknown SQLite helper action")
