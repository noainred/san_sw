"""자동 업그레이드 적용.

확인(check)은 version.check_latest()가 담당한다. 여기서는 실제 적용을 한다:
저장소 루트에서 scripts/upgrade.sh 를 실행(git fetch + 최신 태그 체크아웃 +
의존성 설치)한다. 안전을 위해 기본은 비활성(SANSW_ALLOW_UPGRADE_APPLY=1 필요).

정직성 메모: 업그레이드 후 새 코드 반영에는 프로세스 재시작이 필요하다.
이 함수는 스크립트 실행 결과만 보고하며, 재시작은 운영 환경(systemd/도커
restart 정책 등)에 위임한다.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from .config import ALLOW_UPGRADE_APPLY, BASE_DIR

_SCRIPT = BASE_DIR / "scripts" / "upgrade.sh"


async def apply_upgrade() -> dict:
    if not ALLOW_UPGRADE_APPLY:
        return {
            "ok": False,
            "applied": False,
            "error": "업그레이드 적용이 비활성화됨. "
                     "SANSW_ALLOW_UPGRADE_APPLY=1 로 활성화하세요.",
        }
    if not _SCRIPT.exists():
        return {"ok": False, "applied": False,
                "error": f"업그레이드 스크립트 없음: {_SCRIPT}"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(_SCRIPT),
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "applied": ok,
            "returncode": proc.returncode,
            "log": stdout.decode("utf-8", "replace")[-4000:],
            "note": "적용 완료 시 새 코드 반영을 위해 프로세스 재시작이 필요합니다."
                    if ok else None,
        }
    except asyncio.TimeoutError:
        return {"ok": False, "applied": False,
                "error": "업그레이드 시간 초과(300s)"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "applied": False, "error": str(exc)}


def python_executable() -> str:
    return sys.executable or "python3"


def script_path() -> Path:
    return _SCRIPT
