# -*- coding: utf-8 -*-
"""사용자 계정과 로그인 세션 (YMPlayer auth.py와 같은 방식)

- 사용자: DATA_DIR/users.json  [{"username", "salt", "hash", "iterations", "pw_ver", "created"}]
  관리 화면이라 로그인한 사람은 모두 관리자다. 비밀번호는 PBKDF2-SHA256(20만 번)으로만 저장한다.
- 세션: 서명한 쿠키 하나 (gdw_session). 내용 = 사용자명|만료시각|pw_ver, 서명 = HMAC-SHA256(DATA_DIR/secret.key).
  비밀번호를 바꾸거나 사용자를 지우면 pw_ver가 바뀌거나 사용자가 없어져서 그 사람의 기존 쿠키는 바로 무효.
- 처음 실행: 사용자가 하나도 없으면
    * .env의 WEB_USER/WEB_PASSWORD가 있으면 그걸로 관리자를 만든다 (예전 HTTP Basic 인증 설정을 그대로 옮김)
    * 없으면 로그인 화면이 "관리자 계정 만들기"로 바뀐다
- 로그인 실패가 IP마다 10분에 10번을 넘으면 잠시 막는다.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

from . import config

COOKIE = "gdw_session"
SESSION_SEC = 12 * 3600            # "로그인 유지"를 안 켰을 때 (브라우저를 닫아도 서버 쪽 만료는 12시간)
REMEMBER_SEC = 30 * 24 * 3600      # "로그인 유지"
ITERATIONS = 200_000
FAIL_WINDOW_SEC = 600
FAIL_LIMIT = 10
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@가-힣-]{2,32}$")

_lock = threading.Lock()
_fails = {}  # ip -> [실패 시각...]
_key = None


class AuthError(Exception):
    """화면에 그대로 보여줄 수 있는 오류."""


def _path(name):
    return os.path.join(config.data_dir(), name)


def _write_private(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def secret_key():
    global _key
    with _lock:
        if _key:
            return _key
        path = _path("secret.key")
        try:
            with open(path, "rb") as f:
                key = f.read()
        except FileNotFoundError:
            key = b""
        if len(key) < 32:
            key = secrets.token_bytes(32)
            _write_private(path, key)
        _key = key
        return key


# ── 사용자 저장소 ──
def load_users():
    try:
        with open(_path("users.json"), encoding="utf-8") as f:
            users = json.load(f)
        return users if isinstance(users, list) else []
    except (OSError, ValueError):
        return []


def save_users(users):
    with _lock:
        _write_private(_path("users.json"), json.dumps(users, ensure_ascii=False, indent=2).encode("utf-8"))


def find_user(username):
    username = str(username or "").strip().lower()
    return next((u for u in load_users() if u["username"].lower() == username), None)


def public_user(u):
    return {"username": u["username"], "role": "admin", "created": u.get("created")}


def _hash(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def _check_password_rules(password):
    if len(password or "") < 6:
        raise AuthError("비밀번호는 6자 이상이어야 합니다.")


def _new_secret_fields(password):
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "hash": _hash(password, salt), "iterations": ITERATIONS, "pw_ver": secrets.token_hex(4)}


def create_user(username, password, check_rules=True):
    username = str(username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("아이디는 2~32자의 영문/숫자/한글과 _ . @ - 만 쓸 수 있습니다.")
    if check_rules:
        _check_password_rules(password)
    elif not password:
        raise AuthError("비밀번호가 없습니다.")
    users = load_users()
    if any(u["username"].lower() == username.lower() for u in users):
        raise AuthError("이미 있는 아이디입니다.")
    user = {"username": username, **_new_secret_fields(password), "created": int(time.time())}
    users.append(user)
    save_users(users)
    return public_user(user)


def set_password(username, password):
    """비밀번호 변경. pw_ver가 바뀌어 다른 기기의 기존 로그인은 끊긴다."""
    _check_password_rules(password)
    users = load_users()
    user = next((u for u in users if u["username"].lower() == str(username).lower()), None)
    if not user:
        raise AuthError("없는 사용자입니다.")
    user.update(_new_secret_fields(password))
    save_users(users)
    return user


def delete_user(username, acting=None):
    users = load_users()
    user = next((u for u in users if u["username"].lower() == str(username).lower()), None)
    if not user:
        raise AuthError("없는 사용자입니다.")
    if acting and acting.lower() == user["username"].lower():
        raise AuthError("자기 자신은 지울 수 없습니다.")
    if len(users) <= 1:
        raise AuthError("사용자가 한 명은 있어야 합니다.")
    save_users([u for u in users if u is not user])


def verify_password(username, password):
    user = find_user(username)
    if not user:
        _hash(password or "", b"\0" * 16)  # 없는 아이디도 같은 시간이 걸리게
        return None
    expect = _hash(password or "", bytes.fromhex(user["salt"]), int(user.get("iterations") or ITERATIONS))
    return user if hmac.compare_digest(expect, user["hash"]) else None


def bootstrap_from_env():
    """사용자가 없고 .env에 WEB_PASSWORD가 있으면 WEB_USER(기본 admin)를 관리자로 만든다 (예전 Basic 인증에서 옮겨오기).
    예전 비밀번호를 그대로 쓰도록 6자 규칙은 적용하지 않는다."""
    if load_users():
        return None
    password = config.env("WEB_PASSWORD")
    if not password:
        return None
    try:
        return create_user(config.env("WEB_USER", "admin") or "admin", password, check_rules=False)
    except AuthError:
        return None


def needs_setup():
    return not load_users()


# ── 세션 쿠키 ──
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user, remember=False):
    expires = int(time.time()) + (REMEMBER_SEC if remember else SESSION_SEC)
    body = f"{user['username']}|{expires}|{user['pw_ver']}".encode("utf-8")
    sig = hmac.new(secret_key(), body, hashlib.sha256).digest()
    return f"{_b64(body)}.{_b64(sig)}"


def user_from_token(token):
    """올바르고 만료 안 됐고 비밀번호가 바뀌지 않은 쿠키면 사용자, 아니면 None."""
    try:
        body_b64, sig_b64 = str(token or "").split(".", 1)
        body = _unb64(body_b64)
        if not hmac.compare_digest(hmac.new(secret_key(), body, hashlib.sha256).digest(), _unb64(sig_b64)):
            return None
        username, expires, pw_ver = body.decode("utf-8").split("|")
        if int(expires) < time.time():
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    user = find_user(username)
    if not user or not hmac.compare_digest(user["pw_ver"], pw_ver):
        return None
    return user


# ── 로그인 실패 제한 ──
def throttled(ip):
    now = time.time()
    with _lock:
        recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW_SEC]
        _fails[ip] = recent
        return len(recent) >= FAIL_LIMIT


def record_failure(ip):
    with _lock:
        _fails.setdefault(ip, []).append(time.time())


def clear_failures(ip):
    with _lock:
        _fails.pop(ip, None)
