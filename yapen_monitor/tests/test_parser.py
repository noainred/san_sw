"""파서 판정 로직 검증(대표 마크업 픽스처 기반).

실제 사이트 HTML은 네트워크 정책상 빌드 환경에서 확인 불가하므로,
야펜류 예약 위젯에서 흔한 형태를 본떠 픽스처를 만들고 '로직 계약'을 검증한다.
정규식 기본값이 실제와 다르면 config env로 조정한다.
"""
from yapen_monitor.config import (
    DEFAULT_AVAILABLE_RE,
    DEFAULT_LABEL_TEMPLATE,
    DEFAULT_SOLDOUT_RE,
    DEFAULT_WINDOW,
)
from yapen_monitor.parser import html_to_text, parse_availability

BUILDINGS = ["A", "B", "C", "D", "F"]

SAMPLE = """
<html><body>
<ul class="roomList">
  <li class="room"><span class="name">A동 (4인)</span>
      <a class="btn" href="#">예약하기</a></li>
  <li class="room"><span class="name">B동 (6인)</span>
      <span class="state">예약마감</span></li>
  <li class="room"><span class="name">C동 (커플)</span>
      <span class="state">예약대기</span></li>
  <li class="room"><span class="name">D동 (단체)</span>
      <span class="rest">잔여 1</span><a class="btn" href="#">바로예약</a></li>
  <!-- F동은 이 날짜에 목록에 없음 -->
</ul>
</body></html>
"""


def _parse(doc):
    return parse_availability(
        doc, BUILDINGS,
        label_template=DEFAULT_LABEL_TEMPLATE,
        available_re=DEFAULT_AVAILABLE_RE,
        soldout_re=DEFAULT_SOLDOUT_RE,
        window=DEFAULT_WINDOW,
    )


def test_html_to_text_strips_tags():
    txt = html_to_text("<div>A동 &amp; <b>예약하기</b></div>")
    assert "A동" in txt
    assert "&" in txt
    assert "<" not in txt


def test_available_building_detected():
    r = _parse(SAMPLE)
    assert r["A"].matched and r["A"].available
    assert r["D"].matched and r["D"].available


def test_soldout_building_not_available():
    r = _parse(SAMPLE)
    assert r["B"].matched and not r["B"].available   # 예약마감
    assert r["C"].matched and not r["C"].available   # 예약대기


def test_missing_building_marked_unmatched():
    r = _parse(SAMPLE)
    assert not r["F"].matched
    assert not r["F"].available


def test_soldout_takes_priority_over_available():
    # 같은 창에 '가능'과 '불가능'이 함께 있으면 불가로 판정.
    doc = "<span>A동</span> <span>예약불가능</span>"
    r = _parse(doc)
    assert r["A"].matched and not r["A"].available


def test_multiple_rooms_any_available_wins():
    doc = (
        "<li>A동 201호 예약마감</li>"
        "<li>A동 202호 예약하기</li>"
    )
    r = _parse(doc)
    assert r["A"].available
