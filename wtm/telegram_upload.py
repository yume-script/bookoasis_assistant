# -*- coding: utf-8 -*-
"""고른 작품의 회차 파일을 텔레그램 채널에 올리기 (독립형 추가 기능)

작품 카드의 📤 버튼으로 작품마다 켜고 끈다 (작품 정보의 telegram_upload 표시).
  - 켜면: 그 작품 폴더에 이미 있는 회차를 회차 순서대로 전부 대기열에 넣는다 (이미 올린 회차는 다시 올리지 않음)
  - 켜 둔 작품의 새 회차가 저장 경로에 들어오면 (downloader._move_into_library / kakao_pipeline 웹소설)
    host.file_ready() → enqueue()가 대기열에 추가한다. 켜지 않은 작품은 올리지 않는다.
  - 끄면: 아직 올리지 않은(대기 중인) 회차를 대기열에서 뺀다
작품 폴더 이름은 '제목 (작품ID)'이고(downloader.title_dir), 이 ID로 파일 → 작품을 찾는다.

흐름
  대기열(telegram_upload.db)에 넣기만 한다 (다운로드를 막지 않음, 어느 프로세스에서든)
    → 관리 화면 프로세스(app.py)의 업로드 스레드가 하나씩 sendDocument로 올린다
       - 재시작해도 대기열이 남아 이어서 올림
       - 429(속도 제한)는 텔레그램이 알려 준 시간만큼 쉬고, 그 밖의 실패는 1분부터 두 배씩(최대 1시간) 8번까지 재시도
       - 크기 제한(기본 50MB, 공식 Bot API 한도)을 넘는 파일은 올리지 않고 '건너뜀'으로 남김.
         로컬 Bot API 서버(telegram-bot-api)를 쓰면 TELEGRAM_UPLOAD_API_URL과 최대 크기(최대 2000MB)를 바꾼다.

설정 (화면 [설정] > [공통] > 텔레그램 채널 업로드)
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
YAML_NAME = "kavita.yaml"   # kavita_yaml.YAML_NAME - 작품 정보. 채널에는 '작품명.yaml'로 올린다
DEFAULT_API = "https://api.telegram.org"
OFFICIAL_LIMIT_MB = 50
MAX_ATTEMPTS = 8
GAP_SECONDS = 3.0          # 업로드 사이 간격 (채널은 분당 20개 정도가 한도)
_LOCK = threading.Lock()
_STATE = {"thread": None}


def settings(cfg=None):
    cfg = cfg if cfg is not None else host.load_settings()
    try:
        max_mb = float(cfg.get("TELEGRAM_UPLOAD_MAX_MB") or OFFICIAL_LIMIT_MB)
    except (TypeError, ValueError):
        max_mb = OFFICIAL_LIMIT_MB
    return {
        "chat": str(cfg.get("TELEGRAM_UPLOAD_CHAT_ID") or "").strip(),
        "token": str(cfg.get("TELEGRAM_UPLOAD_BOT_TOKEN") or cfg.get("NOTIFY_TELEGRAM_BOT_TOKEN") or "").strip(),
        "api": (str(cfg.get("TELEGRAM_UPLOAD_API_URL") or "").strip() or DEFAULT_API).rstrip("/"),
        "max_bytes": int(max(1.0, min(2000.0, max_mb)) * 1024 * 1024),
    }


def ready(s):
    return bool(s["chat"] and s["token"])


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


_ID_RE = re.compile(r"\(([^()]+)\)\s*$")


def _is_episode(path):
    return os.path.splitext(str(path or ""))[1].lower() in UPLOAD_EXTS


def title_of(path, cfg=None):
    """회차 파일 경로 → (platform, title_id, 작품 정보) 또는 None. 폴더 이름 끝의 (작품ID)와 저장 경로로 찾는다."""
    from . import state_store as ss
    series_dir = os.path.dirname(os.path.abspath(path))
    m = _ID_RE.search(os.path.basename(series_dir))
    if not m:
        return None
    tid = m.group(1).strip()
    parent = os.path.normpath(os.path.dirname(series_dir))
    cfg = cfg if cfg is not None else host.load_settings()
    naver_root = os.path.normpath(cfg.get("DOWNLOAD_ROOT") or ss.DOWNLOAD_DEFAULT_DIR)
    order = (("naver", ss.get_title), ("kakao", ss.get_kakao_title))
    if parent != naver_root:  # 네이버 저장 경로가 아니면 카카오(웹툰·웹소설)부터
        order = order[::-1]
    for platform, getter in order:
        t = getter(tid)
        if t:
            return platform, tid, t
    return None


def _series_name(series_dir):
    """작품 폴더 이름 '제목 (작품ID)' → '제목'"""
    return _ID_RE.sub("", os.path.basename(os.path.normpath(series_dir))).strip() or os.path.basename(series_dir)


def upload_name(path):
    """채널에 올릴 파일 이름: kavita.yaml은 '작품명.yaml', 회차 파일은 그대로"""
    if os.path.basename(path) == YAML_NAME:
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", _series_name(os.path.dirname(path))).strip(" .") or "kavita"
        return name + ".yaml"
    return os.path.basename(path)


def _yaml_once(db, series_dir):
    """작품 정보(kavita.yaml)를 아직 대기열에 넣은 적이 없으면 넣는다 (작품당 한 번). 반환: 넣었는지"""
    path = os.path.join(series_dir, YAML_NAME)
    if not os.path.isfile(path):
        return False
    return _insert(db, [path]) > 0


def _insert(db, paths):
    now, added = time.time(), 0
    for path in paths:
        # 이미 올린 회차는 그대로, 실패·건너뜀이었으면 다시
        cur = db.execute("INSERT INTO upload(path, created) VALUES(?, ?) ON CONFLICT(path) DO UPDATE SET "
                         "status='pending', attempts=0, next_at=0, error=NULL WHERE upload.status IN ('failed', 'skipped')",
                         (path, now))
        added += cur.rowcount
    return added


def enqueue(path):
    """새 회차가 저장 경로에 들어왔을 때: 📤를 켠 작품이면 대기열에 넣는다. 반환: 넣었는지."""
    path = str(path or "")
    if not _is_episode(path):
        return False
    found = title_of(path)
    if not found or not found[2].get("telegram_upload"):
        return False
    db = _db()
    try:
        with db:
            _yaml_once(db, os.path.dirname(path))  # 새 작품이면 첫 회차와 함께 작품 정보도 (이미 넣었으면 그대로)
            return _insert(db, [path]) > 0
    except sqlite3.Error as error:
        log.warning("텔레그램 업로드 대기열에 넣지 못함: %s", error)
        return False
    finally:
        db.close()


def _episode_key(name):
    """회차 순서: 파일 이름 속 숫자를 숫자로 비교 ('제목 0012화#3.zip' → 12화가 9화 뒤)."""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", name)]


def series_dir_for(platform, tid, t, cfg=None):
    from . import downloader, kakao_pipeline, state_store as ss
    cfg = cfg if cfg is not None else host.load_settings()
    root = (kakao_pipeline.series_root(cfg, t) if platform == "kakao"
            else (cfg.get("DOWNLOAD_ROOT") or ss.DOWNLOAD_DEFAULT_DIR))
    return downloader.title_dir(root, t.get("title") or tid, tid)


def add_title(platform, tid, t, cfg=None):
    """📤를 켰을 때: 작품 폴더의 회차를 회차 순서대로 대기열에 넣는다. 반환 (넣은 수, 폴더 안 회차 수, 폴더)."""
    series_dir = series_dir_for(platform, tid, t, cfg)
    try:
        names = sorted((n for n in os.listdir(series_dir) if _is_episode(n) and not n.startswith(".")), key=_episode_key)
    except OSError:
        names = []
    db = _db()
    try:
        with db:
            _yaml_once(db, series_dir)   # 작품 정보(작품명.yaml)를 회차보다 먼저
            added = _insert(db, [os.path.join(series_dir, n) for n in names])
    finally:
        db.close()
    return added, len(names), series_dir


def remove_title(platform, tid, t, cfg=None):
    """📤를 껐을 때: 아직 올리지 않은 회차를 대기열에서 뺀다. 반환: 뺀 수."""
    if not os.path.exists(DB_PATH):
        return 0
    prefix = series_dir_for(platform, tid, t, cfg).rstrip("/") + "/"
    db = _db()
    try:
        with db:
            return db.execute("DELETE FROM upload WHERE status='pending' AND substr(path, 1, ?) = ?",
                              (len(prefix), prefix)).rowcount
    finally:
        db.close()


def _hashtag(text):
    tag = re.sub(r"[^\w가-힣]+", "_", text).strip("_")
    return "#" + tag if tag else ""


def caption_for(path):
    """캡션: #작품명 해시태그(채널에서 작품별로 찾기) + 파일 이름 (작품 정보는 '작품 정보')."""
    series = os.path.basename(os.path.dirname(path))
    name = "작품 정보" if os.path.basename(path) == YAML_NAME else os.path.splitext(os.path.basename(path))[0]
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
                              files={"document": (upload_name(path), f)}, timeout=(15, 600))
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
    if not s["chat"]:
        return None, "채널 ID 없음"
    if not s["token"]:
        return False, "봇 토큰 없음"
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
