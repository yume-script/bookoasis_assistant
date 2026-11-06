"""BookOasis 3D 서재 - colaiuta 건물 1층 '재즈 청음실'의 인터넷 재즈 라디오

방송국 목록은 colaiuta77/jazzradio 플러그인을 참고했다(코드는 따로 썼다).
- 스트림 중계: 브라우저가 같은 주소에서 받아야 소리를 분석(스펙트럼 막대)할 수 있어서 서버가 이어 준다.
- 지금 곡: 스트림을 잠깐 열어 ICY 메타데이터(StreamTitle='가수 - 곡')를 읽는다 (방송국마다 20초 보관).
- 앨범 커버: iTunes 검색(키 필요 없음)으로 가수·곡명이 맞는 것을 고르고, 그림도 서버가 이어 준다(정해 둔 주소만).
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

STATIONS = [
    {"id": "relaxingjazz", "name": "RelaxingJazz", "sub": "Smooth Jazz · Saint Lucia", "url": "https://443-1.autopo.st/171/stream/3/",
     "home": "https://relaxingjazz.com/"},
    {"id": "swissjazz", "name": "Radio Swiss Jazz", "sub": "Jazz · Blues · Soul · Switzerland", "url": "https://stream.srg-ssr.ch/srgssr/rsj/mp3/128",
     "home": "https://www.radioswissjazz.ch/"},
    {"id": "jazz24", "name": "Jazz24", "sub": "Classic & Modern Jazz · Seattle", "url": "https://knkx-live-a.edge.audiocdn.com/6285_128k",
     "home": "https://www.jazz24.org/"},
]
UA = "Mozilla/5.0 (BookOasisAssistant 3D library jazz room)"
NOW_TTL = 20
ART_HOSTS = re.compile(r"^https://is\d+-ssl\.mzstatic\.com/")
_LOCK = threading.Lock()
_NOW = {}      # 방송국 → (시각, {artist, title, raw})
_ART = {}      # "가수\n곡" → (시각, 그림 주소 또는 "")


def station(sid):
    s = next((x for x in STATIONS if x["id"] == sid), None)
    if not s:
        raise ValueError("없는 방송국입니다.")
    return s


def stations():
    return [{k: s[k] for k in ("id", "name", "sub", "home")} for s in STATIONS]


def open_stream(sid, meta=False):
    """방송 스트림 응답 (meta=True면 ICY 메타데이터를 섞어 받음)"""
    s = station(sid)
    headers = {"User-Agent": UA, "Accept": "audio/mpeg, */*"}
    if meta:
        headers["Icy-MetaData"] = "1"
    return urllib.request.urlopen(urllib.request.Request(s["url"], headers=headers), timeout=15)


def _icy_title(sid):
    """스트림 앞부분에서 StreamTitle 한 번 읽기"""
    with open_stream(sid, meta=True) as r:
        every = int(r.headers.get("icy-metaint") or 0)
        if not every:
            return ""
        for _ in range(3):   # 처음 몇 블록 안에 제목이 온다
            left = every
            while left > 0:
                chunk = r.read(min(left, 65536))
                if not chunk:
                    return ""
                left -= len(chunk)
            n = r.read(1)
            if not n:
                return ""
            size = n[0] * 16
            if not size:
                continue
            raw = r.read(size).rstrip(b"\0").decode("utf-8", "replace")
            m = re.search(r"StreamTitle='(.*?)';", raw)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return ""


def _split(raw):
    raw = re.sub(r"\s+", " ", raw or "").strip()
    if " - " in raw:
        a, t = raw.split(" - ", 1)
        return a.strip(), t.strip()
    return "", raw


def _artwork(artist, title):
    if not title:
        return ""
    key = (artist + "\n" + title).lower()
    with _LOCK:
        hit = _ART.get(key)
        if hit and time.time() - hit[0] < 6 * 3600:
            return hit[1]
    url = ""
    try:
        q = urllib.parse.urlencode({"term": (artist + " " + title).strip(), "media": "music", "entity": "song", "limit": 8})
        with urllib.request.urlopen(urllib.request.Request("https://itunes.apple.com/search?" + q, headers={"User-Agent": UA}), timeout=8) as r:
            results = json.loads(r.read().decode("utf-8", "replace")).get("results") or []
        norm = lambda v: re.sub(r"[^0-9a-z가-힣]", "", str(v or "").lower())
        best = None
        for it in results:
            score = (2 if norm(it.get("trackName")) == norm(title) else 1 if norm(title) in norm(it.get("trackName")) else 0) \
                + (2 if artist and norm(artist) in norm(it.get("artistName")) else 0)
            if score >= 3 and (not best or score > best[0]):
                best = (score, it)
        if best:
            url = re.sub(r"/\d+x\d+bb\.", "/600x600bb.", str(best[1].get("artworkUrl100") or ""))
    except Exception:  # noqa: BLE001 - 커버가 없으면 턴테이블만
        url = ""
    with _LOCK:
        if len(_ART) > 500:
            _ART.clear()
        _ART[key] = (time.time(), url if ART_HOSTS.match(url) else "")
    return _ART[key][1]


def now_playing(sid):
    station(sid)
    with _LOCK:
        hit = _NOW.get(sid)
        if hit and time.time() - hit[0] < NOW_TTL:
            return hit[1]
    try:
        raw = _icy_title(sid)
    except Exception:  # noqa: BLE001
        raw = ""
    artist, title = _split(raw)
    out = {"artist": artist, "title": title, "raw": raw, "art": _artwork(artist, title) if title else ""}
    with _LOCK:
        _NOW[sid] = (time.time(), out)
    return out


def art_bytes(url):
    """앨범 커버 그림 (iTunes 그림 주소만)"""
    if not ART_HOSTS.match(str(url or "")):
        raise ValueError("허용하지 않는 그림 주소입니다.")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=10) as r:
        return r.read(3 * 1024 * 1024), r.headers.get("Content-Type") or "image/jpeg"
