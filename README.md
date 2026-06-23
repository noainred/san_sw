# san_sw — Brocade SAN Switch Manager

전세계 데이터센터에 분산된 **Brocade(브로케이드) SAN 스위치**를 모니터링·관리하는 웹 애플리케이션.

- 리전/데이터센터별 **포트 사용율, 사용중 포트 수, 비어있는(미사용) 포트 수** 집계
- 포트별 **상태/속도/포트타입/WWN** 조회
- **대역폭 사용율(tx/rx %)** — octet 카운터 델타 기반(REST/SNMP), 2회차 폴링부터
- **전역/스위치별 포트 사용율 추이 차트**(무의존 SVG, 시계열)
- **수집 방식 3종**: FOS REST API · SNMP(v2c) · 데모(합성)
- 스위치 등록·삭제·즉시 폴링, 주기 폴링(백그라운드)
- **비밀번호 암호화 저장**(Fernet) — API 응답엔 비노출
- 웹 UI에 **버전 상시 표시** + **업데이트 확인/자동 업그레이드**

### v0.3.0 신규 (운영 기능 10종)
- **포트 에러 카운터**(CRC/enc_out/link_failure/loss_of_sync) 수집·표시 + 경고 하이라이트
- **SFP DDM**(온도/전압/Tx·Rx 파워) 수집·표시
- **펌웨어 인벤토리 + EoL 추적**(지원중/임박/경과 분류)
- **패브릭 토폴로지**(ISL/E_Port 그래프 시각화)
- **용량 계획 리포트** + **CSV 다운로드**, 사용율 추세
- **감사 로그**(변경 이력) + **구성 백업**(스냅샷)
- **임계치 알림**(규칙 평가 + Slack/Webhook 발송)
- **Prometheus exporter**(`GET /metrics`) + **외부 시크릿(Vault) 연동**
- **사용자 인증 + RBAC**(admin/operator/viewer, 기본 비활성)
- **글로벌 지도 대시보드**(데이터센터 위치)
- 탭 기반 웹 UI(대시보드/지도/토폴로지/펌웨어/알림/리포트/감사)

> 현재 버전: `VERSION` 파일 참조 (v0.3.0)
>
> 실장비 연결 방법은 [docs/INTEGRATION.md](docs/INTEGRATION.md) 참고.

---

## 정직성 메모 (꼭 읽어주세요)

- **이 저장소를 만든 환경에는 실제 Brocade 장비가 없습니다.** 따라서 FOS REST
  수집 코드는 공개된 API 명세에 맞춰 작성했지만 **실장비로 검증하지 못했습니다.**
  실환경 적용 시 펌웨어 버전(FOS 8.2+/9.x)에 따라 필드명 보정이 필요할 수 있습니다.
- UI/집계 로직 검증을 위해 **데모 수집기(method=demo)** 가 합성 데이터를 만듭니다.
  데모 값은 실제 측정값이 아닙니다.
- **대역폭 사용율(tx/rx %)** 은 REST/SNMP의 octet 카운터 델타로 계산합니다(순수
  계산 로직은 단위테스트됨). 다만 **실장비 네트워크 I/O는 미검증**이며, octet
  필드명/OID는 펌웨어별로 보정이 필요할 수 있습니다(docs/INTEGRATION.md).
  카운터가 없으면 추측값 대신 빈 값으로 둡니다.
- **SNMP 수집기**는 `pysnmp`(선택 의존성)가 있을 때만 동작하며, IF-MIB 표준
  OID를 사용합니다. 실 에이전트 대상 검증은 미수행.

---

## 용어 정의 (혼동 방지)

| 용어 | 정의 |
|------|------|
| 포트 사용율(occupancy) | 사용중 포트 / 전체 포트 × 100. SAN에서 "포트 사용율"은 보통 이 점유율 |
| 대역폭 사용율(utilization) | 트래픽 / 포트 속도 × 100 (포트별 tx/rx) |
| 사용중(used) | operational online 포트 |
| 비어있는(free) | 사용중도 장애도 아닌 포트 (no_module/no_light/offline 등) |
| 장애(error) | faulty 계열 포트 |

---

## 빠른 시작

```bash
# 1) 가상환경 + 의존성
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 2) 실행 (기본 0.0.0.0:8000, 첫 기동 시 데모 스위치 6대 자동 시드)
./run.sh
# 또는
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

접속: http://localhost:8000 (대시보드) · http://localhost:8000/docs (API 문서)

실제 운영 시 데모 시드 끄기: `SANSW_SEED_DEMO=0`

### 서비스로 실행(systemd / Docker)

상시 서비스 배포는 [docs/DEPLOY.md](docs/DEPLOY.md) 참고. 빠른 요약:

```bash
# systemd (권장) — /opt/san_sw 에 설치 + 서비스 등록/기동
sudo bash deploy/install.sh
systemctl status san_sw

# 또는 docker-compose
cd deploy && docker compose up -d --build
```

배포 파일: `deploy/san_sw.service`, `deploy/install.sh`, `deploy/Dockerfile`,
`deploy/docker-compose.yml`, 환경변수 예시 `.env.example`.

---

## 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SANSW_DB_PATH` | `data/sansw.db` | SQLite 경로 |
| `SANSW_POLL_INTERVAL` | `60` | 폴링 주기(초). `0` 이하 = 백그라운드 폴러 끔 |
| `SANSW_HTTP_TIMEOUT` | `15` | 스위치 REST 호출 타임아웃(초) |
| `SANSW_SEED_DEMO` | `1` | 최초 기동 시 데모 스위치 시드 |
| `SANSW_GITHUB_REPO` | `noainred/san_sw` | 업데이트 확인 대상 |
| `SANSW_ALLOW_UPGRADE_APPLY` | `0` | `1`이면 업그레이드 적용(apply) 허용 |
| `SANSW_SAMPLE_RETENTION` | `1440` | 스위치당 시계열 샘플 보관 개수 |

---

## API 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/version` | 현재 버전 |
| GET | `/api/upgrade/check` | GitHub 최신 릴리스와 비교 |
| POST | `/api/upgrade/apply` | 업그레이드 적용(허용 시) |
| GET | `/api/summary` | 전역/리전/DC 집계 |
| GET | `/api/summary/history` | 전역 포트 사용율 추이(분 버킷) |
| GET | `/api/firmware` | 펌웨어 인벤토리 + EoL |
| GET | `/api/topology` | ISL 토폴로지(노드/엣지) |
| GET | `/api/reports/capacity[.csv]` | 용량 리포트 / CSV |
| GET/POST/DELETE | `/api/alert-rules` | 알림 규칙 |
| GET | `/api/alerts` | 발생 알림, `POST /api/alerts/evaluate` 즉시 평가 |
| GET | `/api/audit` | 감사 로그 |
| POST/GET | `/api/switches/{id}/backup(s)` | 구성 스냅샷 백업/목록 |
| POST | `/api/auth/login`, `GET /api/auth/me` | 인증(RBAC) |
| GET/POST/DELETE | `/api/users` | 사용자 관리(admin) |
| GET | `/metrics` | Prometheus exposition |
| GET/POST | `/api/switches` | 스위치 목록/추가 |
| GET/PUT/DELETE | `/api/switches/{id}` | 상세(포트 포함)/수정/삭제 |
| GET | `/api/switches/{id}/ports` | 포트 목록+요약 |
| GET | `/api/switches/{id}/samples` | 시계열 샘플 |
| POST | `/api/switches/{id}/poll` | 해당 스위치 즉시 폴링 |
| POST | `/api/poll` | 전체 즉시 폴링 |

---

## 아키텍처

```
backend/app/
  main.py          FastAPI 앱 + 라우트 + 정적 서빙 + lifespan(폴러)
  config.py        환경변수 설정
  version.py       버전 단일출처(VERSION) + GitHub 릴리스 비교
  db.py            SQLite 연결/스키마
  repository.py    스위치/포트/샘플/카운터 CRUD, 전역 히스토리
  models.py        도메인 모델(PortInfo/SwitchSnapshot)
  stats.py         포트 사용율/집계 계산
  util_calc.py     대역폭 사용율(카운터 델타) 순수 계산
  crypto.py        비밀번호 암호화(Fernet)
  poller.py        백그라운드/수동 폴링 + 카운터 기반 사용율 산출
  upgrade.py       업그레이드 적용(scripts/upgrade.sh 실행)
  collectors/
    base.py        수집기 추상화
    fos_rest.py    FOS REST API 수집기(실장비 대상)
    snmp.py        SNMP(v2c) 수집기(IF-MIB, pysnmp lazy import)
    demo.py        데모 합성 데이터
frontend/          정적 대시보드(HTML/CSS/Vanilla JS, 무의존 SVG 차트)
docs/INTEGRATION.md 실장비(REST/SNMP) 연동 가이드
scripts/upgrade.sh 업그레이드 스크립트
```

수집 방식은 `collectors`로 추상화되어 있어 REST/SNMP/데모를 같은
인터페이스로 사용하며, 추후 SSH 수집기도 동일하게 추가할 수 있습니다.

---

## 자동 업그레이드

1. UI 우상단 **"업데이트 확인"** → `/api/upgrade/check`가 GitHub 최신 릴리스 태그와 현재 버전을 비교.
2. 새 버전이 있으면 `/api/upgrade/apply`(또는 `scripts/upgrade.sh`)로 최신 태그 체크아웃 + 의존성 설치.
3. **새 코드 반영에는 프로세스 재시작이 필요**합니다(systemd/docker restart 정책 권장). apply는 기본 비활성(`SANSW_ALLOW_UPGRADE_APPLY=1`로 활성화).

---

## 보안 주의 (알려진 한계)

- 스위치 계정 비밀번호는 **Fernet 대칭키로 암호화**해 SQLite에 저장합니다
  (`enc:` 접두어). API 응답에도 비노출. 단, 암호화 키(`data/secret.key` 또는
  `SANSW_SECRET_KEY`)와 DB가 같은 호스트에 있으면 둘 다 접근 가능한 공격자는
  복호화할 수 있습니다. 완전한 비밀 보호는 외부 시크릿 매니저(Vault/KMS) 연동이
  필요합니다(로드맵).
- FOS REST는 자체서명 인증서가 흔해 기본 `verify_tls=False`입니다. 사내 CA가
  있으면 켜세요.
- SNMP는 현재 v2c(community)만 지원합니다. v3(인증/암호화)는 추후.

---

## 테스트

```bash
. .venv/bin/activate
pip install pytest
python -m pytest
```

집계 로직(stats), 대역폭 계산(util_calc), 암호화(crypto), 데모/SNMP 수집기,
API 흐름(추가→폴링→요약→삭제, 암호화 저장, 히스토리)을 검증합니다(25건).

---

## 로드맵 / 완료 현황

완료 (v0.2.0):
- [x] FOS REST 대역폭 사용율(octet 카운터 델타) 계산 로직 — *실장비 I/O 미검증*
- [x] SNMP(v2c) 수집기(IF-MIB) — *실 에이전트 미검증*
- [x] 비밀번호 암호화 저장(Fernet)
- [x] 포트 사용율 추이 차트(전역/스위치별, 시계열 UI)

추천 기능 10가지 (v0.3.0에서 1차 구현 — 데모 검증, 실장비/실서버 I/O 일부 미검증):
1. [x] **임계치 알림** — 규칙 평가 + Slack/Webhook 발송 (이메일은 추후)
2. [x] **사용자 인증 + RBAC** — admin/operator/viewer (기본 비활성)
3. [x] **포트 에러 카운터** — CRC/enc_out/link_failure/loss_of_sync
4. [x] **SFP DDM 진단** — 온도/전압/Tx·Rx 파워
5. [x] **용량 계획 리포트** — 속도 분포·DC 롤업·추세 + CSV (PDF는 추후)
6. [x] **FOS 펌웨어 인벤토리 + EoL** — 분류(EoL 날짜는 검증 필요)
7. [x] **패브릭 토폴로지 맵** — ISL 그래프 (Zoning은 추후, 데모 링크)
8. [x] **감사 로그 + 구성 백업** — 변경 이력 + 스냅샷 백업
9. [x] **글로벌 지도 대시보드** — DC 위치(개략 좌표, 지도 타일 없음)
10. [x] **Prometheus exporter + Vault 연동** — /metrics + 시크릿 백엔드 추상화

남은 고도화(로드맵): 이메일 알림 · PDF 리포트 · Zoning/실데이터 ISL 매칭 ·
SNMP v3 · 알림 자동 해소(resolve) · 펌웨어 EoL 자동 동기화 · 읽기 endpoint RBAC.
```
