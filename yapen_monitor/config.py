"""실행 설정. 우선순위: CLI 인자 > 환경변수 > 기본값.

파싱 규칙(정규식)을 env로 바꿀 수 있게 해서, 실제 페이지 마크업이 기본값과
다를 때 코드 수정 없이 튜닝할 수 있게 한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# 감시 대상 기본 URL(사용자 요청 페이지).
DEFAULT_URL = (
    "https://rev.yapen.co.kr/external/set"
    "?ypIdx=53970&roomIdx=404526&setDate=2026-07-11"
)

# 감시 대상 동(건물) 키. 라벨은 LABEL_TEMPLATE로 만든다(기본 "A동" ...).
DEFAULT_BUILDINGS = ["A", "B", "C", "D", "F"]

# 동 라벨 정규식 템플릿. {key}에 동 키가 들어간다. 기본은 "A" 뒤 공백 후 "동".
DEFAULT_LABEL_TEMPLATE = r"{key}\s*동"

# 예약 '가능' 신호. 동 라벨 주변 텍스트에서 이 중 하나가 보이면 가능 후보.
DEFAULT_AVAILABLE_RE = r"예약가능|예약하기|예약신청|신청가능|잔여|바로예약|가능"

# 예약 '불가/마감' 신호. 가능 신호보다 우선한다(있으면 불가로 판정).
DEFAULT_SOLDOUT_RE = r"마감|예약불가|불가|만실|매진|품절|예약대기|대기예약"

# 라벨 주변으로 살펴볼 텍스트 창 크기(문자). 좌우 각각 이만큼.
DEFAULT_WINDOW = 300

DEFAULT_INTERVAL = 60          # 초
DEFAULT_TIMEOUT = 20           # 초
DEFAULT_STATE_FILE = "data/yapen_state.json"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


def _split(value: str) -> list[str]:
    return [t.strip() for t in value.replace(",", " ").split() if t.strip()]


@dataclass
class Config:
    url: str = field(default_factory=lambda: _env("YAPEN_URL", DEFAULT_URL))
    buildings: list[str] = field(
        default_factory=lambda: _split(_env("YAPEN_BUILDINGS", " ".join(DEFAULT_BUILDINGS)))
    )
    webhook_url: str = field(default_factory=lambda: _env("YAPEN_SLACK_WEBHOOK", ""))
    interval: int = field(default_factory=lambda: int(_env("YAPEN_INTERVAL", str(DEFAULT_INTERVAL))))
    timeout: int = field(default_factory=lambda: int(_env("YAPEN_TIMEOUT", str(DEFAULT_TIMEOUT))))
    state_file: str = field(default_factory=lambda: _env("YAPEN_STATE_FILE", DEFAULT_STATE_FILE))
    label_template: str = field(
        default_factory=lambda: _env("YAPEN_LABEL_TEMPLATE", DEFAULT_LABEL_TEMPLATE)
    )
    available_re: str = field(default_factory=lambda: _env("YAPEN_AVAILABLE_RE", DEFAULT_AVAILABLE_RE))
    soldout_re: str = field(default_factory=lambda: _env("YAPEN_SOLDOUT_RE", DEFAULT_SOLDOUT_RE))
    window: int = field(default_factory=lambda: int(_env("YAPEN_WINDOW", str(DEFAULT_WINDOW))))
    user_agent: str = field(default_factory=lambda: _env("YAPEN_USER_AGENT", _UA))
    # 1이면 Playwright로 렌더링 후 HTML 취득(JS 렌더링 페이지 대응).
    render: bool = field(default_factory=lambda: _env("YAPEN_RENDER", "0") == "1")
