from backend.app.util_calc import bandwidth_util_pct


def test_basic_percent():
    # 16Gbps 포트, 10초간 2e9 octet => 1.6Gbps => 10%
    assert bandwidth_util_pct(2_000_000_000, 10, 16.0) == 10.0


def test_capped_at_100():
    assert bandwidth_util_pct(10**15, 1, 16.0) == 100.0


def test_counter_reset_returns_none():
    assert bandwidth_util_pct(-5, 10, 16.0) is None


def test_zero_delta_is_zero():
    assert bandwidth_util_pct(0, 10, 16.0) == 0.0


def test_invalid_inputs():
    assert bandwidth_util_pct(100, 0, 16.0) is None      # dt<=0
    assert bandwidth_util_pct(100, 10, None) is None      # 속도 미상
    assert bandwidth_util_pct(100, 10, 0) is None         # 속도 0
