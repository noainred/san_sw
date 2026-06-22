"""애플리케이션 설정.

모든 값은 환경변수로 덮어쓸 수 있다. 소규모(~수십 대) 운영을 가정해
SQLite + 단일 프로세스 폴링 구조를 사용한다.
"""
from __future__ import annotations

import os
from pathlib import Path

# 저장소 루트 (backend/app/config.py -> backend -> repo root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR = Path(os.environ.get("SANSW_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("SANSW_DB_PATH", str(DATA_DIR / "sansw.db")))

# 폴링 주기(초). 0 이하이면 백그라운드 폴러를 끈다(수동 폴링만).
POLL_INTERVAL = int(os.environ.get("SANSW_POLL_INTERVAL", "60"))

# 스위치 HTTP/REST 호출 타임아웃(초)
HTTP_TIMEOUT = float(os.environ.get("SANSW_HTTP_TIMEOUT", "15"))

# 스위치당 시계열 샘플 보관 개수(소규모 가정, 링버퍼처럼 잘라냄)
SAMPLE_RETENTION = int(os.environ.get("SANSW_SAMPLE_RETENTION", "1440"))

# 자동 업그레이드 대상 GitHub 저장소(owner/repo)
GITHUB_REPO = os.environ.get("SANSW_GITHUB_REPO", "noainred/san_sw")

# 업그레이드 적용(apply) 허용 여부. 운영 환경에서 의도치 않은 실행 방지를 위해
# 기본값은 비활성(확인만 가능). "1"로 설정하면 apply 엔드포인트가 동작한다.
ALLOW_UPGRADE_APPLY = os.environ.get("SANSW_ALLOW_UPGRADE_APPLY", "0") == "1"

# 최초 기동 시 DB가 비어 있으면 데모 스위치를 자동 생성한다(UI 확인용).
# 실제 운영 시 "0"으로 끈다.
SEED_DEMO = os.environ.get("SANSW_SEED_DEMO", "1") == "1"

# 비밀번호 암호화 키.
# - SANSW_SECRET_KEY 가 있으면 그것을 사용(Fernet 키이거나 임의 문자열→파생).
# - 없으면 data/secret.key 에 자동 생성(권한 0600).
SECRET_KEY = os.environ.get("SANSW_SECRET_KEY")
SECRET_KEY_FILE = Path(
    os.environ.get("SANSW_SECRET_KEY_FILE", str(DATA_DIR / "secret.key"))
)

# SNMP 기본값(스위치별로 community/port를 username 칸 등에 따로 둘 수도 있음)
SNMP_COMMUNITY = os.environ.get("SANSW_SNMP_COMMUNITY", "public")
SNMP_PORT = int(os.environ.get("SANSW_SNMP_PORT", "161"))
SNMP_TIMEOUT = float(os.environ.get("SANSW_SNMP_TIMEOUT", "5"))

# 인증/RBAC. 기본 비활성(기존 동작·테스트 호환). 1이면 보호 활성화.
AUTH_ENABLED = os.environ.get("SANSW_AUTH_ENABLED", "0") == "1"
SESSION_TTL = int(os.environ.get("SANSW_SESSION_TTL", "28800"))  # 8h
# 최초 기동 시 생성할 기본 관리자(인증 활성 + users 비었을 때만).
BOOTSTRAP_ADMIN_USER = os.environ.get("SANSW_ADMIN_USER", "admin")
BOOTSTRAP_ADMIN_PASS = os.environ.get("SANSW_ADMIN_PASS", "admin")

# 알림 채널. webhook은 generic JSON 또는 Slack incoming-webhook 모두 호환.
ALERT_WEBHOOK_URL = os.environ.get("SANSW_ALERT_WEBHOOK_URL")
ALERT_EVAL_ON_POLL = os.environ.get("SANSW_ALERT_EVAL_ON_POLL", "1") == "1"

# 시크릿 백엔드: local(파일/env) | vault(HashiCorp Vault KV v2)
SECRET_BACKEND = os.environ.get("SANSW_SECRET_BACKEND", "local").lower()
VAULT_ADDR = os.environ.get("SANSW_VAULT_ADDR")
VAULT_TOKEN = os.environ.get("SANSW_VAULT_TOKEN")
VAULT_KV_PATH = os.environ.get("SANSW_VAULT_KV_PATH", "secret/data/san_sw")

FRONTEND_DIR = BASE_DIR / "frontend"
