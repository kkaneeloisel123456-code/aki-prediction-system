# -*- coding: utf-8 -*-
"""Local account authentication and signed session cookies.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes. Session tokens contain no
password or other sensitive data and are signed with the local config secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from .config import AUTH_CONFIG_FILE

_PBKDF2_ITERATIONS = 310_000
_RATE_MAX_FAILURES = 5
_RATE_WINDOW_SECONDS = 5 * 60
_RATE_LOCK_SECONDS = 5 * 60


class AuthConfigError(RuntimeError):
    """The local authentication config is absent or invalid."""


class AuthTokenError(RuntimeError):
    """A session cookie is absent, malformed, expired, or invalid."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    if not isinstance(password, str) or not 8 <= len(password) <= 1024:
        raise ValueError("密码长度必须为 8–1024 个字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, expected_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        if not 100_000 <= iterations <= 5_000_000:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(expected_raw)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


_config_lock = threading.Lock()
_config_cache: dict[str, Any] = {"signature": None, "data": None}


def load_auth_config(path: Path | None = None) -> dict[str, Any]:
    config_path = Path(path or AUTH_CONFIG_FILE)
    try:
        stat = config_path.stat()
        signature = (config_path.resolve(), stat.st_mtime_ns, stat.st_size)
    except OSError as exc:
        raise AuthConfigError("登录功能尚未初始化，请先运行 scripts/init_auth.py") from exc

    with _config_lock:
        if _config_cache["signature"] == signature:
            return _config_cache["data"]
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthConfigError("登录配置文件无法读取，请重新初始化授权账号") from exc
        _validate_config(data)
        _config_cache["signature"] = signature
        _config_cache["data"] = data
        return data


def _validate_config(data: Any) -> None:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise AuthConfigError("登录配置版本无效")
    secret = data.get("secret_key")
    if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
        raise AuthConfigError("登录会话密钥无效")
    users = data.get("users")
    if not isinstance(users, dict) or not users:
        raise AuthConfigError("尚未配置授权账号")
    for username, record in users.items():
        if not isinstance(username, str) or not username:
            raise AuthConfigError("授权账号名称无效")
        if not isinstance(record, dict):
            raise AuthConfigError("授权账号记录无效")
        if record.get("role") not in {"admin", "doctor"}:
            raise AuthConfigError("授权账号角色无效")
        if not isinstance(record.get("password_hash"), str):
            raise AuthConfigError("授权账号密码哈希无效")


def public_user(record: dict[str, Any]) -> dict[str, str]:
    return {"username": record["username"], "role": record["role"]}


# A dummy verification makes unknown usernames perform similar password work.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def authenticate(username: str, password: str) -> dict[str, str] | None:
    config = load_auth_config()
    record = config["users"].get(username)
    if record is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, record["password_hash"]):
        return None
    return public_user({"username": username, "role": record["role"]})


def create_session_token(user: dict[str, str], ttl_seconds: int) -> str:
    if ttl_seconds <= 0:
        raise ValueError("会话有效期必须大于零")
    config = load_auth_config()
    now = int(time.time())
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    body = _b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        config["secret_key"].encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{body}.{_b64encode(signature)}"


def read_session_token(token: str) -> dict[str, str]:
    config = load_auth_config()
    try:
        body, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            config["secret_key"].encode("utf-8"), body.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64decode(supplied_signature), expected):
            raise AuthTokenError("会话签名无效")
        payload = json.loads(_b64decode(body).decode("utf-8"))
        if int(payload["exp"]) <= int(time.time()):
            raise AuthTokenError("会话已过期")
        username = payload["sub"]
        role = payload["role"]
        record = config["users"].get(username)
        if record is None or record["role"] != role:
            raise AuthTokenError("授权账号已变化")
        return public_user({"username": username, "role": role})
    except AuthTokenError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthTokenError("会话格式无效") from exc


_rate_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def is_rate_limited(key: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        if _locked_until.get(key, 0) > now:
            return True
        _locked_until.pop(key, None)
        recent = [t for t in _failures.get(key, []) if now - t < _RATE_WINDOW_SECONDS]
        if recent:
            _failures[key] = recent
        else:
            _failures.pop(key, None)
        return False


def record_login_failure(key: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        recent = [t for t in _failures.get(key, []) if now - t < _RATE_WINDOW_SECONDS]
        recent.append(now)
        if len(recent) >= _RATE_MAX_FAILURES:
            _locked_until[key] = now + _RATE_LOCK_SECONDS
            _failures.pop(key, None)
        else:
            _failures[key] = recent


def clear_login_failures(key: str) -> None:
    with _rate_lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset_rate_limits() -> None:
    """Reset in-memory limits (used by isolated tests)."""
    with _rate_lock:
        _failures.clear()
        _locked_until.clear()
