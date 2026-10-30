# -*- coding: utf-8 -*-
"""시간대별 예상 다운로드 수량과 실제 다운로드 수량 (화면 [웹툰 다운로더 > 시간대별 다운로드])

- 실제: 다운로드 이력(history.jsonl)의 받은 회차를 시(0~23)별로 센다. 기다무 대여권으로 연 회차와 그 밖
  (새 회차·무료·대여·소장·보유 대여권)을 나눈다.
- 예상:
  - 기다무: 대여권을 쓰는 작품(구독·구매 + 잠긴 회차 남음)마다 계정별로 '마지막으로 쓴 시각 + 충전 주기 + 평균 지연'에
    한 장씩, 그 뒤로도 (주기 + 지연)마다 한 장씩 쓴다고 보고 시간대에 놓는다. '1일 이상 기다무는 새벽부터'를 켰으면
    그 규칙(ready_at)을 따른다. 작품마다 남은 잠긴 회차(최신 10화 제외)보다 많이는 세지 않는다.
  - 그 밖: 최근 7일 동안 실제로 받은 새 회차 등의 시간대별 평균 (새 회차는 연재 시각·실행 주기에 따라 들어오므로)
- 하루의 예상은 그날 처음 계산할 때(보통 자정 직후, 스케줄러) 저장해 두고 하루 동안 바꾸지 않는다 → 실제와 비교.
  업데이트한 날처럼 하루 중간에 처음 계산했으면 그 시각 이전 시간대는 예상이 없다(from_hour).

    python3 -m wtm.hourly_stats              오늘 (예상 / 실제)
    python3 -m wtm.hourly_stats 2026-10-29   그날
    python3 -m wtm.hourly_stats --tomorrow   내일 예상
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

KINDS = (("waitfree", "기다무"), ("other", "새 회차·무료·보유 대여권"))
PLAN_KEEP_DAYS = 40
NEW_AVG_DAYS = 7
_hist = {"sig": None, "days": {}, "at": 0.0}


def _plan_path():
    from . import state_store as ss
    return os.path.join(ss.DATA_DIR, "hourly_plan.json")


def _day_start(day):
    return time.mktime(time.strptime(day, "%Y-%m-%d"))


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _empty():
    return {k: [0] * 24 for k, _l in KINDS}


def _kind(e):
    return "waitfree" if "기다무" in str(e.get("via") or "") else "other"


def actual_days():
    """이력 파일 전체를 날짜·시간대별로 센다 {날짜: {kind: [24]}} (파일이 바뀌었을 때만, 최대 30초에 한 번 다시 셈)"""
    from . import state_store as ss
    sig = ss._file_sig(ss.HISTORY_PATH)
    if _hist["sig"] == sig or (_hist["sig"] is not None and time.time() - _hist["at"] < 30):
        return _hist["days"]
    days = {}
    try:
        with open(ss.HISTORY_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"download"' not in line and '"manual_download"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") not in ("download", "manual_download") or not e.get("ts"):
                    continue
                lt = time.localtime(float(e["ts"]))
                d = days.setdefault(time.strftime("%Y-%m-%d", lt), _empty())
                d[_kind(e)][lt.tm_hour] += 1
    except OSError:
        pass
    _hist.update(sig=sig, days=days, at=time.time())
    return days


def _cfg():
    from . import host
    from .webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    return cfg


def waitfree_events(cfg, now, end):
    """[now, end) 사이에 기다무 대여권을 쓸 것으로 보는 시각들 (작품·계정별 충전 일정, 남은 회차만큼)"""
    from . import download_stats as ds, kakao_pipeline as kp
    nums, cands = kp._waitfree_candidates(cfg)
    if not cands:
        return []
    delay = ds.avg_waitfree_delay()                       # 충전 뒤 1분 + 평균 대기 (초)
    extra = max(0.0, delay - kp.WAITFREE_READY_GRACE)     # ready_at에는 1분이 이미 들어 있다
    night = kp.night_info(cfg, now)
    out = []
    for sid, t in cands.items():
        period = kp.waitfree_period(t)
        if t.get("episode_count"):
            left = max(0, int(t["episode_count"]) - kp.WAITFREE_LATEST_EXCLUDED - int(t.get("last_downloaded_no") or 0))
        else:
            left = None
        evs = []
        for n in nums:
            r = max(now, kp.ready_at(cfg, t, n, now=now, night=night, nums=nums) + extra)
            while r < end:
                evs.append(r)
                r += period + extra
        evs.sort()
        out.extend(evs if left is None else evs[:left])
    return out


def other_average(before_day, days=NEW_AVG_DAYS):
    """before_day 전 days일 동안 '기다무 아닌' 다운로드의 시간대별 평균 [24] (기록이 있는 날만으로 나눔)"""
    hist = actual_days()
    start = _day_start(before_day)
    tot, n = [0] * 24, 0
    for i in range(1, days + 1):
        d = hist.get(_day(start - i * 86400 + 3600))
        if d is None:
            continue
        n += 1
        for h in range(24):
            tot[h] += d["other"][h]
    return [round(v / n, 1) for v in tot] if n else [0] * 24


def compute_plan(day, now=None, cfg=None):
    """그날의 시간대별 예상 {"waitfree": [24], "other": [24], "from_hour", "at"} - now 이후 시간대만 채운다"""
    now = now or time.time()
    cfg = cfg or _cfg()
    start = _day_start(day)
    end = start + 86400
    if end <= now:
        return None
    frm = max(start, now)
    wf = [0] * 24
    for r in waitfree_events(cfg, frm, end):
        if r >= start:
            wf[time.localtime(r).tm_hour] += 1
    from_hour = time.localtime(frm).tm_hour if frm > start else 0
    other = other_average(day)
    other = [v if h >= from_hour else 0 for h, v in enumerate(other)]
    return {"waitfree": wf, "other": other, "from_hour": from_hour, "at": now}


def ensure_plan(now=None, log=None):
    """오늘 예상이 저장돼 있지 않으면 계산해 저장한다 (스케줄러가 1분마다 부름 - 자정 직후에 하루치가 정해진다)"""
    from . import state_store as ss
    now = now or time.time()
    day = _day(now)
    data = ss.read_json(_plan_path(), {})
    if day in data:
        return data[day]
    plan = compute_plan(day, now)
    data[day] = plan
    for old in sorted(data)[:-PLAN_KEEP_DAYS]:
        data.pop(old, None)
    ss.write_json(_plan_path(), data)
    if log:
        log("시간대별 다운로드 예상: %s 기다무 %d화 · 그 밖 %.0f화 (%02d시부터)" % (
            day, sum(plan["waitfree"]), sum(plan["other"]), plan["from_hour"]))
    return plan


def report(day=None, now=None):
    """화면용 {"day", "days": [고를 수 있는 날짜], "hours": [{"hour", "plan": {..}, "actual": {..}}], "total", "note"}
    day가 내일이면 지금 다시 계산한 예상만 (실제 없음)."""
    from . import state_store as ss
    now = now or time.time()
    today = _day(now)
    day = day or today
    tomorrow = _day(_day_start(today) + 86400 + 3600)
    if day == tomorrow:
        plan = compute_plan(day, now)
        note = "지금 기록으로 다시 계산한 내일 예상입니다 (실제는 내일부터)."
    else:
        plan = ensure_plan(now) if day == today else ss.read_json(_plan_path(), {}).get(day)
        note = ("자정 직후(또는 처음 연 시각)에 정해 둔 예상입니다. %02d시 전은 예상을 만들기 전이라 비어 있습니다." % plan["from_hour"]
                if plan and plan.get("from_hour") else "")
        if not plan:
            note = "이 날은 저장된 예상이 없습니다 (이 기능을 넣기 전). 실제만 보여 줍니다."
    act = actual_days().get(day) if day != tomorrow else None
    hours = []
    for h in range(24):
        hours.append({"hour": h,
                      "plan": {k: (plan[k][h] if plan and h >= int(plan.get("from_hour") or 0) else None)
                               for k, _l in KINDS},
                      "actual": {k: (act[k][h] if act else 0) for k, _l in KINDS} if day != tomorrow else None,
                      "past": day < today or (day == today and h < time.localtime(now).tm_hour),
                      "now": day == today and h == time.localtime(now).tm_hour})
    hist = actual_days()
    plans = ss.read_json(_plan_path(), {})
    days = sorted(set([d for d in hist if d >= _day(now - 13 * 86400)] + [d for d in plans if d >= _day(now - 13 * 86400)]
                      + [today]), reverse=True)
    total = {"plan": {k: round(sum((plan or {}).get(k) or [0]), 1) for k, _l in KINDS},
             "actual": {k: sum((act or {}).get(k) or [0]) for k, _l in KINDS}}
    return {"day": day, "today": today, "tomorrow": tomorrow, "days": [tomorrow] + days, "hours": hours,
            "total": total, "kinds": [list(k) for k in KINDS], "note": note,
            "plan_from_hour": (plan or {}).get("from_hour")}


def main(argv):
    from gdw import config
    config.load_env()
    config.utf8_console()
    os.environ.setdefault("WTM_HOST", "1")
    now = time.time()
    day = _day(now + 86400) if "--tomorrow" in argv else next((a for a in argv if a[:2] == "20"), None)
    r = report(day, now)
    print("■ %s 시간대별 다운로드 (예상 / 실제)  %s" % (r["day"], r["note"]))
    print("  시    기다무(예상/실제)   그 밖(예상/실제)")
    for x in r["hours"]:
        p, a = x["plan"], x["actual"] or {}

        def f(v):
            return "-" if v is None else ("%g" % v)
        print("  %02d   %7s / %-7s   %7s / %-7s%s" % (x["hour"], f(p["waitfree"]), f(a.get("waitfree")),
                                                     f(p["other"]), f(a.get("other")), "  ← 지금" if x["now"] else ""))
    t = r["total"]
    print("  합계 기다무 %g / %g · 그 밖 %g / %g" % (t["plan"]["waitfree"], t["actual"]["waitfree"],
                                                t["plan"]["other"], t["actual"]["other"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
