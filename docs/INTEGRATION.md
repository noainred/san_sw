# 실장비 연동 가이드 (FOS REST / SNMP)

> 정직성: 이 저장소는 실제 Brocade 장비가 없는 환경에서 작성됐습니다. 아래
> 절차는 공개 명세 기준이며, 실장비에서 한 번은 검증/보정이 필요합니다.
> 특히 펌웨어 버전에 따라 일부 필드명이 다를 수 있습니다.

---

## 1. FOS REST API (권장, FabricOS 8.2+/9.x)

### 사전 준비
- 스위치에서 REST 인터페이스 활성화 여부 확인 (보통 HTTPS/443).
- REST 권한이 있는 계정(읽기 권한이면 모니터링에 충분).
- 자체서명 인증서가 흔하므로 기본 `verify_tls=false`. 사내 CA가 있으면 켜세요.

### 등록
UI → "스위치 추가" → 수집 방식 **FOS REST API**, 계정/비밀번호 입력.
또는 API:

```bash
curl -X POST http://localhost:8000/api/switches -H 'Content-Type: application/json' -d '{
  "ip": "10.10.0.21", "name": "dc1-sw01",
  "region": "APAC", "dc": "Seoul-DC1",
  "method": "fos_rest", "username": "admin", "password": "******",
  "verify_tls": false
}'
```

### 사용하는 엔드포인트
| 용도 | 엔드포인트 |
|------|-----------|
| 로그인/로그아웃 | `POST /rest/login`, `POST /rest/logout` |
| 스위치 이름/펌웨어 | `GET /rest/running/brocade-fibrechannel-switch/fibrechannel-switch` |
| 모델명 | `GET /rest/running/brocade-chassis/chassis` |
| 포트 상태/속도/타입 | `GET /rest/running/brocade-interface/fibrechannel` |
| 포트 카운터(대역폭) | `GET /rest/running/brocade-interface/fibrechannel-statistics` |

### 대역폭 사용율 검증 포인트 (중요)
대역폭 사용율(tx/rx %)은 `fibrechannel-statistics`의 **octet 카운터 델타**로
계산합니다(2회차 폴링부터 값 생성). 코드는 다음 후보 필드명을 시도합니다:

- tx(송신): `out-octets`, `out-bytes`, `stat-tx-octets`, `tx-octets`
- rx(수신): `in-octets`, `in-bytes`, `stat-rx-octets`, `rx-octets`

실장비 응답을 한 번 떠서(`curl`로 위 statistics 엔드포인트 호출) octet 누적
카운터의 **정확한 키 이름**을 확인하세요. 목록에 없으면
`backend/app/collectors/fos_rest.py`의 `_TX_OCTET_FIELDS`/`_RX_OCTET_FIELDS`에
추가하면 됩니다. octet 카운터가 전혀 없으면 사용율은 빈 값으로 남습니다
(프레임 수로 추정하는 부정확한 값은 넣지 않습니다).

### 상태 매핑
`operational-status`(정수) → 2=online(사용중), 3=offline·6=testing(비어있음),
5=faulty(장애). REST는 SFP 장착여부(no_module)를 CLI만큼 세분화하지 않으므로
'사용중이 아니면 비어있음'으로 분류합니다.

---

## 2. SNMP (v2c, 구형 포함 폭넓은 호환)

### 사전 준비
- 스위치에서 SNMP v2c 활성화 + community 설정(읽기 전용 권장).
- 방화벽 UDP 161 허용.
- `pysnmp` 설치 필요: `pip install pysnmp` (미설치 시 SNMP 스위치만 실패).

### 등록
UI → 수집 방식 **SNMP**, **계정칸에 community 문자열** 입력(비밀번호칸 미사용).
community 미입력 시 `SANSW_SNMP_COMMUNITY`(기본 `public`) 사용.

```bash
curl -X POST http://localhost:8000/api/switches -H 'Content-Type: application/json' -d '{
  "ip": "10.10.0.31", "name": "dc2-sw01",
  "method": "snmp", "username": "public",
  "region": "EMEA", "dc": "Frankfurt-DC"
}'
```

### 사용하는 OID (IF-MIB 표준)
| 항목 | OID |
|------|-----|
| 포트명 | `1.3.6.1.2.1.2.2.1.2` (ifDescr) |
| 운영상태 | `1.3.6.1.2.1.2.2.1.8` (ifOperStatus: 1=up) |
| 속도(Mbps) | `1.3.6.1.2.1.31.1.1.1.15` (ifHighSpeed) |
| 수신 octet | `1.3.6.1.2.1.31.1.1.1.6` (ifHCInOctets) |
| 송신 octet | `1.3.6.1.2.1.31.1.1.1.10` (ifHCOutOctets) |
| 장비명/설명 | `1.3.6.1.2.1.1.5.0`, `1.3.6.1.2.1.1.1.0` |

대역폭 사용율은 ifHCIn/OutOctets 델타로 계산합니다(FOS REST와 동일 로직).

### 한계
- IF-MIB만 사용하므로 포트 타입(E/F_Port 등) 같은 FC 특화 정보는 채우지 않습니다.
  더 정확한 FC 정보가 필요하면 FCMGMT-MIB 매핑 추가가 필요합니다(로드맵).
- 현재 SNMP v2c만 지원. v3(인증/암호화)는 추후.

---

## 검증 체크리스트
1. 스위치 1대 등록 후 "폴링" → 상태가 `online`이 되는지.
2. 포트 그리드에서 사용중/비어있음 분류가 실제와 맞는지.
3. 1분 이상 간격으로 2회 이상 폴링 후 대역폭 사용율(%)이 채워지는지.
4. 맞지 않으면 위의 필드명/OID 보정.
