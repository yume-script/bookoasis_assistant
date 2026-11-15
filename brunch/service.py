# -*- coding: utf-8 -*-
"""브런치 EPUB 받기 - 설정·받기 대기열·받은 목록·화면 API (gdw/web.py가 /api/brunch… 요청을 넘긴다)

- 브런치북 하나 = EPUB 하나 (발행된 회차 전부가 장으로). 브런치북에 없는 글은 글 하나로 EPUB 하나.
- 저장: 설정 > 저장 폴더 (비우면 .env의 BRUNCH_DOWNLOAD_ROOT, 그것도 없으면 DATA_DIR/brunch/files)
  기본은 <저장 폴더>/<작가>/<브런치북 제목>.epub. 같은 책을 다시 받으면 새 회차까지 담아 덮어쓴다.
- 저장 폴더가 BookOasis 보관함 안이면 웹툰처럼 드라이브 변경 감시에 넘겨 바로 스캔한다 (gdw/handoff.py).
- 화면의 [내려받기]로 브라우저에도 받을 수 있다.
- 새 글 자동 받기: 받은 브런치북(연재 중)을 정해 둔 간격(기본 6시간)마다 확인해, 발행된 회차가 늘었으면 다시 받아 덮어쓴다.
  책마다 [자동 받기]를 끌 수 있고, 완결된 책은 확인하지 않는다.
설정·기록: DATA_DIR/brunch/ (settings.json, history.json, check.json)
"""
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections import deque
from datetime import datetime

from gdw import config

from . import epub, fetch

log = logging.getLogger("brunch")
MAX_HISTORY = 300
MAX_IMAGES = 600          # 책 하나에 넣는 그림 수 (넘으면 그 뒤 그림은 뺀다)
_LOCK = threading.RLock()
_JOBS = deque(maxlen=50)  # 최근 작업 (대기·진행·끝)
_WAKE = threading.Event()
_STATE = {"thread": None, "client": None, "checking": False}
CHECK_HOURS = (1, 2, 3, 6, 12, 24)
FIRST_CHECK_DELAY = 120   # 켠 뒤 처음 확인까지 (시작을 무겁게 하지 않게)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ── 저장 위치·설정 ──
def data_dir():
    return os.path.join(config.data_dir(), "brunch")


def _settings_path():
    return os.path.join(data_dir(), "settings.json")


def _history_path():
    return os.path.join(data_dir(), "history.json")


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_settings():
    s = _read_json(_settings_path(), {})
    try:
        hours = int(s.get("check_hours") or 6)
    except (TypeError, ValueError):
        hours = 6
    return {"save_dir": str(s.get("save_dir") or ""), "by_author": s.get("by_author", True) is not False,
            "auto_check": s.get("auto_check", True) is not False,
            "check_hours": hours if hours in CHECK_HOURS else 6}


def save_root(settings=None):
    s = settings or load_settings()
    root = s["save_dir"] or config.env("BRUNCH_DOWNLOAD_ROOT", "").strip()
    return os.path.abspath(root) if root else os.path.join(data_dir(), "files")


def clean_settings(body):
    save_dir = str(body.get("save_dir") or "").strip()
    if save_dir:
        if "\x00" in save_dir or not os.path.isabs(save_dir):
            raise ValueError("저장 폴더는 서버의 절대 경로로 적으세요 (예: /mnt/books/브런치).")
        save_dir = os.path.normpath(save_dir)
    try:
        hours = int(body.get("check_hours") or 6)
    except (TypeError, ValueError):
        hours = 6
    if hours not in CHECK_HOURS:
        raise ValueError("새 글 확인 간격은 %s시간 중 하나입니다." % ", ".join(map(str, CHECK_HOURS)))
    return {"save_dir": save_dir, "by_author": bool(body.get("by_author", True)),
            "auto_check": bool(body.get("auto_check", True)), "check_hours": hours}


_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(text, fallback="브런치"):
    s = _BAD.sub(" ", str(text or "")).strip().strip(".").strip()
    s = re.sub(r"\s+", " ", s)[:120].strip()
    return s or fallback


def target_path(settings, author, title):
    root = save_root(settings)
    folder = os.path.join(root, safe_name(author, "작가 미상")) if settings["by_author"] else root
    return os.path.join(folder, safe_name(title) + ".epub")


# ── 받은 목록 ──
def load_history():
    return [h for h in _read_json(_history_path(), []) if isinstance(h, dict) and h.get("id")]


def _remember(entry):
    with _LOCK:
        hist = load_history()
        old = next((h for h in hist if h.get("key") == entry["key"]), None)
        if old is not None and "auto" in old:   # 다시 받아도 [자동 받기] 선택은 그대로
            entry["auto"] = old["auto"]
        hist = [h for h in hist if h.get("key") != entry["key"]]
        hist.insert(0, entry)
        _write_json(_history_path(), hist[:MAX_HISTORY])


def _update_entry(hid, **fields):
    with _LOCK:
        hist = load_history()
        for h in hist:
            if h.get("id") == hid:
                h.update(fields)
                _write_json(_history_path(), hist)
                return h
    return None


# ── 새 글 자동 받기 ──
def _check_path():
    return os.path.join(data_dir(), "check.json")


def check_state():
    return _read_json(_check_path(), {})


def watched(h):
    """자동으로 새 글을 확인할 책: 브런치북이고, [자동 받기]가 켜져 있고, 완결이 아닌 것"""
    return h.get("kind") == "book" and h.get("auto", True) is not False and h.get("status") != "COMPLETE"


def _has_new(h, book):
    """받은 뒤 새로 발행된 회차가 있는지 (회차 번호를 기억해 둔 책은 번호로, 예전 기록은 회차 수로)"""
    now_ids = {int(e["article_no"]) for e in book["episodes"]}
    if h.get("episode_ids"):
        return bool(now_ids - set(int(x) for x in h["episode_ids"]))
    return len(now_ids) > int(h.get("chapters") or 0) + len(h.get("skipped") or [])


def check_now(reason="자동"):
    """받은 연재 중 브런치북을 모두 확인해 새 회차가 있으면 다시 받기 대기열에. 반환: 새 글이 있는 책 수"""
    if _STATE["checking"]:
        return 0
    _STATE["checking"] = True
    found = 0
    try:
        c = _client()
        for h in [x for x in load_history() if watched(x)]:
            address = h["key"].partition(":")[2]
            try:
                book = c.book(address)
            except fetch.BrunchError as e:
                log.info("브런치 새 글 확인 실패 (%s): %s", h.get("title"), e)
                _update_entry(h["id"], checked_at=_now(), check_error=str(e))
                continue
            new = _has_new(h, book)
            fields = {"checked_at": _now(), "check_error": ""}
            if book.get("status") == "COMPLETE" and not new:
                fields["status"] = "COMPLETE"   # 완결됐고 다 받았으면 더 확인하지 않는다
            _update_entry(h["id"], **fields)
            if new:
                found += 1
                log.info("브런치 새 글: %s (발행 %d화) - 다시 받습니다", book["title"], len(book["episodes"]))
                enqueue("book", address, book["title"], auto=True)
        _write_json(_check_path(), {"last": time.time(), "found": found, "reason": reason})
    finally:
        _STATE["checking"] = False
    return found


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _check_due(started):
    s = load_settings()
    if not s["auto_check"] or time.time() - started < FIRST_CHECK_DELAY:
        return False
    last = float(check_state().get("last") or 0)
    return time.time() - last >= s["check_hours"] * 3600


def _public_history():
    out = []
    for h in load_history():
        item = {k: h.get(k) for k in ("id", "key", "kind", "title", "author", "url", "chapters", "images",
                                      "restricted", "skipped", "at", "size", "status", "file_name", "scan",
                                      "checked_at", "check_error")}
        item["auto"] = h.get("kind") == "book" and h.get("auto", True) is not False
        item["watched"] = watched(h)
        item["exists"] = bool(h.get("file")) and os.path.isfile(h["file"])
        item["path"] = h.get("file") or ""
        out.append(item)
    return out


# ── 받기 대기열 ──
def _client():
    if _STATE["client"] is None:
        _STATE["client"] = fetch.Client()
    return _STATE["client"]


def start(stop_event=None):
    try:
        import requests  # noqa: F401
    except ImportError:
        log.warning("requests가 없어 브런치 EPUB 받기를 켜지 못했습니다: pip install -r requirements.txt")
        return False
    with _LOCK:
        if _STATE["thread"] and _STATE["thread"].is_alive():
            return True
        t = threading.Thread(target=_loop, args=(stop_event,), name="brunch", daemon=True)
        _STATE["thread"] = t
        t.start()
    return True


def _loop(stop_event):
    started = time.time()
    while not (stop_event and stop_event.is_set()):
        job = None
        with _LOCK:
            job = next((j for j in reversed(_JOBS) if j["state"] == "queued"), None)
            if job:
                job["state"] = "running"
                job["started"] = time.time()
        if not job:
            if _check_due(started):
                try:
                    check_now()
                except Exception as e:  # noqa: BLE001
                    log.warning("브런치 새 글 확인 실패: %s", e)
                    _write_json(_check_path(), {"last": time.time(), "found": 0, "error": str(e)})
                continue
            _WAKE.wait(30)
            _WAKE.clear()
            continue
        try:
            _run(job)
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001
            log.warning("브런치 EPUB 받기 실패 (%s): %s", job.get("title") or job["key"], e)
            job["state"], job["error"] = "error", str(e)
        job["finished"] = time.time()


def enqueue(kind, target, title="", auto=False):
    """kind: book(target=브런치북 주소) / article(target=(user_id, 번호)). 같은 것이 이미 대기·진행 중이면 그 작업을 돌려준다"""
    key = "book:%s" % target if kind == "book" else "article:%s/%s" % tuple(target)
    with _LOCK:
        for j in _JOBS:
            if j["key"] == key and j["state"] in ("queued", "running"):
                return j
        job = {"id": uuid.uuid4().hex[:12], "key": key, "kind": kind, "target": target, "title": title,
               "state": "queued", "done": 0, "total": 0, "error": "", "note": "", "added": time.time(), "auto": auto}
        _JOBS.appendleft(job)
    if not (_STATE["thread"] and _STATE["thread"].is_alive()):
        start()
    _WAKE.set()
    return job


def _public_jobs():
    with _LOCK:
        return [{k: j.get(k) for k in ("id", "key", "kind", "title", "state", "done", "total", "error", "note", "added", "history_id", "auto")}
                for j in _JOBS]


def _run(job):
    c = _client()
    settings = load_settings()
    images, by_url = {}, {}
    cover = None

    def on_img(src):
        if src in by_url:
            return by_url[src]
        if len(images) >= MAX_IMAGES:
            return None
        got = c.get_image(src)
        if not got:
            by_url[src] = None
            return None
        name = "img%04d%s" % (len(images) + 1, epub.ext_of(got[1]))
        images[name] = got
        by_url[src] = "images/" + name
        return by_url[src]

    if job["kind"] == "book":
        book = c.book(job["target"])
        job["title"] = book["title"]
        eps = book["episodes"]
        if not eps:
            raise fetch.BrunchError("이 브런치북에는 아직 발행된 글이 없습니다.")
        meta = {"title": book["title"], "author": book["author"], "description": book["description"],
                "url": book["url"], "status": book["status"]}
        cover_url = book["cover"]
    else:
        uid, no = job["target"]
        eps = [{"num": "", "title": "", "user_id": uid, "article_no": int(no)}]
        meta, cover_url = None, ""
    job["total"] = len(eps)
    chapters, skipped, restricted = [], [], 0
    for ep in eps:
        try:
            art = c.article(ep["user_id"], ep["article_no"])
        except fetch.BrunchError as e:
            skipped.append("%s (%s)" % (ep.get("title") or ep["article_no"], e))
            job["done"] += 1
            continue
        if meta is None:   # 글 하나 받기: 글 제목이 책 제목
            meta = {"title": art["title"], "author": art["author"], "description": art["subtitle"], "url": art["url"], "status": ""}
            cover_url = art["cover"]
            job["title"] = art["title"]
        restricted += art["restricted"]
        chapters.append({"num": ep.get("num") or "", "title": art["title"] or ep.get("title") or "",
                         "subtitle": art["subtitle"], "url": art["url"], "restricted": art["restricted"],
                         "body": fetch.sanitize(art["html"], on_img)})
        job["done"] += 1
        job["note"] = "%d/%d화 · 그림 %d장" % (job["done"], job["total"], len(images))
    if not chapters:
        raise fetch.BrunchError("받은 글이 없습니다: " + "; ".join(skipped[:3]))
    if cover_url:
        cover = c.get_image(cover_url)
    final = target_path(settings, meta["author"], meta["title"])
    work = os.path.join(data_dir(), "tmp")
    os.makedirs(work, exist_ok=True)
    local = os.path.join(work, job["id"] + ".epub")
    ident = "brunch:" + job["key"]
    epub.build(local, meta, chapters, images, cover=cover, identifier=ident)
    _move(local, final)
    size = os.path.getsize(final)
    scan = _handoff(final)
    entry = {"id": uuid.uuid4().hex[:12], "key": job["key"], "kind": job["kind"], "title": meta["title"], "author": meta["author"],
             "url": meta["url"], "chapters": len(chapters), "images": len(images), "restricted": restricted,
             "skipped": skipped, "status": meta.get("status") or "", "file": final, "file_name": os.path.basename(final),
             "size": size, "scan": scan, "at": _now(), "checked_at": _now(),
             "episode_ids": [int(e["article_no"]) for e in eps], "auto": job["kind"] == "book"}
    _remember(entry)
    job["history_id"] = entry["id"]
    job["note"] = "%d화 · 그림 %d장 · %.1fMB%s" % (len(chapters), len(images), size / 1048576,
                                              " · 빠진 글 %d" % len(skipped) if skipped else "")
    log.info("브런치 EPUB: %s (%d화) -> %s", meta["title"], len(chapters), final)


def _move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError:   # 다른 디스크(원격 마운트 등): 복사한 뒤 바꿔 넣는다
        tmp = dst + ".tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
        os.remove(src)


def _handoff(path):
    """보관함 안에 저장했으면 드라이브 변경 감시에 바로 넘겨 BookOasis가 스캔하게 (웹툰 다운로더와 같은 길)"""
    if not config.env_bool("GDW_ENABLED", os.name != "nt"):
        return False
    try:
        from gdw import handoff
        return bool(handoff.enqueue(path, source="브런치"))
    except Exception:  # noqa: BLE001
        return False


# ── 화면 API ──
def _state():
    s = load_settings()
    chk = check_state()
    last = float(chk.get("last") or 0)
    return {"success": True, "settings": s, "root": save_root(s), "env_root": config.env("BRUNCH_DOWNLOAD_ROOT", "").strip(),
            "jobs": _public_jobs(), "history": _public_history(), "check_hours": list(CHECK_HOURS),
            "check": {"last": last, "next": (last + s["check_hours"] * 3600) if (s["auto_check"] and last) else 0,
                      "found": chk.get("found", 0), "error": chk.get("error", ""), "running": _STATE["checking"]}}


def _entry(hid):
    return next((h for h in load_history() if h.get("id") == hid), None)


def api_get(path, query):
    """JSON 또는 (bytes, content-type, 파일 이름)"""
    c = _client()
    try:
        if path == "/api/brunch":
            return _state()
        if path == "/api/brunch/list":
            return dict(c.list(query.get("day", "MONDAY"), query.get("sort", ""), query.get("next") or None), success=True)
        if path == "/api/brunch/resolve":   # 붙여 넣은 주소 미리 보기
            kind, target = fetch.parse_input(query.get("url", ""))
            if kind == "book":
                b = c.book(target)
                return {"success": True, "kind": "book", "book": _book_preview(b)}
            art = c.article(*target)
            res = {"success": True, "kind": "article", "article": {
                "title": art["title"], "subtitle": art["subtitle"], "author": art["author"], "url": art["url"],
                "cover": art["cover"], "restricted": art["restricted"], "book_title": art["book_title"],
                "user_id": target[0], "article_no": target[1]}}
            if art["book_address"]:
                try:
                    res["book"] = _book_preview(c.book(art["book_address"]))
                except fetch.BrunchError:
                    pass
            return res
        if path == "/api/brunch/book":   # 목록에서 고른 글의 브런치북 찾기 (?user_id=&no=)
            art = c.article(query.get("user_id", ""), query.get("no", ""))
            if not art["book_address"]:
                return {"success": True, "book": None}
            return {"success": True, "book": _book_preview(c.book(art["book_address"]))}
        if path == "/api/brunch/file":
            h = _entry(query.get("id", ""))
            if not h or not h.get("file") or not os.path.isfile(h["file"]):
                raise ApiError(404, "파일이 없습니다 (옮겼거나 지웠을 수 있음).")
            with open(h["file"], "rb") as f:
                return f.read(), "application/epub+zip", os.path.basename(h["file"])
    except ValueError as e:
        raise ApiError(400, str(e))
    except fetch.BrunchError as e:
        raise ApiError(502, str(e))
    raise ApiError(404, "없는 주소입니다.")


def _book_preview(b):
    return {"address": b["address"], "url": b["url"], "title": b["title"], "author": b["author"], "cover": b["cover"],
            "description": b["description"][:400], "status": b["status"], "count": len(b["episodes"]),
            "planned": b["planned"], "first": (b["episodes"][0]["title"] if b["episodes"] else "")}


def api_post(path, body):
    try:
        if path == "/api/brunch/download":
            # {address} 브런치북 / {user_id, article_no} 글 하나 / {url, scope: book|article}
            if body.get("url"):
                kind, target = fetch.parse_input(body["url"])
                if kind == "article" and body.get("scope") == "book":
                    art = _client().article(*target)
                    if not art["book_address"]:
                        raise ApiError(400, "이 글은 브런치북에 묶여 있지 않습니다. [이 글만 받기]를 쓰세요.")
                    kind, target = "book", art["book_address"]
            elif body.get("address"):
                fetch.book_url(body["address"])
                kind, target = "book", str(body["address"])
            else:
                fetch.article_url(body.get("user_id"), body.get("article_no"))
                kind, target = "article", (str(body["user_id"]), int(body["article_no"]))
            job = enqueue(kind, target, str(body.get("title") or "")[:200])
            return {"success": True, "job": job["id"], "jobs": _public_jobs()}
        if path == "/api/brunch/redownload":   # 받은 목록의 [다시 받기] - 새 회차까지 담아 덮어쓴다
            h = _entry(str(body.get("id") or ""))
            if not h:
                raise ApiError(404, "받은 목록에 없습니다.")
            kind, _, rest = h["key"].partition(":")
            target = rest if kind == "book" else tuple(rest.split("/", 1))
            job = enqueue(kind, target if kind == "book" else (target[0], int(target[1])), h.get("title") or "")
            return {"success": True, "job": job["id"], "jobs": _public_jobs()}
        if path == "/api/brunch/forget":   # 받은 목록에서 빼기 {id, remove_file}
            h = _entry(str(body.get("id") or ""))
            if not h:
                raise ApiError(404, "받은 목록에 없습니다.")
            if body.get("remove_file") and h.get("file") and os.path.isfile(h["file"]):
                os.remove(h["file"])
            with _LOCK:
                _write_json(_history_path(), [x for x in load_history() if x.get("id") != h["id"]])
            return _state()
        if path == "/api/brunch/settings":
            _write_json(_settings_path(), clean_settings(body))
            return _state()
        if path == "/api/brunch/auto":   # 받은 목록의 [자동 받기] 켜고 끄기 {id, auto}
            h = _entry(str(body.get("id") or ""))
            if not h or h.get("kind") != "book":
                raise ApiError(404, "자동 받기는 받은 브런치북에만 쓸 수 있습니다.")
            _update_entry(h["id"], auto=bool(body.get("auto")))
            return _state()
        if path == "/api/brunch/check":   # [지금 새 글 확인] - 백그라운드에서 확인하고 바로 돌아온다
            if not _STATE["checking"]:
                threading.Thread(target=check_now, kwargs={"reason": "수동"}, name="brunch-check", daemon=True).start()
                time.sleep(0.2)
            return _state()
        if path == "/api/brunch/clear-jobs":   # 끝난 작업 줄 지우기
            with _LOCK:
                keep = [j for j in _JOBS if j["state"] in ("queued", "running")]
                _JOBS.clear()
                _JOBS.extend(keep)
            return _state()
    except ValueError as e:
        raise ApiError(400, str(e))
    except fetch.BrunchError as e:
        raise ApiError(502, str(e))
    raise ApiError(404, "없는 주소입니다.")
