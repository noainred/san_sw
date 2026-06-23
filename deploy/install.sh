#!/usr/bin/env bash
# san_sw systemd 설치 스크립트 (Linux)
# 동작: /opt/san_sw 에 복사 → venv 생성 → 의존성 설치 → systemd 등록/기동.
# 사용: sudo bash deploy/install.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/san_sw}"
SVC_USER="${SVC_USER:-sansw}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[install] 소스: $SRC_DIR"
echo "[install] 설치 경로: $APP_DIR  (서비스 계정: $SVC_USER)"

# 1) 전용 시스템 계정
if ! id "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$SVC_USER"
  echo "[install] 계정 생성: $SVC_USER"
fi

# 2) 파일 복사(.git/.venv/data 제외)
mkdir -p "$APP_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '.git' --exclude '.venv' --exclude 'data' \
    --exclude '__pycache__' --exclude '.pytest_cache' \
    "$SRC_DIR"/ "$APP_DIR"/
else
  cp -r "$SRC_DIR"/. "$APP_DIR"/
  rm -rf "$APP_DIR/.git" "$APP_DIR/.venv"
fi

# 3) venv + 의존성
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 4) 데이터 디렉터리 + .env(없으면 예시 복사)
mkdir -p "$APP_DIR/data"
[ -f "$APP_DIR/.env" ] || cp "$APP_DIR/.env.example" "$APP_DIR/.env"
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env" || true

# 5) systemd 등록
cp "$APP_DIR/deploy/san_sw.service" /etc/systemd/system/san_sw.service
systemctl daemon-reload
systemctl enable --now san_sw

echo "[install] 완료. 상태 확인: systemctl status san_sw"
echo "[install] 로그: journalctl -u san_sw -f"
echo "[install] 접속: http://<서버IP>:8000"
echo "[install] 설정 변경: $APP_DIR/.env  수정 후  systemctl restart san_sw"
