#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""드라이브 변경 감시 (독립형) 진입점

  python3 app.py            관리 화면 + 워커 감독 + DB 중복 확인 (상주)
  python3 app.py --check    설정만 점검하고 끝냄 (.env, rclone, BookOasis DB/토큰)

설정은 .env (env.example 참고). 워커(worker.py)는 이 프로세스의 자식으로 돈다.
"""
import ipaddress
import logging
import os
import signal
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()  # gdw.service가 DATA_DIR을 정하기 전에

from gdw import bookoasis_db, screener, service, supervisor  # noqa: E402
from gdw.web import make_server  # noqa: E402

log = logging.getLogger("gdw")


def _is_loopback(host):
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check(svc):
    """설정 점검 결과를 출력한다. 문제가 있으면 종료 코드 1."""
    problems = 0
    settings = config.settings()
    print(f".env            : {config.ENV_PATH}" + ("" if os.path.exists(config.ENV_PATH) else "  (없음 - env.example을 복사하세요)"))
    print(f"DATA_DIR        : {service.DATA_DIR}")
    print(f"rclone          : {settings['rclone_path']}  (설정 파일: {settings['rclone_config'] or 'rclone 기본 위치'})")
    if settings["rclone_config"] and not os.path.isfile(settings["rclone_config"]):
        print("  ✗ rclone.conf를 찾을 수 없습니다.")
        problems += 1
    if bookoasis_db.configured():
        for db_type in config.db_types():
            url = config.db_url(db_type)
            if not url:
                continue
            try:
                n = len(bookoasis_db.gateway(db_type).fetch_all("SELECT id FROM libraries"))
                print(f"BookOasis DB    : {db_type:<9} ✓ 보관함 {n}개  ({bookoasis_db.describe(url)})")
            except Exception as error:
                print(f"BookOasis DB    : {db_type:<9} ✗ {error}  ({bookoasis_db.describe(url)})")
                problems += 1
    else:
        libs = svc._manual_libraries() if os.path.exists(config.libraries_file()) else []
        print(f"보관함           : BookOasis DB 없음 → 보관함 파일 {config.libraries_file()} ({len(libs)}개)")
        if not libs:
            print("  ✗ 보관함이 없어 변경을 감지해도 스캔하지 않습니다.")
            problems += 1
    ok, message = service._verify_token(settings["bookoasis_url"], settings["webhook_token"])
    print(f"스캔 요청        : {settings['bookoasis_url']}  {'✓' if ok else '✗'} {message}")
    problems += 0 if ok else 1
    return 1 if problems else 0


def main():
    level = getattr(logging, config.env("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    os.makedirs(service.DATA_DIR, exist_ok=True)
    svc = service.Service()
    moved = svc.migrate_plugin_env()
    if moved:
        log.info("플러그인 시절 watch.json의 실행 환경을 .env로 옮겼습니다: %s", ", ".join(moved))
    if "--check" in sys.argv:
        return check(svc)

    host = config.env("WEB_HOST", "127.0.0.1") or "127.0.0.1"
    port = config.env_int("WEB_PORT", 5931)
    if not config.env("WEB_PASSWORD") and not _is_loopback(host) and not config.env_bool("WEB_ALLOW_NO_AUTH"):
        log.error("WEB_PASSWORD 없이 %s에 열 수 없습니다 (토큰·rclone 설정을 바꿀 수 있는 화면). "
                  ".env에 WEB_PASSWORD를 넣거나 WEB_HOST=127.0.0.1로 두세요.", host)
        return 2

    stop_event = threading.Event()
    svc._sync_runtime(force_libraries=True)
    screener.start(stop_event)
    supervisor.start(svc, stop_event)
    server = make_server(svc, host, port)

    def on_signal(signum, _frame):
        log.info("종료 신호(%s)를 받았습니다.", signal.Signals(signum).name)
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    log.info("관리 화면: http://%s:%d/  (데이터: %s, 보관함: %s)", host, port, service.DATA_DIR,
             "BookOasis DB" if bookoasis_db.configured() else config.libraries_file())
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.server_close()
        supervisor.shutdown()
    log.info("종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
