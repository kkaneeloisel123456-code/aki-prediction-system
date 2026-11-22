#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create or update local AKI login accounts.

Examples:
  python scripts/init_auth.py --generate-password
  python scripts/init_auth.py --username doctor --role doctor
  python scripts/init_auth.py --username admin --reset-password

The generated JSON contains password hashes only and is ignored by Git.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import database as db  # noqa: E402
from backend.app.auth import hash_password  # noqa: E402
from backend.app.config import AUTH_CONFIG_FILE  # noqa: E402

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PASSWORD_MIN_LENGTH = 12


def update_database_account(username: str, role: str, password: str) -> bool:
    """Update the live database account when one already exists.

    Returns True when the database was authoritative (it already had users),
    so the legacy JSON file is no longer written.
    """
    db.ensure_initialized()
    with db.reader() as conn:
        if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return False
        existing = conn.execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)
        ).fetchone()
    with db.transaction(immediate=True) as conn:
        now = db.utc_now()
        if existing is None:
            user_id = "U-" + hashlib.sha256(
                username.lower().encode("utf-8")
            ).hexdigest()[:12].upper()
            conn.execute(
                """INSERT INTO users
                   (id,username,display_name,role,password_hash,active,
                    must_change_password,created_at,updated_at,last_login_at)
                   VALUES(?,?,?,?,?,1,0,?,?,NULL)""",
                (user_id, username, username, role, hash_password(password), now, now),
            )
        else:
            conn.execute(
                """UPDATE users SET password_hash=?,must_change_password=0,
                       updated_at=? WHERE id=?""",
                (hash_password(password), now, existing["id"]),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (now, existing["id"]),
            )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin", help="账号，默认 admin")
    parser.add_argument("--role", choices=("admin", "doctor"), default="admin")
    parser.add_argument("--password", help="密码；不建议在共享终端中使用此参数")
    parser.add_argument("--generate-password", action="store_true", help="生成随机密码并打印一次")
    parser.add_argument("--reset-password", action="store_true", help="允许更新已存在账号")
    parser.add_argument("--config", type=Path, default=AUTH_CONFIG_FILE, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not USERNAME_RE.fullmatch(args.username):
        raise SystemExit("账号只能包含字母、数字、点、下划线和连字符，长度 1–64。")
    if args.password is not None and args.generate_password:
        raise SystemExit("--password 与 --generate-password 不能同时使用。")

    generated = False
    if args.generate_password:
        password = secrets.token_urlsafe(12)
        generated = True
    elif args.password is not None:
        password = args.password
    else:
        password = getpass.getpass(f"请输入新密码（至少 {PASSWORD_MIN_LENGTH} 个字符）：")
        confirmation = getpass.getpass("请再次输入：")
        if password != confirmation:
            raise SystemExit("两次输入的密码不一致。")
    if not PASSWORD_MIN_LENGTH <= len(password) <= 1024:
        raise SystemExit(f"密码长度必须为 {PASSWORD_MIN_LENGTH}–1024 个字符。")

    # Once the database has accounts, the JSON file is only a legacy bootstrap
    # source and is ignored. Write the reset to the live database instead.
    if update_database_account(args.username, args.role, password):
        print(f"已更新数据库账号：{args.username}（{args.role}）")
        if generated:
            print(f"初始密码（仅显示一次）：{password}")
        print("明文密码未写入任何文件。旧会话已失效，重启后端后登录生效。")
        return 0

    path = args.config.expanduser().resolve()
    data = {"version": 1, "secret_key": secrets.token_urlsafe(48), "users": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"无法读取现有配置：{exc}") from exc
        if not isinstance(data.get("users"), dict) or not isinstance(data.get("secret_key"), str):
            raise SystemExit("现有配置格式无效，请先备份并修复该文件。")
    if args.username in data["users"] and not args.reset_password:
        raise SystemExit("账号已存在；如需重置密码，请添加 --reset-password。")

    data["version"] = 1
    data["users"][args.username] = {
        "role": args.role,
        "password_hash": hash_password(password),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)

    print(f"已配置账号：{args.username}（{args.role}）")
    print(f"配置文件：{path}")
    if generated:
        print(f"初始密码（仅显示一次）：{password}")
    print("明文密码未写入配置文件。重启后端后登录生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
