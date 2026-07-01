"""HTML → 동(건물)별 예약가능 여부 판정.

판정 방식(휴리스틱, 튜닝 가능):
1. HTML 태그를 공백으로 바꾸고 엔티티를 해제해 '평문'을 만든다.
2. 각 동 라벨(기본 "A동" 등) 위치를 찾는다.
3. 라벨 주변 ±window 문자 창을 본다.
4. 창에 SOLDOUT 신호가 있으면 불가, 없고 AVAILABLE 신호가 있으면 가능.
5. 같은 동이 여러 번 나오면(여러 객실) 하나라도 가능하면 그 동은 '가능'.

실제 페이지 마크업이 다르면 정규식(config)만 바꾸면 된다.
`--debug`로 각 동의 판정 근거(창 텍스트)를 확인할 수 있다.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class BuildingState:
    key: str
    matched: bool          # 페이지에서 동 라벨을 찾았는가
    available: bool        # 예약 가능 상태인가
    evidence: str = ""     # 판정 근거(창 텍스트 일부)


def html_to_text(html_doc: str) -> str:
    """태그 제거 + 엔티티 해제 + 공백 정리."""
    text = _TAG_RE.sub(" ", html_doc)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def parse_availability(
    html_doc: str,
    buildings: list[str],
    *,
    label_template: str,
    available_re: str,
    soldout_re: str,
    window: int,
) -> dict[str, BuildingState]:
    text = html_to_text(html_doc)
    avail_re = re.compile(available_re)
    sold_re = re.compile(soldout_re)

    # 모든 대상 동 라벨의 위치를 모아 정렬한다. 각 라벨의 '구간'은
    # 그 라벨부터 다음(어떤 대상이든) 라벨 직전까지다 — 옆 객실의 마감/가능
    # 신호가 섞이지 않게 하려는 것. window는 구간 최대 길이 상한으로만 쓴다.
    marks: list[tuple[int, int, str]] = []
    for key in buildings:
        label_re = re.compile(label_template.format(key=re.escape(key)))
        for m in label_re.finditer(text):
            marks.append((m.start(), m.end(), key))
    marks.sort(key=lambda t: t[0])

    result: dict[str, BuildingState] = {
        key: BuildingState(key=key, matched=False, available=False)
        for key in buildings
    }

    for idx, (start, _end, key) in enumerate(marks):
        next_start = marks[idx + 1][0] if idx + 1 < len(marks) else len(text)
        seg_end = min(next_start, start + window)
        segment = text[start:seg_end]

        soldout = bool(sold_re.search(segment))
        available = bool(avail_re.search(segment)) and not soldout

        st = result[key]
        st.matched = True
        # 같은 동이 여러 객실로 나오면 하나라도 가능하면 '가능'.
        if available and not st.available:
            st.available = True
            st.evidence = segment[:400]
        elif not st.evidence:
            st.evidence = segment[:400]
    return result
