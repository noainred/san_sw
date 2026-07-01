"""페이지 fetch + 상태 저장 + 전환 감지 + 루프.

- run_once(): 1회 점검 후 새로 '가능'해진 동을 반환하고 필요 시 Slack 발송.
- run_loop(): interval마다 run_once() 반복(개별 실패는 로그 후 계속).
- 상태 파일에 동별 마지막 가능 여부를 저장해 '불가→가능' 전환에서만 알린다.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

import httpx

from . import __version__
from .config import Config
from .notify import build_message, send_slack
from .parser import BuildingState, parse_availability

log = logging.getLogger("yapen.monitor")


# ---- fetch -----------------------------------------------------------------

def fetch_html(cfg: Config) -> str:
    if cfg.render:
        return _render_html(cfg)
    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": "https://rev.yapen.co.kr/",
    }
    resp = httpx.get(cfg.url, headers=headers, timeout=cfg.timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _render_html(cfg: Config) -> str:
    """JS 렌더링 페이지 대응(선택). Playwright 필요."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - 선택 의존성
        raise RuntimeError(
            "YAPEN_RENDER=1 이지만 playwright가 없습니다. "
            "`pip install playwright && playwright install chromium` 후 사용하세요."
        ) from exc
    with sync_playwright() as p:  # pragma: no cover - 브라우저 필요
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=cfg.user_agent)
        page.goto(cfg.url, timeout=cfg.timeout * 1000, wait_until="networkidle")
        content = page.content()
        browser.close()
        return content


# ---- 상태 저장 --------------------------------------------------------------

def load_state(path: str) -> dict[str, bool]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: bool(v) for k, v in data.get("available", {}).items()}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def save_state(path: str, available: dict[str, bool]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"available": available}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---- 전환 감지 --------------------------------------------------------------

def detect_newly_available(
    results: dict[str, BuildingState], prev: dict[str, bool]
) -> list[str]:
    """이전에 가능이 아니었는데 이번에 가능해진 동 목록."""
    out = []
    for key, st in results.items():
        if st.matched and st.available and not prev.get(key, False):
            out.append(key)
    return out


def merge_state(
    results: dict[str, BuildingState], prev: dict[str, bool]
) -> dict[str, bool]:
    """이번에 라벨을 찾은 동만 갱신, 못 찾은 동은 이전값 유지(깜빡임 방지)."""
    new = dict(prev)
    for key, st in results.items():
        if st.matched:
            new[key] = st.available
    return new


# ---- 오케스트레이션 ---------------------------------------------------------

def run_once(cfg: Config, *, debug: bool = False, notify: bool = True) -> dict:
    html_doc = fetch_html(cfg)
    results = parse_availability(
        html_doc, cfg.buildings,
        label_template=cfg.label_template,
        available_re=cfg.available_re,
        soldout_re=cfg.soldout_re,
        window=cfg.window,
    )
    prev = load_state(cfg.state_file)
    newly = detect_newly_available(results, prev)

    if debug:
        for key, st in results.items():
            status = "가능" if st.available else ("불가" if st.matched else "라벨없음")
            log.info("[%s동] %s | 근거: %s", key, status,
                     (st.evidence[:120] + "…") if st.evidence else "-")
        if not any(st.matched for st in results.values()):
            log.warning(
                "어떤 동 라벨도 못 찾았습니다. 페이지 마크업이 다르거나 JS 렌더링일 수 있습니다. "
                "YAPEN_RENDER=1 또는 YAPEN_LABEL_TEMPLATE/정규식 조정을 검토하세요."
            )

    if newly and notify:
        msg = build_message(cfg.url, newly)
        sent = send_slack(cfg.webhook_url, msg)
        log.info("전환 감지 %s → Slack %s", newly, "발송" if sent else "실패/생략")

    save_state(cfg.state_file, merge_state(results, prev))
    return {
        "results": {k: vars(v) for k, v in results.items()},
        "newly_available": newly,
    }


def run_loop(cfg: Config, *, debug: bool = False) -> None:
    log.info(
        "yapen_monitor v%s 시작 | interval=%ds | 대상=%s | url=%s",
        __version__, cfg.interval, ",".join(cfg.buildings), cfg.url,
    )
    while True:
        try:
            run_once(cfg, debug=debug)
        except httpx.HTTPError as exc:
            log.warning("페이지 fetch 실패(계속): %s", exc)
        except Exception as exc:  # noqa: BLE001 - 루프는 죽지 않게
            log.exception("점검 중 예외(계속): %s", exc)
        time.sleep(max(5, cfg.interval))


# ---- CLI -------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yapen_monitor",
        description="야펜 외부예약 페이지에서 지정 동이 계약 가능해지면 Slack 알림.",
    )
    p.add_argument("--once", action="store_true", help="1회만 점검하고 종료(cron용)")
    p.add_argument("--debug", action="store_true", help="동별 판정 근거 출력")
    p.add_argument("--test-slack", action="store_true", help="Slack 발송 테스트 후 종료")
    p.add_argument("--url", help="감시할 페이지 URL")
    p.add_argument("--buildings", help="대상 동(예: 'A B C D F' 또는 'A,B,C')")
    p.add_argument("--webhook", help="Slack Incoming Webhook URL")
    p.add_argument("--interval", type=int, help="점검 주기(초)")
    p.add_argument("--state-file", help="상태 저장 파일 경로")
    p.add_argument("--render", action="store_true", help="Playwright로 렌더링 후 파싱")
    p.add_argument("--version", action="version", version=f"yapen_monitor {__version__}")
    return p


def _apply_args(cfg: Config, args: argparse.Namespace) -> Config:
    if args.url:
        cfg.url = args.url
    if args.buildings:
        cfg.buildings = [t.strip() for t in args.buildings.replace(",", " ").split() if t.strip()]
    if args.webhook:
        cfg.webhook_url = args.webhook
    if args.interval:
        cfg.interval = args.interval
    if args.state_file:
        cfg.state_file = args.state_file
    if args.render:
        cfg.render = True
    return cfg


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_parser().parse_args(argv)
    cfg = _apply_args(Config(), args)

    if args.test_slack:
        ok = send_slack(cfg.webhook_url, ":white_check_mark: yapen_monitor Slack 연결 테스트")
        print("Slack 발송:", "성공" if ok else "실패(웹훅/네트워크 확인)")
        return 0 if ok else 1

    if args.once:
        out = run_once(cfg, debug=args.debug)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    run_loop(cfg, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
