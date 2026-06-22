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
