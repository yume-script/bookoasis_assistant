#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YMPlayer(ym_player)의 자동 올리기 코드를 tgup/로 가져온다 (같은 사람이 만든 두 프로그램이 같은 기능을 쓰도록).

  python3 tools/sync_tgup_from_ymp.py /경로/ym_player

ym_player/plex_to_tg.py, ym_player/folder_watch.py를 복사하고, YMPlayer에만 있는 것(소스 설정·텔레그램 색인·
서버의 Plex 헤더)을 tgup의 작은 대신할 것(compat, tgaccount)으로 바꾼다. 바꿀 곳을 못 찾으면 멈춘다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAD = ("# -*- coding: utf-8 -*-\n"
        "# YMPlayer(https://github.com/yume-script/ym_player)의 {name}에서 가져옴 - tools/sync_tgup_from_ymp.py로 다시 가져온다.\n"
        "# 고칠 것은 YMPlayer 쪽을 고친 뒤 다시 가져오는 것이 좋다 (두 프로그램이 같게).\n")


def rep(s, a, b, n=1):
    if s.count(a) != n:
        sys.exit(f"바꿀 곳을 찾지 못했습니다 ({s.count(a)}/{n}): {a[:80]!r}")
    return s.replace(a, b)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = os.path.join(sys.argv[1], "ym_player")
    with open(os.path.join(src, "plex_to_tg.py"), encoding="utf-8") as f:
        p = f.read()
    with open(os.path.join(src, "folder_watch.py"), encoding="utf-8") as f:
        w = f.read()

    p = rep(p, "from . import config_store, folder_watch, telegram_src, transcode",
            "from . import compat as config_store, compat as transcode, folder_watch, tgaccount as telegram_src")
    p = rep(p, "from .server import plex_headers", "from .compat import plex_headers", 3)
    # Plex 서버가 보는 경로 -> 이 프로그램이 보는 경로 (.env의 PLEX_PATH_MAP)
    p = rep(p, 'local_file = str(part.get("file") or "")', 'local_file = config_store.local_path(str(part.get("file") or ""))')
    # 작품 정보(포스터·줄거리)는 YMPlayer의 텔레그램 색인에만 쓰인다 - 여기서는 남기지 않는다
    p = rep(p, '''        if not msgs:
            return
        try:
            show = m''', '''        if not msgs or not telegram_src.KEEP_PLEX_META:
            return
        try:
            show = m''')
    w = rep(w, "from . import transcode", "from . import compat as transcode")
    # 안내 문구의 환경변수 이름은 이 프로그램 것으로 (compat이 RCLONE_PATH/RCLONE_CONFIG를 MP_…로 넘겨 준다)
    w = rep(w, "MP_RCLONE에 실행 파일 경로를", "RCLONE_PATH에 실행 파일 경로를")
    w = rep(w, "MP_RCLONE_CONFIG에 rclone.conf 경로를", "RCLONE_CONFIG에 rclone.conf 경로를")

    out = os.path.join(ROOT, "tgup")
    for name, text in (("plex_to_tg.py", p), ("folder_watch.py", w)):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(HEAD.format(name=f"ym_player/{name}") + text)
    print("tgup/plex_to_tg.py, tgup/folder_watch.py를 가져왔습니다.")


if __name__ == "__main__":
    main()
