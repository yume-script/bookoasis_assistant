# -*- coding: utf-8 -*-
"""미니게임 아케이드 (독립형). 원본: yume-script/ym_mini_game (BookOasis 플러그인 v2.0.2).

게임은 모두 브라우저에서만 돈다(서버 로직 없음). games/<id>/ 의 manifest.json · template.html · style.css · game.js를
읽어 /games 화면 하나로 묶어 준다 (플러그인은 로드할 때 index.html/style.css/script.js 파일을 새로 썼지만,
독립형은 파일을 쓰지 않고 메모리에서 묶어 바로 돌려준다 - 저장소 폴더가 읽기 전용이어도 된다).
게임을 추가하려면 games/ 아래에 같은 구성의 폴더를 넣으면 된다.
"""
