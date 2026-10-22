#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BookOasis 보조 프로그램 (독립형) 진입점 - 웹툰 다운로더 (+ 드라이브 변경 감시 · 미니게임)

  python3 app.py            관리 화면 + 작업 프로세스 감독 + DB 중복 확인 (상주)
  python3 app.py --check    설정만 점검하고 끝냄 (.env, rclone, BookOasis DB/토큰, 웹툰 경로)

설정은 .env (env.example 참고). 모듈은 WTM_ENABLED / GDW_ENABLED / MINI_ENABLED로 켜고 끈다 (웹툰 다운로더가 기본·첫 화면).
각 모듈의 무거운 일은 따로 도는 작업 프로세스가 한다 (웹툰: wtm/worker_main.py, 드라이브 감시: worker.py).
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

from gdw import auth, bookoasis_db, screener, service, supervisor  # noqa: E402
from gdw.web import make_server, modules  # noqa: E402

log = logging.getLogger("gdw")


def _is_loopback(host):
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def kakao_accounts_text(cfg):
    """카카오 쿠키가 저장된 계정 번호 (.env의 WTM_KAKAO_COOKIE, WTM_KAKAO_COOKIE_2~5)"""
    keys = ("KAKAO_COOKIE", "KAKAO_COOKIE_2", "KAKAO_COOKIE_3", "KAKAO_COOKIE_4", "KAKAO_COOKIE_5")
    nums = [str(i) for i, k in enumerate(keys, start=1) if str(cfg.get(k) or "").strip()]
    return ("계정 " + ", ".join(nums)) if nums else "없음"


def check_wtm():
    from wtm import host
    problems = 0
    if host.migrate_plugin_data():
        print("웹툰 설정        : 플러그인 데이터의 worker_cfg.json을 settings.json과 .env로 옮겼습니다.")
    cfg = host.load_settings()
    print(f"웹툰 데이터       : {host.DATA_DIR}  (설정 {host.SETTINGS_PATH}"
          + ("" if os.path.exists(host.SETTINGS_PATH) else ", 아직 없음 - 화면에서 저장하면 생김") + ")")
    for key, label in (("DOWNLOAD_ROOT", "네이버 저장"), ("KAKAO_DOWNLOAD_ROOT", "카카오 저장"),
                       ("KAKAO_NOVEL_DOWNLOAD_ROOT", "웹소설 저장"), ("TEMP_DOWNLOAD_ROOT", "임시 작업")):
        path = cfg.get(key)
        if not path:
            continue
        ok = os.path.isdir(path) and os.access(path, os.W_OK)
        print(f"  {label:<10}: {path}  {'✓' if ok else '✗ 없거나 쓸 수 없음'}")
        problems += 0 if ok else 1
    print(f"  쿠키          : 네이버 {'있음' if cfg.get('NAVER_COOKIE_JSON') else '없음'} · "
          f"카카오 {kakao_accounts_text(cfg)}")
    try:
        import requests  # noqa: F401
    except ImportError:
        print("  ✗ requests가 없습니다: pip install -r requirements.txt")
        problems += 1
    return problems


def check(svc):
    """설정 점검 결과를 출력한다. 문제가 있으면 종료 코드 1."""
    problems = 0
    mods = modules()
    print(f"모듈            : 웹툰 다운로더 {'켬' if mods['wtm'] else '끔'} · 드라이브 변경 감시 {'켬' if mods['gdw'] else '끔'}"
          f" · 미니게임 {'켬' if mods['mini'] else '끔'}")
    settings = config.settings()
    print(f".env            : {config.ENV_PATH}" + ("" if os.path.exists(config.ENV_PATH) else "  (없음 - env.example을 복사하세요)"))
    print(f"DATA_DIR        : {service.DATA_DIR}")
    if mods["gdw"]:  # rclone은 드라이브 변경 감시에서만 쓴다
        print(f"rclone          : {settings['rclone_path']}  (설정 파일: {settings['rclone_config'] or 'rclone 기본 위치'})")
    if mods["gdw"] and settings["rclone_config"] and not os.path.isfile(settings["rclone_config"]):
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
        if not libs and mods["gdw"]:
            print("  ✗ 보관함이 없어 변경을 감지해도 스캔하지 않습니다.")
            problems += 1
    if mods["wtm"]:
        problems += check_wtm()
    if mods["gdw"]:
        ok, message = service._verify_token(settings["bookoasis_url"], settings["webhook_token"])
        print(f"스캔 요청        : {settings['bookoasis_url']}  {'✓' if ok else '✗'} {message}")
        problems += 0 if ok else 1
    return 1 if problems else 0


def main():
    level = getattr(logging, config.env("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    os.makedirs(service.DATA_DIR, exist_ok=True)
    mods = modules()
    svc = service.Service()
    moved = svc.migrate_plugin_env()
    if moved:
        log.info("플러그인 시절 watch.json의 실행 환경을 .env로 옮겼습니다: %s", ", ".join(moved))
    if "--check" in sys.argv:
        return check(svc)
    if not mods["gdw"]:
        svc = None

    host = config.env("WEB_HOST", "127.0.0.1") or "127.0.0.1"
    port = config.env_int("WEB_PORT", 5931)
    if auth.bootstrap_from_env():  # 사용자가 없으면 .env의 WEB_USER/WEB_PASSWORD로 첫 관리자를 만든다
        log.info("로그인 계정 '%s'을(를) .env의 WEB_USER/WEB_PASSWORD로 만들었습니다. 이후 비밀번호는 화면에서 바꿉니다.",
                 config.env("WEB_USER", "admin") or "admin")
    if auth.needs_setup() and not _is_loopback(host) and not config.env_bool("WEB_ALLOW_NO_AUTH"):
        # 계정이 없으면 처음 연 사람이 관리자를 만들 수 있으므로 외부에 그대로 열지 않는다
        log.error("로그인 계정이 없어 %s에 열 수 없습니다 (토큰·rclone 설정을 바꿀 수 있는 화면). "
                  ".env에 WEB_USER/WEB_PASSWORD를 넣어 첫 관리자를 만들거나, WEB_HOST=127.0.0.1로 열어 화면에서 만드세요.", host)
        return 2

    stop_event = threading.Event()
    if svc is not None:
        svc._sync_runtime(force_libraries=True)
        screener.start(stop_event)
    if mods["wtm"]:
        from wtm import service as wtm_service, telegram_upload
        wtm_service.provider()  # 설정 이전(플러그인 데이터) + 스케줄러·작업 프로세스 시작
        telegram_upload.start(stop_event)  # 받은 회차 → 텔레그램 채널 (켰을 때만 실제로 올림)
    supervisor.start(svc, stop_event, wtm=mods["wtm"])
    server = make_server(svc, host, port)

    def on_signal(signum, _frame):
        log.info("종료 신호(%s)를 받았습니다.", signal.Signals(signum).name)
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    log.info("관리 화면: http://%s:%d/  (데이터: %s, 보관함: %s, 모듈: %s)", host, port, service.DATA_DIR,
             "BookOasis DB" if bookoasis_db.configured() else config.libraries_file(),
             ", ".join(name for name, on in (("웹툰 다운로더", mods["wtm"]), ("드라이브 변경 감시", mods["gdw"]),
                                             ("미니게임", mods["mini"])) if on))
    if mods["wtm"]:  # 재시작 뒤 어떤 카카오 계정 쿠키가 살아 있는지 로그로 바로 확인할 수 있게
        try:
            from wtm import host as wtm_host
            log.info("웹툰 다운로더 카카오 쿠키: %s", kakao_accounts_text(wtm_host.load_settings()))
        except Exception:  # noqa: BLE001
            pass
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        server.server_close()
        supervisor.shutdown(gdw=svc is not None, wtm=mods["wtm"])
    log.info("종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
