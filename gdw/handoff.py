# -*- coding: utf-8 -*-
"""다른 모듈(웹툰 다운로더)이 라이브러리에 넣은 파일을 드라이브 변경 감시 처리 대기열에 바로 넣는다.

Drive 변경 감지(Changes/폴더 비교)를 기다리지 않고 VFS 새로고침 → 파일 확인 → BookOasis 부분 스캔을 태운다.
감시 폴더가 감지하는 것과 같은 방식(ready_at = 지금 + 모아서 처리 시간)으로 넣으므로, 같은 폴더에 연달아 들어오는
회차는 워커의 '폴더가 조용해질 때까지' 처리에 묶여 새로고침·스캔이 한 번으로 끝난다.
나중에 Drive 쪽에서 같은 파일을 감지해도 그때는 이미 BookOasis에 등록돼 있어 '이미 등록된 파일'로 건너뛴다.

작업 프로세스(다른 프로세스)에서도 부르므로 state.db에 직접 쓴다 (SQLite 잠금으로 워커와 안전하게 공유).
"""
import json
import os
import sqlite3
import time
from datetime import datetime

from . import config


def _data_dir():
    return config.data_dir()


def _runtime():
    try:
        with open(os.path.join(_data_dir(), "runtime.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _in_library(path, runtime):
    for lib in runtime.get("libraries") or []:
        for root in lib.get("roots") or []:
            root = str(root).rstrip("/")
            if root and (path == root or path.startswith(root + "/")):
                return True
    return False


def enqueue(path, source="웹툰 다운로더", action="create"):
    """반환: 넣었는지. 보관함 밖 경로, 드라이브 변경 감시를 쓰지 않는 경우(state.db 없음)는 넣지 않는다."""
    path = os.path.normpath(str(path or ""))
    db_path = os.path.join(_data_dir(), "state.db")
    if not path.startswith("/") or not os.path.exists(db_path):
        return False
    runtime = _runtime()
    if not _in_library(path, runtime):
        return False
    buffer_seconds = max(0, int(runtime.get("buffer_seconds", 60) or 0))
    db = sqlite3.connect(db_path, timeout=30)
    try:
        db.execute("PRAGMA busy_timeout=30000")
        with db:
            # 같은 파일이 아직 처리 대기 중이면 또 넣지 않는다
            if db.execute("SELECT 1 FROM event WHERE path=? AND status IN ('pending','waiting') LIMIT 1",
                          (path,)).fetchone():
                return False
            db.execute("INSERT INTO event(root, action, item_type, path, removed_path, created, ready_at) "
                       "VALUES(?,?,?,?,?,?,?)",
                       (source, action, "file", path, path if action == "delete" else "",
                        datetime.now().isoformat(timespec="seconds"), time.time() + buffer_seconds))
    except sqlite3.Error:
        return False
    finally:
        db.close()
    return True
