# -*- coding: utf-8 -*-
"""웹툰 다운로더 (독립형). 원본: yume-script/webtoon_manager (BookOasis 플러그인 v1.39.3).

wtm.host가 BookOasis 대신 설정(.env + settings.json)·BookOasis DB·데이터 폴더를 준다.
화면 RPC는 app.py의 웹 서버가 /api/wtm/… 로 받아 WebtoonManagerMetadataProvider에 넘긴다.
"""
