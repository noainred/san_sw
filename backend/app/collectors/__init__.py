"""수집기 팩토리.

스위치 레코드의 method 값에 따라 알맞은 수집기를 돌려준다.
"""
from __future__ import annotations

from typing import Any

from .base import BaseCollector
from .demo import DemoCollector
from .fos_rest import FOSRestCollector


def get_collector(switch: dict[str, Any]) -> BaseCollector:
    method = (switch.get("method") or "fos_rest").lower()
    if method == "demo":
        return DemoCollector(switch)
    if method == "fos_rest":
        return FOSRestCollector(switch)
    raise ValueError(f"지원하지 않는 수집 방식: {method}")


__all__ = ["BaseCollector", "DemoCollector", "FOSRestCollector", "get_collector"]
