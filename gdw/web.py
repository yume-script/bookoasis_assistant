# -*- coding: utf-8 -*-
"""관리 화면 웹 서버 (표준 라이브러리만)

  GET  /            관리 화면 (web/index.html)
  GET  /<정적 파일>  web/ 아래 style.css, script.js
  POST /api/rpc/<동작>  화면 RPC (본문: JSON 컨텍스트)
  GET  /healthz     상태 확인 (인증 없음, 워커 실행 여부만)

인증: WEB_PASSWORD가 있으면 HTTP Basic 인증(WEB_USER / WEB_PASSWORD).
RPC는 Content-Type: application/json만 받는다 → 다른 사이트의 폼 전송(CSRF)으로는 호출할 수 없다.
"""
import base64
import hmac
import json
import logging
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, service

log = logging.getLogger("gdw.web")
WEB_DIR = os.path.join(config.ROOT, "web")
STATIC = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/script.js": "script.js"}
MAX_BODY = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "gdrive_watch_sa"
    svc = None  # make_server에서 지정

    def log_message(self, fmt, *args):  # 접근 로그는 디버그로만 (화면이 15초마다 상태를 묻는다)
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _authorized(self):
        password = config.env("WEB_PASSWORD")
        if not password:
            return True
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            user, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            return False
        ok_user = hmac.compare_digest(user.encode(), (config.env("WEB_USER", "admin") or "admin").encode())
        ok_pass = hmac.compare_digest(given.encode(), password.encode())
        return ok_user and ok_pass

    def _deny(self):
        self._send(401, {"success": False, "error": "인증이 필요합니다."},
                   extra={"WWW-Authenticate": 'Basic realm="gdrive_watch", charset="UTF-8"'})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, {"ok": True, "worker": service._worker_alive()})
        if not self._authorized():
            return self._deny()
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

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not self._authorized():
            return self._deny()
        if not path.startswith("/api/rpc/"):
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
        result = self.svc.dispatch(path[len("/api/rpc/"):], context)
        self._send(200, result)


def make_server(svc, host, port):
    handler = type("GdwHandler", (Handler,), {"svc": svc})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
