import asyncio

from backend.app.collectors.demo import DemoCollector


def test_stable_topology_same_ip():
    sw = {"ip": "10.1.2.3", "name": "t"}
    a = asyncio.run(DemoCollector(sw).collect())
    b = asyncio.run(DemoCollector(sw).collect())
    assert a.reachable is True
    assert a.model == b.model
    assert len(a.ports) == len(b.ports) > 0
    # 포트별 상태(사용중/모듈없음 등)는 시드로 고정되어 안정적이어야 한다
    assert [p.operational_status for p in a.ports] == \
           [p.operational_status for p in b.ports]


def test_used_ports_have_speed():
    res = asyncio.run(DemoCollector({"ip": "10.9.9.9"}).collect())
    assert len(res.ports) > 0
    for p in res.ports:
        assert p.name
        if p.is_used:
            assert p.speed_gbps and p.speed_gbps > 0
            assert 0 <= (p.tx_util_pct or 0) <= 100
