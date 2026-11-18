# -*- coding: utf-8 -*-
"""기다무 하루 계획표 (설정 WAITFREE_DAILY_PLAN) - 매일 계획 시각(기본 0시)에 앞으로 24시간 동안 기다무 대여권을 쓸
작품과 시각을 정해 두고, 그날은 계획에 든 작품만 쓴다.

  1시간·2시간·3시간·6시간·12시간 기다무: 그 주기마다 (충전 시각부터 24시간 안에 들어가는 만큼)
  1일 기다무: 하루에 한 번 (오늘 충전되는 시각)
  2일·3일·7일 기다무: 오늘 충전되는 날만 - 아니면 오늘 계획에서 뺀다 (다음 충전 날에 들어감)

쓸 수 있는 시각은 kakao_pipeline.ready_at(충전 시각, 새벽 사용·확인 계획 규칙 포함)을 그대로 쓴다. 지난 충전을
못 쓴 작품은 계획 시작 시각에 넣는다. 계획을 짠 뒤에 새로 구독한 작품은 처음 볼 때 오늘 계획에 더한다.
저장: job_state["waitfree_plan"] = {"start", "made_at", "items": {sid: {title, period, slots}}, "skipped": {sid: {title, period, next}}}
"""
import time

MAX_SLOTS = 48   # 한 작품의 하루 슬롯 상한 (30분 기다무 등)


def enabled(cfg):
    v = (cfg or {}).get("WAITFREE_DAILY_PLAN")
    return v if isinstance(v, bool) else str(v or "").lower() in ("1", "true", "on", "yes", "y")


def plan_hour(cfg):
    try:
        return int(float((cfg or {}).get("WAITFREE_PLAN_HOUR", 0))) % 24
    except (TypeError, ValueError):
        return 0


def day_start(cfg, now=None):
    """지금이 속한 계획 하루의 시작 (오늘 또는 어제 계획 시각)"""
    now = now or time.time()
    h = plan_hour(cfg)
    lt = time.localtime(now)
    s = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, 0, 0, 0, 0, -1))
    if s > now:
        s = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - 1, h, 0, 0, 0, 0, -1))
    return s


def _entry(cfg, t, nums, start, end, now, night):
    """작품 하나의 오늘 계획: ("item", {..slots}) 또는 ("skip", {..next})"""
    from . import kakao_pipeline as kp
    period = kp.waitfree_period(t)
    first = min(kp.ready_at(cfg, t, n, now, night, nums) for n in nums)
    first = max(first, start)   # 지난 충전을 아직 못 썼으면 오늘 계획 시작부터
    base = {"title": t.get("title") or "", "period": period // 60, "label": kp.waitfree_label(t)}
    if first >= end:   # 오늘 안에 충전되지 않음 (2일·3일 기다무의 쉬는 날, 늦게 쓴 1일 기다무)
        return "skip", dict(base, next=int(first))
    if period < 86400:   # 하루보다 짧은 기다무: 주기마다
        slots, at = [], first
        while at < end and len(slots) < MAX_SLOTS:
            slots.append(int(at))
            at += period
    else:                # 1일 이상: 오늘 한 번
        slots = [int(first)]
    return "item", dict(base, slots=slots)


def build(cfg, now=None):
    """오늘(계획 하루) 계획을 새로 짠다 (저장하지 않음)"""
    from . import kakao_pipeline as kp
    now = now or time.time()
    start = day_start(cfg, now)
    end = start + 86400
    nums, cands = kp._waitfree_candidates(cfg)
    plan = {"start": int(start), "made_at": int(now), "items": {}, "skipped": {}}
    if not nums:
        return plan
    night = kp.night_info(cfg, now)
    for sid, t in cands.items():
        kind, e = _entry(cfg, t, nums, start, end, now, night)
        plan["items" if kind == "item" else "skipped"][sid] = e
    return plan


def summary(plan):
    """'작품 120개 · 대여권 사용 410번 (1시간 3개, 3시간 40개, 1일 60개, 2일 17개) · 오늘 쉼 25개'"""
    by = {}
    for e in plan["items"].values():
        by[e["label"]] = by.get(e["label"], 0) + 1
    order = sorted(by, key=lambda k: next((e["period"] for e in plan["items"].values() if e["label"] == k), 0))
    slots = sum(len(e["slots"]) for e in plan["items"].values())
    parts = ", ".join("%s %d개" % (k.replace(" 기다무", ""), by[k]) for k in order)
    return "작품 %d개 · 대여권 사용 %d번%s · 오늘 쉼 %d개" % (
        len(plan["items"]), slots, " (%s)" % parts if parts else "", len(plan["skipped"]))


def current(cfg, now=None, log=None):
    """오늘 계획 (없거나 날이 바뀌었으면 새로 짜서 저장). 계획을 짠 뒤에 새로 생긴 기다무 작품은 오늘 계획에 더한다"""
    from . import kakao_pipeline as kp, state_store as ss
    now = now or time.time()
    plan = ss.load_job_state().get("waitfree_plan") or {}
    start = day_start(cfg, now)
    if plan.get("start") != int(start):
        plan = build(cfg, now)
        ss.save_job_state({"waitfree_plan": plan})
        if log:
            log("카카오 기다무 하루 계획 (%s부터 24시간): %s" % (time.strftime("%m-%d %H:%M", time.localtime(start)), summary(plan)))
        return plan
    nums, cands = kp._waitfree_candidates(cfg)
    new = [sid for sid in cands if sid not in plan["items"] and sid not in plan["skipped"]]
    if new and nums:
        night = kp.night_info(cfg, now)
        for sid in new:
            kind, e = _entry(cfg, cands[sid], nums, start, start + 86400, now, night)
            plan["items" if kind == "item" else "skipped"][sid] = e
        ss.save_job_state({"waitfree_plan": plan})
        if log:
            log("카카오 기다무 하루 계획: 새로 생긴 기다무 작품 %d개를 오늘 계획에 더함" % len(new))
    return plan


def allowed(cfg, cands, now=None):
    """계획을 켰으면 오늘 계획에 든 작품만 {sid: 작품}, 끄면 그대로"""
    if not enabled(cfg):
        return cands
    items = current(cfg, now)["items"]
    return {sid: t for sid, t in cands.items() if sid in items}


def report(cfg, now=None):
    """화면용: 시간대별 계획 [{hour, count, titles}], 오늘 쉬는 작품, 요약"""
    from . import kakao_pipeline as kp, state_store as ss
    now = now or time.time()
    on = enabled(cfg)
    plan = current(cfg, now) if on else build(cfg, now)   # 끄면 미리 보기 (저장하지 않음)
    titles = ss.load_kakao_titles()
    hours = [{"at": int(plan["start"] + h * 3600), "count": 0, "done": 0, "titles": []} for h in range(24)]
    for sid, e in plan["items"].items():
        t = titles.get(sid) or {}
        used = max([kp._ticket_at(t, n) for n in range(1, 6)] or [0])
        for s in e["slots"]:
            i = int((s - plan["start"]) // 3600)
            if 0 <= i < 24:
                done = used >= s - 60
                hours[i]["count"] += 1
                hours[i]["done"] += 1 if done else 0
                hours[i]["titles"].append({"sid": sid, "title": e["title"], "label": e["label"], "at": s, "done": done})
    for hrow in hours:
        hrow["titles"].sort(key=lambda x: x["at"])
    skipped = sorted(({"sid": sid, **e} for sid, e in plan["skipped"].items()), key=lambda x: x["next"])
    return {"enabled": on, "start": plan["start"], "made_at": plan["made_at"], "hour": plan_hour(cfg),
            "summary": summary(plan), "hours": hours, "skipped": skipped}
