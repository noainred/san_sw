"""시크릿 해석(로컬 암호화 / 외부 Vault).

스위치 비밀번호 값이:
- "vault:<field>" 형태면 HashiCorp Vault KV v2에서 가져온다(SECRET_BACKEND=vault).
- 그 외에는 로컬 암호화(crypto)로 복호화한다.

정직성 메모: Vault 서버가 없는 환경이라 Vault 경로는 미검증이다(httpx 호출
구조만 작성). VAULT_ADDR/TOKEN 미설정 시 명확히 실패를 반환한다.
"""
from __future__ import annotations

import logging

import httpx

from . import crypto
from .config import HTTP_TIMEOUT, VAULT_ADDR, VAULT_KV_PATH, VAULT_TOKEN

log = logging.getLogger("sansw.secrets")
VAULT_PREFIX = "vault:"


def _vault_get(field: str) -> str | None:
    if not VAULT_ADDR or not VAULT_TOKEN:
        log.warning("Vault 미설정(VAULT_ADDR/TOKEN) — 시크릿 해석 불가")
        return None
    url = f"{VAULT_ADDR.rstrip('/')}/v1/{VAULT_KV_PATH.lstrip('/')}"
    try:
        resp = httpx.get(
            url, headers={"X-Vault-Token": VAULT_TOKEN}, timeout=HTTP_TIMEOUT
        )
        resp.raise_for_status()
        # KV v2: {"data": {"data": {field: value}}}
        data = resp.json().get("data", {}).get("data", {})
        return data.get(field)
    except httpx.HTTPError as exc:
        log.warning("Vault 조회 실패: %s", exc)
        return None


def resolve_password(value: str | None) -> str | None:
    """저장된 비밀번호 값을 실제 평문으로 해석."""
    if not value:
        return value
    if value.startswith(VAULT_PREFIX):
        return _vault_get(value[len(VAULT_PREFIX):])
    return crypto.decrypt(value)
