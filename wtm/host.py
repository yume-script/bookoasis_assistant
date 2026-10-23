# -*- coding: utf-8 -*-
"""웹툰 다운로더 - 독립형 호스트 (예전 BookOasis 플러그인 기반 클래스 자리)

플러그인일 때 BookOasis가 주던 것 세 가지를 여기서 준다.
  - get_plugin_config / set_plugin_config : 설정 저장
  - get_db_gateway                       : BookOasis DB (중복 확인 라이브러리)
  - 데이터 폴더                           : WTM_DATA_DIR (기본 DATA_DIR/webtoon)

설정은 두 곳에 나눠 둔다.
  - .env  (WTM_ 접두사) : 저장 경로·쿠키·알림 주소/토큰 같은 환경 값과 비밀 값 (ENV_KEYS)
  - settings.json        : 구독·속도·플랫폼 옵션 등 화면에서 바꾸는 운영 옵션
화면의 [설정 저장]은 두 곳에 알맞게 나눠 쓴다. 웹 화면 프로세스와 작업 프로세스가 같은 파일을 읽으므로
작업 프로세스에 설정을 따로 넘길 필요가 없다 (플러그인 시절 worker_cfg.json 대체).
"""
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import bookoasis_db, config  # noqa: E402


def data_dir():
    path = config.env("WTM_DATA_DIR")
    if not path:
        return os.path.join(config.data_dir(), "webtoon")
    return os.path.abspath(path if os.path.isabs(path) else os.path.join(ROOT, path))


DATA_DIR = data_dir()
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

# .env에 WTM_<키>로 두는 설정 (경로·쿠키·알림 = 환경/비밀 값)
ENV_KEYS = (
    "DOWNLOAD_ROOT", "KAKAO_DOWNLOAD_ROOT", "KAKAO_NOVEL_DOWNLOAD_ROOT", "TEMP_DOWNLOAD_ROOT",
    "NAVER_COOKIE_JSON", "KAKAO_COOKIE", "KAKAO_COOKIE_2", "KAKAO_COOKIE_3", "KAKAO_COOKIE_4", "KAKAO_COOKIE_5",
    "DISCORD_WEBHOOK_URL", "DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID",
    "NOTIFY_TELEGRAM_BOT_TOKEN", "NOTIFY_TELEGRAM_CHAT_ID", "NOTIFY_SLACK_WEBHOOK_URL",
    "NOTIFY_NTFY_URL", "NOTIFY_NTFY_TOKEN",
    "TELEGRAM_UPLOAD_CHAT_ID", "TELEGRAM_UPLOAD_BOT_TOKEN", "TELEGRAM_UPLOAD_API_URL",
)
# 로그인 쿠키는 길고(Cookie-Editor JSON) 계정마다 하나라 .env 대신 파일로 둔다: WTM_DATA_DIR/cookies/<이름>.json
# 서버에 파일을 직접 넣어도 된다(Cookie-Editor로 내보낸 JSON 그대로). 파일이 없으면 예전처럼 .env(WTM_…) 값을 쓴다.
COOKIE_FILES = {"NAVER_COOKIE_JSON": "naver.json", "KAKAO_COOKIE": "kakao_1.json", "KAKAO_COOKIE_2": "kakao_2.json",
                "KAKAO_COOKIE_3": "kakao_3.json", "KAKAO_COOKIE_4": "kakao_4.json", "KAKAO_COOKIE_5": "kakao_5.json"}
COOKIE_DIR = os.path.join(DATA_DIR, "cookies")
_LOCK = threading.RLock()
_ENV_CACHE = {"mtime": None, "values": {}}


def cookie_path(key):
    return os.path.join(COOKIE_DIR, COOKIE_FILES[key])


def _read_cookie_file(key):
    try:
        with open(cookie_path(key), encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return None


def _write_cookie_file(key, value):
    """값이 같으면 쓰지 않는다. 빈 값이면 파일을 지운다."""
    path = cookie_path(key)
    if not value:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    if _read_cookie_file(key) == value.strip():
        return
    os.makedirs(COOKIE_DIR, exist_ok=True)
    try:
        os.chmod(COOKIE_DIR, 0o700)
    except OSError:
        pass
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value.strip() + "\n")
    config.replace_file(tmp, path)


def enabled():
    return config.env_bool("WTM_ENABLED", True)


def _env_file_values():
    """.env를 다시 읽는다(mtime 캐시). 화면 프로세스가 저장한 쿠키를 작업 프로세스도 바로 본다."""
    try:
        mtime = os.path.getmtime(config.ENV_PATH)
    except OSError:
        mtime = None
    if _ENV_CACHE["mtime"] != mtime:
        _ENV_CACHE.update(mtime=mtime, values=config.read_env_file())
    return _ENV_CACHE["values"]


def _env_value(key):
    name = "WTM_" + key
    if config.overridden([name]):
        return os.environ[name]          # 실제 환경변수(docker/systemd)가 우선
    return _env_file_values().get(name)


def load_settings():
    with _LOCK:
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    cfg = data if isinstance(data, dict) else {}
    for key in ENV_KEYS:
        value = _env_value(key)
        if value is not None:
            cfg[key] = value
    for key in COOKIE_FILES:  # 쿠키 파일이 있으면 그 값 (.env보다 우선)
        value = _read_cookie_file(key)
        if value:
            cfg[key] = value
    return cfg


def save_settings(cfg):
    """ENV_KEYS는 .env(WTM_…)로, 나머지는 settings.json으로. 바뀐 .env 키만 쓴다."""
    cfg = dict(cfg or {})
    env_patch = {}
    for key in COOKIE_FILES:  # 쿠키는 파일로. .env에 남은 예전 값은 비워 둔다(두 곳에 다른 값이 남지 않게)
        if key in cfg:
            value = cfg.pop(key)
            value = "" if value is None else str(value)
            _write_cookie_file(key, value)
            if _env_value(key):
                env_patch["WTM_" + key] = ""
    for key in ENV_KEYS:
        if key in cfg:
            value = cfg.pop(key)
            value = "" if value is None else str(value)
            if value != (_env_value(key) or ""):
                env_patch["WTM_" + key] = value
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        config.replace_file(tmp, SETTINGS_PATH)
        if env_patch:
            config.save_env(env_patch)
            _ENV_CACHE["mtime"] = None


class BaseMetadataProvider(object):
    """웹툰 다운로더 코드가 기대하는 플러그인 기반 클래스의 독립형 구현."""

    def __init__(self, *args, **kwargs):
        pass

    def get_plugin_config(self, db_type=None, default=None):
        cfg = load_settings()
        return cfg if cfg else (default if default is not None else {})

    def set_plugin_config(self, db_type, cfg):
        save_settings(cfg)

    def get_db_gateway(self, db_type=None):
        return bookoasis_db.gateway(db_type or "general")


def migrate_plugin_data():
    """플러그인 데이터 폴더(plugins/data/webtoon_manager)를 WTM_DATA_DIR로 복사해 온 경우:
    작업 프로세스용으로 남아 있던 worker_cfg.json(플러그인 설정 전체)을 settings.json + .env로 옮긴다.
    settings.json이 이미 있으면 아무것도 하지 않는다. 반환: 옮겼는지."""
    legacy = os.path.join(DATA_DIR, "worker_cfg.json")
    if os.path.exists(SETTINGS_PATH) or not os.path.exists(legacy):
        return False
    try:
        with open(legacy, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict):
        return False
    current_env = config.read_env_file()
    for key in ENV_KEYS:  # .env에 이미 적어 둔 값은 덮지 않는다
        if current_env.get("WTM_" + key):
            cfg.pop(key, None)
    save_settings(cfg)
    return True


# ── 드라이브 변경 감시로 넘기기 ──
def file_ready(path):
    """회차 파일이 라이브러리에 들어간 직후 (둘 다 대기열에 넣기만 하므로 다운로드를 늦추지 않는다)
      - 드라이브 변경 감시에 바로 반영(VFS 새로고침 → 스캔)을 맡긴다. Drive 변경 감지를 기다리지 않아도 되고,
        같은 파일을 나중에 감지해도 '이미 등록된 파일'로 건너뛴다.
      - 텔레그램 채널 업로드를 켰으면 업로드 대기열에 넣는다 (telegram_upload.py)."""
    if config.env_bool("WTM_HANDOFF_GDW", True) and config.env_bool("GDW_ENABLED", True):
        try:
            from gdw import handoff
            handoff.enqueue(path, source="웹툰 다운로더")
        except Exception:  # noqa: BLE001 - 넘기기 실패가 다운로드를 막으면 안 된다
            pass
    try:
        from . import telegram_upload
        telegram_upload.enqueue(path)
    except Exception:  # noqa: BLE001
        pass
