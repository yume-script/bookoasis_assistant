"""BookOasis 3D 서재 - 바깥에서 오는 일 (배달·외부 AI의 말)

- 배달: 책·영상·웹툰이 서재에 들어오면 배달원이 입구로 들어와 안내 데스크에 상자를 놓고 나간다.
  보내는 곳: (1) POST /api/lib3d/events (LIB3D_EVENT_TOKEN, 디스코드 봇 같은 외부 프로그램)
           (2) 웹툰 다운로더가 회차를 라이브러리에 넣을 때 (다른 프로세스라 파일에 한 줄씩 덧붙인다)
- 웹툰은 회차마다 오므로, 잠잠해질 때까지(GROUP_SEC) 모아 상자 하나로 배달한다.
- 배달은 한 번에 한 명씩 차례로 (DUR초 동안: 들어옴 → 데스크 → 나감).
저장: DATA_DIR/lib3d_deliveries.jsonl (한 줄 = 받은 것 하나, 웹 프로세스가 가끔 줄인다)
"""
import hmac
import json
import os
import threading
import time

from . import config

FILE = "lib3d_deliveries.jsonl"
KEEP = 300            # 파일에 남길 줄 수
SHOW_SEC = 6 * 3600   # 이보다 오래된 배달은 화면에 보내지 않는다 (서버를 오래 꺼 두었다 켜도 몰려오지 않게)
GROUP_SEC = 90        # 웹툰 회차가 이 간격 안에 이어 오면 한 상자로
QUIET_SEC = 20        # 마지막 회차 뒤 이만큼 잠잠하면 출발
DUR = 52              # 배달 한 번 (입구 8초 → 데스크 30초 → 나감 14초)
KINDS = {"book": "책", "webtoon": "웹툰", "video": "영상", "audio": "오디오북", "comic": "만화"}
VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts")
AUDIO_EXT = (".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".wav")
_LOCK = threading.Lock()
_CACHE = {"sig": None, "rows": []}
_DONE = set()          # 이 프로세스에서 이미 채팅에 알린 배달


def _path():
    return os.path.join(config.data_dir(), FILE)


def settings():
    """[AI 직원] 설정의 배달 항목 (lib3d_agents.json - 웹툰 다운로더 프로세스에서도 읽는다)"""
    try:
        with open(os.path.join(config.data_dir(), "lib3d_agents.json"), encoding="utf-8") as f:
            d = (json.load(f) or {}).get("delivery") or {}
    except (OSError, ValueError):
        d = {}
    return {"enabled": d.get("enabled", True) is not False, "webtoon": d.get("webtoon", True) is not False,
            "name": str(d.get("name") or "배달원")[:20], "look": int(d.get("look") or 59)}


def token_ok(header):
    expect = config.env("LIB3D_EVENT_TOKEN", "").strip()
    given = str(header or "").strip()
    given = given[7:].strip() if given.lower().startswith("bearer ") else given
    return bool(expect) and bool(given) and hmac.compare_digest(given.encode(), expect.encode())


def _clean_items(items):
    out = []
    for it in (items or [])[:30]:
        if isinstance(it, str):
            it = {"title": it}
        if not isinstance(it, dict):
            continue
        title = " ".join(str(it.get("title") or "").split())[:80]
        if not title:
            continue
        kind = str(it.get("kind") or "book").lower()
        out.append({"title": title, "sub": " ".join(str(it.get("sub") or "").split())[:60], "kind": kind if kind in KINDS else "book"})
    return out


def add(items, sender="", note="", src="api"):
    """배달 하나 받기 (어느 프로세스에서든). 반환: 넣은 줄 또는 None"""
    if not config.env_bool("LIB3D_ENABLED", False) or not settings()["enabled"]:
        return None
    items = _clean_items(items)
    if not items:
        raise ValueError("items에 제목을 하나 이상 넣어 주세요.")
    row = {"t": time.time(), "id": "%x%04x" % (int(time.time() * 1000), os.getpid() & 0xffff), "src": str(src)[:20],
           "from": " ".join(str(sender or "").split())[:30], "note": " ".join(str(note or "").split())[:160], "items": items}
    os.makedirs(config.data_dir(), exist_ok=True)
    line = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(_path(), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)   # 한 번에 덧붙이기 (다른 프로세스와 섞이지 않게)
    finally:
        os.close(fd)
    return row


def from_webtoon(path):
    """웹툰 다운로더: 회차 파일이 라이브러리에 들어감 → 배달 대기 (작품 폴더 이름 = 제목)"""
    s = settings()
    if not (s["enabled"] and s["webtoon"]):
        return None
    path = os.path.normpath(str(path or ""))
    stem = os.path.splitext(os.path.basename(path))[0]
    series = os.path.basename(os.path.dirname(path)) or stem
    low = path.lower()
    kind = "video" if low.endswith(VIDEO_EXT) else "audio" if low.endswith(AUDIO_EXT) else "webtoon"
    return add([{"title": series, "sub": stem if stem != series else "", "kind": kind}], src="webtoon")


def _rows():
    try:
        st = os.stat(_path())
    except OSError:
        return []
    sig = (st.st_mtime_ns, st.st_size)
    with _LOCK:
        if _CACHE["sig"] == sig:
            return _CACHE["rows"]
        rows = []
        try:
            with open(_path(), encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and r.get("items"):
                        rows.append(r)
        except OSError:
            return _CACHE["rows"]
        if len(rows) > KEEP * 2:   # 가끔 줄인다 (줄이는 사이 덧붙은 줄은 다음에 다시 읽힘)
            rows = rows[-KEEP:]
            tmp = _path() + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
                os.replace(tmp, _path())
                st = os.stat(_path())
                sig = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        _CACHE["sig"], _CACHE["rows"] = sig, rows
        return rows


def schedule(now=None):
    """배달 차례표: [{id, start, from, note, items, src}] (웹툰은 묶어서, 한 명씩 차례로)"""
    now = now or time.time()
    out, box = [], None
    for r in _rows():
        if now - r["t"] > SHOW_SEC:
            continue
        if r.get("src") == "webtoon":
            if box and r["t"] - box["last"] <= GROUP_SEC:
                box["items"] += r["items"]
                box["last"] = r["t"]
                continue
            box = {"id": r["id"], "src": "webtoon", "from": "", "note": "", "items": list(r["items"]), "first": r["t"], "last": r["t"]}
            out.append(box)
        else:
            out.append({"id": r["id"], "src": r.get("src", "api"), "from": r.get("from", ""), "note": r.get("note", ""),
                        "items": r["items"], "first": r["t"], "last": r["t"]})
    end = 0
    for d in sorted(out, key=lambda x: x["last"]):
        ready = d["last"] + (QUIET_SEC if d["src"] == "webtoon" else 0)
        d["start"] = max(ready, end)
        end = d["start"] + DUR
    return sorted(out, key=lambda x: x["start"])


def summary(items):
    """'웹툰 3편(작품A·작품B), 책 1권'"""
    by = {}
    for it in items:
        by.setdefault(it["kind"], []).append(it["title"])
    parts = []
    for k, titles in by.items():
        names = list(dict.fromkeys(titles))
        unit = "권" if k in ("book", "comic", "audio") else "편"
        parts.append("%s %d%s(%s%s)" % (KINDS.get(k, "책"), len(titles), unit, "·".join(names[:3]), " 외" if len(names) > 3 else ""))
    return ", ".join(parts)


def active(now=None):
    """지금 서재에 와 있는 배달원 (0~1명): {id, start, phase, target, say, ...}"""
    now = now or time.time()
    for d in schedule(now):
        el = now - d["start"]
        if 0 <= el < DUR:
            d["elapsed"] = el
            d["target"] = "desk" if 8 <= el < 38 else "entrance"
            d["say"] = (d["note"] or ("%s 왔습니다! 데스크에 둘게요." % summary(d["items"]))) if 10 <= el < 22 else ""
            return d
    return None


def first_arrival(d):
    """이 배달을 처음 알리는지 (프로세스마다 한 번)"""
    with _LOCK:
        if d["id"] in _DONE:
            return False
        _DONE.add(d["id"])
        if len(_DONE) > 500:
            _DONE.clear()
            _DONE.add(d["id"])
        return True


def recent(n=8):
    """관리자 화면: 최근 배달 (도착 순)"""
    now = time.time()
    rows = [d for d in schedule(now) if d["start"] <= now][-n:]
    return [{"t": d["start"], "from": d["from"], "src": d["src"], "text": summary(d["items"]), "note": d["note"]} for d in rows[::-1]]
