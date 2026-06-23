"""테스트 환경 격리(앱 임포트 이전에 실행됨)."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.setdefault("SANSW_DATA_DIR", _tmp)
os.environ.setdefault("SANSW_DB_PATH", os.path.join(_tmp, "test.db"))
os.environ.setdefault("SANSW_SECRET_KEY", "unit-test-secret-key")
os.environ.setdefault("SANSW_SEED_DEMO", "0")
os.environ.setdefault("SANSW_POLL_INTERVAL", "0")
