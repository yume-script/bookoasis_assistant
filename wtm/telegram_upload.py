# -*- coding: utf-8 -*-
"""받은 회차 파일을 텔레그램 채널에 올리기 (독립형 추가 기능)

흐름
  회차 zip/epub이 저장 경로에 들어감 (downloader._move_into_library / kakao_pipeline 웹소설)
    → host.file_ready() → enqueue(): 대기열(telegram_upload.db)에 넣기만 한다 (다운로드를 막지 않음, 어느 프로세스에서든)
    → 관리 화면 프로세스(app.py)의 업로드 스레드가 하나씩 sendDocument로 올린다
       - 재시작해도 대기열이 남아 이어서 올림
       - 429(속도 제한)는 텔레그램이 알려 준 시간만큼 쉬고, 그 밖의 실패는 1분부터 두 배씩(최대 1시간) 8번까지 재시도
       - 크기 제한(기본 50MB, 공식 Bot API 한도)을 넘는 파일은 올리지 않고 '건너뜀'으로 남김.
         로컬 Bot API 서버(telegram-bot-api)를 쓰면 TELEGRAM_UPLOAD_API_URL과 최대 크기(최대 2000MB)를 바꾼다.

설정 (화면 [설정] > [공통] > 텔레그램 채널 업로드)
  TELEGRAM_UPLOAD_ENABLE      켜기 (settings.json)
  TELEGRAM_UPLOAD_CHAT_ID     채널 ID(-100…) 또는 @채널이름 (.env WTM_TELEGRAM_UPLOAD_CHAT_ID)
  TELEGRAM_UPLOAD_BOT_TOKEN   봇 토큰. 비우면 알림용 NOTIFY_TELEGRAM_BOT_TOKEN (.env)
  TELEGRAM_UPLOAD_API_URL     Bot API 주소. 비우면 https://api.telegram.org (.env)
  TELEGRAM_UPLOAD_MAX_MB      올릴 최대 크기 (settings.json, 기본 50)
봇을 그 채널의 관리자로 추가하고 '메시지 보내기' 권한을 줘야 한다.
"""
import html
import logging
import os
import re
import sqlite3
import threading
import time

from . import host

log = logging.getLogger("wtm.telegram")
DB_PATH = os.path.join(host.DATA_DIR, "telegram_upload.db")
UPLOAD_EXTS = {".zip", ".cbz", ".epub"}
DEFAULT_API = "https://api.telegram.org"
OFFICIAL_LIMIT_MB = 50
MAX_ATTEMPTS = 8
GAP_SECONDS = 3.0          # 업로드 사이 간격 (채널은 분당 20개 정도가 한도)
_LOCK = threading.Lock()
_STATE = {"thread": None}


def _truthy(v):
    return v if isinstance(v, bool) else str(v or "").strip().lower() in ("1", "true", "on", "yes")


def settings(cfg=None):
    cfg = cfg if cfg is not None else host.load_settings()
    try:
        max_mb = float(cfg.get("TELEGRAM_UPLOAD_MAX_MB") or OFFICIAL_LIMIT_MB)
    except (TypeError, ValueError):
        max_mb = OFFICIAL_LIMIT_MB
    return {
        "enabled": _truthy(cfg.get("TELEGRAM_UPLOAD_ENABLE")),
        "chat": str(cfg.get("TELEGRAM_UPLOAD_CHAT_ID") or "").strip(),
        "token": str(cfg.get("TELEGRAM_UPLOAD_BOT_TOKEN") or cfg.get("NOTIFY_TELEGRAM_BOT_TOKEN") or "").strip(),
        "api": (str(cfg.get("TELEGRAM_UPLOAD_API_URL") or "").strip() or DEFAULT_API).rstrip("/"),
        "max_bytes": int(max(1.0, min(2000.0, max_mb)) * 1024 * 1024),
    }


def ready(s):
    return s["enabled"] and s["chat"] and s["token"]


def _db():
    os.makedirs(host.DATA_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("""CREATE TABLE IF NOT EXISTS upload (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, status TEXT DEFAULT 'pending',
        attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, message_id INTEGER, error TEXT,
        created REAL, finished REAL)""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_upload_status ON upload(status, next_at)")
    return db


def enqueue(path):
    """회차 파일을 대기열에 넣는다. 반환: 넣었는지. 같은 경로는 한 번만 (다시 받은 경우 다시 올림)."""
    path = str(path or "")
    if os.path.splitext(path)[1].lower() not in UPLOAD_EXTS:
        return False
    if not ready(settings()):
        return False
    db = _db()
    try:
        with db:
            db.execute("INSERT INTO upload(path, created) VALUES(?, ?) ON CONFLICT(path) DO UPDATE SET "
                       "status='pending', attempts=0, next_at=0, error=NULL, created=excluded.created "
                       "WHERE upload.status != 'pending'", (path, time.time()))
    except sqlite3.Error as error:
        log.warning("텔레그램 업로드 대기열에 넣지 못함: %s", error)
        return False
    finally:
        db.close()
    return True


def _hashtag(text):
    tag = re.sub(r"[^\w가-힣]+", "_", text).strip("_")
    return "#" + tag if tag else ""


def caption_for(path):
    """캡션: #작품명 해시태그(채널에서 작품별로 찾기) + 파일 이름."""
    series = os.path.basename(os.path.dirname(path))
    name = os.path.splitext(os.path.basename(path))[0]
    parts = [p for p in (_hashtag(series), html.escape(name)) if p]
    return "\n".join(parts)[:1000]


def _send(s, path):
    """반환 (결과, 메시지, message_id, retry_after). 결과: ok | skip | retry | fail"""
    import requests
    try:
        size = os.path.getsize(path)
    except OSError:
        return "skip", "파일이 없어짐", None, 0
    if size > s["max_bytes"]:
        return "skip", "크기 %.1fMB가 한도 %dMB를 넘음 (로컬 Bot API 서버면 최대 크기를 올리세요)" % (
            size / 1048576, s["max_bytes"] // 1048576), None, 0
    url = "%s/bot%s/sendDocument" % (s["api"], s["token"])
    try:
        with open(path, "rb") as f:
            r = requests.post(url, data={"chat_id": s["chat"], "caption": caption_for(path), "parse_mode": "HTML",
                                         "disable_notification": "true"},
                              files={"document": (os.path.basename(path), f)}, timeout=(15, 600))
    except requests.RequestException as e:
        return "retry", "연결 오류: %s" % e, None, 0
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code == 200 and body.get("ok"):
        return "ok", "", (body.get("result") or {}).get("message_id"), 0
    desc = str(body.get("description") or r.text[:200])
    if r.status_code == 429:
        return "retry", desc, None, int((body.get("parameters") or {}).get("retry_after") or 30)
    if r.status_code == 413 or "too big" in desc.lower():
        return "skip", "텔레그램이 너무 크다고 거절: " + desc, None, 0
    if r.status_code in (400, 401, 403, 404):  # 채널/토큰/권한 문제는 설정을 고칠 때까지 길게 쉬며 재시도
        return "retry", "HTTP %s %s" % (r.status_code, desc), None, 600
    return "retry", "HTTP %s %s" % (r.status_code, desc), None, 0


def process_once():
    """대기열에서 하나 올린다. 반환: 처리했는지."""
    s = settings()
    if not ready(s):
        return False
    db = _db()
    try:
        row = db.execute("SELECT * FROM upload WHERE status='pending' AND next_at<=? ORDER BY id LIMIT 1",
                         (time.time(),)).fetchone()
        if not row:
            return False
        result, message, message_id, retry_after = _send(s, row["path"])
        now = time.time()
        with db:
            if result == "ok":
                db.execute("UPDATE upload SET status='done', message_id=?, error=NULL, finished=? WHERE id=?",
                           (message_id, now, row["id"]))
            elif result == "skip":
                db.execute("UPDATE upload SET status='skipped', error=?, finished=? WHERE id=?", (message, now, row["id"]))
                _log_job("텔레그램 업로드 건너뜀: %s (%s)" % (os.path.basename(row["path"]), message))
            else:
                attempts = row["attempts"] + 1
                if attempts >= MAX_ATTEMPTS and not retry_after:
                    db.execute("UPDATE upload SET status='failed', attempts=?, error=?, finished=? WHERE id=?",
                               (attempts, message, now, row["id"]))
                    _log_job("텔레그램 업로드 실패(포기): %s (%s)" % (os.path.basename(row["path"]), message))
                else:
                    wait = retry_after or min(3600, 60 * 2 ** (attempts - 1))
                    db.execute("UPDATE upload SET attempts=?, error=?, next_at=? WHERE id=?",
                               (attempts if not retry_after else row["attempts"], message, now + wait, row["id"]))
                    if attempts == 1 or retry_after >= 600:
                        _log_job("텔레그램 업로드 다시 시도 예정(%d초 뒤): %s (%s)"
                                 % (wait, os.path.basename(row["path"]), message))
        return True
    finally:
        db.close()


def _log_job(text):
    log.info(text)
    try:
        from . import state_store
        state_store.append_log(text)
    except Exception:  # noqa: BLE001
        pass


def counts():
    if not os.path.exists(DB_PATH):
        return {}
    db = _db()
    try:
        return {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM upload GROUP BY status")}
    finally:
        db.close()


def retry_failed(include_skipped=False):
    """실패한(또는 건너뛴) 업로드를 다시 대기열로, 재시도를 기다리던 것은 바로. 설정을 저장할 때 부른다."""
    if not os.path.exists(DB_PATH):
        return 0
    statuses = ("failed", "skipped") if include_skipped else ("failed",)
    db = _db()
    try:
        with db:
            db.execute("UPDATE upload SET next_at=0 WHERE status='pending'")
            return db.execute("UPDATE upload SET status='pending', attempts=0, next_at=0, error=NULL WHERE status IN (%s)"
                              % ",".join("?" * len(statuses)), statuses).rowcount
    finally:
        db.close()


def test(cfg=None):
    """설정 확인: 업로드 채널에 글 하나를 보낸다. 반환 (ok, 메시지)."""
    import requests
    s = settings(cfg)
    if not s["enabled"]:
        return None, "꺼짐"
    if not s["chat"] or not s["token"]:
        return False, "채널 ID 또는 봇 토큰 없음"
    try:
        r = requests.post("%s/bot%s/sendMessage" % (s["api"], s["token"]),
                          data={"chat_id": s["chat"], "text": "📤 웹툰 다운로더: 이 채널로 받은 회차 파일을 올립니다.",
                                "disable_notification": "true"}, timeout=15)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except (requests.RequestException, ValueError) as e:
        return False, str(e)
    if r.status_code == 200 and body.get("ok"):
        return True, "ok"
    return False, "HTTP %s %s" % (r.status_code, body.get("description") or r.text[:150])


def _loop(stop_event):
    while not stop_event.is_set():
        try:
            did = process_once()
        except Exception as error:  # noqa: BLE001 - 업로드 스레드는 죽지 않게
            log.warning("텔레그램 업로드 처리 오류: %s", error)
            did = False
        stop_event.wait(GAP_SECONDS if did else 5)


def start(stop_event):
    """관리 화면 프로세스에서 한 번 (app.py). 설정이 꺼져 있으면 스레드는 대기만 한다."""
    with _LOCK:
        if _STATE["thread"] and _STATE["thread"].is_alive():
            return _STATE["thread"]
        thread = threading.Thread(target=_loop, args=(stop_event,), daemon=True, name="wtm-telegram-upload")
        thread.start()
        _STATE["thread"] = thread
        return thread
