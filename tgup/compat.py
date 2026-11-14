# -*- coding: utf-8 -*-
"""YMPlayer에서 가져온 자동 올리기 코드(plex_to_tg.py, folder_watch.py)가 찾는 것들을 이 프로그램 식으로 채운다.

  config_store 자리: DATA_DIR(data/tgup), load()/save() - 자동 올리기 설정(data/tgup/settings.json)
  transcode 자리:    ffmpeg_path(), ffprobe_path() - .env의 FFMPEG_PATH / FFPROBE_PATH, 없으면 PATH에서
  server 자리:       plex_headers(cfg, token)
  local_path():      Plex 서버가 보는 파일 경로 -> 이 프로그램이 보는 경로 (.env의 PLEX_PATH_MAP, 드라이브 감시와 같은 값)
"""
import json
import os
import shutil
import threading

from gdw import config
from gdw import plex as gdw_plex

DATA_DIR = os.path.join(config.data_dir(), "tgup")
SETTINGS_NAME = "settings.json"
_LOCK = threading.Lock()

# folder_watch는 MP_RCLONE / MP_RCLONE_CONFIG를 본다 - 이 프로그램의 RCLONE_PATH / RCLONE_CONFIG를 그대로 쓴다
if config.env("RCLONE_PATH") and not os.environ.get("MP_RCLONE"):
    os.environ["MP_RCLONE"] = config.env("RCLONE_PATH")
if config.env("RCLONE_CONFIG") and not os.environ.get("MP_RCLONE_CONFIG"):
    os.environ["MP_RCLONE_CONFIG"] = config.env("RCLONE_CONFIG")


def _path():
    return os.path.join(DATA_DIR, SETTINGS_NAME)


def load():
    """{"plex_to_tg": 자동 올리기 설정, "telegram": {"api_id", "api_hash", "phone"}}"""
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save(data):
    with _LOCK:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        try:
            os.chmod(tmp, 0o600)   # Telegram API Hash가 들어 있다
        except OSError:
            pass
        os.replace(tmp, _path())


def ffmpeg_path():
    return config.env("FFMPEG_PATH") or shutil.which("ffmpeg")


def ffprobe_path():
    return config.env("FFPROBE_PATH") or shutil.which("ffprobe")


def available():
    return bool(ffmpeg_path() and ffprobe_path())


def plex_headers(cfg=None, token=None):
    h = {"X-Plex-Product": "bookoasis_assistant", "X-Plex-Version": "1.0",
         "X-Plex-Client-Identifier": (cfg or {}).get("client_id") or "bookoasis_assistant",
         "X-Plex-Platform": "Linux", "X-Plex-Device-Name": "bookoasis_assistant"}
    if token:
        h["X-Plex-Token"] = token
    return h


def plex_conf():
    """.env의 PLEX_URL / PLEX_TOKEN (드라이브 감시의 Plex 설정과 같은 값 - Plex 스캔을 꺼 둬도 쓴다)"""
    return {"id": "plex", "type": "plex", "name": "Plex",
            "url": (config.env("PLEX_URL") or "").strip().rstrip("/"), "token": config.env("PLEX_TOKEN"),
            "verify_ssl": not config.env_bool("PLEX_INSECURE", False)}


def local_path(path):
    """Plex 서버가 보는 경로를 이 프로그램이 보는 경로로 (PLEX_PATH_MAP '이 프로그램 경로=Plex 경로;…')"""
    if not path:
        return path
    return gdw_plex.to_local(path, gdw_plex.parse_map(config.env("PLEX_PATH_MAP")))
