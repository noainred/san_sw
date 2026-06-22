"""비밀번호 등 비밀값의 대칭키 암호화(Fernet).

저장 형식: 평문이 아니라 "enc:<token>" 형태로 DB에 저장한다.
- decrypt()는 "enc:" 접두어가 없으면 평문으로 간주(하위호환).
- 키 출처: SANSW_SECRET_KEY(환경변수) > data/secret.key(자동 생성).

정직성 메모: 키 파일과 DB가 같은 호스트에 있으면, 둘 다 접근 가능한 공격자는
복호화할 수 있다. 즉 '평문 저장보다 낫다(DB만 유출 시 안전)'는 수준이며,
완전한 비밀 보호가 필요하면 외부 시크릿 매니저(Vault/KMS) 연동이 필요하다.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import SECRET_KEY, SECRET_KEY_FILE

log = logging.getLogger("sansw.crypto")

ENC_PREFIX = "enc:"
_fernet: Fernet | None = None


def _derive_key(raw: bytes) -> bytes:
    """임의 문자열을 Fernet 키(urlsafe base64 32B)로 파생."""
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())


def _load_key() -> bytes:
    if SECRET_KEY:
        candidate = SECRET_KEY.encode()
        try:
            Fernet(candidate)  # 이미 올바른 Fernet 키인지 검사
            return candidate
        except (ValueError, TypeError):
            return _derive_key(candidate)
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_FILE.write_bytes(key)
    try:
        os.chmod(SECRET_KEY_FILE, 0o600)
    except OSError:
        pass
    log.info("암호화 키 생성: %s (권한 0600)", SECRET_KEY_FILE)
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    if not plaintext:
        return plaintext
    if plaintext.startswith(ENC_PREFIX):
        return plaintext  # 이미 암호화됨(중복 암호화 방지)
    token = _get_fernet().encrypt(plaintext.encode()).decode()
    return ENC_PREFIX + token


def decrypt(value: str | None) -> str | None:
    if not value:
        return value
    if not value.startswith(ENC_PREFIX):
        return value  # 평문(하위호환)
    token = value[len(ENC_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        log.warning("비밀번호 복호화 실패(키 불일치 가능성)")
        return None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(ENC_PREFIX)
