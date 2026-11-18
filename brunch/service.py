# -*- coding: utf-8 -*-
"""브런치 EPUB 받기 - 설정·받기 대기열·받은 목록·화면 API (gdw/web.py가 /api/brunch… 요청을 넘긴다)

- 브런치북 하나 = EPUB 하나 (발행된 회차 전부가 장으로). 브런치북에 없는 글은 글 하나로 EPUB 하나.
- 저장: 설정 > 저장 폴더 (비우면 .env의 BRUNCH_DOWNLOAD_ROOT, 그것도 없으면 DATA_DIR/brunch/files)
  기본은 <저장 폴더>/<작가>/<브런치북 제목>/<브런치북 제목>.epub (책마다 폴더 하나). 같은 책을 다시 받으면 새 회차까지 담아 덮어쓴다.
- kavita.yaml: 웹툰 다운로더처럼 책 폴더에 BookOasis 메타데이터(제목·작가·소개·연재 상태·발행일·원문 주소·표지)를 같이 둔다
  (brunch/kavita.py, 설정에서 끌 수 있음). 예전(2.55.0까지) 작가 폴더에 바로 받은 책은 한 번 다시 받아 책 폴더로 옮긴다.
- 저장 폴더가 BookOasis 보관함 안이면 웹툰처럼 드라이브 변경 감시에 넘겨 바로 스캔한다 (gdw/handoff.py).
- 화면의 [내려받기]로 브라우저에도 받을 수 있다.
- 새 글 자동 받기: 받은 브런치북(연재 중)을 정해 둔 간격(분 - 10·20·30분 … 기본 6시간)마다 확인해, 발행된 회차가 늘었으면 다시 받아 덮어쓴다.
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

from . import epub, fetch, kavita

log = logging.getLogger("brunch")
MAX_HISTORY = 3000        # (완결작 모두 받기로 수백 권이 될 수 있다)
BULK_MAX_PAGES = 60       # 완결작 모두 받기: 완결 목록을 몇 쪽까지 넘겨 보나
MAX_IMAGES = 600          # 책 하나에 넣는 그림 수 (넘으면 그 뒤 그림은 뺀다)
_LOCK = threading.RLock()
_JOBS = deque()           # 최근 작업 (대기·진행·끝) - 끝난 것은 MAX_DONE_JOBS개만 남긴다 (대기 중인 것은 버리지 않음)
MAX_DONE_JOBS = 50
_WAKE = threading.Event()
_STATE = {"thread": None, "client": None, "checking": False}
CHECK_MINUTES = (10, 20, 30, 40, 50, 60, 90, 120, 180, 360, 720, 1440)
CHECK_HOURS = tuple(m // 60 for m in CHECK_MINUTES if m % 60 == 0)   # (예전 설정 값 - 화면은 분 단위)
DEFAULT_CHECK_MIN = 360
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


def _check_min(s):
    """새 글 확인 간격(분) - check_minutes, 예전 설정은 check_hours x 60"""
    try:
        if s.get("check_minutes") not in (None, ""):
            return int(s["check_minutes"])
        if s.get("check_hours") not in (None, ""):
            return int(s["check_hours"]) * 60
    except (TypeError, ValueError):
        pass
    return DEFAULT_CHECK_MIN


def load_settings():
    s = _read_json(_settings_path(), {})
    minutes = _check_min(s)
    minutes = minutes if minutes in CHECK_MINUTES else DEFAULT_CHECK_MIN
    return {"save_dir": str(s.get("save_dir") or ""), "by_author": s.get("by_author", True) is not False,
            "auto_check": s.get("auto_check", True) is not False, "kavita_yaml": s.get("kavita_yaml", True) is not False,
            "check_minutes": minutes, "check_hours": round(minutes / 60, 2)}


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
    minutes = _check_min(body)
    if minutes not in CHECK_MINUTES:
        raise ValueError("새 글 확인 간격은 %s분 중 하나입니다." % ", ".join(map(str, CHECK_MINUTES)))
    return {"save_dir": save_dir, "by_author": bool(body.get("by_author", True)),
            "auto_check": bool(body.get("auto_check", True)), "check_minutes": minutes,
            "kavita_yaml": bool(body.get("kavita_yaml", True))}


_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(text, fallback="브런치"):
    s = _BAD.sub(" ", str(text or "")).strip().strip(".").strip()
    s = re.sub(r"\s+", " ", s)[:120].strip()
    return s or fallback


def target_path(settings, author, title):
    """책마다 폴더 하나 (kavita.yaml이 폴더 단위라서): <저장 폴더>[/<작가>]/<제목>/<제목>.epub"""
    root = save_root(settings)
    folder = os.path.join(root, safe_name(author, "작가 미상")) if settings["by_author"] else root
    name = safe_name(title)
    return os.path.join(folder, name, name + ".epub")


LAYOUT = 2   # 2.56.0부터 책마다 폴더 (history의 layout이 이보다 작으면 예전 위치)


def _remove_book_file(path, keep=None):
    """예전에 받은 EPUB을 지운다 (같은 폴더의 kavita.yaml도, 비면 폴더도). keep(새 경로)과 같으면 그대로"""
    if not path or (keep and os.path.normpath(path) == os.path.normpath(keep)) or not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    folder = os.path.dirname(path)
    yaml_path = os.path.join(folder, kavita.YAML_NAME)
    # 그 폴더에 이 책 말고 다른 EPUB이 없을 때만 (예전 작가 폴더에는 kavita.yaml이 없다)
    if os.path.isfile(yaml_path) and not any(n.lower().endswith(".epub") for n in os.listdir(folder)):
        try:
            os.remove(yaml_path)
        except OSError:
            pass
    try:
        os.rmdir(folder)   # 비었을 때만 지워진다
    except OSError:
        pass
    _handoff(path, action="delete")
    return True


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
            # 받은 목록에 보일 "브런치에 발행된 회차 수 / 마지막 회차" (EPUB에 다 들었는지)
            fields = {"checked_at": _now(), "check_error": "", "published": len(book["episodes"]),
                      "latest_title": (book["episodes"][-1].get("title") or "") if book["episodes"] else ""}
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


def _pub_day(ms):
    """브런치 발행 시각(밀리초) -> 'YYYY-MM-DD' (없으면 '')"""
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d") if ms else ""
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _check_due(started):
    s = load_settings()
    if not s["auto_check"] or time.time() - started < FIRST_CHECK_DELAY:
        return False
    last = float(check_state().get("last") or 0)
    return time.time() - last >= s["check_minutes"] * 60


def _public_history():
    out = []
    with _LOCK:
        busy = {j["key"] for j in _JOBS if j["state"] in ("queued", "running")}
    for h in load_history():
        item = {k: h.get(k) for k in ("id", "key", "kind", "title", "author", "url", "chapters", "images",
                                      "restricted", "skipped", "at", "size", "status", "file_name", "scan",
                                      "checked_at", "check_error", "yaml", "first_published", "last_published")}
        item["auto"] = h.get("kind") == "book" and h.get("auto", True) is not False
        item["watched"] = watched(h)
        item["exists"] = bool(h.get("file")) and os.path.isfile(h["file"])
        # EPUB 상태: missing(파일 없음) / queued(만드는 중) / behind(브런치에 새 회차가 있는데 아직 안 담음) / latest(최신 회차까지)
        have = int(h.get("chapters") or 0) + len(h.get("skipped") or [])
        published = int(h.get("published") or have)
        item["published"] = published
        item["latest_title"] = h.get("latest_title") or ""
        item["new_count"] = max(0, published - have)
        if h.get("key") in busy:
            item["epub_state"] = "queued"
        elif not item["exists"]:
            item["epub_state"] = "missing"
        elif item["new_count"]:
            item["epub_state"] = "behind"
        else:
            item["epub_state"] = "latest"
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
    try:
        migrate_layout()
    except Exception as e:  # noqa: BLE001
        log.warning("브런치 책 폴더 옮기기 실패: %s", e)
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
    """kind: book(target=브런치북 주소) / article(target=(user_id, 번호)) / bookof(target=(user_id, 번호) - 그 글이 든 브런치북,
    받을 때 찾는다). 같은 것이 이미 대기·진행 중이면 그 작업을 돌려준다"""
    key = "book:%s" % target if kind == "book" else ("bookof:%s/%s" if kind == "bookof" else "article:%s/%s") % tuple(target)
    with _LOCK:
        for j in _JOBS:
            if j["key"] == key and j["state"] in ("queued", "running"):
                return j
        job = {"id": uuid.uuid4().hex[:12], "key": key, "kind": kind, "target": target, "title": title,
               "state": "queued", "done": 0, "total": 0, "error": "", "note": "", "added": time.time(), "auto": auto}
        _JOBS.appendleft(job)
        done = [j for j in _JOBS if j["state"] in ("done", "error")]
        for j in done[MAX_DONE_JOBS:]:   # (예전 deque(maxlen=50)은 완결작 모두 받기처럼 많이 넣으면 대기 중인 것까지 버렸다)
            _JOBS.remove(j)
    if not (_STATE["thread"] and _STATE["thread"].is_alive()):
        start()
    _WAKE.set()
    return job


def _have_all(key):
    """그 브런치북을 받아 두었고 파일도 있으며 완결이라 더 받을 회차가 없는지"""
    h = _entry_by_key(key)
    return bool(h and h.get("status") == "COMPLETE" and h.get("file") and os.path.isfile(h["file"]))


def epub_state(items):
    """연재 목록의 글마다 EPUB에 담겼는지: done(이 회차까지 EPUB에 있음) / old(책은 받았지만 이 회차는 아직) /
    queued(받는 중·대기) / ""(받지 않은 책). 회차 번호(작가/번호)로, 예전 기록은 책 제목+번호로 맞춘다"""
    hist = [h for h in load_history() if h.get("kind") == "book"]
    by_key, by_title = set(), {}
    for h in hist:
        by_key.update(h.get("episode_keys") or [])
        by_title.setdefault(str(h.get("title") or "").strip(), []).append(h)
    with _LOCK:
        busy = {j["title"] for j in _JOBS if j["state"] in ("queued", "running") and j.get("title")}
    for it in items:
        k = "%s/%s" % (it.get("user_id") or "", it.get("article_no") or 0)
        title = str(it.get("book_title") or "").strip()
        books = by_title.get(title) or []
        if k in by_key or any(int(it.get("article_no") or 0) in set(int(x) for x in h.get("episode_ids") or []) for h in books):
            it["epub"] = "done"
        elif title and title in busy:
            it["epub"] = "queued"
        elif books:
            it["epub"] = "old"
        else:
            it["epub"] = ""
        if books:   # 받아 둔 EPUB이 어디까지인지 (가장 최근에 받은 것): 회차 수, 마지막 회차, 그 회차가 발행된 날
            b = max(books, key=lambda h: str(h.get("at") or ""))
            it["epub_at"] = b.get("at") or ""
            it["epub_chapters"] = int(b.get("chapters") or 0)
            it["epub_latest"] = b.get("latest_title") or ""
            it["epub_last_pub"] = b.get("last_published") or ""
    return items


_DAY_NAME = {"MONDAY": "월요일", "TUESDAY": "화요일", "WEDNESDAY": "수요일", "THURSDAY": "목요일", "FRIDAY": "금요일",
             "SATURDAY": "토요일", "SUNDAY": "일요일", "COMPLETE": "완결작"}


def bulk_complete(day="COMPLETE"):
    """[완결작 모두 EPUB으로] / [이 요일 모두 EPUB으로]: 그 목록(완결 또는 요일 연재)을 끝까지 넘겨 보며 아직 받지 않았거나
    새 회차가 EPUB에 없는 책을 대기열에 넣는다 (뒤에서). 최신 회차까지 받아 둔 책과 받는 중인 책은 건너뛴다.
    _BULK에 진행 {running, day, label, pages, seen, queued, skipped, error}"""
    if day not in _DAY_NAME:
        raise ApiError(400, "알 수 없는 요일입니다.")
    st = _BULK
    if st.get("running"):
        return st
    st.clear()
    st.update(running=True, day=day, label=_DAY_NAME[day], pages=0, seen=0, queued=0, skipped=0, error="", started=time.time())

    def work():
        try:
            c, nxt, books = _client(), None, set()
            while st["pages"] < BULK_MAX_PAGES:
                res = c.list(day, "", nxt)
                st["pages"] += 1
                for it in epub_state([x for x in res["items"] if x.get("url")]):
                    title = it.get("book_title") or ""
                    if title in books:
                        continue
                    books.add(title)
                    st["seen"] += 1
                    if it["epub"] in ("done", "queued"):
                        st["skipped"] += 1
                        continue
                    enqueue("bookof", (it["user_id"], int(it["article_no"])), title)
                    st["queued"] += 1
                nxt = res.get("next_url") or None
                if not (res.get("more") and nxt):
                    break
        except Exception as e:  # noqa: BLE001
            st["error"] = str(e)[:300]
            log.warning("브런치 %s 모두 받기 실패: %s", st["label"], e)
        finally:
            st["running"] = False
            log.info("브런치 %s 모두 받기: 책 %d권 중 %d권을 대기열에 (이미 받음 %d)", st["label"], st["seen"], st["queued"], st["skipped"])
    threading.Thread(target=work, name="brunch-bulk", daemon=True).start()
    return st


_BULK = {}


# ── 제목으로 찾기 ──
# 브런치 연재 목록 API는 요일별·완결로만 나뉘어 있고 찾기가 없다 - 모든 요일과 완결 목록을 끝까지 넘겨 모아 두고
# (뒤에서, SEARCH_CACHE_SEC 동안 다시 쓰기) 그 안에서 브런치북 제목·회차 제목·작가로 찾는다.
SEARCH_CACHE_SEC = 30 * 60
SEARCH_MAX_PAGES = 40       # 요일·완결 목록마다 넘겨 볼 쪽 수
_DAY_LABEL = {"MONDAY": "월", "TUESDAY": "화", "WEDNESDAY": "수", "THURSDAY": "목", "FRIDAY": "금",
              "SATURDAY": "토", "SUNDAY": "일", "COMPLETE": "완결"}
_SEARCH = {"items": [], "at": 0.0, "building": False, "pages": 0, "error": ""}
_SEARCH_LOCK = threading.Lock()


def _norm_q(text):
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _build_search_index():
    st = _SEARCH
    try:
        c, items, pages = _client(), {}, 0
        for day in list(_DAY_LABEL):
            nxt = None
            for _ in range(SEARCH_MAX_PAGES):
                res = c.list(day, "", nxt)
                pages += 1
                st["pages"] = pages
                for it in res["items"]:
                    if not it.get("url"):
                        continue
                    key = (it.get("book_title") or it.get("title"), it.get("author"))
                    have = items.get(key)
                    if have is None or (it.get("publish_time") or 0) > (have.get("publish_time") or 0):
                        days = (have or {}).get("days") or []
                        items[key] = dict(it, days=days)
                    if _DAY_LABEL[day] not in items[key]["days"]:
                        items[key]["days"] = items[key]["days"] + [_DAY_LABEL[day]]
                nxt = res.get("next_url") or None
                if not (res.get("more") and nxt):
                    break
        st.update(items=sorted(items.values(), key=lambda x: -(x.get("publish_time") or 0)), at=time.time(), error="")
        log.info("브런치 찾기: 연재 목록 %d쪽에서 브런치북 %d권을 모음", pages, len(items))
    except Exception as e:  # noqa: BLE001
        st["error"] = str(e)[:300]
        log.warning("브런치 찾기 목록 모으기 실패: %s", e)
    finally:
        st["building"] = False


def search(q, limit=60):
    """{"items", "building"(아직 모으는 중), "pages", "total"(모은 책 수), "error"} - 처음이거나 오래됐으면 뒤에서 모으기 시작"""
    st = _SEARCH
    with _SEARCH_LOCK:
        if not st["building"] and (not st["items"] or time.time() - st["at"] > SEARCH_CACHE_SEC):
            st.update(building=True, pages=0)
            threading.Thread(target=_build_search_index, name="brunch-search", daemon=True).start()
    want = _norm_q(q)
    hits = []
    if want:
        for it in st["items"]:
            if any(want in _norm_q(it.get(k)) for k in ("book_title", "title", "author")):
                hits.append(dict(it))
                if len(hits) >= limit:
                    break
    return {"items": epub_state(hits), "building": st["building"], "pages": st["pages"],
            "total": len(st["items"]), "error": st["error"], "success": True}


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

    if job["kind"] == "bookof":   # 완결작 모두 받기: 목록의 글 -> 그 글이 든 브런치북
        art = c.article(*job["target"])
        if not art["book_address"]:
            raise fetch.BrunchError("이 글은 브런치북에 묶여 있지 않습니다.")
        job.update(kind="book", target=art["book_address"], key="book:%s" % art["book_address"])
        with _LOCK:
            dup = any(j is not job and j["key"] == job["key"] and j["state"] in ("queued", "running") for j in _JOBS)
        if dup or _have_all(job["key"]):
            job["note"] = "이미 받았거나 받는 중이라 건너뜀"
            return
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
    chapters, skipped, restricted, first_pub = [], [], 0, 0
    ep_dates = {}   # 회차(글 번호) -> 브런치에 발행된 날 (받은 날이 아니라)
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
        if art.get("publish_time") and (not first_pub or art["publish_time"] < first_pub):
            first_pub = art["publish_time"]
        if art.get("publish_time"):
            ep_dates[int(ep["article_no"])] = _pub_day(art["publish_time"])
        chapters.append({"num": ep.get("num") or "", "title": art["title"] or ep.get("title") or "",
                         "subtitle": art["subtitle"], "url": art["url"], "restricted": art["restricted"],
                         "published": _pub_day(art.get("publish_time")),
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
    epub.build(local, dict(meta, published=_pub_day(first_pub)), chapters, images, cover=cover, identifier=ident)
    yaml_ok = False
    if settings["kavita_yaml"]:   # 책 폴더에 메타데이터 먼저 (EPUB이 들어오며 스캔될 때 같이 읽히게)
        try:
            os.makedirs(os.path.dirname(final), exist_ok=True)
            data = kavita.build_data(job["key"], dict(meta, cover_url=cover_url), os.path.basename(final),
                                     kavita.word_count(chapters), kavita.shrink_cover(cover[0]) if cover else "", first_pub)
            yaml_ok = bool(kavita.write(os.path.dirname(final), data))
        except Exception as e:  # noqa: BLE001 - 메타데이터는 덤, EPUB 받기를 막지 않는다
            log.warning("브런치 kavita.yaml을 만들지 못했습니다 (%s): %s", meta["title"], e)
    replaced = os.path.exists(final)   # 예전에 받은(올린) 같은 책을 새 회차까지 담아 덮어씀
    _move(local, final)
    size = os.path.getsize(final)
    old = _entry_by_key(job["key"])
    if old and old.get("file"):   # 예전 위치(예전 작가 폴더·바뀐 제목)에 받은 파일은 치운다
        _remove_book_file(old["file"], keep=final)
    # 덮어쓴 책은 '수정'으로 넘긴다 - '추가'로 넘기면 같은 경로가 이미 BookOasis에 있어 '이미 등록된 파일'로 건너뛰어
    # 새 회차가 반영되지 않았다
    scan = _handoff(final, action="edit" if replaced else "create")
    entry = {"id": uuid.uuid4().hex[:12], "key": job["key"], "kind": job["kind"], "title": meta["title"], "author": meta["author"],
             "url": meta["url"], "chapters": len(chapters), "images": len(images), "restricted": restricted,
             "skipped": skipped, "status": meta.get("status") or "", "file": final, "file_name": os.path.basename(final),
             "size": size, "scan": scan, "at": _now(), "checked_at": _now(),
             "episode_ids": [int(e["article_no"]) for e in eps], "auto": job["kind"] == "book",
             "episode_keys": ["%s/%s" % (e.get("user_id") or "", int(e["article_no"])) for e in eps],
             "published": len(eps), "latest_title": (eps[-1].get("title") or "") if eps else "",
             "yaml": yaml_ok, "layout": LAYOUT,
             # 브런치에 발행된 날 (at·checked_at은 받은 때·확인한 때)
             "episode_dates": {str(k): v for k, v in ep_dates.items()},
             "first_published": min(ep_dates.values()) if ep_dates else "",
             "last_published": max(ep_dates.values()) if ep_dates else ""}
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


def _handoff(path, action="create"):
    """보관함 안에 저장했으면 드라이브 변경 감시에 바로 넘겨 BookOasis가 스캔하게 (웹툰 다운로더와 같은 길)"""
    if not config.env_bool("GDW_ENABLED", os.name != "nt"):
        return False
    try:
        from gdw import handoff
        return bool(handoff.enqueue(path, source="브런치", action=action))
    except Exception:  # noqa: BLE001
        return False


# ── 화면 API ──
def _state():
    s = load_settings()
    chk = check_state()
    last = float(chk.get("last") or 0)
    return {"success": True, "settings": s, "root": save_root(s), "env_root": config.env("BRUNCH_DOWNLOAD_ROOT", "").strip(),
            "jobs": _public_jobs(), "history": _public_history(), "check_minutes": list(CHECK_MINUTES), "bulk": dict(_BULK),
            "check": {"last": last, "next": (last + s["check_minutes"] * 60) if (s["auto_check"] and last) else 0,
                      "found": chk.get("found", 0), "error": chk.get("error", ""), "running": _STATE["checking"]}}


def _entry_by_key(key):
    return next((h for h in load_history() if h.get("key") == key), None)


def migrate_layout():
    """2.55.0까지 작가 폴더에 바로 받은 책(kavita.yaml을 둘 수 없는 위치)을 한 번 다시 받아 책 폴더로 옮긴다.
    새로 받으면 kavita.yaml이 생기고 예전 파일은 지운다. 반환: 대기열에 넣은 수"""
    if not load_settings()["kavita_yaml"]:
        return 0
    n = 0
    for h in load_history():
        if int(h.get("layout") or 1) >= LAYOUT or not h.get("file") or not os.path.isfile(h["file"]):
            continue
        kind, _, rest = h["key"].partition(":")
        if kind == "book":
            enqueue("book", rest, h.get("title") or "")
        else:
            uid, _, no = rest.partition("/")
            enqueue("article", (uid, int(no)), h.get("title") or "")
        n += 1
    if n:
        log.info("브런치: 예전에 받은 책 %d권을 책 폴더로 옮기며 kavita.yaml을 만듭니다 (다시 받기)", n)
    return n


def _entry(hid):
    return next((h for h in load_history() if h.get("id") == hid), None)


def api_get(path, query):
    """JSON 또는 (bytes, content-type, 파일 이름)"""
    c = _client()
    try:
        if path == "/api/brunch":
            return _state()
        if path == "/api/brunch/list":
            res = c.list(query.get("day", "MONDAY"), query.get("sort", ""), query.get("next") or None)
            # (캐시한 목록을 고치지 않게 글마다 복사해서 EPUB 상태를 붙인다)
            return dict(res, items=epub_state([dict(x) for x in res["items"]]), success=True)
        if path == "/api/brunch/search":   # 제목으로 찾기 (?q=)
            return search(query.get("q", ""))
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
            if body.get("remove_file") and h.get("file"):
                _remove_book_file(h["file"])   # 책 폴더의 kavita.yaml도 같이
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
        if path == "/api/brunch/bulk-complete":   # [완결작/이 요일 모두 EPUB으로] - 뒤에서 그 목록을 넘기며 대기열에 ({"day": …})
            return {"success": True, "bulk": dict(bulk_complete(str((body or {}).get("day") or "COMPLETE").upper()))}
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
