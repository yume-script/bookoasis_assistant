# -*- coding: utf-8 -*-
"""
웹툰 다운로더 별도 작업 프로세스 시작점(worker_ctl.spawn()이 실행한다).

독립형: 플러그인 시절처럼 BookOasis 패키지 대역을 끼워 넣을 필요 없이, 저장소 루트를 경로에 넣고
.env를 읽은 뒤 wtm 패키지를 그대로 불러온다. 설정·BookOasis DB는 wtm.host가 직접 읽는다.
"""
import os
import sys


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ["WTM_WORKER"] = "1"
    from gdw import config
    config.load_env()
    from wtm import worker_ctl
    worker_ctl.run_worker()


if __name__ == "__main__":
    main()
