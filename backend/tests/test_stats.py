from backend.app.models import PortInfo
from backend.app.stats import merge_summaries, summarize_ports


def _p(status, tx=None, rx=None):
    return PortInfo(name="x", operational_status=status, tx_util_pct=tx, rx_util_pct=rx)


def test_summarize_counts():
    ports = [_p("online"), _p("online", 50, 50), _p("no_module"),
             _p("no_light"), _p("faulty")]
    s = summarize_ports(ports)
    assert s["total_ports"] == 5
    assert s["used_ports"] == 2
    assert s["error_ports"] == 1
    assert s["free_ports"] == 2          # no_module + no_light
    assert s["occupancy_pct"] == 40.0    # 2/5
    assert s["avg_util_pct"] == 50.0     # (50+50)/2


def test_empty_summary():
    s = summarize_ports([])
    assert s["total_ports"] == 0
    assert s["occupancy_pct"] == 0.0
    assert s["avg_util_pct"] is None


def test_free_equals_total_minus_used_minus_error():
    ports = [_p("online")] * 3 + [_p("no_module")] * 5 + [_p("faulty")] * 2
    s = summarize_ports(ports)
    assert s["free_ports"] == s["total_ports"] - s["used_ports"] - s["error_ports"]


def test_merge_summaries():
    a = summarize_ports([_p("online"), _p("no_module")])
    b = summarize_ports([_p("online"), _p("online")])
    m = merge_summaries([a, b])
    assert m["total_ports"] == 4
    assert m["used_ports"] == 3
    assert m["occupancy_pct"] == 75.0
