# -*- coding: utf-8 -*-
"""BookOasis 3D 서재(따로 설치하는 bookoasis_3d)에 웹툰 다운로더가 받은 회차를 알린다 → 배달원이 안내 데스크로 가져온다.

.env의 LIB3D_URL(3D 서재 주소)과 LIB3D_EVENT_TOKEN(3D 서재 .env와 같은 값)이 둘 다 있을 때만 보낸다.
회차마다 한 번 POST /api/lib3d/events {"type": "delivery", "source": "webtoon", ...} - 묶는 것(잠잠해질 때까지 모아
한 상자로)은 3D 서재가 한다. 다운로드를 늦추지 않게 따로 도는 스레드에서 보내고, 실패해도 무시한다.
"""
import json
import logging
import os
import threading
import urllib.request

from . import config

log = logging.getLogger("gdw.lib3d_link")
VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".ts")
AUDIO_EXT = (".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".wav")


def enabled():
    return bool(config.env("LIB3D_URL", "").strip() and config.env("LIB3D_EVENT_TOKEN", "").strip())


def webtoon_item(path):
    """회차 파일 경로 → {title: 작품 폴더 이름, sub: 회차, kind}"""
    path = os.path.normpath(str(path or ""))
    stem = os.path.splitext(os.path.basename(path))[0]
    series = os.path.basename(os.path.dirname(path)) or stem
    low = path.lower()
    kind = "video" if low.endswith(VIDEO_EXT) else "audio" if low.endswith(AUDIO_EXT) else "webtoon"
    return {"title": series[:80], "sub": (stem if stem != series else "")[:60], "kind": kind}


def _post(body):
    base = config.env("LIB3D_URL", "").strip().rstrip("/")
    if base.endswith("/library3d"):
        base = base[: -len("/library3d")]
    req = urllib.request.Request(base + "/api/lib3d/events", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "bookoasis_assistant",
                                          "Authorization": "Bearer " + config.env("LIB3D_EVENT_TOKEN", "").strip()})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(4096)
    except Exception as error:  # noqa: BLE001 - 3D 서재가 꺼져 있어도 다운로드는 계속
        log.debug("3D 서재 배달 알림 실패: %s", error)


def webtoon_ready(path):
    """웹툰 다운로더: 회차 파일이 라이브러리에 들어감 (켜져 있을 때만, 기다리지 않음)"""
    if not enabled():
        return False
    body = {"type": "delivery", "source": "webtoon", "items": [webtoon_item(path)]}
    threading.Thread(target=_post, args=(body,), name="lib3d-delivery", daemon=True).start()
    return True
