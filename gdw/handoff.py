# -*- coding: utf-8 -*-
"""다른 모듈(웹툰 다운로더)이 라이브러리에 넣은 파일을 드라이브 변경 감시 처리 대기열에 바로 넣는다.

Drive 변경 감지(Changes/폴더 비교)를 기다리지 않고 VFS 새로고침 → 파일 확인 → BookOasis 부분 스캔을 태운다.
- 바로 스캔(WTM_SCAN_IMMEDIATE, 기본 켬): 모으지 않고 곧바로 처리한다. 받은 회차가 바로 BookOasis에 등록되고
  메타데이터가 붙는다. 회차마다 그 작품 폴더를 부분 스캔하므로 BookOasis 스캔 횟수는 늘어난다.
  (처리 대기열에 이미 있는 같은 폴더의 기록은 한 번에 묶여 처리된다)
- 끄면: 감시 폴더가 감지하는 것과 같은 방식(지금 + 모아서 처리 시간)이라, 같은 폴더에 연달아 들어오는
  회차는 워커의 '폴더가 조용해질 때까지' 처리에 묶여 새로고침·스캔이 한 번으로 끝난다(최대 대기 시간까지 늦어질 수 있음).
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
    immediate = config.env_bool("WTM_SCAN_IMMEDIATE", True)
    buffer_seconds = 0 if immediate else max(0, int(runtime.get("buffer_seconds", 60) or 0))
    db = sqlite3.connect(db_path, timeout=30)
    try:
        db.execute("PRAGMA busy_timeout=30000")
        with db:
            # 같은 파일이 아직 처리 대기 중이면 또 넣지 않는다
            if db.execute("SELECT 1 FROM event WHERE path=? AND status IN ('pending','waiting') LIMIT 1",
                          (path,)).fetchone():
                return False
            # 바로 스캔: force=1(폴더 모으기·전체 스캔 회피를 건너뜀), screened=1(방금 받은 새 파일이라 DB 중복 확인 불필요)
            db.execute("INSERT INTO event(root, action, item_type, path, removed_path, created, ready_at, force, screened) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (source, action, "file", path, path if action == "delete" else "",
                        datetime.now().isoformat(timespec="seconds"), time.time() + buffer_seconds,
                        1 if immediate else 0, 1 if immediate else 0))
    except sqlite3.Error:
        return False
    finally:
        db.close()
    if immediate:  # 워커가 쉬는 중이면 바로 깨워 처리하게 (wake.flag와 달리 Drive 변경 확인은 다시 하지 않음)
        try:
            open(os.path.join(_data_dir(), "process.flag"), "w").close()
        except OSError:
            pass
    return True
