# -*- coding: utf-8 -*-
"""신규 회차 확인 계획대로 다운로드 시각을 다시 놓는 간이 스크립트 (기다무 대여권 일부를 포기하더라도)

    venv/bin/python -m wtm.rebalance                 # 미리 보기 (아무것도 안 바꿈)
    systemctl stop bookoasis_assistant
    venv/bin/python -m wtm.rebalance --apply         # 적용 (작품 기록 2개를 .bak-날짜시각으로 백업한 뒤)
    systemctl start bookoasis_assistant

    --window 시작시 끝시: 1일 이상 기다무를 펼칠 오전 시간대 (기본 5 12 = 05:00~11:59)

- 카카오 1·2·3·6·12시간 기다무 (남은 회차가 10개 넘음): 주기별로 한 주기 안에 같은 간격 - 24시간 내내 주기마다.
- 카카오 1·2·3·7일 기다무 (남은 회차가 10개 넘음): 오전 05~12시에 같은 간격. 2·3·7일은 날짜는 그대로 시각만.
- 새 회차 (네이버 연재 작품, 카카오 구독·구매 작품 - 기다무가 아니거나 남은 회차가 10개 이하인 것 포함):
  작품마다 오후 12~20시 안의 확인 시각을 연재 요일별로 고르게 정한다. 그 시각에 못 찾으면 12시간 뒤(다음 날 오전) 한 번 더.
- 20~05시는 비운다 (FF·rclone 업로드 지연 시간대).

카카오는 실제 충전보다 앞당길 수 없으므로(거절됨) 자리가 충전보다 이르면 다음 주기(일 단위면 다음 날)의 같은 자리로
보낸다 → 그만큼 대여권을 한 번 포기한다(한 작품당 최대 한 주기). 한 작품의 계정들은 같은 시각으로 맞춘다.
--apply는 설정도 바꾼다: 신규 회차 확인 계획 켬, 새벽 사용 끔, 매일 1일 이상 기다무를 오전에 유지.
작업 프로세스가 작품 기록을 메모리에 들고 있으므로 서비스를 멈추고 실행한다.
"""
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

DAY = 86400


def _at(ts, hour, minute=0, day_offset=0):
    lt = time.localtime(ts)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + day_offset, hour, minute, 0, 0, 0, -1))


def _cfg():
    from wtm import host
    from wtm.webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    return cfg


def kakao_plan(cfg, titles, start_h, end_h, now):
    """{sid: (patch, 지금 충전, 새 충전, 주기(분))}"""
    from wtm import kakao_pipeline as kp
    nums, cands = kp._waitfree_candidates(cfg)
    if not nums:
        return {}
    span = ((end_h - start_h) % 24 or 24) * 3600
    short, daily = {}, {}
    for sid, t0 in cands.items():
        t = titles.get(sid) or t0
        pm = int(t.get("waitfree_period_min") or 1440)
        period = pm * 60
        cur = max(now, max((kp._ticket_at(t, n) + period) if kp._ticket_at(t, n) else now for n in nums))
        if pm < 1440:
            short.setdefault(pm, []).append((cur, sid, t))
        else:
            w = _at(cur, start_h)              # cur가 시간대 뒤(20시 이후)면 다음 날 시간대로
            if cur >= w + span:
                w = _at(cur, start_h, day_offset=1)
            elif cur < w and cur < _at(cur, start_h, day_offset=-1) + span:
                w = _at(cur, start_h, day_offset=-1)
            daily.setdefault((pm, time.strftime("%Y-%m-%d", time.localtime(w))), []).append((cur, sid, t, w))
    plan = {}

    def put(sid, t, cur, slot, pm):
        stamp = slot - pm * 60
        patch = {"last_ticket_at": stamp}
        if any(n != 1 for n in nums):
            patch["ticket_at_acc"] = dict(t.get("ticket_at_acc") or {}, **{str(n): stamp for n in nums if n != 1})
        plan[sid] = (patch, cur, slot, pm)

    def assign(items, slots, repeat):
        """자리(slots: 같은 간격의 시각들, repeat초마다 반복)를 작품에 하나씩 - 충전 순서대로, 각자 충전 뒤 가장 가까운
        빈 자리. 그래서 대부분은 조금만 늦어지고, 자리가 모자란 구간의 작품만 다음 반복(다음 주기·다음 날)으로 간다."""
        free = list(slots)
        for cur, sid, t, pm in sorted(items, key=lambda x: (x[0], x[1])):
            best, bi = None, None
            for j, s0 in enumerate(free):
                at = s0 + max(0, -(-(cur - s0) // repeat)) * repeat   # cur 이후 첫 반복
                if best is None or at < best:
                    best, bi = at, j
            free.pop(bi)
            put(sid, t, cur, best, pm)

    # 시간 단위: 주기별로 한 주기 안에 같은 간격 (지금부터 주기/개수마다 한 자리)
    for pm, items in short.items():
        period = pm * 60
        gap = period / len(items)
        assign([(c, sid, t, pm) for c, sid, t in items], [now + gap * (j + 0.5) for j in range(len(items))], period)
    # 일 단위: (주기, 날짜)마다 그날 시간대 안에 같은 간격 (모자라면 다음 날 같은 자리)
    for (pm, _day), items in daily.items():
        w = items[0][3]
        n = len(items)
        assign([(c, sid, t, pm) for c, sid, t, _w in items], [w + span * (j + 0.5) / n for j in range(n)], DAY)
    return plan


def naver_plan(cfg, titles, start_h, end_h):
    """{tid: 확인 시각(자정부터 분)} - 연재 요일(매일+는 따로)별로 시간대 안에 같은 간격"""
    span = ((end_h - start_h) % 24 or 24) * 60
    groups = {}
    for tid, t in titles.items():
        if not t.get("subscribed") or t.get("excluded") or t.get("unsubscribed"):
            continue
        wds = t.get("weekdays") or []
        key = "dailyPlus" if "dailyPlus" in wds else (sorted(wds)[0] if wds else "-")
        groups.setdefault(key, []).append(tid)
    out = {}
    for key, tids in groups.items():
        tids.sort(key=lambda x: (str(titles[x].get("title") or ""), x))
        for i, tid in enumerate(tids):
            out[tid] = int(start_h * 60 + span * (i + 0.5) / len(tids)) % 1440
    return out


def _hist(rows):
    c = Counter()
    for h in rows:
        c[h] += 1
    return c


def main(argv):
    from wtm import host, kakao_pipeline as kp, state_store as ss, worker_ctl
    apply = "--apply" in argv
    from wtm.pipeline import PLAN_AM, PLAN_PM
    start_h, end_h = PLAN_AM          # 1일 이상 기다무: 오전 (신규 회차 확인 계획)
    pm_a, pm_b = PLAN_PM              # 새 회차(네이버·카카오 연재일): 오후
    if "--window" in argv:
        i = argv.index("--window")
        try:
            start_h, end_h = int(argv[i + 1]) % 24, int(argv[i + 2]) % 24
        except (IndexError, ValueError):
            print("사용법: python3 -m wtm.rebalance --window 시작시 끝시 [--apply]   (예: --window 5 12)")
            return 2
    if apply and "--force" not in argv and worker_ctl.status(timeout=0.5):
        print("웹툰 작업 프로세스가 돌고 있습니다. 먼저 systemctl stop bookoasis_assistant 로 멈추세요 "
              "(돌고 있으면 메모리의 작품 기록이 고친 내용을 덮어씀).")
        return 1
    cfg = dict(_cfg(), CHECK_PLAN_ENABLE=True)   # 계획 기준으로 대상 고르기 (남은 회차 10개 이하는 대여권 대상 아님)
    now = time.time()
    ktitles = ss.load_kakao_titles()
    ntitles = ss.load_titles()
    kplan = kakao_plan(cfg, ktitles, start_h, end_h, now)
    nplan = naver_plan(cfg, ntitles, pm_a, pm_b)
    kslots = naver_plan(cfg, {sid: t for sid, t in ktitles.items() if t.get("purchased") or t.get("subscribed")}, pm_a, pm_b)

    print("■ 신규 회차 확인 계획대로 다시 놓기 (지금 %s)\n  오전 %02d:00~%02d:59 1일 이상 기다무 대여권 · 오후 %02d:00~%02d:59 새 회차"
          "(네이버·카카오 연재일) · 1~12시간 기다무는 24시간"
          % (time.strftime("%m-%d %H:%M"), start_h, (end_h - 1) % 24, pm_a, (pm_b - 1) % 24))
    groups = {}
    for sid, (_p, cur, slot, pm) in kplan.items():
        g = groups.setdefault(pm, {"n": 0, "before": Counter(), "after": Counter(), "lost": 0, "delay": 0.0})
        g["n"] += 1
        g["before"][time.localtime(cur).tm_hour] += 1
        g["after"][time.localtime(slot).tm_hour] += 1
        g["delay"] += slot - cur
        if slot - cur >= pm * 60 * 0.5:
            g["lost"] += 1
    print("\n  카카오 기다무 (작품 수 · 평균 늦어짐 · 반 주기 넘게 늦어져 사실상 대여권 1장 포기)")
    for pm in sorted(groups):
        g = groups[pm]
        label = kp.waitfree_label({"waitfree_period_min": pm})
        print("    %-12s %5d개 · 평균 %5.1f시간 늦어짐 · 포기 약 %d장/계정" % (label, g["n"], g["delay"] / g["n"] / 3600, g["lost"]))
    daily_b, daily_a = Counter(), Counter()
    for pm, g in groups.items():
        if pm >= 1440:
            daily_b.update(g["before"])
            daily_a.update(g["after"])
    if daily_a:
        print("\n  일 단위 기다무 다음 충전 시각(시)    전 → 후")
        for h in range(24):
            if daily_b[h] or daily_a[h]:
                print("    %02d시  %5d → %5d" % (h, daily_b[h], daily_a[h]))
    nb = Counter()
    from wtm import pipeline as pl
    for tid in nplan:
        m = pl.naver_slot_min(cfg, dict(ntitles[tid], check_slot_min=nplan[tid]))
        nb[m // 60] += 1
    if nplan:
        print("\n  네이버 구독 %d개 확인 시각(시): %s" % (len(nplan), " ".join("%02d시 %d" % (h, nb[h]) for h in range(24) if nb[h])))
    if kslots:
        print("  카카오 %d개 새 회차 확인 시각: %02d~%02d시에 연재 요일별로 고르게" % (len(kslots), pm_a, (pm_b - 1) % 24))

    settings = {"CHECK_PLAN_ENABLE": True, "WAITFREE_NIGHT_ENABLE": False, "WAITFREE_SPREAD_ENABLE": True,
                "WAITFREE_SPREAD_START": start_h, "WAITFREE_SPREAD_END": end_h,
                "NAVER_SPREAD_ENABLE": True, "NAVER_SPREAD_START": pm_a, "NAVER_SPREAD_END": pm_b}
    print("\n  설정: " + ", ".join("%s=%s" % kv for kv in settings.items()))
    if not apply:
        print("\n미리 보기입니다. 사용법 예시:")
        print("  venv/bin/python -m wtm.rebalance                 # 미리 보기 (아무것도 안 바꿈)")
        print("  systemctl stop bookoasis_assistant")
        print("  venv/bin/python -m wtm.rebalance --apply         # 적용 (작품 기록 2개를 .bak-날짜시각으로 백업한 뒤)")
        print("  systemctl start bookoasis_assistant")
        return 0
    stamp = time.strftime("%Y%m%d%H%M%S")
    for path in (ss.KAKAO_TITLES_PATH, ss.TITLES_PATH):
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak-" + stamp)
    if kplan:
        ss.upsert_kakao_title({sid: v[0] for sid, v in kplan.items()})
    if nplan:
        ss.upsert_title({tid: {"check_slot_min": m} for tid, m in nplan.items()})
    if kslots:
        ss.upsert_kakao_title({sid: {"check_slot_min": m} for sid, m in kslots.items()})
    ss.flush_titles()
    cur = host.load_settings()
    cur.update(settings)
    host.save_settings(cur)
    print("\n적용했습니다. 백업: *.bak-%s (되돌리려면 서비스를 멈추고 그 파일을 원래 이름으로 복사)" % stamp)
    print("이제 systemctl start bookoasis_assistant")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
