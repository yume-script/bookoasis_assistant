# -*- coding: utf-8 -*-
"""Plex 미디어 서버: 라이브러리 목록(폴더 위치)과 부분 스캔 요청.

드라이브 변경 감시는 변경된 폴더가 Plex 라이브러리 폴더 안이면 BookOasis와 똑같이 rclone VFS를 새로고침한 뒤
Plex에 그 폴더만 스캔하라고 보낸다 (GET /library/sections/{id}/refresh?path=폴더). Plex가 다른 경로로 보는 경우
(도커 등) PLEX_PATH_MAP에 '이 프로그램 경로=Plex 경로'를 ; 로 적는다. 예) /mnt/gds2=/data;/mnt/local=/media
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def parse_map(text):
    """'로컬=Plex;…' → [(로컬, Plex)] (긴 경로 먼저)"""
    out = []
    for part in str(text or "").replace("\n", ";").split(";"):
        if "=" in part:
            a, b = part.split("=", 1)
            a, b = a.strip().rstrip("/") or "/", b.strip().rstrip("/") or "/"
            if a and b:
                out.append((a, b))
    return sorted(out, key=lambda x: -len(x[0]))


def _swap(path, pairs, src, dst):
    for pair in pairs:
        a, b = pair[src], pair[dst]
        if path == a or path.startswith(a.rstrip("/") + "/"):
            return b.rstrip("/") + path[len(a.rstrip("/")):] if a != "/" else b.rstrip("/") + path
    return path


def to_plex(path, pairs):
    return _swap(path, pairs, 0, 1)


def to_local(path, pairs):
    return _swap(path, pairs, 1, 0)


def _get(url, token, path, params=None, timeout=20):
    q = dict(params or {})
    query = ("?" + urlencode(q)) if q else ""
    req = Request(url.rstrip("/") + path + query,
                  headers={"Accept": "application/json", "X-Plex-Token": token or "",
                           "X-Plex-Product": "bookoasis_assistant", "X-Plex-Client-Identifier": "bookoasis_assistant"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.status, (json.loads(body) if body.strip().startswith(b"{") else {})


def libraries(url, token, path_map=""):
    """[{"id", "name", "type", "roots": [이 프로그램 기준 경로], "plex_roots": [...]}] - Plex에 접속 못 하면 예외"""
    pairs = parse_map(path_map)
    _code, data = _get(url, token, "/library/sections")
    out = []
    for d in (data.get("MediaContainer") or {}).get("Directory") or []:
        plex_roots = [loc.get("path") for loc in d.get("Location") or [] if loc.get("path")]
        out.append({"id": int(d.get("key")), "name": d.get("title") or "", "type": d.get("type") or "",
                    "plex_roots": plex_roots, "roots": [to_local(p.rstrip("/") or "/", pairs) for p in plex_roots]})
    return out


def scan(url, token, section_id, plex_path, timeout=30):
    """부분 스캔 요청 (Plex는 받자마자 200을 주고 스캔은 뒤에서 한다). 반환 (ok, 메시지)"""
    try:
        code, _ = _get(url, token, "/library/sections/%d/refresh" % int(section_id), {"path": plex_path}, timeout=timeout)
    except HTTPError as e:
        if e.code == 401:
            return False, "Plex가 거부했습니다(토큰 확인: PLEX_TOKEN)"
        return False, "Plex HTTP %s" % e.code
    except URLError as e:
        return False, "Plex 연결 실패: %s" % e.reason
    except OSError as e:
        return False, "Plex 연결 실패: %s" % e
    return (code < 300), ("Plex 스캔 요청 %s" % plex_path) if code < 300 else "Plex HTTP %s" % code


def check(url, token):
    """(ok, 메시지) - 접속·토큰 확인"""
    if not url:
        return False, "PLEX_URL이 비어 있습니다"
    try:
        code, data = _get(url, token, "/identity", timeout=10)
        name = (data.get("MediaContainer") or {}).get("friendlyName") or ""
        libs = libraries(url, token)
        return True, "Plex 연결됨%s · 라이브러리 %d개" % ((" (%s)" % name) if name else "", len(libs))
    except HTTPError as e:
        return False, "Plex HTTP %s%s" % (e.code, " - 토큰이 틀렸습니다" if e.code == 401 else "")
    except (URLError, OSError, ValueError) as e:
        return False, "Plex에 연결할 수 없습니다: %s" % getattr(e, "reason", e)
