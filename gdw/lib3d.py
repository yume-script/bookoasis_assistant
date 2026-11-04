# -*- coding: utf-8 -*-
"""BookOasis 3D 서재 (화면 /library3d): BookOasis 보관함을 부스로, 작품(시리즈)을 책장의 책으로 보여 준다. 혼자 둘러보기.

- 보관함·작품: BookOasis DB에서 읽는다 (세션마다 libraries, 보관함마다 최근 추가된 작품 LIB3D_PER_LIBRARY개)
- 표지 (/api/lib3d/cover?k=세션:도서번호 - 가까이 간 책만 화면이 요청, 작게 줄여 DATA_DIR/lib3d_covers에 저장):
  BookOasis가 화면에 쓰는 표지 그대로 - BookOasis 주소(BOOKOASIS_URL)의 /covers/… (로그인 없이 열림)
  1) 시리즈 대표 표지 ({보관함}/series_{md5(시리즈)}.jpg) 2) 그 책의 books.cover_image 3) 같은 시리즈 다른 책의 cover_image
  BookOasis에 표지가 없을 때만: LIB3D_COVER_URL → 웹툰 다운로더 썸네일 → 폴더의 cover/folder/poster → 첫 zip의 첫 그림
- 책을 누르면 BookOasis의 작품 상세 화면을 연다: {BOOKOASIS_URL}/#detail?series=…&libraryId=…&type=세션&repBookId=…
  (BookOasis 화면이 쓰는 주소 형식, 다른 형식이 필요하면 LIB3D_BOOK_URL)
"""
import hashlib
import io
import json
import os
import re
import threading
import time
import zipfile
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from . import bookoasis_db, config

VERSION = "1.2.0"
CACHE_SEC = 300
COVER_WIDTH = 200
_DATA = {"at": 0.0, "v": None}
_LOCK = threading.Lock()
_ID_IN_NAME = re.compile(r"\((\d{3,})\)\s*$")
_IMG = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def enabled():
    return config.env_bool("LIB3D_ENABLED", False)


def per_library():
    try:
        return max(10, min(400, int(config.env("LIB3D_PER_LIBRARY", "120") or 120)))
    except ValueError:
        return 120


def _cover_dir():
    path = os.path.join(config.data_dir(), "lib3d_covers")
    os.makedirs(path, exist_ok=True)
    return path


def _series(gw, library_id, limit):
    """[{"title", "count", "last"}] 최근 추가된 작품부터. series_name이 없는 DB면 폴더로 묶는다."""
    alive = "COALESCE(is_deleted, 0) = 0"
    try:
        rows = gw.fetch_all(
            "SELECT series_name AS s, COUNT(*) AS n, MAX(id) AS last FROM books WHERE library_id = %s AND " + alive +
            " GROUP BY series_name ORDER BY last DESC LIMIT %s", (library_id, limit))
        out = [{"title": r.get("s") or "", "count": int(r.get("n") or 0), "last": int(r.get("last") or 0)} for r in rows]
        if out and any(x["title"] for x in out):
            return out
    except Exception:  # noqa: BLE001 - 칼럼이 없는 BookOasis 버전
        pass
    rows = gw.fetch_all("SELECT id, file_path FROM books WHERE library_id = %s AND " + alive +
                        " ORDER BY id DESC LIMIT %s", (library_id, limit * 40))
    groups = {}
    for r in rows:
        folder = os.path.dirname(str(r.get("file_path") or ""))
        g = groups.setdefault(folder, {"title": os.path.basename(folder) or folder, "count": 0, "last": int(r["id"])})
        g["count"] += 1
    return list(groups.values())[:limit]


def data(force=False):
    """{"libraries": [{"key", "db_type", "id", "name", "series": [...]}], "book_url": bool, "at"} (5분 캐시)"""
    with _LOCK:
        if not force and _DATA["v"] is not None and time.time() - _DATA["at"] < CACHE_SEC:
            return _DATA["v"]
    libs, errors = [], []
    limit = per_library()
    for db_type in config.db_types():
        if not config.db_url(db_type):
            continue
        try:
            gw = bookoasis_db.gateway(db_type)
            for lib in gw.fetch_all("SELECT id, name FROM libraries ORDER BY name"):
                series = _series(gw, int(lib["id"]), limit)
                if series:
                    libs.append({"key": "%s:%s" % (db_type, lib["id"]), "db_type": db_type, "id": int(lib["id"]),
                                 "name": lib.get("name") or "보관함 %s" % lib["id"], "series": series})
        except Exception as error:  # noqa: BLE001
            errors.append("%s: %s" % (db_type, error))
    out = {"libraries": libs, "errors": errors, "book_url": True, "at": time.time()}
    with _LOCK:
        _DATA.update(at=time.time(), v=out)
    return out


def _bookoasis():
    return config.settings()["bookoasis_url"].rstrip("/")


def book_url(db_type, book_id, library_id="", series=""):
    """BookOasis 작품 상세 화면 주소. BookOasis 화면(static/js/url_obfuscator.js)이 받는 형식:
    /#detail?series=…&libraryId=…&type=…&repBookId=… (LIB3D_BOOK_URL이 있으면 그 형식)"""
    tpl = config.env("LIB3D_BOOK_URL") or ""
    if tpl:
        return (tpl.replace("{id}", str(book_id)).replace("{db_type}", db_type).replace("{library_id}", str(library_id))
                .replace("{series}", quote(str(series or ""))).replace("{bookoasis}", _bookoasis()))
    if not series:
        return ""
    q = urlencode({"series": series, "libraryId": library_id or "all", "type": db_type, "repBookId": book_id}, quote_via=quote)
    return "%s/#detail?%s" % (_bookoasis(), q)


# ── 표지 ──
def _shrink(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im = im.convert("RGB")
        if im.width > COVER_WIDTH:
            im = im.resize((COVER_WIDTH, max(1, int(im.height * COVER_WIDTH / float(im.width)))))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - Pillow가 없거나 그림이 아님: 원본 그대로
        return raw


def _http(url):
    from urllib.parse import urlparse
    u = urlparse(url)
    # 네이버·카카오 이미지 서버는 자기 사이트에서 온 요청만 받는 경우가 있어 Referer를 그 서버 주소로
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "%s://%s/" % (u.scheme, u.netloc)})
    with urlopen(req, timeout=15) as resp:
        return resp.read()


def _cover_src(cover_image):
    """books.cover_image → 주소 (BookOasis 화면의 getBookCoverSrc와 같은 규칙: 파일 이름이면 /covers/…)"""
    c = str(cover_image or "").strip()
    if not c:
        return ""
    if c.startswith(("http://", "https://")):
        return c
    if c.startswith("/api/"):
        return ""          # 오디오북·영상 포스터 주소는 로그인이 필요하다
    c = c.lstrip("/\\").split("?", 1)[0]
    if c.lower().startswith("covers/"):
        c = c[7:].lstrip("/\\")
    if not c or "." not in os.path.basename(c):
        return ""
    return "%s/covers/%s" % (_bookoasis(), quote(c.replace("\\", "/")))


def bookoasis_covers(gw, row):
    """BookOasis에 있는 표지 주소 후보 (시리즈 대표 표지 → 이 책 → 같은 시리즈 다른 책)"""
    out = []
    series, lib = str(row.get("series_name") or ""), row.get("library_id")
    if series:
        h = hashlib.md5(series.encode("utf-8")).hexdigest()
        if lib is not None:
            out.append("%s/covers/%s/series_%s.jpg" % (_bookoasis(), lib, h))
        out.append("%s/covers/series_%s.jpg" % (_bookoasis(), h))
    out.append(_cover_src(row.get("cover_image")))
    if series and lib is not None:
        try:
            for r in gw.fetch_all("SELECT cover_image FROM books WHERE library_id = %s AND series_name = %s AND "
                                  "cover_image IS NOT NULL AND cover_image <> '' ORDER BY id LIMIT 3", (lib, series)):
                out.append(_cover_src(r.get("cover_image")))
        except Exception:  # noqa: BLE001
            pass
    seen, uniq = set(), []
    for u in out:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _webtoon_thumb(folder):
    """폴더 이름 끝의 (작품번호)로 웹툰 다운로더 작품 기록의 썸네일 주소를 찾는다"""
    m = _ID_IN_NAME.search(os.path.basename(folder))
    if not m:
        return ""
    try:
        from wtm import state_store as ss
    except Exception:  # noqa: BLE001
        return ""
    tid = m.group(1)
    for loader in (ss.load_titles, ss.load_kakao_titles):
        try:
            t = loader().get(tid)
        except Exception:  # noqa: BLE001
            t = None
        if t and (t.get("thumbnail") or t.get("cover_url")):
            return t.get("thumbnail") or t.get("cover_url")
    return ""


def _folder_image(folder):
    for name in ("cover", "folder", "poster", "Cover", "Folder", "Poster"):
        for ext in _IMG:
            p = os.path.join(folder, name + ext)
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    return f.read()
    return b""


def _zip_image(file_path, folder):
    """그 책(zip/cbz)이나 폴더의 첫 zip에서 이름순 첫 그림"""
    cands = [file_path] if str(file_path).lower().endswith((".zip", ".cbz")) else []
    if not cands:
        try:
            cands = [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if n.lower().endswith((".zip", ".cbz"))][:1]
        except OSError:
            cands = []
    for path in cands:
        try:
            with zipfile.ZipFile(path) as z:
                names = sorted(n for n in z.namelist() if n.lower().endswith(_IMG))
                if names:
                    return z.read(names[0])
        except (OSError, zipfile.BadZipFile):
            continue
    return b""


def cover(key):
    """key '세션:도서번호' → (그림 바이트, 형식) 또는 (None, 이유). 한 번 만든 표지는 파일로 저장해 둔다."""
    m = re.match(r"^([A-Za-z0-9_]+):(\d+)$", str(key or ""))
    if not m or m.group(1) not in config.db_types():
        return None, "잘못된 표지 키"
    db_type, book_id = m.group(1), int(m.group(2))
    path = os.path.join(_cover_dir(), "%s_%d.jpg" % (db_type, book_id))
    miss = path + ".none"
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read(), "image/jpeg"
    if os.path.isfile(miss) and time.time() - os.path.getmtime(miss) < 86400:
        return None, "표지 없음"
    gw = bookoasis_db.gateway(db_type)
    try:
        row = gw.fetch_one("SELECT id, library_id, series_name, cover_image, file_path FROM books WHERE id = %s", (book_id,))
    except Exception:  # noqa: BLE001 - 칼럼이 다른 BookOasis 버전
        row = gw.fetch_one("SELECT id, file_path FROM books WHERE id = %s", (book_id,))
    if not row:
        return None, "없는 도서"
    file_path = str(row.get("file_path") or "")
    folder = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
    raw = b""
    tpl = config.env("LIB3D_COVER_URL") or ""
    tries = [(lambda u=u: _http(u)) for u in bookoasis_covers(gw, row)]   # BookOasis 표지 먼저
    if tpl:
        tries.append(lambda: _http(tpl.replace("{id}", str(book_id)).replace("{db_type}", db_type)
                                   .replace("{bookoasis}", config.settings()["bookoasis_url"])))
    tries.append(lambda: _http(_webtoon_thumb(folder)) if _webtoon_thumb(folder) else b"")
    tries.append(lambda: _folder_image(folder))
    tries.append(lambda: _zip_image(file_path, folder))
    for fn in tries:
        try:
            raw = fn() or b""
        except Exception:  # noqa: BLE001
            raw = b""
        if len(raw) > 200:
            break
    if len(raw) <= 200:
        open(miss, "w").close()
        return None, "표지 없음"
    raw = _shrink(raw)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
    return raw, "image/jpeg"


def open_url(key):
    """책 열기: key '세션:도서번호' → BookOasis 주소 (LIB3D_BOOK_URL이 없으면 '')"""
    m = re.match(r"^([A-Za-z0-9_]+):(\d+)$", str(key or ""))
    if not m or m.group(1) not in config.db_types():
        return "", ""
    row = None
    try:
        row = bookoasis_db.gateway(m.group(1)).fetch_one(
            "SELECT id, library_id, series_name, file_path FROM books WHERE id = %s", (int(m.group(2)),))
    except Exception:  # noqa: BLE001
        pass
    row = row or {}
    return (book_url(m.group(1), m.group(2), row.get("library_id") or "", row.get("series_name") or ""),
            row.get("file_path") or "")


def info_json(key):
    url, path = open_url(key) if key else ("", "")
    return json.dumps({"url": url, "path": path}, ensure_ascii=False)
