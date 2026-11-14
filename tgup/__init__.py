# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기 (Plex 라이브러리 · rclone 드라이브 -> 텔레그램 채널) - YMPlayer의 설정 > 자동 올리기와 같은 기능.

  tgup/plex_to_tg.py, tgup/folder_watch.py  YMPlayer에서 그대로 가져온 코드 (tools/sync_tgup_from_ymp.py)
  tgup/compat.py, tgup/tgaccount.py          YMPlayer에만 있던 것(설정 저장소·텔레그램 소스·Plex 헤더)을 대신하는 작은 것
  tgup/service.py                             asyncio 루프 스레드에서 돌리고, 관리 화면 API를 받는다
"""
