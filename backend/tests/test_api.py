import os
import tempfile

# 앱 임포트 전에 환경 격리(임시 DB, 데모 시드/폴러 끔)
os.environ["SANSW_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SANSW_SEED_DEMO"] = "0"
os.environ["SANSW_POLL_INTERVAL"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


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
        assert "password" not in body            # 민감정보 비노출
        assert body["summary"]["total_ports"] > 0  # 추가 즉시 폴링됨

        s = c.get("/api/summary").json()
        assert s["switch_count"] == 1
        assert s["global"]["total_ports"] > 0
        assert s["global"]["used_ports"] + s["global"]["free_ports"] \
            + s["global"]["error_ports"] == s["global"]["total_ports"]

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
