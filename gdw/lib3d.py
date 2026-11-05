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

VERSION = "2.25.0"
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


# ── 설정: 보여 줄 보관함 (DATA_DIR/lib3d.json {"libraries": ["세션:번호", …]} - 없거나 null이면 전부) ──
def _settings_path():
    return os.path.join(config.data_dir(), "lib3d.json")


def load_settings():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(libraries):
    """보여 줄 보관함 키 목록 저장 (None이면 전부). 다음 화면 요청부터 반영"""
    clean = None
    if libraries is not None:
        clean = sorted({str(k) for k in libraries if re.match(r"^[A-Za-z0-9_]+:\d+$", str(k))})
    data_ = dict(load_settings(), libraries=clean)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())
    with _LOCK:
        _DATA.update(at=0.0, v=None)
    return data_


PEOPLE_KINDS = ("walk", "browse", "read", "sit", "chat", "staff", "trooper", "elf", "beach")
PEOPLE_MAX = 20


def save_people(people):
    """층별 인물 수 {"general": {"walk": 3, ...}, ...} 저장. 빈 값·없는 종류는 자동(저장하지 않음)"""
    clean = {}
    for floor, kinds in (people or {}).items():
        if not re.match(r"^[A-Za-z0-9_]+$", str(floor)) or not isinstance(kinds, dict):
            continue
        row = {}
        for kind, value in kinds.items():
            if kind not in PEOPLE_KINDS or value is None or value == "":
                continue
            try:
                row[kind] = max(0, min(PEOPLE_MAX, int(value)))
            except (TypeError, ValueError):
                raise ValueError("인물 수는 0~%d 사이 숫자여야 합니다: %s %s" % (PEOPLE_MAX, floor, kind))
        if row:
            clean[str(floor)] = row
    data_ = dict(load_settings(), people=clean)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())
    return clean


OUTSIDE_CHOICES = {"time": ("auto", "day", "dusk", "night"), "season": ("auto", "spring", "summer", "autumn", "winter"),
                   "weather": ("auto", "clear", "cloudy", "rain", "snow")}


def save_outside(outside):
    """창밖 풍경 {"time", "season", "weather"} 저장 (모르는 값은 기본값으로)"""
    clean = {}
    for key, choices in OUTSIDE_CHOICES.items():
        value = str((outside or {}).get(key) or "")
        clean[key] = value if value in choices else ("clear" if key == "weather" else "auto")
    data_ = dict(load_settings(), outside=clean)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())
    return clean


def save_models(value):
    """3D 모형: basic(코드로 그린 가구·차) | real(모형 파일)"""
    clean = "real" if value == "real" else "basic"
    data_ = dict(load_settings(), models=clean)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())
    return clean


# ── CRARES 건물 현수막 그림: 등록한 주소의 그림을 서버가 받아 두었다가 내려준다 (브라우저 CORS 제한을 피함) ──
BANNER_MAX = 15 * 1024 * 1024
BANNER_TTL = 6 * 3600


def save_banner(url):
    url = str(url or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        raise ValueError("그림 주소는 http:// 또는 https://로 시작해야 합니다.")
    data_ = dict(load_settings(), banner=url)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())
    return url


def save_banner_library(lib_key, sec):
    """현수막을 보관함 표지 무작위로 (lib_key '세션:보관함번호', 비우면 끔), sec초마다 바꿈"""
    lib_key = str(lib_key or "").strip()
    if lib_key and not re.match(r"^[A-Za-z0-9_]+:\d+$", lib_key):
        raise ValueError("보관함을 골라 주세요.")
    try:
        sec = max(5, min(3600, int(sec or 30)))
    except (TypeError, ValueError):
        sec = 30
    data_ = dict(load_settings(), banner_lib=lib_key, banner_sec=sec)
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data_, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _settings_path())


def banner_info():
    st = load_settings()
    url = st.get("banner") or ""
    lib_key = st.get("banner_lib") or ""
    return {"url": url, "v": hashlib.md5(url.encode("utf-8")).hexdigest()[:10] if url else "",
            "lib": lib_key, "sec": int(st.get("banner_sec") or 30),
            "mode": "library" if lib_key else ("url" if url else "")}


_PICK = {}   # 보관함 → (읽은 시각, 작품 목록)


def banner_pick():
    """현수막에 띄울 무작위 작품 {key, title, lib}: 설정한 보관함의 최근 작품 중 하나 (목록은 5분 캐시)"""
    import random
    lib_key = load_settings().get("banner_lib") or ""
    m = re.match(r"^([A-Za-z0-9_]+):(\d+)$", lib_key)
    if not m or m.group(1) not in config.db_types():
        raise ValueError("현수막 보관함이 설정돼 있지 않습니다.")
    db_type, lib_id = m.group(1), int(m.group(2))
    at, series, name = _PICK.get(lib_key, (0, None, ""))
    if series is None or time.time() - at > CACHE_SEC:
        gw = bookoasis_db.gateway(db_type)
        series = [x for x in _series(gw, lib_id, per_library()) if x.get("last")]
        try:
            row = gw.fetch_all("SELECT name FROM libraries WHERE id = %s", (lib_id,))
            name = (row[0].get("name") if row else "") or ""
        except Exception:  # noqa: BLE001
            name = ""
        _PICK[lib_key] = (time.time(), series, name)
    if not series:
        raise ValueError("그 보관함에 작품이 없습니다.")
    s = random.choice(series)
    return {"key": "%s:%s" % (db_type, s["last"]), "title": s["title"], "count": s.get("count"), "lib": lib_key, "lib_name": name, "db": db_type}


def banner_image(force=False):
    """(그림 바이트, content-type) - 등록한 주소가 바뀌었거나 6시간이 지나면 다시 받는다"""
    url = load_settings().get("banner") or ""
    if not url:
        raise ValueError("현수막 그림 주소가 없습니다.")
    path = os.path.join(config.data_dir(), "lib3d_banner.bin")
    meta_path = path + ".json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    if not force and meta.get("url") == url and os.path.isfile(path) and time.time() - os.path.getmtime(path) < BANNER_TTL:
        with open(path, "rb") as f:
            return f.read(), meta.get("type") or "image/jpeg"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (BookOasisAssistant 3D library)"})
    try:
        with urlopen(req, timeout=20) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data_ = r.read(BANNER_MAX + 1)
    except Exception as error:  # noqa: BLE001 - 못 받으면 예전 그림이라도
        if meta.get("url") == url and os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read(), meta.get("type") or "image/jpeg"
        raise ValueError("현수막 그림을 받지 못했습니다: %s" % error) from error
    if len(data_) > BANNER_MAX:
        raise ValueError("현수막 그림이 너무 큽니다 (15MB 넘음).")
    if not ctype.startswith("image/"):
        sig = data_[:12]
        ctype = ("image/jpeg" if sig[:3] == b"\xff\xd8\xff" else "image/png" if sig[:8] == b"\x89PNG\r\n\x1a\n"
                 else "image/gif" if sig[:4] == b"GIF8" else "image/webp" if sig[8:12] == b"WEBP" else "")
        if not ctype:
            raise ValueError("그 주소는 그림(jpg·png·gif·webp)이 아닙니다.")
    os.makedirs(config.data_dir(), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data_)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"url": url, "type": ctype}, f)
    return data_, ctype


def all_libraries():
    """설정 화면용: 세션별 보관함 전부 [{key, db_type, id, name, shown}] (작품은 세지 않음 - 빠르게)"""
    chosen = load_settings().get("libraries")
    out, errors = [], []
    for db_type in config.db_types():
        if not config.db_url(db_type):
            continue
        try:
            for lib in bookoasis_db.gateway(db_type).fetch_all("SELECT id, name FROM libraries ORDER BY name"):
                key = "%s:%s" % (db_type, lib["id"])
                out.append({"key": key, "db_type": db_type, "id": int(lib["id"]),
                            "name": lib.get("name") or "보관함 %s" % lib["id"], "shown": chosen is None or key in chosen})
        except Exception as error:  # noqa: BLE001
            errors.append("%s: %s" % (db_type, error))
    return {"libraries": out, "all": chosen is None, "errors": errors}


def data(force=False):
    """{"libraries": [{"key", "db_type", "id", "name", "series": [...]}], "book_url": bool, "at"} (5분 캐시)"""
    with _LOCK:
        if not force and _DATA["v"] is not None and time.time() - _DATA["at"] < CACHE_SEC:
            return _DATA["v"]
    libs, errors = [], []
    limit = per_library()
    chosen = load_settings().get("libraries")   # None이면 전부
    for db_type in config.db_types():
        if not config.db_url(db_type):
            continue
        try:
            gw = bookoasis_db.gateway(db_type)
            for lib in gw.fetch_all("SELECT id, name FROM libraries ORDER BY name"):
                if chosen is not None and "%s:%s" % (db_type, lib["id"]) not in chosen:
                    continue
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
    return "%s/#detail?%s" % (public_url(), q)


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


# ── 3D 서재 안에서 읽기 (자체 뷰어) ──
# BookOasis 뷰어는 다른 주소 안에 넣을 수 없어서(X-Frame-Options: SAMEORIGIN) 간단한 뷰어를 따로 둔다.
# 만화·웹툰 zip/cbz·이미지 폴더는 그림을, epub은 본문(문단·그림)을, pdf는 브라우저 PDF 보기로. 읽은 위치는 BookOasis와 따로.
_LIST_CACHE = {}
_NUM = re.compile(r"(\d+)")


def _natural(s):
    return [int(p) if p.isdigit() else p.lower() for p in _NUM.split(str(s))]


def public_url():
    """브라우저가 여는 BookOasis 주소 (열기·BookOasis 뷰어 링크). LIB3D_PUBLIC_URL, 없으면 BOOKOASIS_URL"""
    return (config.env("LIB3D_PUBLIC_URL") or _bookoasis()).rstrip("/")


def _book(bkey):
    """'세션:도서번호' → (세션, 행 {id, library_id, series_name, title, file_path, file_format}) 또는 예외"""
    m = re.match(r"^([A-Za-z0-9_]+):(\d+)$", str(bkey or ""))
    if not m or m.group(1) not in config.db_types():
        raise ValueError("잘못된 도서 키")
    gw = bookoasis_db.gateway(m.group(1))
    try:
        row = gw.fetch_one("SELECT id, library_id, series_name, title, file_path, file_format FROM books WHERE id = %s",
                           (int(m.group(2)),))
    except Exception:  # noqa: BLE001
        row = gw.fetch_one("SELECT id, library_id, file_path FROM books WHERE id = %s", (int(m.group(2)),))
    if not row:
        raise ValueError("없는 도서")
    return m.group(1), row


def volumes(bkey):
    """그 책이 속한 시리즈의 권(회차) 목록 [{key, title, format}] (이름 자연 정렬)"""
    db_type, row = _book(bkey)
    gw = bookoasis_db.gateway(db_type)
    rows = []
    if row.get("series_name") is not None and row.get("library_id") is not None:
        try:
            rows = gw.fetch_all("SELECT id, title, file_path, file_format FROM books WHERE library_id = %s AND "
                                "series_name = %s AND COALESCE(is_deleted, 0) = 0", (row["library_id"], row["series_name"]))
        except Exception:  # noqa: BLE001
            rows = []
    rows = rows or [row]
    rows.sort(key=lambda r: _natural(os.path.basename(str(r.get("file_path") or r.get("title") or ""))))
    return [{"key": "%s:%s" % (db_type, r["id"]), "id": int(r["id"]),
             "title": r.get("title") or os.path.splitext(os.path.basename(str(r.get("file_path") or "")))[0],
             "format": _kind(str(r.get("file_path") or ""))} for r in rows]


def _kind(path):
    low = path.lower()
    if low.endswith((".zip", ".cbz")):
        return "images"
    if low.endswith(".epub"):
        return "epub"
    if low.endswith(".pdf"):
        return "pdf"
    if os.path.isdir(path):
        return "images"
    return "unsupported"


def _entries(path):
    """zip/cbz 또는 그림 폴더의 그림 목록 (자연 정렬, 파일이 바뀌면 다시 읽음)"""
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        raise ValueError("파일을 열 수 없습니다 (마운트 확인)")
    hit = _LIST_CACHE.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    if os.path.isdir(path):
        names = sorted((n for n in os.listdir(path) if n.lower().endswith(_IMG)), key=_natural)
    else:
        with zipfile.ZipFile(path) as z:
            names = sorted((n for n in z.namelist() if n.lower().endswith(_IMG) and not n.endswith("/")), key=_natural)
    if len(_LIST_CACHE) > 200:
        _LIST_CACHE.clear()
    _LIST_CACHE[path] = (sig, names)
    return names


def _epub_spine(path):
    """epub의 읽는 순서 [본문 파일 경로] (OPF spine)"""
    hit = _LIST_CACHE.get(("epub", path))
    if hit:
        return hit
    with zipfile.ZipFile(path) as z:
        container = z.read("META-INF/container.xml").decode("utf-8", "replace")
        opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
        opf = z.read(opf_path).decode("utf-8", "replace")
    base = posix_dir(opf_path)
    items = dict(re.findall(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', opf))
    items.update({i: h for h, i in re.findall(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', opf)})
    spine = [join_path(base, items[i]) for i in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf) if i in items]
    _LIST_CACHE[("epub", path)] = spine
    return spine


def posix_dir(p):
    return p.rsplit("/", 1)[0] if "/" in p else ""


def join_path(base, href):
    from urllib.parse import unquote
    parts = (base.split("/") if base else []) + unquote(href.split("#", 1)[0]).split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def book_info(bkey):
    """뷰어용 {key, title, kind, count, series, volumes, kiosk(BookOasis 뷰어 주소의 앞부분)}"""
    db_type, row = _book(bkey)
    path = str(row.get("file_path") or "")
    kind = _kind(path)
    count = 0
    if kind == "images":
        count = len(_entries(path))
    elif kind == "epub":
        count = len(_epub_spine(path))
    elif kind == "pdf":
        count = 1
    return {"key": bkey, "id": int(row["id"]), "db_type": db_type, "kind": kind, "count": count,
            "title": row.get("title") or os.path.splitext(os.path.basename(path))[0],
            "series": row.get("series_name") or "",
            "kiosk": "%s/?kiosk=1&book=%s&type=%s" % (public_url(), row["id"], quote(db_type))}


def page(bkey, index):
    """그림 한 장 (바이트, 형식)"""
    import mimetypes
    _db, row = _book(bkey)
    path = str(row.get("file_path") or "")
    names = _entries(path)
    i = int(index)
    if not 0 <= i < len(names):
        raise ValueError("없는 쪽")
    name = names[i]
    if os.path.isdir(path):
        with open(os.path.join(path, name), "rb") as f:
            data = f.read()
    else:
        with zipfile.ZipFile(path) as z:
            data = z.read(name)
    return data, mimetypes.guess_type(name)[0] or "image/jpeg"


def chapter(bkey, index):
    """epub 한 장의 본문을 안전한 HTML로 (문단·제목·목록·그림만, 스크립트·스타일·링크는 뺌)"""
    from html import escape
    from html.parser import HTMLParser
    _db, row = _book(bkey)
    path = str(row.get("file_path") or "")
    spine = _epub_spine(path)
    i = int(index)
    if not 0 <= i < len(spine):
        raise ValueError("없는 장")
    with zipfile.ZipFile(path) as z:
        src = z.read(spine[i]).decode("utf-8", "replace")
    base = posix_dir(spine[i])
    keep = {"p": "p", "h1": "h2", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h4", "h6": "h4", "li": "li",
            "blockquote": "blockquote", "br": "br", "hr": "hr"}
    out, stack = [], []

    class P(HTMLParser):
        skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "head"):
                self.skip += 1
                return
            if tag in ("img", "image"):
                a = dict(attrs)
                src_ = a.get("src") or a.get("xlink:href") or a.get("href")
                if src_:
                    out.append('<img src="api/lib3d/res?b=%s&p=%s" alt="">' % (quote(bkey), quote(join_path(base, src_))))
                return
            t = keep.get(tag)
            if t in ("br", "hr"):
                out.append("<%s>" % t)
            elif t:
                out.append("<%s>" % t)
                stack.append(t)

        def handle_endtag(self, tag):
            if tag in ("script", "style", "head"):
                self.skip = max(0, self.skip - 1)
                return
            t = keep.get(tag)
            if t and t not in ("br", "hr") and t in stack:
                while stack:
                    x = stack.pop()
                    out.append("</%s>" % x)
                    if x == t:
                        break

        def handle_data(self, data):
            if not self.skip and data.strip():
                out.append(escape(data))
    P().feed(src)
    while stack:
        out.append("</%s>" % stack.pop())
    return "".join(out)


def resource(bkey, inner):
    """epub 안의 그림"""
    import mimetypes
    _db, row = _book(bkey)
    path = str(row.get("file_path") or "")
    if not str(inner).lower().endswith(_IMG + (".svg",)):
        raise ValueError("그림이 아닙니다")
    with zipfile.ZipFile(path) as z:
        return z.read(inner), mimetypes.guess_type(inner)[0] or "image/jpeg"


def pdf_path(bkey):
    _db, row = _book(bkey)
    path = str(row.get("file_path") or "")
    if _kind(path) != "pdf":
        raise ValueError("pdf가 아닙니다")
    return path
