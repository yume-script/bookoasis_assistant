# -*- coding: utf-8 -*-
"""BookOasis DB 중복 확인

새 파일(추가) 기록을 워커가 처리하기 전에, 같은 경로의 도서가 이미 BookOasis DB에 있으면
VFS 새로고침·스캔 없이 '이미 등록됨'으로 끝낸다.

플러그인일 때는 DB를 BookOasis 프로세스 안에서만 볼 수 있어서 Flask 앱 문맥을 빌려 오고,
여러 BookOasis 프로세스 중 하나만 돌도록 파일 잠금을 걸었다. 독립형은 DB에 직접 붙으므로
이 프로세스의 스레드 하나로 충분하다. 워커와의 약속(screener.json, event.screened)은 그대로다.
"""
import json
import logging
import sqlite3
import threading
import time

from . import bookoasis_db
from .service import _is_book_file, _path, _read_json, _write_json

log = logging.getLogger("gdw.screener")


def screen_once(runtime, state):
    libraries = sorted(runtime.get("libraries") or [], key=lambda lib: -max((len(r) for r in lib.get("roots") or [""]), default=0))

    def library_for(path):
        for lib in libraries:
            for root in lib.get("roots") or []:
                root = root.rstrip("/")
                if root and (path == root or path.startswith(root + "/")):
                    return lib
        return None

    db = sqlite3.connect(_path("state.db"), timeout=30)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute("SELECT id, root, action, item_type, path, force, created FROM event "
                          "WHERE status='pending' AND COALESCE(screened, 0)=0 ORDER BY id LIMIT 500").fetchall()
        if not rows:
            return 0
        dups, now = 0, time.strftime("%Y-%m-%dT%H:%M:%S")
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
        # 1) 확인할 기록을 고르고 세션(db_type)별로 모아 2) 한 번의 연결로 일괄 조회한다
        #    (예전: 기록마다 DB에 새로 접속 - 대기 기록이 수백 건이면 확인에만 수십 초가 걸려 처리 전체가 밀렸다)
        by_type = {}
        for row in rows:
            if (row["action"] == "create" and row["item_type"] == "file" and not row["force"]
                    and row["root"] != "수동 요청" and _is_book_file(row["path"])):
                lib = library_for(row["path"])
                # 같은 경로가 최근 1시간 안에 지워졌다면(다시 올림) 내용이 바뀌었을 수 있으니 중복으로 보지 않는다
                reupload = db.execute("SELECT 1 FROM event WHERE action IN ('delete','rename','move') "
                                      "AND removed_path=? AND created>=? LIMIT 1", (row["path"], since)).fetchone()
                if lib and not reupload:
                    by_type.setdefault(lib.get("db_type") or "general", set()).add(row["path"])
        registered = {}
        for db_type, paths in by_type.items():
            for found in bookoasis_db.gateway(db_type).fetch_in(
                    "SELECT id, file_path, COALESCE(is_deleted, 0) AS gone FROM books WHERE file_path IN ({marks})", sorted(paths)):
                if not int(found.get("gone") or 0):
                    registered[found["file_path"]] = found["id"]
        with db:  # 결과는 한 번에 기록 (기록마다 커밋하지 않음)
            for row in rows:
                dup = registered.get(row["path"]) if row["path"] in by_type.get(
                    (library_for(row["path"]) or {}).get("db_type") or "general", ()) else None
                if dup:
                    dups += 1
                    message = f"이미 BookOasis에 등록된 파일 (도서 #{dup}) · VFS 새로고침·스캔 생략"
                    result = {"vfs": [], "scans": [], "db_ok": True, "db_msg": f"도서 #{dup}", "dup": dup, "db_at": time.time()}
                    db.execute("UPDATE event SET status='skipped', screened=1, message=?, result=?, finished=? WHERE id=?",
                               (message, json.dumps(result, ensure_ascii=False), now, row["id"]))
                else:
                    db.execute("UPDATE event SET screened=1 WHERE id=?", (row["id"],))
        if dups:
            state["dups"] = [t for t in state.get("dups", []) if t >= time.time() - 3600] + [time.time()] * dups
        return len(rows)
    finally:
        db.close()


def _release_pending():
    """DB를 볼 수 없을 때 워커가 기다리지 않도록 확인 대기 중인 기록을 풀어 준다."""
    try:
        db = sqlite3.connect(_path("state.db"), timeout=30)
        with db:
            db.execute("UPDATE event SET screened=1 WHERE status='pending' AND COALESCE(screened, 0)=0")
        db.close()
    except sqlite3.Error:
        pass


def loop(stop_event):
    import os
    state = {"dups": []}
    last_error = None
    while not stop_event.is_set():
        runtime = _read_json("runtime.json", {}) or {}
        # DB가 없으면(보관함 파일로 사용) 사용 안 함으로 알린다 → 워커는 확인을 기다리지 않는다
        info = {"ts": time.time(), "enabled": bool(runtime.get("db_dedupe", True)) and bookoasis_db.configured(),
                "ok": True, "pid": os.getpid()}
        try:
            if info["enabled"] and os.path.exists(_path("state.db")):
                screen_once(runtime, state)
            last_error = None
        except Exception as error:
            info.update(ok=False, error=f"{type(error).__name__}: {error}"[:300])
            if info["error"] != last_error:
                log.warning("중복 확인 실패 (1분 뒤 다시): %s", info["error"])
                last_error = info["error"]
            _release_pending()
        info["dups_1h"] = sum(1 for t in state.get("dups", []) if t >= time.time() - 3600)
        try:
            _write_json("screener.json", info)
        except OSError:
            pass
        stop_event.wait(5 if info["ok"] else 60)


def start(stop_event):
    thread = threading.Thread(target=loop, args=(stop_event,), daemon=True, name="gdw-dedupe")
    thread.start()
    return thread
