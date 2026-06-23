from datetime import date

from backend.app import alerts, auth, firmware, topology


# ------------------------------------------------------------ firmware EoL

def test_firmware_classify():
    today = date(2026, 6, 22)
    assert firmware.classify("9.1.1", today)["status"] == "supported"
    assert firmware.classify("7.4.2", today)["status"] == "eol"
    # 8.2 EoL 2026-12-31: 6/22 기준 192일 남음 → supported
    assert firmware.classify("8.2.3c", today)["status"] == "supported"
    # 같은 8.2를 10/1 기준으로 보면 180일 이내 → eol_soon
    assert firmware.classify("8.2.3c", date(2026, 10, 1))["status"] == "eol_soon"
    assert firmware.classify("99.9.9", today)["status"] == "unknown"


def test_firmware_inventory():
    sw = [{"id": 1, "name": "a", "region": "APAC", "dc": "x",
           "fos_version": "9.1.1"},
          {"id": 2, "name": "b", "region": "APAC", "dc": "x",
           "fos_version": "7.4.0"}]
    inv = firmware.inventory(sw, date(2026, 6, 22))
    assert inv["status_counts"]["supported"] == 1
    assert inv["status_counts"]["eol"] == 1
    assert inv["by_version"]["9.1.1"] == 1


# --------------------------------------------------------------- topology

def test_topology_ring_and_graph():
    sw = [{"id": i, "name": f"s{i}", "region": "APAC", "dc": "x",
           "status": "online", "model": "G620"} for i in (1, 2, 3)]
    links = topology.build_demo_isl(sw)
    g = topology.graph(sw, [
        {"switch_id": sid, **lk} for sid, lst in links.items() for lk in lst])
    assert len(g["nodes"]) == 3
    # 3노드 링 → 3엣지(중복 제거)
    assert len(g["edges"]) == 3


def test_topology_two_nodes_single_link():
    sw = [{"id": 1, "name": "a", "region": "EMEA"},
          {"id": 2, "name": "b", "region": "EMEA"}]
    links = topology.build_demo_isl(sw)
    g = topology.graph(sw, [
        {"switch_id": sid, **lk} for sid, lst in links.items() for lk in lst])
    assert len(g["edges"]) == 1


# ------------------------------------------------------------------- auth

def test_password_hash_verify():
    h = auth.hash_password("hunter2")
    assert h.startswith("pbkdf2$")
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False


def test_token_roundtrip():
    tok = auth.make_token("alice", "operator")
    decoded = auth.decode_token(tok)
    assert decoded == {"username": "alice", "role": "operator"}
    assert auth.decode_token("garbage") is None


# ------------------------------------------------------------------ alerts

def test_alert_comparator():
    assert alerts._cmp(95, ">", 90) is True
    assert alerts._cmp(85, ">", 90) is False
    assert alerts._cmp(-16, "<", -15) is True


def test_alert_switch_metrics():
    ports = [
        {"operational_status": "online", "crc_errors": 50000,
         "sfp_rx_power_dbm": -18.0},
        {"operational_status": "online", "crc_errors": 3,
         "sfp_rx_power_dbm": -4.0},
        {"operational_status": "no_module"},
    ]
    m = alerts._switch_metrics({"status": "online"}, ports)
    assert m["crc_errors"] == 50000.0          # 최대값
    assert m["sfp_rx_power_dbm"] == -18.0        # 최소값
    assert m["switch_unreachable"] == 0.0
