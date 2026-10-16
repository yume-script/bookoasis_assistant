# -*- coding: utf-8 -*-
"""워커 감독

플러그인일 때는 화면을 열거나 BookOasis가 시작될 때만 워커를 띄우고 보관함 목록을 갱신했다.
그래서 화면을 안 열면 보관함 변경(cron·RC 주소·새 보관함)이 워커에 반영되지 않았고,
워커가 죽어도 누가 화면을 열 때까지 그대로였다. 독립형은 이 스레드가 상주하며
  - 30초마다 runtime.json 동기화 (보관함 목록은 60초 캐시)
  - 자동 시작(AUTO_START) · 워커가 죽으면 다시 시작 (연달아 죽으면 간격을 늘림)
을 맡는다. 사용자가 [중지]를 누르면(disabled.flag) 다시 띄우지 않는다.
"""
import logging
import os
import threading
import time

from . import service

log = logging.getLogger("gdw.supervisor")
CHECK_SECONDS = 30


def loop(svc, stop_event):
    backoff, next_try, was_alive = CHECK_SECONDS, 0.0, False
    while not stop_event.is_set():
        try:
            runtime = svc._sync_runtime()
            alive = service._worker_alive()
            if was_alive and not alive and not os.path.exists(service._path("disabled.flag")):
                log.warning("워커가 종료됐습니다. worker.log / worker.out을 확인하세요.")
            was_alive = alive
            wanted = runtime.get("auto_start") and runtime.get("roots") and not os.path.exists(service._path("disabled.flag"))
            if alive:
                backoff = CHECK_SECONDS
            elif wanted and time.time() >= next_try:
                if service._start_worker():
                    log.info("워커를 시작했습니다.")
                    next_try = time.time() + backoff
                    backoff = min(backoff * 2, 600)  # 바로 죽는 상태면 30초 → 최대 10분 간격으로
        except Exception as error:
            log.warning("감독 확인 실패: %s: %s", type(error).__name__, error)
        stop_event.wait(CHECK_SECONDS)


def start(svc, stop_event):
    thread = threading.Thread(target=loop, args=(svc, stop_event), daemon=True, name="gdw-supervisor")
    thread.start()
    return thread


def shutdown(wait=40):
    """서비스 종료 시: 워커도 정상 종료시킨다 (disabled.flag는 남기지 않음 → 다음 시작 때 자동 시작)."""
    if service._worker_alive():
        log.info("워커 종료 중…")
        if not service._stop_worker(disable=False, wait=wait):
            log.warning("워커가 %d초 안에 끝나지 않았습니다.", wait)
