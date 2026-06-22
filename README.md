# san_sw — Brocade SAN Switch Manager

전세계 데이터센터에 분산된 **Brocade(브로케이드) SAN 스위치**를 모니터링·관리하는 웹 애플리케이션.

- 리전/데이터센터별 **포트 사용율, 사용중 포트 수, 비어있는(미사용) 포트 수** 집계
- 포트별 **상태/속도/포트타입/WWN** 조회
- 스위치 등록·삭제·즉시 폴링, 주기 폴링(백그라운드)
- 웹 UI에 **버전 상시 표시** + **업데이트 확인/자동 업그레이드**

> 현재 버전: `VERSION` 파일 참조 (v0.1.0)

---

## 정직성 메모 (꼭 읽어주세요)

- **이 저장소를 만든 환경에는 실제 Brocade 장비가 없습니다.** 따라서 FOS REST
  수집 코드는 공개된 API 명세에 맞춰 작성했지만 **실장비로 검증하지 못했습니다.**
  실환경 적용 시 펌웨어 버전(FOS 8.2+/9.x)에 따라 필드명 보정이 필요할 수 있습니다.
- UI/집계 로직 검증을 위해 **데모 수집기(method=demo)** 가 합성 데이터를 만듭니다.
  데모 값은 실제 측정값이 아닙니다.
- **대역폭 사용율(tx/rx %)** 은 데모에서만 제공합니다. REST 실측(octet 카운터
  델타 기반)은 펌웨어별 필드 확인이 필요해 v0.1에서는 비워둡니다(None). 추측값을
  넣지 않습니다. → 로드맵 참고.

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
  repository.py    스위치/포트/샘플 CRUD
  models.py        도메인 모델(PortInfo/SwitchSnapshot)
  stats.py         포트 사용율/집계 계산
  poller.py        백그라운드/수동 폴링
  upgrade.py       업그레이드 적용(scripts/upgrade.sh 실행)
  collectors/
    base.py        수집기 추상화
    fos_rest.py    FOS REST API 수집기(실장비 대상)
    demo.py        데모 합성 데이터
frontend/          정적 대시보드(HTML/CSS/Vanilla JS)
scripts/upgrade.sh 업그레이드 스크립트
```

수집 방식은 `collectors`로 추상화되어 있어 추후 SNMP/SSH 수집기를 같은
인터페이스로 추가할 수 있습니다.

---

## 자동 업그레이드

1. UI 우상단 **"업데이트 확인"** → `/api/upgrade/check`가 GitHub 최신 릴리스 태그와 현재 버전을 비교.
2. 새 버전이 있으면 `/api/upgrade/apply`(또는 `scripts/upgrade.sh`)로 최신 태그 체크아웃 + 의존성 설치.
3. **새 코드 반영에는 프로세스 재시작이 필요**합니다(systemd/docker restart 정책 권장). apply는 기본 비활성(`SANSW_ALLOW_UPGRADE_APPLY=1`로 활성화).

---

## 보안 주의 (알려진 한계)

- 스위치 계정 비밀번호가 **SQLite에 평문 저장**됩니다(v0.1). API 응답에는
  비밀번호를 노출하지 않지만, DB 파일 접근 통제가 필요합니다. → 로드맵에서
  비밀 암호화/외부 시크릿 연동 예정.
- FOS REST는 자체서명 인증서가 흔해 기본 `verify_tls=False`입니다. 사내 CA가
  있으면 켜세요.

---

## 테스트

```bash
. .venv/bin/activate
pip install pytest
python -m pytest
```

집계 로직(stats), 데모 수집기, API 흐름(추가→폴링→요약→삭제)을 검증합니다.

---

## 로드맵

- [ ] FOS REST 대역폭 사용율 실측(octet 카운터 델타) + 실장비 검증
- [ ] SNMP / SSH 수집기 추가
- [ ] 비밀번호 암호화 저장 / 외부 시크릿 연동
- [ ] 사용율 추이 차트(시계열 UI)
- [ ] 알림(임계치 초과) / 사용자 인증
```
