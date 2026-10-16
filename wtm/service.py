# -*- coding: utf-8 -*-
"""app.py(웹 화면 프로세스)에서 웹툰 다운로더를 다루는 진입점.

플러그인 시절 BookOasis가 하던 일:
  - 화면 데이터 /api/media/dashboard/widgets/<id>/data      → dashboard()
  - 화면 동작 /api/media/context-menu/book/plugins/action   → action()
  - 화면을 열 때마다 스케줄러·작업 프로세스 확인             → tick() (감독 스레드가 30초마다, 화면을 안 열어도)
"""
import logging
import os
import threading

log = logging.getLogger("wtm")
_STATE = {"provider": None}
_LOCK = threading.Lock()
DB_TYPE = "general"  # 플러그인은 세션별 설정을 둘 수 있었지만 작업 프로세스는 늘 general 설정을 썼다 → 하나로


def provider():
    with _LOCK:
        if _STATE["provider"] is None:
            os.environ["WTM_HOST"] = "1"
            from . import host
            if host.migrate_plugin_data():
                log.info("플러그인 데이터 폴더의 설정(worker_cfg.json)을 settings.json과 .env로 옮겼습니다.")
            from .webtoon_manager import WebtoonManagerMetadataProvider
            _STATE["provider"] = WebtoonManagerMetadataProvider()
        return _STATE["provider"]


def dashboard():
    return provider().get_dashboard_data(DB_TYPE, limit=5000)


def action(action_id, context):
    if not isinstance(action_id, str) or not action_id.replace("_", "").isalnum():
        return {"success": False, "error": "알 수 없는 동작: %s" % action_id}
    return provider().run_context_menu_action(DB_TYPE, action_id, context or {})


def tick():
    p = provider()
    return p._ensure_background(DB_TYPE, p._get_cfg(DB_TYPE))


def shutdown(wait=40):
    if _STATE["provider"] is None:
        return
    from . import state_store, worker_ctl
    try:
        state_store.flush_titles()
    except Exception:  # noqa: BLE001
        pass
    if not worker_ctl.stop(wait=wait):
        log.warning("웹툰 작업 프로세스가 %d초 안에 끝나지 않았습니다.", wait)
