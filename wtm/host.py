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
_LOCK = threading.RLock()
_ENV_CACHE = {"mtime": None, "values": {}}


def enabled():
    return config.env_bool("WTM_ENABLED", False)


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
    return cfg


def save_settings(cfg):
    """ENV_KEYS는 .env(WTM_…)로, 나머지는 settings.json으로. 바뀐 .env 키만 쓴다."""
    cfg = dict(cfg or {})
    env_patch = {}
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
        os.replace(tmp, SETTINGS_PATH)
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
