"""인증 + RBAC.

- 비밀번호: PBKDF2-HMAC-SHA256(표준 라이브러리) 해시 저장.
- 세션 토큰: Fernet 봉인(만료 내장) — crypto 모듈 재사용.
- 역할: viewer < operator < admin.
- AUTH_ENABLED=0(기본)이면 보호를 적용하지 않고 가상 admin으로 동작
  (기존 동작/테스트 호환). 1이면 토큰 필수.
"""
from __future__ import annotations

import hashlib
import os
import secrets as _secrets

from fastapi import Depends, Header, HTTPException

from . import crypto
from . import repository as repo
from .config import (
    AUTH_ENABLED,
    BOOTSTRAP_ADMIN_PASS,
    BOOTSTRAP_ADMIN_USER,
    SESSION_TTL,
)

_ROLES = {"viewer": 0, "operator": 1, "admin": 2}
_PBKDF2_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return f"pbkdf2${_PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return _secrets.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def make_token(username: str, role: str) -> str:
    return crypto.make_session_token(f"{username}:{role}")


def decode_token(token: str) -> dict | None:
    payload = crypto.read_session_token(token, SESSION_TTL)
    if not payload or ":" not in payload:
        return None
    username, role = payload.split(":", 1)
    return {"username": username, "role": role}


def bootstrap_admin() -> None:
    """인증 활성 + 사용자 없음이면 기본 관리자 생성."""
    if not AUTH_ENABLED:
        return
    if repo.count_users() > 0:
        return
    repo.create_user(
        BOOTSTRAP_ADMIN_USER, hash_password(BOOTSTRAP_ADMIN_PASS), "admin"
    )


def authenticate(username: str, password: str) -> dict | None:
    user = repo.get_user(username)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return {"username": user["username"], "role": user["role"]}


# ---------------------------------------------------------- FastAPI 의존성

async def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not AUTH_ENABLED:
        return {"username": "(auth-disabled)", "role": "admin"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 필요(Bearer 토큰)")
    user = decode_token(authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(status_code=401, detail="토큰 무효/만료")
    return user


def require_role(minimum: str):
    """최소 역할 이상을 요구하는 의존성 팩토리."""
    need = _ROLES.get(minimum, 99)

    async def _dep(user: dict = Depends(current_user)) -> dict:
        if _ROLES.get(user.get("role"), -1) < need:
            raise HTTPException(
                status_code=403, detail=f"권한 부족(필요: {minimum} 이상)"
            )
        return user

    return _dep
