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


def _tail_logs(lines=12):
    """워커가 죽었을 때 원인을 바로 보이게: worker.log 끝부분 + worker.out(예외 흔적) 끝부분."""
    out = []
    for name, count in (("worker.log", lines), ("worker.out", lines)):
        try:
            with open(service._path(name), "rb") as handle:
                handle.seek(0, 2)
                handle.seek(max(0, handle.tell() - 32 * 1024))
                tail = handle.read().decode("utf-8", "replace").splitlines()[-count:]
        except OSError:
            continue
        if tail:
            out.append(f"── {name} ──")
            out.extend("  " + line for line in tail)
    return "\n".join(out) or "(로그 없음)"


def loop(svc, stop_event, wtm=False):
    backoff, next_try, was_alive = CHECK_SECONDS, 0.0, False
    while not stop_event.is_set():
        if wtm:  # 웹툰 다운로더: 스케줄러·작업 프로세스 (플러그인 시절에는 화면을 열 때만 확인)
            try:
                from wtm import service as wtm_service
                wtm_service.tick()
            except Exception as error:
                log.warning("웹툰 다운로더 확인 실패: %s: %s", type(error).__name__, error)
        if svc is None:
            stop_event.wait(CHECK_SECONDS)
            continue
        try:
            runtime = svc._sync_runtime()
            alive = service._worker_alive()
            if was_alive and not alive and not os.path.exists(service._path("disabled.flag")):
                log.warning("워커가 종료됐습니다. 마지막 로그:\n%s", _tail_logs())
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


def start(svc, stop_event, wtm=False):
    thread = threading.Thread(target=loop, args=(svc, stop_event, wtm), daemon=True, name="gdw-supervisor")
    thread.start()
    return thread


def shutdown(wait=40, gdw=True, wtm=False):
    """서비스 종료 시: 워커도 정상 종료시킨다 (disabled.flag는 남기지 않음 → 다음 시작 때 자동 시작).
    두 모듈의 작업 프로세스를 동시에 멈춘다 (각자 진행 중인 작업을 마무리할 시간이 필요)."""
    threads = []
    if wtm:
        def _wtm():
            try:
                from wtm import service as wtm_service
                log.info("웹툰 작업 프로세스 종료 중…")
                wtm_service.shutdown(wait=wait)
            except Exception as error:
                log.warning("웹툰 작업 프로세스 종료 실패: %s", error)
        threads.append(threading.Thread(target=_wtm, daemon=True))
        threads[-1].start()
    if gdw and service._worker_alive():
        log.info("워커 종료 중…")
        if not service._stop_worker(disable=False, wait=wait):
            log.warning("워커가 %d초 안에 끝나지 않았습니다.", wait)
    for thread in threads:
        thread.join(wait + 5)
