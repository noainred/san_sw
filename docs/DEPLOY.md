# 배포 / 서비스 실행 가이드

san_sw를 상시 서비스로 띄우는 3가지 방법: **systemd**(권장, 베어메탈/VM),
**Docker**, **docker-compose**. 자동 업그레이드 연동과 리버스 프록시 예시도 포함.

관련 파일:
- `deploy/san_sw.service` — systemd 유닛
- `deploy/install.sh` — systemd 자동 설치
- `deploy/Dockerfile` — 컨테이너 이미지
- `deploy/docker-compose.yml` — compose 배포
- `.env.example` — 환경변수 예시

---

## 1) systemd (권장)

가장 간단한 방법은 설치 스크립트:

```bash
git clone https://github.com/noainred/san_sw.git
cd san_sw
sudo bash deploy/install.sh
```

스크립트가 하는 일:
1. 전용 계정 `sansw` 생성
2. `/opt/san_sw` 로 복사 + `.venv` 생성 + 의존성 설치
3. `/opt/san_sw/.env` 생성(없으면 예시 복사, 권한 600)
4. `san_sw.service` 등록 후 `enable --now`

확인/운영:
```bash
systemctl status san_sw
journalctl -u san_sw -f          # 로그 실시간
sudo nano /opt/san_sw/.env       # 설정 변경
sudo systemctl restart san_sw    # 적용
```

접속: `http://<서버IP>:8000`

> 수동 설치를 원하면 위 단계를 직접 수행하고
> `deploy/san_sw.service`의 `User`/`WorkingDirectory`를 환경에 맞게 수정하세요.

---

## 2) Docker (단일 컨테이너)

```bash
# 이미지 빌드(컨텍스트는 저장소 루트)
docker build -f deploy/Dockerfile -t san_sw:latest .

# 실행(데이터 영속화 + 운영 설정 예시)
docker run -d --name san_sw -p 8000:8000 \
  -v san_sw_data:/app/data \
  -e SANSW_SEED_DEMO=0 \
  -e SANSW_AUTH_ENABLED=1 \
  -e SANSW_ADMIN_PASS='change-me' \
  -e SANSW_SECRET_KEY='set-a-long-random-string' \
  --restart unless-stopped \
  san_sw:latest

docker logs -f san_sw
```

---

## 3) docker-compose

```bash
cd deploy
docker compose up -d --build
docker compose logs -f
docker compose down            # 중지(볼륨 sansw-data는 유지)
```

설정은 `deploy/docker-compose.yml`의 `environment:`에서 조정하거나,
`.env` 파일을 만들고 `env_file` 주석을 해제하세요.

---

## 환경변수

전체 목록과 기본값은 [`.env.example`](../.env.example) 참고. 운영 핵심:

| 변수 | 권장(운영) | 설명 |
|------|-----------|------|
| `SANSW_SEED_DEMO` | `0` | 데모 스위치 자동시드 끄기 |
| `SANSW_SECRET_KEY` | (긴 무작위값) | 비밀번호 암호화 키 고정 |
| `SANSW_AUTH_ENABLED` | `1` | 인증/RBAC 활성화 |
| `SANSW_ADMIN_PASS` | (변경) | 최초 관리자 비밀번호 |
| `SANSW_POLL_INTERVAL` | `60` | 폴링 주기(초) |
| `SANSW_ALERT_WEBHOOK_URL` | (선택) | Slack/Webhook 알림 |

> 인증을 켜면(`SANSW_AUTH_ENABLED=1`) 최초 기동 시 `ADMIN_USER/ADMIN_PASS`로
> 관리자 계정이 1회 생성됩니다. 로그인 후 비밀번호를 바꾸고 추가 계정을 만드세요.

---

## 자동 업그레이드와 서비스 재시작

1. UI "업데이트 확인" 또는 `GET /api/upgrade/check`로 새 버전 확인.
2. 적용 허용 시(`SANSW_ALLOW_UPGRADE_APPLY=1`) `POST /api/upgrade/apply`
   → `scripts/upgrade.sh`가 최신 태그 체크아웃 + 의존성 설치.
3. **새 코드 반영에는 프로세스 재시작 필요.**
   - systemd: `sudo systemctl restart san_sw` (유닛에 `Restart=always` 설정됨)
   - docker: `docker restart san_sw` 또는 새 이미지로 `compose up -d --build`

> 컨테이너 환경에서는 이미지 재빌드/재배포가 더 깔끔합니다.
> 자동 업그레이드(in-place)는 systemd/베어메탈 배포에 적합합니다.

---

## 리버스 프록시(nginx, 선택)

TLS 종단/도메인 연결 예시:

```nginx
server {
    listen 443 ssl;
    server_name sansw.example.com;
    ssl_certificate     /etc/ssl/certs/sansw.crt;
    ssl_certificate_key /etc/ssl/private/sansw.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

---

## Prometheus 스크래핑

`GET /metrics` 노출. 스크래핑 설정 예:

```yaml
scrape_configs:
  - job_name: san_sw
    static_configs:
      - targets: ["sansw.example.com:8000"]
```

---

## 점검 체크리스트
- [ ] `systemctl status san_sw` 또는 `docker ps`에서 running
- [ ] `curl http://localhost:8000/healthz` → `{"status":"ok"}`
- [ ] 웹 접속 + 버전 배지 표시
- [ ] (운영) `SANSW_SEED_DEMO=0`, `SANSW_SECRET_KEY` 고정, 인증 활성
- [ ] 데이터 볼륨/디렉터리 백업 정책
