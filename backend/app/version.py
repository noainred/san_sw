"""버전 관리 및 업데이트 확인.

- 버전 단일 출처: 저장소 루트의 VERSION 파일.
- GitHub Releases의 최신 태그와 비교해 업데이트 가능 여부를 알려준다.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from .config import GITHUB_REPO, HTTP_TIMEOUT

_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"


def get_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0+unknown"


__version__ = get_version()


def parse_semver(v: str) -> tuple[int, int, int]:
    """'v1.2.3' / '1.2.3' / '1.2.3+meta' -> (1, 2, 3). 실패 시 (0,0,0)."""
    if not v:
        return (0, 0, 0)
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_newer(latest: str, current: str) -> bool:
    return parse_semver(latest) > parse_semver(current)


async def check_latest() -> dict:
    """GitHub Releases의 최신 버전을 조회한다.

    네트워크 차단/오류/릴리스 없음 등은 정직하게 error 필드로 보고한다.
    """
    current = get_version()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    result = {
        "current": current,
        "latest": None,
        "update_available": False,
        "repo": GITHUB_REPO,
        "html_url": None,
        "error": None,
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(
                url, headers={"Accept": "application/vnd.github+json"}
            )
        if resp.status_code == 404:
            result["error"] = "릴리스가 아직 없습니다(404)."
            return result
        resp.raise_for_status()
        data = resp.json()
        latest = (data.get("tag_name") or "").strip()
        result["latest"] = latest
        result["html_url"] = data.get("html_url")
        result["update_available"] = is_newer(latest, current)
    except httpx.HTTPError as exc:
        result["error"] = f"업데이트 확인 실패(네트워크/HTTP): {exc!s}"
    except Exception as exc:  # noqa: BLE001 - 외부 응답 파싱 방어
        result["error"] = f"업데이트 확인 실패: {exc!s}"
    return result
