# -*- coding: utf-8 -*-
"""Database-backed authentication, sessions, CSRF and account management."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from . import database as db
from .auth import (
    AuthConfigError,
    AuthTokenError,
    hash_password,
    load_auth_config,
    verify_password,
)

SESSION_TTL_HOURS_DEFAULT = 12
SESSION_TTL_REMEMBER_DAYS_DEFAULT = 7
SESSION_TTL_SECONDS = SESSION_TTL_HOURS_DEFAULT * 3600
REMEMBER_TTL_SECONDS = SESSION_TTL_REMEMBER_DAYS_DEFAULT * 24 * 3600
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCK_SECONDS = 15 * 60
PASSWORD_MIN_LENGTH = 12


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user_id(username: str) -> str:
    return "U-" + hashlib.sha256(username.lower().encode("utf-8")).hexdigest()[:12].upper()


def bootstrap_users_from_config() -> int:
    """Import legacy auth_config accounts once when the database has no users."""
    db.ensure_initialized()
    with db.reader() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return 0
    try:
        config = load_auth_config()
    except AuthConfigError:
        return 0
    records = config.get("users", {})
    if not isinstance(records, dict):
        return 0
    inserted = 0
    with db.transaction(immediate=True) as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return 0
        now = db.utc_now()
        for username, record in records.items():
            if not isinstance(username, str) or not isinstance(record, dict):
                continue
            role = record.get("role")
            password_hash = record.get("password_hash")
            if role not in {"admin", "doctor"} or not isinstance(password_hash, str):
                continue
            conn.execute(
                """INSERT OR IGNORE INTO users
                   (id,username,display_name,role,password_hash,active,must_change_password,
                    created_at,updated_at,last_login_at)
                   VALUES(?,?,?,?,?,1,0,?,?,NULL)""",
                (_user_id(username), username, username, role, password_hash, now, now),
            )
            inserted += 1
    return inserted


def is_configured() -> bool:
    bootstrap_users_from_config()
    with db.reader() as conn:
        return bool(
            conn.execute("SELECT 1 FROM users WHERE active=1 LIMIT 1").fetchone()
        )


def public_user(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "must_change_password": bool(row["must_change_password"]),
    }


def get_user(user_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    """Return one account. Session checks use the active-only default."""
    with db.reader() as conn:
        sql = "SELECT * FROM users WHERE id=?"
        if not include_inactive:
            sql += " AND active=1"
        row = conn.execute(sql, (user_id,)).fetchone()
        return db.row_to_dict(row)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    """Verify a DB account. Unknown users still pay a PBKDF2 cost."""
    bootstrap_users_from_config()
    from .auth import _DUMMY_HASH  # shared dummy hash avoids timing enumeration

    with db.transaction(immediate=True) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1",
            (username,),
        ).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        now = db.utc_now()
        conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, row["id"]))
        return public_user(row)


def _check_throttle(conn: Any, key: str) -> bool:
    now = int(time.time())
    row = conn.execute(
        "SELECT * FROM login_throttle WHERE throttle_key=?", (key,)
    ).fetchone()
    if row is None:
        return False
    if int(row["locked_until"]) > now:
        return True
    if now - int(row["window_start"]) > LOGIN_WINDOW_SECONDS:
        conn.execute("DELETE FROM login_throttle WHERE throttle_key=?", (key,))
        return False
    return int(row["failures"]) >= MAX_LOGIN_FAILURES


def login_rate_limited(key: str) -> bool:
    with db.reader() as conn:
        return _check_throttle(conn, key)


def record_login_failure(key: str) -> None:
    now = int(time.time())
    with db.transaction(immediate=True) as conn:
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


def clear_login_failures(key: str) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM login_throttle WHERE throttle_key=?", (key,))


def create_session(
    user: dict[str, Any],
    ttl_seconds: int,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str, int]:
    """Create an opaque session. Returns (token, csrf_token, expires_epoch)."""
    token = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    session_id = db.new_id("S")
    expires = int(time.time()) + max(60, int(ttl_seconds))
    with db.transaction(immediate=True) as conn:
        conn.execute(
            """INSERT INTO sessions
               (id,user_id,token_hash,csrf_hash,created_at,expires_at,revoked_at,ip,user_agent)
               VALUES(?,?,?,?,?,?,NULL,?,?)""",
            (
                session_id,
                user["id"],
                _digest(token),
                _digest(csrf),
                db.utc_now(),
                expires,
                ip,
                (user_agent or "")[:300],
            ),
        )
    return token, csrf, expires


def read_session(token: str) -> tuple[dict[str, Any], str]:
    """Resolve an opaque cookie. Returns (public_user, csrf_hash)."""
    if not token or len(token) > 256:
        raise AuthTokenError("会话格式无效")
    with db.transaction(immediate=True) as conn:
        row = conn.execute(
            """SELECT s.*,u.username,u.display_name,u.role,u.active,u.must_change_password
               FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=?""",
            (_digest(token),),
        ).fetchone()
        if row is None:
            raise AuthTokenError("会话无效")
        if int(row["expires_at"]) <= int(time.time()):
            conn.execute("UPDATE sessions SET revoked_at=? WHERE id=?", (db.utc_now(), row["id"]))
            raise AuthTokenError("会话已过期")
        if row["revoked_at"] is not None or not row["active"]:
            raise AuthTokenError("会话已失效")
        user = {
            "id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "must_change_password": bool(row["must_change_password"]),
        }
        return user, row["csrf_hash"]


def revoke_session(token: str) -> None:
    if not token:
        return
    with db.transaction() as conn:
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
            (db.utc_now(), _digest(token)),
        )


def verify_csrf(csrf_hash: str, header_token: str | None, cookie_token: str | None) -> bool:
    if not header_token or not cookie_token:
        return False
    if not hmac.compare_digest(header_token, cookie_token):
        return False
    return hmac.compare_digest(_digest(header_token), csrf_hash)


def cleanup_expired() -> None:
    now = int(time.time())
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at<?", (now - 86400,))
        conn.execute("DELETE FROM portal_sessions WHERE expires_at<?", (now - 86400,))


def list_users() -> list[dict[str, Any]]:
    with db.reader() as conn:
        rows = conn.execute(
            """SELECT id,username,display_name,role,active,must_change_password,
                      created_at,updated_at,last_login_at
               FROM users ORDER BY role,username"""
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(
    *,
    actor_id: str,
    username: str,
    display_name: str,
    role: str,
    password: str,
    must_change_password: bool = True,
    ip: str | None = None,
) -> dict[str, Any]:
    if role not in {"admin", "doctor"}:
        raise ValueError("角色无效")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"密码至少 {PASSWORD_MIN_LENGTH} 个字符")
    user_id = _user_id(username)
    now = db.utc_now()
    with db.transaction(immediate=True) as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE username=? COLLATE NOCASE", (username,)
        ).fetchone():
            raise ValueError("账号已存在")
        conn.execute(
            """INSERT INTO users
               (id,username,display_name,role,password_hash,active,must_change_password,
                created_at,updated_at,last_login_at)
               VALUES(?,?,?,?,?,1,?,?,?,NULL)""",
            (
                user_id,
                username,
                display_name or username,
                role,
                hash_password(password),
                1 if must_change_password else 0,
                now,
                now,
            ),
        )
        db.record_audit(
            conn, actor_type="user", actor_id=actor_id, action="user_create",
            entity_type="user", entity_id=user_id,
            detail={"username": username, "role": role}, ip=ip,
        )
    return get_user(user_id) or {}


def update_user(
    *,
    actor_id: str,
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    password: str | None = None,
    must_change_password: bool | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    with db.transaction(immediate=True) as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("账号不存在")
        if role is not None and role not in {"admin", "doctor"}:
            raise ValueError("角色无效")
        if role is not None and role != row["role"]:
            admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
            ).fetchone()[0]
            if row["role"] == "admin" and admins <= 1:
                raise ValueError("不能降级系统内唯一的管理员")
        if active is False:
            if user_id == actor_id:
                raise ValueError("不能停用自己的账号")
            if row["role"] == "admin" and int(row["active"]) == 1:
                admins = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1"
                ).fetchone()[0]
                if admins <= 1:
                    raise ValueError("不能停用系统内唯一的管理员")
        password_hash = row["password_hash"]
        if password is not None:
            if len(password) < PASSWORD_MIN_LENGTH:
                raise ValueError(f"密码至少 {PASSWORD_MIN_LENGTH} 个字符")
            password_hash = hash_password(password)
            # Existing sessions must be revoked on password reset.
            conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (db.utc_now(), user_id),
            )
        conn.execute(
            """UPDATE users SET display_name=?,role=?,active=?,password_hash=?,
                   must_change_password=?,updated_at=? WHERE id=?""",
            (
                row["display_name"] if display_name is None else display_name,
                row["role"] if role is None else role,
                row["active"] if active is None else int(bool(active)),
                password_hash,
                row["must_change_password"] if must_change_password is None
                else int(bool(must_change_password)),
                db.utc_now(),
                user_id,
            ),
        )
        if active is False:
            conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (db.utc_now(), user_id),
            )
        db.record_audit(
            conn, actor_type="user", actor_id=actor_id, action="user_update",
            entity_type="user", entity_id=user_id,
            detail={"role": role, "active": active, "password_reset": password is not None},
            ip=ip,
        )
    return get_user(user_id, include_inactive=True) or {}


def change_password(
    user_id: str, current_password: str, new_password: str, *,
    keep_session_token: str | None = None, ip: str | None = None,
) -> None:
    if len(new_password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"密码至少 {PASSWORD_MIN_LENGTH} 个字符")
    with db.transaction(immediate=True) as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None or not verify_password(current_password, row["password_hash"]):
            raise ValueError("当前密码错误")
        conn.execute(
            """UPDATE users SET password_hash=?,must_change_password=0,updated_at=?
               WHERE id=?""",
            (hash_password(new_password), db.utc_now(), user_id),
        )
        conn.execute(
            """UPDATE sessions SET revoked_at=?
               WHERE user_id=? AND revoked_at IS NULL AND token_hash<>?""",
            (db.utc_now(), user_id, _digest(keep_session_token or "")),
        )
        db.record_audit(
            conn, actor_type="user", actor_id=user_id, action="password_change",
            entity_type="user", entity_id=user_id, ip=ip,
        )
