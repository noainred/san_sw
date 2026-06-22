from fastapi.testclient import TestClient

from backend.app import repository as repo
from backend.app.main import app


def test_version_and_health():
    with TestClient(app) as c:
        v = c.get("/api/version").json()
        assert v["version"]
        assert c.get("/healthz").json()["status"] == "ok"


def test_switch_crud_and_summary():
    with TestClient(app) as c:
        assert c.get("/api/switches").json() == []

        r = c.post("/api/switches", json={
            "ip": "10.0.0.5", "name": "t1", "method": "demo",
            "region": "APAC", "dc": "X",
        })
        assert r.status_code == 201
        body = r.json()
        assert "password" not in body
        assert body["summary"]["total_ports"] > 0  # 추가 즉시 폴링됨

        s = c.get("/api/summary").json()
        assert s["switch_count"] == 1
        g = s["global"]
        assert g["total_ports"] > 0
        assert g["used_ports"] + g["free_ports"] + g["error_ports"] == g["total_ports"]

        sid = body["id"]
        detail = c.get(f"/api/switches/{sid}").json()
        assert len(detail["ports"]) > 0

        assert c.delete(f"/api/switches/{sid}").json()["deleted"] is True
        assert c.get("/api/switches").json() == []


def test_duplicate_ip_rejected():
    with TestClient(app) as c:
        c.post("/api/switches", json={"ip": "10.0.0.9", "method": "demo"})
        dup = c.post("/api/switches", json={"ip": "10.0.0.9", "method": "demo"})
        assert dup.status_code == 400


def test_password_encrypted_in_db():
    with TestClient(app) as c:
        r = c.post("/api/switches", json={
            "ip": "10.0.0.77", "method": "demo",
            "username": "admin", "password": "p@ssw0rd",
        })
        sid = r.json()["id"]
        row = repo.get_switch(sid)
        assert row["password"].startswith("enc:")   # 암호문으로 저장
        assert "p@ssw0rd" not in row["password"]
        # 복호화하면 원문 복구
        assert repo.crypto.decrypt(row["password"]) == "p@ssw0rd"
        # API 응답엔 비밀번호 비노출
        assert "password" not in c.get(f"/api/switches/{sid}").json()


def test_metrics_endpoint():
    with TestClient(app) as c:
        c.post("/api/switches", json={"ip": "10.1.0.1", "method": "demo"})
        txt = c.get("/metrics").text
        assert "sansw_switches_total" in txt
        assert "sansw_ports_total" in txt
        assert "sansw_switch_up" in txt


def test_firmware_topology_reports():
    with TestClient(app) as c:
        c.post("/api/switches", json={"ip": "10.1.0.2", "method": "demo",
                                      "region": "APAC", "dc": "Z"})
        fw = c.get("/api/firmware").json()
        assert "status_counts" in fw and "switches" in fw

        topo = c.get("/api/topology").json()
        assert "nodes" in topo and "edges" in topo

        rep = c.get("/api/reports/capacity").json()
        assert "totals" in rep and "speed_distribution" in rep
        csv = c.get("/api/reports/capacity.csv")
        assert csv.status_code == 200
        assert "switch_id" in csv.text


def test_alert_rules_and_eval():
    with TestClient(app) as c:
        rules = c.get("/api/alert-rules").json()["rules"]
        assert len(rules) >= 5  # 기본 규칙 시드됨
        r = c.post("/api/alert-rules", json={
            "name": "테스트규칙", "metric": "occupancy_pct",
            "comparator": ">", "threshold": 0, "severity": "info"})
        assert r.status_code == 201
        c.post("/api/switches", json={"ip": "10.1.0.3", "method": "demo"})
        ev = c.post("/api/alerts/evaluate").json()
        assert "count" in ev


def test_auth_disabled_login_and_audit():
    with TestClient(app) as c:
        cfg = c.get("/api/auth/config").json()
        assert cfg["auth_enabled"] is False
        tok = c.post("/api/auth/login",
                     json={"username": "x", "password": "y"}).json()
        assert tok["token"]
        # 감사 로그: 스위치 생성이 기록되는지
        c.post("/api/switches", json={"ip": "10.1.0.4", "method": "demo"})
        audit = c.get("/api/audit").json()["audit"]
        assert any(a["action"] == "create_switch" for a in audit)


def test_history_endpoint_no_inflation():
    with TestClient(app) as c:
        c.post("/api/switches", json={"ip": "10.0.0.88", "method": "demo"})
        # 같은 분에 여러 번 폴링해도 버킷 절대값이 부풀려지면 안 된다
        for _ in range(3):
            c.post("/api/poll")
        hist = c.get("/api/summary/history").json()["history"]
        assert isinstance(hist, list) and hist
        g = c.get("/api/summary").json()["global"]
        # 최신 버킷의 절대값 == 현재 라이브 합계(중복 합산 없음)
        assert hist[-1]["total_ports"] == g["total_ports"]
        assert hist[-1]["used_ports"] == g["used_ports"]
