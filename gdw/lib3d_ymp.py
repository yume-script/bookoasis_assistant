"""BookOasis 3D 서재 영화관 층 - YMPlayer의 IPTV·텔레그램을 서버끼리 중계

브라우저가 YMPlayer를 직접 부르지 않고 이 서버가 YMPlayer에 로그인해서(서재용 계정) 대신 받아 넘긴다.
그래서 화면 입장에서는 모두 서재 주소라 https/http 섞임·다른 사이트 쿠키 문제가 없고,
영상이 같은 주소에서 오므로 3D 상영관 스크린(WebGL 텍스처)에 바로 그릴 수 있다.

설정(.env)
  LIB3D_YMPLAYER_URL        브라우저에서 열리는 YMPlayer 주소 (영화관 층을 만들고 [새 탭으로]에 씀)
  LIB3D_YMPLAYER_INTERNAL   이 서버가 부를 YMPlayer 주소 (비우면 위와 같음, 예 http://127.0.0.1:8899)
  LIB3D_YMPLAYER_USER / LIB3D_YMPLAYER_PASSWORD  서재가 쓸 YMPlayer 계정 (보여 줄 범위를 YMPlayer에서 제한해 두기를 권함)
  LIB3D_YMPLAYER_VIEWERS    관람자 계정도 영화관을 볼지 (기본 true)

중계하는 것 (나머지 YMPlayer 기능·관리자 API는 막음)
  sources                            IPTV·텔레그램 소스 목록 (id·이름·채널만)
  iptv/<sid>/channels, iptv/<sid>/epg
  stream?url=...                     IPTV 스트림 (HLS 재생목록 안의 주소도 이 서버로 바꿔 넣음)
  tg/<sid>/channels|videos|home, tg/<sid>/video/<c>/<m>
  tg/<sid>/stream|transcode|thumb|sub/<c>/<m>, POST tg/<sid>/hls/<c>/<m>, tg-hls/<job>/<name>
"""
import http.cookiejar
import json
import logging
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import config, lib3d

log = logging.getLogger("gdw.lib3d_ymp")

TIMEOUT = 30
_ID = r"[A-Za-z0-9_-]{1,40}"
_CM = r"-?\d{1,20}/\d{1,12}"
ALLOW_GET = [re.compile(p) for p in (
    r"^iptv/%s/(channels|epg)$" % _ID,
    r"^stream$",
    r"^tg/%s/(channels|videos|home)$" % _ID,
    r"^tg/%s/(video|stream|transcode|thumb|sub)/%s$" % (_ID, _CM),
    r"^tg-hls/[A-Za-z0-9_-]{1,64}/[A-Za-z0-9_.-]{1,64}$",
)]
ALLOW_POST = [re.compile(r"^tg/%s/hls/%s$" % (_ID, _CM))]

_LOCK = threading.Lock()
_STATE = {"opener": None, "base": ""}


def base():
    return str(config.env("LIB3D_YMPLAYER_INTERNAL") or "").strip().rstrip("/") or lib3d.ymplayer_url()


def configured():
    return bool(base() and config.env("LIB3D_YMPLAYER_USER") and config.env("LIB3D_YMPLAYER_PASSWORD"))


def viewers_ok():
    return str(config.env("LIB3D_YMPLAYER_VIEWERS", "true") or "true").strip().lower() not in ("false", "0", "no", "off")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):   # 로그인 화면으로 넘기는 것 등은 따라가지 않고 그대로 실패로
        return None


def _login():
    """서재용 계정으로 로그인한 opener (쿠키 보관)"""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect())
    body = json.dumps({"username": config.env("LIB3D_YMPLAYER_USER"), "password": config.env("LIB3D_YMPLAYER_PASSWORD"),
                       "remember": True}).encode()
    req = urllib.request.Request(base() + "/api/auth/login", data=body, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError("YMPlayer 로그인 실패 (%s): %s" % (e.code, _err_text(e)))
    except OSError as e:
        raise RuntimeError("YMPlayer에 연결하지 못했습니다 (%s): %s" % (base(), e))
    _STATE["opener"], _STATE["base"] = opener, base()
    return opener


def _opener():
    with _LOCK:
        if _STATE["opener"] is None or _STATE["base"] != base():
            return _login()
        return _STATE["opener"]


def _err_text(e):
    try:
        raw = e.read().decode("utf-8", "replace")
        return (json.loads(raw).get("error") if raw.startswith("{") else raw)[:200]
    except Exception:  # noqa: BLE001
        return str(e)


def open_upstream(path, query="", headers=None, data=None):
    """YMPlayer /api/<path>를 열어 응답 객체(스트리밍)를 돌려준다. 로그인이 풀렸으면 한 번 다시 로그인"""
    url = "%s/api/%s%s" % (base(), path, ("?" + query) if query else "")
    for attempt in (0, 1):
        opener = _opener()
        req = urllib.request.Request(url, data=data, headers=dict(headers or {}), method="POST" if data is not None else "GET")
        try:
            return opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and attempt == 0:
                with _LOCK:
                    _STATE["opener"] = None
                continue
            return e   # 상태 코드·본문을 그대로 넘긴다
    raise RuntimeError("YMPlayer 로그인이 유지되지 않습니다.")


def allowed(path, post=False):
    return any(p.match(path) for p in (ALLOW_POST if post else ALLOW_GET))


def sources():
    """화면에 줄 소스 목록: IPTV·텔레그램만, 주소·키는 빼고"""
    r = open_upstream("config")
    raw = r.read()
    if getattr(r, "code", 200) >= 400:
        raise RuntimeError("YMPlayer 설정을 읽지 못했습니다 (%s)" % r.code)
    out = []
    for s in json.loads(raw.decode("utf-8")).get("sources") or []:
        if s.get("type") not in ("iptv", "telegram") or s.get("enabled") is False:
            continue
        item = {"id": s.get("id"), "type": s["type"], "name": s.get("name") or s["type"]}
        if s["type"] == "telegram":
            item["channels"] = [{"id": str(c.get("id")), "title": c.get("title") or "", "kind": c.get("kind") or ""}
                                for c in s.get("channels") or [] if (c.get("kind") or "") in ("", "video")]
        else:
            item["has_epg"] = bool(s.get("epg") or s.get("has_epg"))
        out.append(item)
    return out


def rewrite_playlist(text):
    """HLS 재생목록 안의 YMPlayer 주소(/api/stream?…, /api/tg-hls/…)를 이 서버 중계 주소로"""
    return text.replace("/api/stream?", "/api/lib3d/ym/stream?").replace("/api/tg-hls/", "/api/lib3d/ym/tg-hls/")
