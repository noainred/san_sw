# yapen_monitor

야펜(yapen) 외부예약 위젯 페이지를 주기적으로 점검해서, 지정한 **동(건물)**이
**계약(예약) 가능** 상태가 되면 **Slack**으로 알려주는 독립 실행형 감시기.

- 대상 페이지 예: `https://rev.yapen.co.kr/external/set?ypIdx=53970&roomIdx=404526&setDate=2026-07-11`
- 기본 감시 동: `A B C D F`
- 알림: '불가 → 가능' **전환 시점에만** 1회(상태 파일로 중복 억제)

## ⚠️ 먼저 확인할 점 (중요)

이 코드를 만든 빌드 환경에서는 네트워크 정책상 `rev.yapen.co.kr` 접속이 **차단**되어
있어, 실제 페이지 HTML을 직접 검증하지 못했습니다. 그래서 가능/마감 판정은
**정규식 휴리스틱**으로 구현했고, 실제 마크업이 기본값과 다르면 아래처럼
환경변수만 바꿔 튜닝할 수 있게 했습니다.

**최초 1회는 반드시 `--debug --once`로 판정 근거를 확인**하세요:

```bash
python -m yapen_monitor --once --debug
```

- 각 동이 `가능 / 불가 / 라벨없음`으로 찍히고, 판정 근거 텍스트가 함께 출력됩니다.
- 모든 동이 `라벨없음`이면 → 페이지가 JS 렌더링이거나 라벨 형식이 다른 것.
  `--render`(Playwright) 또는 `YAPEN_LABEL_TEMPLATE`/정규식을 조정하세요.

## 사용법

```bash
# 상시 감시(기본 60초 간격) — Slack 웹훅 필요
export YAPEN_SLACK_WEBHOOK="https://hooks.slack.com/services/XXX/YYY/ZZZ"
python -m yapen_monitor

# 1회만 점검(cron에서 사용)
python -m yapen_monitor --once

# 판정 근거 보기
python -m yapen_monitor --once --debug

# Slack 연결 테스트
python -m yapen_monitor --test-slack

# 대상/주기/URL 바꾸기
python -m yapen_monitor --buildings "A B C" --interval 30 --url "https://..."
```

의존성: `httpx`(이미 프로젝트 requirements 포함). `--render` 사용 시에만 `playwright` 필요.

## 설정 (CLI 우선 > 환경변수 > 기본값)

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `YAPEN_URL` | 위 예시 URL | 감시 페이지 |
| `YAPEN_BUILDINGS` | `A B C D F` | 대상 동(공백/쉼표 구분) |
| `YAPEN_SLACK_WEBHOOK` | (없음) | Slack Incoming Webhook |
| `YAPEN_INTERVAL` | `60` | 점검 주기(초) |
| `YAPEN_TIMEOUT` | `20` | HTTP 타임아웃(초) |
| `YAPEN_STATE_FILE` | `data/yapen_state.json` | 상태 저장 파일 |
| `YAPEN_LABEL_TEMPLATE` | `{key}\s*동` | 동 라벨 정규식(‘A동’ 등) |
| `YAPEN_AVAILABLE_RE` | `예약가능\|예약하기\|...\|가능` | 가능 신호 |
| `YAPEN_SOLDOUT_RE` | `마감\|예약불가\|...\|대기예약` | 마감 신호(가능보다 우선) |
| `YAPEN_WINDOW` | `300` | 라벨 구간 최대 길이(문자) |
| `YAPEN_RENDER` | `0` | `1`이면 Playwright로 렌더링 후 파싱 |

## 판정 로직

1. HTML 태그를 제거해 평문으로 만든다.
2. 대상 동 라벨 위치를 모두 찾는다.
3. 각 라벨의 **구간 = 그 라벨 ~ 다음 라벨 직전**(최대 `YAPEN_WINDOW` 문자).
   → 옆 객실의 마감/가능 신호가 섞이지 않는다.
4. 구간에 마감 신호가 있으면 **불가**, 없고 가능 신호가 있으면 **가능**.
5. 한 동이 여러 객실로 나오면 **하나라도 가능하면 그 동은 가능**.

## 상시 실행 배포

### systemd

```ini
# /etc/systemd/system/yapen-monitor.service
[Unit]
Description=yapen reservation monitor
After=network-online.target

[Service]
Environment=YAPEN_SLACK_WEBHOOK=https://hooks.slack.com/services/XXX/YYY/ZZZ
Environment=YAPEN_STATE_FILE=/var/lib/yapen/state.json
WorkingDirectory=/opt/san_sw
ExecStart=/usr/bin/python3 -m yapen_monitor
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### cron (1분마다 단발)

```cron
* * * * * cd /opt/san_sw && YAPEN_SLACK_WEBHOOK=https://hooks.slack.com/... \
  YAPEN_STATE_FILE=/var/lib/yapen/state.json python3 -m yapen_monitor --once >> /var/log/yapen.log 2>&1
```

## 테스트

```bash
python -m pytest yapen_monitor/tests -q
```
