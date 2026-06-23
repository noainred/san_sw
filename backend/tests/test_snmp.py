from backend.app.collectors.snmp import (
    SNMPCollector,
    highspeed_to_gbps,
    index_from_oid,
    snmp_oper_to_status,
)


def test_oper_status_mapping():
    assert snmp_oper_to_status(1) == "online"   # up
    assert snmp_oper_to_status(2) == "offline"  # down
    assert snmp_oper_to_status(6) == "offline"  # notPresent
    assert snmp_oper_to_status(None) == "offline"


def test_highspeed_to_gbps():
    assert highspeed_to_gbps(16000) == 16.0
    assert highspeed_to_gbps(32000) == 32.0
    assert highspeed_to_gbps(0) is None
    assert highspeed_to_gbps(None) is None


def test_index_from_oid():
    assert index_from_oid((1, 3, 6, 1, 2, 1, 2, 2, 1, 2, 12)) == 12
    assert index_from_oid("1.3.6.1.2.1.2.2.1.2.7") == 7
    assert index_from_oid("nonsense") is None


def test_host_and_community_parse():
    c = SNMPCollector({"ip": "https://10.0.0.1/rest", "username": "mycomm"})
    assert c.host == "10.0.0.1"
    assert c.community == "mycomm"
    # community 미입력 시 기본값(public 등)
    c2 = SNMPCollector({"ip": "10.0.0.2"})
    assert c2.host == "10.0.0.2"
    assert c2.community  # 기본 community 존재
