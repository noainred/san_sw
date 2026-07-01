"""Slack Incoming Webhook 발송.

기존 san_sw alerts.py와 동일하게 `{"text": ...}` 페이로드를 쓴다.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("yapen.notify")


def send_slack(webhook_url: str, text: str, *, timeout: float = 10.0) -> bool:
    """Slack으로 메시지 발송. 성공 시 True."""
    if not webhook_url:
        log.warning("Slack webhook 미설정 — 알림 생략: %s", text)
        return False
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=timeout)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("Slack 발송 실패: %s", exc)
        return False


def build_message(url: str, newly_available: list[str]) -> str:
    """계약 가능 전환 알림 메시지 구성."""
    dongs = ", ".join(f"{k}동" for k in newly_available)
    return (
        f":tada: 야펜 예약 가능 알림\n"
        f"• 계약 가능해진 동: *{dongs}*\n"
        f"• 예약 페이지: {url}"
    )
