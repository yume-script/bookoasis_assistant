# -*- coding: utf-8 -*-
"""카카오페이지 '오늘의 선물' 대여권을 지금 받는다 (평소에는 하루 1번 자동 - 설정 '오늘의 선물 대여권 매일 받기').

    python3 -m wtm.today_gift            목록만 보기 (받지 않음)
    python3 -m wtm.today_gift --apply    지금 받기 (오늘 이미 받았어도 남은 것이 있으면 받음)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()
config.utf8_console()
os.environ.setdefault("WTM_HOST", "1")


def main(argv):
    from wtm import host, kakao_pipeline as kp
    from wtm.webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    apply = "--apply" in argv
    r = kp.claim_today_gifts(cfg, log=print, dry_run=not apply)
    if apply:
        print("\n받은 대여권 %d장 (목록에 있는 작품 %d개)" % (r["received"], r["tracked"]))
    else:
        print("\n미리 보기입니다. 받으려면: python3 -m wtm.today_gift --apply")
    return 1 if r.get("auth_expired") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
