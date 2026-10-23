# -*- coding: utf-8 -*-
"""1일·2일·3일 기다무(웹툰·웹소설)의 다음 충전 시각을 새벽으로 옮긴다 (kakao_titles.json을 직접 고침, 한 번만 쓰는 도구).

    systemctl stop bookoasis_assistant
    python3 -m wtm.shift_waitfree            미리 보기 (아무것도 안 바꿈)
    python3 -m wtm.shift_waitfree --apply    적용 (kakao_titles.json.bak-날짜시각 으로 백업한 뒤)
    systemctl start bookoasis_assistant

기다무 대여권은 '마지막으로 쓴 시각 + 충전 주기'에 충전되고, 쓴 시각 + 주기마다 다시 충전되므로, 마지막 사용 시각을
뒤로 옮기면 그 뒤로는 매번 새벽에 충전·사용된다. 계정마다 따로 옮긴다. 옮기는 규칙(다음 충전 시각 기준):
  - 01:00~06:59  그대로 (이미 새벽)
  - 13:00~18:59  +12시간  (13:00 → 01:00, 14:00 → 02:00 …)
  - 그 밖(07:00~12:59, 19:00~00:59)  다음 01:00~06:59 사이로 (분 단위 시각에 따라 고르게 퍼뜨림)
이미 충전돼 기다리는 것(지금보다 이전)은 지금 시각을 기준으로 옮긴다 (13:20이면 → 01:20).
이 작품에서 아직 대여권을 쓴 적이 없는 계정도 같은 규칙으로 '다음 충전'을 정해 준다(낮에 바로 쓰지 않게).
옮기는 만큼 그 작품의 대여권 한 장이 늦어진다(최대 하루 가까이) - 처음 한 번만.

작업 프로세스가 작품 기록을 메모리에 들고 있다가 덮어쓸 수 있으므로 서비스를 멈춘 상태에서 실행한다.
"""
import json
import os
import shutil
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()
config.utf8_console()
os.environ.setdefault("WTM_HOST", "1")

PERIODS = (1440, 2880, 4320)   # 1일·2일·3일 (분)
NIGHT_START, NIGHT_END = 1, 7


def _at(ts, hour, day_offset=0):
    lt = time.localtime(ts)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + day_offset, hour, 0, 0, 0, 0, -1))


def new_charge(c, now):
    """다음 충전 시각 c를 새벽으로 옮긴 시각"""
    c = max(c, now)
    h = time.localtime(c).tm_hour
    if NIGHT_START <= h < NIGHT_END:
        return c
    if 13 <= h < 19:
        return c + 12 * 3600
    start = _at(c, NIGHT_START)
    if start <= c:
        start = _at(c, NIGHT_START, 1)
    lt = time.localtime(c)
    spread = (lt.tm_hour * 60 + lt.tm_min) % ((NIGHT_END - NIGHT_START) * 60)
    return start + spread * 60 + lt.tm_sec


def _hm(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


def main(argv):
    from wtm import host, kakao_pipeline as kp, state_store as ss, worker_ctl
    apply = "--apply" in argv
    if apply and "--force" not in argv and worker_ctl.status(timeout=0.5):
        print("웹툰 작업 프로세스가 돌고 있습니다. 먼저 systemctl stop bookoasis_assistant 로 멈추세요 "
              "(돌고 있으면 메모리의 작품 기록이 고친 내용을 덮어쓸 수 있음).")
        return 1
    cfg = dict(host.load_settings())
    nums = [n for n, _c in kp.accounts(cfg)] or [1]
    path = ss.KAKAO_TITLES_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    now = time.time()
    before, after, moved, kept, samples = Counter(), Counter(), 0, 0, []
    per_period = Counter()
    for sid, t in data.items():
        if not isinstance(t, dict) or not t.get("waitfree"):
            continue
        pm = int(t.get("waitfree_period_min") or 1440)
        if pm not in PERIODS:
            continue
        per_period[pm] += 1
        period = pm * 60
        acc = dict(t.get("ticket_at_acc") or {})
        for n in nums:
            used = kp._ticket_at(t, n)
            c = used + period if used else now
            nc = new_charge(c, now)
            before[time.localtime(max(c, now)).tm_hour] += 1
            after[time.localtime(nc).tm_hour] += 1
            if abs(nc - max(c, now)) < 1 and used:
                kept += 1
                continue
            moved += 1
            stamp = nc - period
            if n == 1:
                t["last_ticket_at"] = stamp
            else:
                acc[str(n)] = stamp
            if len(samples) < 8:
                samples.append("  %s 계정%d: 충전 %s → %s" % (t.get("title") or sid, n, _hm(max(c, now)), _hm(nc)))
        if acc:
            t["ticket_at_acc"] = acc
    print("■ 1일·2일·3일 기다무 충전 시각 새벽으로 옮기기 (지금 %s, 계정 %s)" % (_hm(now), ", ".join(map(str, nums))))
    print("  대상 작품: " + " · ".join("%d일 %d개" % (m // 1440, c) for m, c in sorted(per_period.items())))
    print("  옮김 %d건 (작품×계정) · 이미 새벽이라 그대로 %d건" % (moved, kept))
    print("\n  다음 충전 시각(시) 분포      바꾸기 전 → 바꾼 뒤")
    for h in range(24):
        if before[h] or after[h]:
            print("    %02d시  %5d → %5d" % (h, before[h], after[h]))
    print("\n  예:")
    print("\n".join(samples) or "  (없음)")
    if not apply:
        print("\n미리 보기입니다. 적용하려면: python3 -m wtm.shift_waitfree --apply")
        return 0
    backup = path + ".bak-" + time.strftime("%Y%m%d%H%M")
    shutil.copy2(path, backup)
    ss.write_json(path, data)
    print("\n적용했습니다. 백업: %s (되돌리려면 서비스를 멈추고 이 파일을 kakao_titles.json으로 복사)" % backup)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
