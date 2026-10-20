# -*- coding: utf-8 -*-
"""관리 화면 웹 서버 (표준 라이브러리만)

  GET  /                 드라이브 변경 감시 화면 (web/index.html)
  GET  /webtoon          웹툰 다운로더 화면 (web/webtoon/index.html)
  GET  /<정적 파일>       web/ 아래 theme.css, style.css, script.js, webtoon/…
  GET  /games            미니게임 화면 (mini/bundle.py가 games/ 폴더로 만듦), /games/covers/… 그림 땅따먹기 표지
  GET  /api/modules      켜진 모듈 {"gdw", "wtm", "mini", "games", "version", "user"}
  POST /api/rpc/<동작>    드라이브 변경 감시 RPC (본문: JSON 컨텍스트)
  GET  /api/wtm/data     웹툰 다운로더 화면 데이터
  POST /api/wtm/action   웹툰 다운로더 동작 (본문: {"action_id", "context"})
  GET  /healthz          상태 확인 (인증 없음, 워커 실행 여부만)
  GET  /login            로그인 화면 (사용자가 없으면 '관리자 계정 만들기')
  GET  /api/auth/state   POST /api/auth/login · setup · logout · password
  GET  /api/users        POST /api/users (추가) · /api/users/password (다른 사용자 비밀번호) · /api/users/delete
  POST /mcp              MCP 서버 (gdw/mcp.py, Authorization: Bearer MCP_TOKEN) · GET/POST /api/mcp 설정 > MCP

인증: YMPlayer와 같은 로그인 화면 + 서명한 세션 쿠키 (gdw/auth.py). 로그인 안 했으면 화면은 /login으로, API는 401.
RPC는 Content-Type: application/json만 받는다 → 다른 사이트의 폼 전송(CSRF)으로는 호출할 수 없다.
"""
import json
import logging
import mimetypes
import os
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, config, mcp, service

log = logging.getLogger("gdw.web")
WEB_DIR = os.path.join(config.ROOT, "web")
STATIC = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/script.js": "script.js",
          "/theme.css": "theme.css", "/shell.js": "shell.js", "/webtoon": "webtoon/index.html", "/webtoon/": "webtoon/index.html",
          "/webtoon/style.css": "webtoon/style.css", "/webtoon/script.js": "webtoon/script.js",
          "/login": "login.html", "/login.js": "login.js"}
PUBLIC = {"/login", "/login.js", "/theme.css", "/shell.js", "/healthz", "/api/auth/state", "/api/auth/login", "/api/auth/setup"}
PAGES = {"/", "/index.html", "/webtoon", "/webtoon/", "/games", "/games/"}  # 로그인 안 했으면 로그인 화면으로 보낼 주소
OFF_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">
<link rel="stylesheet" href="theme.css"></head><body data-module=""><main class="gdw-page"><div class="app-off"><h2>{title}: 꺼져 있음</h2>
<p>.env에 <code>{key}=true</code>를 넣고 다시 시작하세요.</p></div></main><script src="shell.js"></script></body></html>"""
MAX_BODY = 2 * 1024 * 1024


THEMES = ("dark", "light", "black", "navy", "auto")
ACCENTS = ("amber", "blue", "green", "purple", "red", "pink", "teal")


def _ui_prefs_path():
    return os.path.join(config.data_dir(), "ui_prefs.json")


def ui_prefs():
    """화면 기본 테마 (YMPlayer 설정 > 화면의 '기본 테마'와 같은 역할). 브라우저마다 따로 고른 테마가 있으면 그게 우선."""
    try:
        with open(_ui_prefs_path(), encoding="utf-8") as f:
            data = json.load(f) or {}
    except (OSError, ValueError):
        data = {}
    return {"theme": data.get("theme") if data.get("theme") in THEMES else "dark",
            "accent": data.get("accent") if data.get("accent") in ACCENTS else "amber"}


def module_versions():
    """모듈별 버전 (왼쪽 위 아이콘 배지: 지금 보는 화면의 모듈 버전)."""
    out = {"gdw": service._plugin_version()}
    for key, path, field in (("wtm", ("wtm", "VERSION"), "plugin version"), ("mini", ("mini", "VERSION"), "plugin version")):
        try:
            with open(os.path.join(config.ROOT, *path), encoding="utf-8") as f:
                out[key] = str(json.load(f).get(field) or "")
        except (OSError, ValueError):
            out[key] = ""
    return out


def modules():
    return {"gdw": config.env_bool("GDW_ENABLED", True), "wtm": config.env_bool("WTM_ENABLED", False),
            "mini": config.env_bool("MINI_ENABLED", True)}


class Handler(BaseHTTPRequestHandler):
    server_version = "gdrive_watch_sa"
    svc = None  # make_server에서 지정 (드라이브 변경 감시를 끄면 None)

    def log_message(self, fmt, *args):  # 접근 로그는 디버그로만 (화면이 15초마다 상태를 묻는다)
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _user(self):
        """로그인한 사용자 (세션 쿠키), 아니면 None"""
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return None
        morsel = cookie.get(auth.COOKIE)
        return auth.user_from_token(morsel.value) if morsel else None

    def _deny(self, path):
        if path in PAGES and self.command in ("GET", "HEAD"):
            page = path.strip("/").split("/")[0].replace("index.html", "")
            return self._send(302, b"", extra={"Location": "login" + ("#" + page if page else "")})  # 로그인 뒤 이 화면으로
        self._send(401, {"success": False, "error": "로그인이 필요합니다.", "login": True})

    def _session_cookie(self, user, remember):
        """Set-Cookie 값. https 뒤(리버스 프록시)면 Secure도 붙인다."""
        parts = [f"{auth.COOKIE}={auth.make_token(user, remember)}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if remember:
            parts.append(f"Max-Age={auth.REMEMBER_SEC}")
        if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https":
            parts.append("Secure")
        return "; ".join(parts)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, {"ok": True, "worker": service._worker_alive() if self.svc else None})
        if path == "/mcp":  # Streamable HTTP의 서버→클라이언트 SSE 스트림은 쓰지 않는다
            return self._send(405, {"success": False, "error": "MCP는 POST만 받습니다."}, extra={"Allow": "POST"})
        user = self._user()
        if path == "/api/auth/state":
            return self._send(200, {"success": True, "setup": auth.needs_setup(), "ui": ui_prefs(),
                                    "version": service._plugin_version(), "user": auth.public_user(user) if user else None})
        if path == "/login" and user:
            return self._send(302, b"", extra={"Location": "./"})
        if not user and path not in PUBLIC:
            return self._deny(path)
        if path == "/api/users":
            return self._send(200, {"success": True, "users": [auth.public_user(u) for u in auth.load_users()]})
        if path == "/api/mcp":
            return self._send(200, {"success": True, "enabled": mcp.enabled(), "token": mcp.token(),
                                    "overridden": bool(config.overridden(["MCP_TOKEN"]))})
        mods = modules()
        if path == "/api/modules":
            info = dict(mods, version=service._plugin_version(), versions=module_versions(), ui=ui_prefs(),
                        user=user["username"])
            if mods["mini"]:
                from mini import bundle
                info["games"] = bundle.menu()
            return self._send(200, info)
        if path == "/games" or path.startswith("/games/"):
            return self._games(path, mods)
        if path == "/api/wtm/data":
            if not mods["wtm"]:
                return self._send(404, {"success": False, "error": "웹툰 다운로더가 꺼져 있습니다 (WTM_ENABLED)."})
            from wtm import service as wtm_service
            return self._send(200, wtm_service.dashboard())
        if path in ("/", "/index.html") and not mods["gdw"]:
            if mods["wtm"] or mods["mini"]:
                return self._send(302, b"", extra={"Location": "webtoon" if mods["wtm"] else "games"})
            return self._send(200, OFF_PAGE.format(title="드라이브 변경 감시", key="GDW_ENABLED").encode(), "text/html; charset=utf-8")
        if path in ("/webtoon", "/webtoon/") and not mods["wtm"]:
            return self._send(200, OFF_PAGE.format(title="웹툰 다운로더", key="WTM_ENABLED").encode(), "text/html; charset=utf-8")
        if path == "/webtoon/":
            return self._send(302, b"", extra={"Location": "/webtoon"})
        name = STATIC.get(path)
        if not name:
            return self._send(404, {"success": False, "error": "없는 주소입니다."})
        try:
            with open(os.path.join(WEB_DIR, name), "rb") as handle:
                data = handle.read()
        except OSError:
            return self._send(404, {"success": False, "error": "파일이 없습니다."})
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)

    def _games(self, path, mods):
        if not mods["mini"]:
            return self._send(200, OFF_PAGE.format(title="미니게임", key="MINI_ENABLED").encode(), "text/html; charset=utf-8")
        from mini import bundle
        if path in ("/games", "/games/"):
            if path == "/games/":
                return self._send(302, b"", extra={"Location": "/games"})
            return self._send(200, bundle.page().encode("utf-8"), "text/html; charset=utf-8")
        if path == "/games/covers/list.json":  # 그림 땅따먹기: covers 폴더의 그림 목록
            return self._send(200, bundle.list_covers())
        if path.startswith("/games/covers/"):
            from urllib.parse import unquote
            real = bundle.cover_path(unquote(path[len("/games/covers/"):]))
            if not real:
                return self._send(404, {"success": False, "error": "없는 그림입니다."})
            try:
                with open(real, "rb") as handle:
                    data = handle.read()
            except OSError:
                return self._send(404, {"success": False, "error": "그림을 읽을 수 없습니다."})
            ctype = mimetypes.guess_type(real)[0] or "application/octet-stream"
            return self._send(200, data, ctype, extra={"Cache-Control": "max-age=3600"})
        return self._send(404, {"success": False, "error": "없는 주소입니다."})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/mcp":
            return self._mcp()
        user = self._user()
        if not user and path not in PUBLIC:
            return self._deny(path)
        if not path.startswith(("/api/rpc/", "/api/auth/", "/api/users")) and path not in ("/api/wtm/action", "/api/ui-prefs", "/api/mcp"):
            return self._send(404, {"success": False, "error": "없는 주소입니다."})
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self._send(415, {"success": False, "error": "Content-Type은 application/json이어야 합니다."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            return self._send(413, {"success": False, "error": "요청이 너무 큽니다."})
        try:
            context = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except ValueError:
            return self._send(400, {"success": False, "error": "JSON 형식이 아닙니다."})
        if not isinstance(context, dict):
            return self._send(400, {"success": False, "error": "JSON 객체를 보내세요."})
        if path.startswith(("/api/auth/", "/api/users")):
            return self._auth_post(path, context, user)
        if path == "/api/mcp":  # 설정 > MCP: 토큰 만들기 / 끄기
            if config.overridden(["MCP_TOKEN"]):
                return self._send(400, {"success": False, "error": "MCP_TOKEN이 실제 환경변수로 지정돼 있어 화면에서 바꿀 수 없습니다."})
            if context.get("action") == "disable":
                mcp.disable()
            else:
                mcp.new_token()
            return self._send(200, {"success": True, "enabled": mcp.enabled(), "token": mcp.token()})
        if path == "/api/ui-prefs":  # 설정 > 화면: 기본 테마 저장
            prefs = {"theme": context.get("theme") if context.get("theme") in THEMES else "dark",
                     "accent": context.get("accent") if context.get("accent") in ACCENTS else "amber"}
            os.makedirs(config.data_dir(), exist_ok=True)
            tmp = _ui_prefs_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
            os.replace(tmp, _ui_prefs_path())
            return self._send(200, {"success": True, "ui": prefs})
        if path == "/api/wtm/action":
            if not modules()["wtm"]:
                return self._send(404, {"success": False, "error": "웹툰 다운로더가 꺼져 있습니다 (WTM_ENABLED)."})
            from wtm import service as wtm_service
            ctx = context.get("context") if isinstance(context.get("context"), dict) else {}
            return self._send(200, wtm_service.action(context.get("action_id"), ctx))
        if self.svc is None:
            return self._send(404, {"success": False, "error": "드라이브 변경 감시가 꺼져 있습니다 (GDW_ENABLED)."})
        result = self.svc.dispatch(path[len("/api/rpc/"):], context)
        self._send(200, result)


    def _mcp(self):
        """MCP (Streamable HTTP, 상태 없음): Bearer 토큰으로만 들어온다 (세션 쿠키 아님)."""
        if not mcp.enabled():
            return self._send(404, {"success": False, "error": "MCP가 꺼져 있습니다 (설정 > MCP에서 토큰을 만드세요)."})
        if not mcp.authorized(self.headers.get("Authorization")):
            return self._send(401, {"success": False, "error": "MCP 토큰이 필요합니다."},
                              extra={"WWW-Authenticate": 'Bearer realm="gdrive_watch_sa"'})
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != (self.headers.get("Host") or ""):
            return self._send(403, {"success": False, "error": "다른 사이트에서 온 요청입니다."})  # DNS 리바인딩 방지
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"null") if 0 < length <= MAX_BODY else None
        except ValueError:
            body = None
        if body is None:
            return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
        code, reply = mcp.handle(body, modules(), self.svc)
        if reply is None:
            return self._send(code, b"", "text/plain; charset=utf-8")
        self._send(code, reply)

    def _auth_post(self, path, body, user):
        """로그인/로그아웃/첫 관리자/비밀번호/사용자 관리 (YMPlayer와 같은 동작)"""
        ok = lambda data=None: self._send(200, dict({"success": True}, **(data or {})))  # noqa: E731
        fail = lambda code, msg: self._send(code, {"success": False, "error": msg})  # noqa: E731
        try:
            if path == "/api/auth/login":
                ip = self.client_address[0] if self.client_address else "?"
                if auth.throttled(ip):
                    return fail(429, "로그인 실패가 너무 많습니다. 10분 뒤에 다시 시도하세요.")
                found = auth.verify_password(body.get("username"), str(body.get("password") or ""))
                if not found:
                    auth.record_failure(ip)
                    time.sleep(0.5)  # 무작위 대입을 느리게
                    return fail(401, "아이디 또는 비밀번호가 틀렸습니다.")
                auth.clear_failures(ip)
                return self._send(200, {"success": True, "user": auth.public_user(found)},
                                  extra={"Set-Cookie": self._session_cookie(found, bool(body.get("remember")))})
            if path == "/api/auth/setup":  # 사용자가 하나도 없을 때만: 첫 관리자 만들기
                if not auth.needs_setup():
                    return fail(403, "이미 관리자 계정이 있습니다.")
                auth.create_user(body.get("username"), str(body.get("password") or ""))
                found = auth.find_user(body.get("username"))
                return self._send(200, {"success": True, "user": auth.public_user(found)},
                                  extra={"Set-Cookie": self._session_cookie(found, bool(body.get("remember")))})
            if path == "/api/auth/logout":
                return self._send(200, {"success": True},
                                  extra={"Set-Cookie": f"{auth.COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            if path == "/api/auth/password":  # 내 비밀번호 바꾸기: 다른 기기의 로그인은 끊기고 이 기기는 새 쿠키
                if not auth.verify_password(user["username"], str(body.get("current") or "")):
                    return fail(400, "지금 비밀번호가 틀렸습니다.")
                changed = auth.set_password(user["username"], str(body.get("new") or ""))
                return self._send(200, {"success": True}, extra={"Set-Cookie": self._session_cookie(changed, True)})
            if path == "/api/users":
                return ok({"user": auth.create_user(body.get("username"), str(body.get("password") or ""))})
            if path == "/api/users/password":
                auth.set_password(body.get("username"), str(body.get("password") or ""))
                return ok()
            if path == "/api/users/delete":
                auth.delete_user(body.get("username"), acting=user["username"])
                return ok()
        except auth.AuthError as error:
            return fail(400, str(error))
        return fail(404, "없는 주소입니다.")


def make_server(svc, host, port):
    handler = type("GdwHandler", (Handler,), {"svc": svc})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
