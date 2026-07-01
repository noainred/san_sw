"""전환 감지·상태 병합·상태 저장 로직 검증."""
import json

from yapen_monitor.monitor import (
    detect_newly_available,
    load_state,
    merge_state,
    save_state,
)
from yapen_monitor.parser import BuildingState


def _states(**kv):
    # kv: key -> (matched, available)
    return {k: BuildingState(key=k, matched=m, available=a) for k, (m, a) in kv.items()}


def test_detect_rising_edge_only():
    results = _states(A=(True, True), B=(True, True), C=(True, False))
    prev = {"A": False, "B": True}   # A는 새로 가능, B는 이미 가능
    newly = detect_newly_available(results, prev)
    assert newly == ["A"]


def test_unmatched_building_never_fires():
    results = _states(F=(False, False))
    assert detect_newly_available(results, {}) == []


def test_merge_keeps_prev_for_unmatched():
    results = _states(A=(True, True), F=(False, False))
    merged = merge_state(results, {"F": True})
    assert merged["A"] is True
    assert merged["F"] is True   # 못 찾은 동은 이전값 유지


def test_state_roundtrip(tmp_path):
    path = str(tmp_path / "sub" / "state.json")
    save_state(path, {"A": True, "B": False})
    assert load_state(path) == {"A": True, "B": False}


def test_load_missing_state_is_empty(tmp_path):
    assert load_state(str(tmp_path / "nope.json")) == {}


def test_load_corrupt_state_is_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_state(str(p)) == {}
