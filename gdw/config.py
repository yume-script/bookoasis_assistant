# -*- coding: utf-8 -*-
"""설정 단일 진입점: .env

실행 환경(rclone, BookOasis 주소·토큰·DB, 웹 화면)은 모두 .env에서 읽는다.
화면의 [실행 환경 저장]도 .env의 해당 줄만 바꿔 쓴다 (주석·다른 변수·순서는 그대로).
감시 폴더·처리 옵션처럼 구조가 있는 값은 DATA_DIR/watch.json (화면에서 편집)에 둔다.
"""
import os
import re
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.abspath(os.environ.get("GDW_ENV_FILE") or os.path.join(ROOT, ".env"))
_LOCK = threading.Lock()
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_LOADED = set()  # .env에서 읽어 os.environ에 넣은 키 (실제 환경변수로 이미 있던 키는 .env가 덮지 않음)


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner
    return re.split(r"\s+#", value, 1)[0].strip()  # 따옴표 없는 값 뒤의 ' # 주석'


def _quote(value):
    value = str(value)
    if value == "" or re.fullmatch(r"[A-Za-z0-9_./:@%+,=-]+", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_env_file(path=None):
    data = {}
    try:
        with open(path or ENV_PATH, encoding="utf-8") as handle:
            for line in handle:
                m = _LINE.match(line)
                if m and not line.lstrip().startswith("#"):
                    data[m.group(1)] = _unquote(m.group(2))
    except OSError:
        pass
    return data


def load_env(path=None):
    """프로세스 시작 시 한 번. 실제 환경변수(docker -e, systemd Environment=)가 .env보다 우선한다."""
    for key, value in read_env_file(path).items():
        if key not in os.environ or key in _LOADED:
            os.environ[key] = value
            _LOADED.add(key)


def save_env(values, path=None):
    """.env에서 주어진 키의 줄만 바꾼다. 없는 키는 맨 아래에 덧붙인다. 파일 권한은 0600."""
    path = path or ENV_PATH
    with _LOCK:
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError:
            lines = []
        pending = dict(values)
        for index, line in enumerate(lines):
            m = _LINE.match(line)
            if m and not line.lstrip().startswith("#") and m.group(1) in pending:
                key = m.group(1)
                lines[index] = f"{key}={_quote(pending.pop(key))}"
        for key, value in pending.items():
            lines.append(f"{key}={_quote(value)}")
        # 제자리 쓰기(같은 inode 유지): 도커에서 .env를 파일 단위로 마운트해도 rename처럼 EBUSY가 나지 않는다
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(fd, "r+", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
    for key, value in values.items():
        os.environ[key] = str(value)
        _LOADED.add(key)


def overridden(keys):
    """.env가 아니라 실제 환경변수(docker environment, systemd Environment=)로 정해진 키.
    이 키들은 .env를 바꿔도 다시 시작하면 환경변수 값으로 돌아간다."""
    return [k for k in keys if k in os.environ and k not in _LOADED]


def env(key, default=""):
    value = os.environ.get(key)
    return default if value is None else value.strip()


def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in ("0", "false", "off", "no")


def env_int(key, default):
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


def data_dir():
    path = env("DATA_DIR", "data")
    return os.path.abspath(path if os.path.isabs(path) else os.path.join(ROOT, path))


def settings():
    """워커·화면이 쓰는 실행 환경 (예전 플러그인 설정 자리)."""
    return {
        "rclone_path": env("RCLONE_PATH", "rclone") or "rclone",
        "rclone_config": env("RCLONE_CONFIG"),
        "bookoasis_url": (env("BOOKOASIS_URL", "http://127.0.0.1:5930") or "http://127.0.0.1:5930").rstrip("/"),
        "webhook_token": env("WEBHOOK_TOKEN"),
        "auto_start": env_bool("AUTO_START", True),
    }


def db_types():
    return [t.strip() for t in env("BOOKOASIS_DB_TYPES", "general,adult,audiobook,video").split(",") if t.strip()]


def db_url(db_type):
    """BOOKOASIS_DB_URL_<TYPE>가 있으면 그것, 없으면 BOOKOASIS_DB_URL의 {db_type}을 채운 값."""
    specific = env(f"BOOKOASIS_DB_URL_{db_type.upper()}")
    if specific:
        return specific
    template = env("BOOKOASIS_DB_URL")
    return template.replace("{db_type}", db_type) if template else ""


def libraries_file():
    path = env("LIBRARIES_FILE")
    if not path:
        return os.path.join(data_dir(), "libraries.manual.json")
    return os.path.abspath(path if os.path.isabs(path) else os.path.join(ROOT, path))
